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
        count = 0
        for pdf in sorted(library_path.rglob("*.pdf")):
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


PROVIDERS: dict[str, type[BackupProvider]] = {
    "icloud": ICloudProvider,
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
