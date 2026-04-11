import platform
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from InquirerPy import inquirer

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


class BackupProvider(ABC):
    name: str

    @abstractmethod
    def backup_file(self, source: Path, dest_relative: str) -> None:
        """Backup a single file, preserving its relative path."""
        ...

    @abstractmethod
    def backup_all(self, library_path: Path) -> int:
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
                print("iCloud Drive not found.")
                print("Enable it in System Settings > Apple ID > iCloud.")
            elif system == "Windows":
                print("iCloud Drive not found.")
                print("Install iCloud for Windows from the Microsoft Store.")
            else:
                print(f"iCloud Drive is not supported on {system}.")
            return

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
        print(f"Configured: {self.dest_root}")

    def backup_file(self, source: Path, dest_relative: str) -> None:
        dest = self.dest_root / dest_relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source), str(dest))

    def backup_all(self, library_path: Path) -> int:
        from wst.document import is_supported

        count = 0
        for pdf in sorted(p for p in library_path.rglob("*") if p.is_file() and is_supported(p)):
            relative = str(pdf.relative_to(library_path))
            print(f"  {relative}...", end=" ", flush=True)
            self.backup_file(pdf, relative)
            print("done")
            count += 1

        # Backup the database too
        db_path = library_path / "wst.db"
        if db_path.exists():
            print("  wst.db...", end=" ", flush=True)
            self.backup_file(db_path, "wst.db")
            print("done")

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
            print(
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
            print(
                "Error: S3 backup requires the 's3' extra. Install it with:\n"
                "\n"
                "  pip install wst-library[s3]\n"
            )
            return

        print("\n--- S3 Backup Configuration ---")
        print("Enter your S3 bucket credentials.")
        print("These are stored locally in ~/wst/config.json\n")

        bucket = inquirer.text(message="Bucket name:").execute().strip()
        if not bucket:
            print("Bucket name is required.")
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
            print("Access Key ID and Secret Access Key are required.")
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
                print(f"\nConfigured and verified: s3://{bucket}")
            except Exception as e:
                print(f"\nConfiguration saved, but connection test failed: {e}")
                print("Check your credentials and bucket name.")

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

    def backup_all(self, library_path: Path) -> int:
        from wst.document import is_supported

        client = self._get_client()
        if not client:
            return 0

        count = 0
        for f in sorted(p for p in library_path.rglob("*") if p.is_file() and is_supported(p)):
            relative = str(f.relative_to(library_path))
            print(f"  {relative}...", end=" ", flush=True)
            self.backup_file(f, relative)
            print("done")
            count += 1

        # Backup the database too
        db_path = library_path / "wst.db"
        if db_path.exists():
            print("  wst.db...", end=" ", flush=True)
            self.backup_file(db_path, "wst.db")
            print("done")

        return count


PROVIDERS: dict[str, type[BackupProvider]] = {
    "icloud": ICloudProvider,
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
    if not provider.is_configured():
        print(f"Provider '{provider.name}' is not configured.")
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
        print(f"\nBacking up to {provider.name}...")
        count = provider.backup_all(library_path)
        print(f"\n{count} file(s) backed up.")
    else:
        entries = db.list_all()
        if not entries:
            print("Library is empty.")
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
            print(f"File not found: {source}")
            return

        print(f"Backing up: {entry.file_path}...", end=" ", flush=True)
        provider.backup_file(source, entry.file_path)
        print("done")


def run_backup_file(
    provider: BackupProvider,
    db: Database,
    library_path: Path,
    identifier: str,
) -> None:
    """Backup a specific file by ID or title."""
    if not provider.is_configured():
        print(f"Provider '{provider.name}' is not configured.")
        provider.configure()
        if not provider.is_configured():
            return

    entry = None
    if identifier.isdigit():
        entry = db.get(int(identifier))
    if entry is None:
        entry = db.get_by_title(identifier)
    if entry is None:
        print(f"Document not found: {identifier}")
        return

    source = library_path / entry.file_path
    if not source.exists():
        print(f"File not found: {source}")
        return

    print(f"Backing up: {entry.file_path}...", end=" ", flush=True)
    provider.backup_file(source, entry.file_path)
    print("done")
