import platform
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

import click

from wst.db import Database
from wst.models import LibraryEntry


def _detect_icloud_base() -> Path | None:
    """Detect iCloud Drive path based on OS."""
    system = platform.system()
    if system == "Darwin":
        p = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
        return p if p.exists() else p
    if system == "Windows":
        # Standard iCloud for Windows path
        p = Path.home() / "iCloudDrive"
        if p.exists():
            return p
        # Alternative: installed via Microsoft Store
        p = Path(f"C:/Users/{Path.home().name}/iCloudDrive")
        if p.exists():
            return p
    return None


def _detect_gdrive_bases() -> list[Path]:
    """Detect Google Drive sync folder roots. Returns all candidates found.

    macOS modern Drive for Desktop uses ~/Library/CloudStorage/GoogleDrive-<email>/My Drive
    and may have multiple entries when several accounts are signed in. Older versions
    used ~/Google Drive/My Drive. Linux/Windows fall back to common conventions.
    """
    system = platform.system()
    candidates: list[Path] = []
    home = Path.home()

    if system == "Darwin":
        cloud_storage = home / "Library" / "CloudStorage"
        if cloud_storage.exists():
            for entry in sorted(cloud_storage.glob("GoogleDrive-*")):
                my_drive = entry / "My Drive"
                if my_drive.exists():
                    candidates.append(my_drive)
        legacy = home / "Google Drive" / "My Drive"
        if legacy.exists():
            candidates.append(legacy)
    elif system == "Windows":
        for p in (home / "Google Drive" / "My Drive", Path("G:/My Drive")):
            if p.exists():
                candidates.append(p)
    else:
        # Linux: rclone, insync, google-drive-ocamlfuse all default near ~/GoogleDrive
        for p in (home / "GoogleDrive", home / "Google Drive"):
            if p.exists():
                candidates.append(p)

    return candidates


class BackupProvider(ABC):
    name: str

    @abstractmethod
    def backup_file(self, source: Path, dest_relative: str) -> None:
        """Backup a single file, preserving its relative path."""
        ...

    @abstractmethod
    def backup_all(self, library_path: Path, *, emit: bool = True) -> int:
        """Backup entire library. Returns number of files backed up."""
        ...

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def configure(self) -> None:
        """Interactive setup for this provider."""
        ...


class ICloudProvider(BackupProvider):
    name = "icloud"

    def __init__(self, subfolder: str = "wst"):
        self.subfolder = subfolder
        self.icloud_base = _detect_icloud_base()
        self.dest_root = self.icloud_base / subfolder if self.icloud_base else Path()

    def is_configured(self) -> bool:
        return self.icloud_base is not None and self.icloud_base.exists()

    def configure(self) -> None:
        if not self.is_configured():
            system = platform.system()
            if system == "Darwin":
                click.echo("iCloud Drive not found.")
                click.echo("Enable it in System Settings > Apple ID > iCloud.")
            elif system == "Windows":
                click.echo("iCloud Drive not found.")
                click.echo("Install iCloud for Windows from the Microsoft Store.")
            else:
                click.echo(f"iCloud Drive is not supported on {system}.")
            return

        from InquirerPy import inquirer

        subfolder = (
            inquirer.text(
                message="Subfolder name in iCloud Drive:",
                default=self.subfolder,
            )
            .execute()
            .strip()
        )

        self.subfolder = subfolder
        self.dest_root = self.icloud_base / subfolder
        self.dest_root.mkdir(parents=True, exist_ok=True)
        click.echo(f"Configured: {self.dest_root}")

    def backup_file(self, source: Path, dest_relative: str) -> None:
        dest = self.dest_root / dest_relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source), str(dest))

    def backup_all(self, library_path: Path, *, emit: bool = True) -> int:
        from wst.document import is_supported

        count = 0
        for pdf in sorted(p for p in library_path.rglob("*") if p.is_file() and is_supported(p)):
            relative = str(pdf.relative_to(library_path))
            if emit:
                click.echo(f"  {relative}... ", nl=False)
            self.backup_file(pdf, relative)
            if emit:
                click.echo("done")
            count += 1

        # Backup the database too
        db_path = library_path / "wst.db"
        if db_path.exists():
            if emit:
                click.echo("  wst.db... ", nl=False)
            self.backup_file(db_path, "wst.db")
            if emit:
                click.echo("done")

        return count


class S3Provider(BackupProvider):
    name = "s3"

    def __init__(self) -> None:
        self._client = None
        self._config: dict | None = None

    def _get_config(self) -> dict | None:
        if self._config is None:
            from wst.config import get_s3_config

            self._config = get_s3_config()
        return self._config

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            import boto3
        except ImportError:
            click.echo(
                "Error: S3 backup requires the 's3' extra. Install it with:\n"
                "\n"
                "  pip install wst-library[s3]\n"
            )
            return None

        cfg = self._get_config()
        if not cfg:
            return None

        kwargs = {
            "service_name": "s3",
            "aws_access_key_id": cfg["access_key_id"],
            "aws_secret_access_key": cfg["secret_access_key"],
            "region_name": cfg.get("region", "us-east-1"),
        }
        if cfg.get("endpoint_url"):
            kwargs["endpoint_url"] = cfg["endpoint_url"]

        self._client = boto3.client(**kwargs)
        return self._client

    def is_configured(self) -> bool:
        return self._get_config() is not None

    def configure(self) -> None:
        from wst.config import save_s3_config

        try:
            import boto3  # noqa: F401
        except ImportError:
            click.echo(
                "Error: S3 backup requires the 's3' extra. Install it with:\n"
                "\n"
                "  pip install wst-library[s3]\n"
            )
            return

        click.echo("\n--- S3 Backup Configuration ---")
        click.echo("Enter your S3 bucket credentials.")
        click.echo("These are stored locally in ~/wst/config.json\n")

        from InquirerPy import inquirer

        bucket = inquirer.text(message="Bucket name:").execute().strip()
        if not bucket:
            click.echo("Bucket name is required.")
            return

        region = (
            inquirer.text(
                message="Region:",
                default="us-east-1",
            )
            .execute()
            .strip()
        )

        endpoint_url = (
            inquirer.text(
                message="Endpoint URL (leave empty for AWS S3):",
                default="",
            )
            .execute()
            .strip()
            or None
        )

        access_key_id = (
            inquirer.text(
                message="Access Key ID:",
            )
            .execute()
            .strip()
        )

        secret_access_key = (
            inquirer.text(
                message="Secret Access Key:",
            )
            .execute()
            .strip()
        )

        prefix = (
            inquirer.text(
                message="Key prefix (optional, e.g. 'wst/'):",
                default="",
            )
            .execute()
            .strip()
        )

        if not access_key_id or not secret_access_key:
            click.echo("Access Key ID and Secret Access Key are required.")
            return

        save_s3_config(
            bucket=bucket,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region=region,
            endpoint_url=endpoint_url,
            prefix=prefix,
        )

        # Test connection
        self._config = None
        self._client = None
        client = self._get_client()
        if client:
            try:
                client.head_bucket(Bucket=bucket)
                click.echo(f"\nConfigured and verified: s3://{bucket}")
            except Exception as e:
                click.echo(f"\nConfiguration saved, but connection test failed: {e}")
                click.echo("Check your credentials and bucket name.")

    def _key(self, dest_relative: str) -> str:
        cfg = self._get_config() or {}
        prefix = cfg.get("prefix", "")
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        return prefix + dest_relative

    def backup_file(self, source: Path, dest_relative: str) -> None:
        client = self._get_client()
        if not client:
            return
        cfg = self._get_config()
        key = self._key(dest_relative)
        client.upload_file(str(source), cfg["bucket"], key)

    def backup_all(self, library_path: Path, *, emit: bool = True) -> int:
        from wst.document import is_supported

        client = self._get_client()
        if not client:
            return 0

        count = 0
        for f in sorted(p for p in library_path.rglob("*") if p.is_file() and is_supported(p)):
            relative = str(f.relative_to(library_path))
            if emit:
                click.echo(f"  {relative}... ", nl=False)
            self.backup_file(f, relative)
            if emit:
                click.echo("done")
            count += 1

        # Backup the database too
        db_path = library_path / "wst.db"
        if db_path.exists():
            if emit:
                click.echo("  wst.db... ", nl=False)
            self.backup_file(db_path, "wst.db")
            if emit:
                click.echo("done")

        return count


class GoogleDriveProvider(BackupProvider):
    name = "gdrive"

    def __init__(self, subfolder: str = "wst", root: Path | None = None):
        self.subfolder = subfolder
        if root is not None:
            self.gdrive_base: Path | None = root
        else:
            from wst.config import get_gdrive_config

            cfg = get_gdrive_config()
            if cfg and cfg.get("root"):
                self.gdrive_base = Path(cfg["root"])
                self.subfolder = cfg.get("subfolder", subfolder)
            else:
                bases = _detect_gdrive_bases()
                # Q1: auto-pick the first match
                self.gdrive_base = bases[0] if bases else None
        self.dest_root = self.gdrive_base / self.subfolder if self.gdrive_base else Path()

    def is_configured(self) -> bool:
        return self.gdrive_base is not None and self.gdrive_base.exists()

    def configure(self) -> None:
        from InquirerPy import inquirer

        from wst.config import save_gdrive_config

        bases = _detect_gdrive_bases()

        if not bases:
            click.echo("Google Drive sync folder not found.")
            system = platform.system()
            if system == "Darwin":
                click.echo(
                    "Install Google Drive for Desktop, sign in, "
                    "and ensure 'My Drive' is set to stream or mirror."
                )
            elif system == "Windows":
                click.echo("Install Google Drive for Desktop and sign in.")
            else:
                click.echo(
                    "On Linux, install rclone/insync/google-drive-ocamlfuse and mount your Drive."
                )
            manual = (
                inquirer.text(
                    message=("Manual path to your Google Drive root (leave empty to skip):"),
                    default="",
                )
                .execute()
                .strip()
            )
            if not manual:
                return
            chosen = Path(manual).expanduser()
            if not chosen.exists():
                click.echo(f"Path not found: {chosen}")
                return
        elif len(bases) == 1:
            chosen = bases[0]
        else:
            choice = inquirer.select(
                message="Multiple Google Drive accounts detected — choose one:",
                choices=[str(b) for b in bases],
            ).execute()
            chosen = Path(choice)

        subfolder = (
            inquirer.text(
                message="Subfolder name in Google Drive:",
                default=self.subfolder,
            )
            .execute()
            .strip()
        )

        self.subfolder = subfolder or "wst"
        self.gdrive_base = chosen
        self.dest_root = self.gdrive_base / self.subfolder
        self.dest_root.mkdir(parents=True, exist_ok=True)
        save_gdrive_config(root=str(self.gdrive_base), subfolder=self.subfolder)
        click.echo(f"Configured: {self.dest_root}")

    def backup_file(self, source: Path, dest_relative: str) -> None:
        dest = self.dest_root / dest_relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source), str(dest))

    def backup_all(self, library_path: Path, *, emit: bool = True) -> int:
        from wst.document import is_supported

        count = 0
        for f in sorted(p for p in library_path.rglob("*") if p.is_file() and is_supported(p)):
            relative = str(f.relative_to(library_path))
            if emit:
                click.echo(f"  {relative}... ", nl=False)
            self.backup_file(f, relative)
            if emit:
                click.echo("done")
            count += 1

        db_path = library_path / "wst.db"
        if db_path.exists():
            if emit:
                click.echo("  wst.db... ", nl=False)
            self.backup_file(db_path, "wst.db")
            if emit:
                click.echo("done")

        return count


PROVIDERS: dict[str, type[BackupProvider]] = {
    "icloud": ICloudProvider,
    "gdrive": GoogleDriveProvider,
    "s3": S3Provider,
}


def get_provider(name: str) -> BackupProvider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown backup provider: {name}. Available: {', '.join(PROVIDERS)}")
    return cls()


def _format_row(entry: LibraryEntry) -> str:
    m = entry.metadata
    year = str(m.year) if m.year else "----"
    doc_type = m.doc_type.value[:12].ljust(12)
    return f"[{entry.id:>3}] {m.title[:45]:<45}  {m.author[:25]:<25}  {doc_type}  {year}"


def run_backup_interactive(
    provider: BackupProvider,
    db: Database,
    library_path: Path,
) -> None:
    """Interactive backup flow: choose all or select a file."""
    from InquirerPy import inquirer

    if not provider.is_configured():
        click.echo(f"Provider '{provider.name}' is not configured.")
        provider.configure()
        if not provider.is_configured():
            return

    choice = inquirer.select(
        message="What to backup?",
        choices=[
            {"name": "All files", "value": "all"},
            {"name": "Select a file", "value": "select"},
        ],
    ).execute()

    if choice == "all":
        click.echo(f"\nBacking up to {provider.name}...")
        count = provider.backup_all(library_path, emit=True)
        click.echo(f"\n{count} file(s) backed up.")
    else:
        entries = db.list_all()
        if not entries:
            click.echo("Library is empty.")
            return

        choices = [{"name": "Cancel", "value": None}] + [
            {"name": _format_row(e), "value": e} for e in entries
        ]

        try:
            entry = inquirer.fuzzy(
                message="Select a file to backup (type to filter, Ctrl+C to cancel):",
                choices=choices,
                max_height="70%",
            ).execute()
        except KeyboardInterrupt:
            return

        if entry is None:
            return

        source = library_path / entry.file_path
        if not source.exists():
            click.echo(f"File not found: {source}")
            return

        click.echo(f"Backing up: {entry.file_path}... ", nl=False)
        provider.backup_file(source, entry.file_path)
        click.echo("done")


def run_backup_file(
    provider: BackupProvider,
    db: Database,
    library_path: Path,
    identifier: str,
    *,
    emit: bool = True,
) -> None:
    """Backup a specific file by ID or title."""
    if not provider.is_configured():
        if emit:
            click.echo(f"Provider '{provider.name}' is not configured.")
        provider.configure()
        if not provider.is_configured():
            return

    entry = None
    if identifier.isdigit():
        entry = db.get(int(identifier))
    if entry is None:
        entry = db.get_by_title(identifier)
    if entry is None:
        if emit:
            click.echo(f"Document not found: {identifier}")
        return

    source = library_path / entry.file_path
    if not source.exists():
        if emit:
            click.echo(f"File not found: {source}")
        return

    if emit:
        click.echo(f"Backing up: {entry.file_path}... ", nl=False)
    provider.backup_file(source, entry.file_path)
    if emit:
        click.echo("done")


def run_backup_all(
    provider: BackupProvider,
    library_path: Path,
    *,
    emit: bool = True,
) -> dict:
    if not provider.is_configured():
        raise RuntimeError(f"Provider '{provider.name}' is not configured.")
    count = provider.backup_all(library_path, emit=emit)
    return {"provider": provider.name, "backed_up_files": count}
