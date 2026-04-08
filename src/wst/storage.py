import re
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from wst.models import DOCTYPE_FOLDER, DocumentMetadata


class StorageBackend(ABC):
    @abstractmethod
    def store(self, source_path: Path, dest_relative: str) -> str:
        """Store a file. Returns the final relative path.

        The source file must remain readable after this call — implementations
        should copy, not move. The caller is responsible for removing the
        original once all backends have stored successfully.
        """
        ...

    @abstractmethod
    def exists(self, dest_relative: str) -> bool: ...

    @abstractmethod
    def list_files(self, prefix: str = "") -> list[str]: ...


class CompositeStorage(StorageBackend):
    """Delegates to a primary backend and zero or more backup backends.

    The primary backend is authoritative (used for exists/list).
    Backup backends receive a copy of every stored file.
    """

    def __init__(self, primary: StorageBackend, backups: list[StorageBackend] | None = None):
        self.primary = primary
        self.backups = backups or []

    def store(self, source_path: Path, dest_relative: str) -> str:
        final_path = self.primary.store(source_path, dest_relative)
        for backup in self.backups:
            backup.store(source_path, final_path)
        return final_path

    def exists(self, dest_relative: str) -> bool:
        return self.primary.exists(dest_relative)

    def list_files(self, prefix: str = "") -> list[str]:
        return self.primary.list_files(prefix)


class LocalStorage(StorageBackend):
    def __init__(self, library_root: Path):
        self.library_root = library_root

    def store(self, source_path: Path, dest_relative: str) -> str:
        dest = self.library_root / dest_relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Handle name collision
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            counter = 1
            while dest.exists():
                dest = dest.parent / f"{stem} ({counter}){suffix}"
                counter += 1
            dest_relative = str(dest.relative_to(self.library_root))
            dest = self.library_root / dest_relative
        shutil.copy2(str(source_path), str(dest))
        return dest_relative

    def exists(self, dest_relative: str) -> bool:
        return (self.library_root / dest_relative).exists()

    def list_files(self, prefix: str = "") -> list[str]:
        root = self.library_root / prefix
        if not root.exists():
            return []
        return [str(p.relative_to(self.library_root)) for p in root.rglob("*.pdf")]


def sanitize_filename(s: str) -> str:
    """Remove or replace characters that are unsafe in filenames."""
    s = re.sub(r'[<>:"/\\|?*]', "", s)
    s = s.strip(". ")
    return s


def build_dest_path(meta: DocumentMetadata) -> str:
    """Build the destination relative path from metadata."""
    folder = DOCTYPE_FOLDER[meta.doc_type]
    author = sanitize_filename(meta.author)
    title = sanitize_filename(meta.title)
    year_part = f" ({meta.year})" if meta.year else ""
    filename = f"{author} - {title}{year_part}.pdf"
    return f"{folder}/{filename}"
