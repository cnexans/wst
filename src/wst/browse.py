import platform
import subprocess
from pathlib import Path

from InquirerPy import inquirer

from wst.db import Database
from wst.models import DocType, LibraryEntry
from wst.storage import LocalStorage, build_dest_path


class BrowseUsageError(ValueError):
    pass


def browse_library(db: Database, storage: LocalStorage, library_path: Path) -> None:
    """Interactive TUI for browsing and editing documents."""
    while True:
        entries = db.list_all()
        if not entries:
            print("Library is empty.")
            return

        try:
            choice = _select_document(entries)
        except KeyboardInterrupt:
            print("\nBye.")
            return
        if choice is None:
            return

        _document_actions(choice, db, storage, library_path)


def _select_document(entries: list[LibraryEntry]) -> LibraryEntry | None:
    """Show a fuzzy-searchable list of documents. Returns selected entry or None."""
    choices = [{"name": "Exit", "value": None}] + [
        {
            "name": _format_row(e),
            "value": e,
        }
        for e in entries
    ]

    return inquirer.fuzzy(
        message="Select a document (type to filter, Ctrl+C to quit):",
        choices=choices,
        max_height="70%",
    ).execute()


def _format_row(entry: LibraryEntry) -> str:
    """Format a single entry for the selection list."""
    m = entry.metadata
    year = str(m.year) if m.year else "----"
    doc_type = m.doc_type.value[:12].ljust(12)
    subject = (m.subject or "")[:20]
    return f"[{entry.id:>3}] {m.title[:45]:<45}  {m.author[:25]:<25}  {doc_type}  {year}  {subject}"


def _document_actions(
    entry: LibraryEntry, db: Database, storage: LocalStorage, library_path: Path
) -> None:
    """Show action menu for a selected document."""
    m = entry.metadata
    print(f"\n  {m.title} — {m.author}")

    action = inquirer.select(
        message="Action:",
        choices=[
            {"name": "View metadata", "value": "view"},
            {"name": "Open file", "value": "open"},
            {"name": "Show in folder", "value": "find"},
            {"name": "Edit metadata", "value": "edit"},
            {"name": "Delete", "value": "delete"},
            {"name": "Back", "value": "back"},
        ],
    ).execute()

    if action == "view":
        _view_document(entry)
    elif action == "open":
        _open_file(entry, library_path)
    elif action == "find":
        _reveal_in_folder(entry, library_path)
    elif action == "edit":
        _edit_document(entry, db, storage, library_path)
    elif action == "delete":
        _delete_document(entry, db, library_path)


def _view_document(entry: LibraryEntry) -> None:
    """Display full metadata for a document."""
    m = entry.metadata
    print(f"\n  Title:         {m.title}")
    print(f"  Author:        {m.author}")
    print(f"  Type:          {m.doc_type.value}")
    print(f"  Year:          {m.year or 'N/A'}")
    print(f"  Publisher:     {m.publisher or 'N/A'}")
    print(f"  ISBN:          {m.isbn or 'N/A'}")
    print(f"  Language:      {m.language or 'N/A'}")
    print(f"  Pages:         {m.page_count or 'N/A'}")
    print(f"  Subject:       {m.subject or 'N/A'}")
    print(f"  Tags:          {', '.join(m.tags) if m.tags else 'N/A'}")
    print(f"  Summary:       {m.summary or 'N/A'}")
    print(f"  File:          {entry.file_path}")
    print(f"  Original file: {entry.original_filename}")
    print(f"  Ingested at:   {entry.ingested_at}")
    print()


def _open_file(entry: LibraryEntry, library_path: Path) -> None:
    """Open the document with the system default application."""
    file_path = library_path / entry.file_path
    if not file_path.exists():
        print(f"  File not found: {file_path}\n")
        return
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", str(file_path)])
    elif system == "Windows":
        subprocess.Popen(["cmd", "/c", "start", "", str(file_path)])
    else:
        subprocess.Popen(["xdg-open", str(file_path)])
    print(f"  Opened: {entry.file_path}\n")


def _reveal_in_folder(entry: LibraryEntry, library_path: Path) -> None:
    """Reveal the document in Finder (macOS) or Explorer (Windows)."""
    file_path = library_path / entry.file_path
    if not file_path.exists():
        print(f"  File not found: {file_path}\n")
        return
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", "-R", str(file_path)])
    elif system == "Windows":
        subprocess.Popen(["explorer", "/select,", str(file_path)])
    else:
        subprocess.Popen(["xdg-open", str(file_path.parent)])
    print(f"  Revealed: {entry.file_path}\n")


def _delete_document(entry: LibraryEntry, db: Database, library_path: Path) -> None:
    """Delete a document from the library and database."""
    m = entry.metadata
    print(f"\n  Title:  {m.title}")
    print(f"  Author: {m.author}")
    print(f"  File:   {entry.file_path}")

    confirm = inquirer.confirm(
        message="Delete this document? This removes the file and the database entry.",
        default=False,
    ).execute()

    if not confirm:
        print("Cancelled.\n")
        return

    # Remove from DB
    db.delete(entry.id)

    # Remove file
    file_path = library_path / entry.file_path
    if file_path.exists():
        file_path.unlink()
        # Clean up empty parent directories
        parent = file_path.parent
        if parent != library_path and not any(parent.iterdir()):
            parent.rmdir()

    print(f"Deleted: {entry.file_path}\n")


def _edit_document(
    entry: LibraryEntry, db: Database, storage: LocalStorage, library_path: Path
) -> None:
    """Step through each field of a document for editing."""
    m = entry.metadata

    print(f"\n--- Editing: {m.title} (ID {entry.id}) ---\n")
    print("For each field: edit the value or press Enter to keep it.\n")

    m.title = _edit_field("Title", m.title)
    m.author = _edit_field("Author", m.author)
    m.doc_type = _edit_doc_type(m.doc_type)

    year_str = _edit_field("Year", str(m.year) if m.year else "")
    m.year = int(year_str) if year_str else None

    m.publisher = _edit_field("Publisher", m.publisher or "") or None
    m.isbn = _edit_field("ISBN", m.isbn or "") or None
    m.language = _edit_field("Language", m.language or "") or None
    m.subject = _edit_field("Subject", m.subject or "") or None

    tags_str = _edit_field("Tags", ", ".join(m.tags))
    m.tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

    m.summary = _edit_field("Summary", m.summary or "") or None

    # Preview changes
    print("\n--- Updated metadata ---")
    print(f"  Title:     {m.title}")
    print(f"  Author:    {m.author}")
    print(f"  Type:      {m.doc_type.value}")
    print(f"  Year:      {m.year or 'N/A'}")
    print(f"  Publisher: {m.publisher or 'N/A'}")
    print(f"  ISBN:      {m.isbn or 'N/A'}")
    print(f"  Language:  {m.language or 'N/A'}")
    print(f"  Subject:   {m.subject or 'N/A'}")
    print(f"  Tags:      {', '.join(m.tags) if m.tags else 'N/A'}")
    print(f"  Summary:   {m.summary or 'N/A'}")

    confirm = inquirer.confirm(message="Save changes?", default=True).execute()
    if not confirm:
        print("Discarded.\n")
        return

    # Move file if path changed
    new_dest = build_dest_path(m)
    old_path = entry.file_path

    if new_dest != old_path:
        old_full = library_path / old_path
        if old_full.exists():
            final = storage.store(old_full, new_dest)
            old_full.unlink()
            entry.file_path = final
            entry.filename = Path(final).name
            print(f"  Moved: {old_path} -> {final}")
        else:
            entry.file_path = new_dest
            entry.filename = Path(new_dest).name

    db.update(entry)
    print("Saved.\n")


def _edit_field(label: str, current: str) -> str:
    """Prompt for a single text field with current value as default."""
    return (
        inquirer.text(
            message=f"{label}:",
            default=current,
        )
        .execute()
        .strip()
    )


def _edit_doc_type(current: DocType) -> DocType:
    """Show a select list for document type."""
    choices = [
        {"name": f"{dt.value}{' (current)' if dt == current else ''}", "value": dt}
        for dt in DocType
    ]

    return inquirer.select(
        message="Document type:",
        choices=choices,
        default=current,
    ).execute()


def resolve_entry(
    db: Database,
    *,
    doc_id: int | None = None,
    title: str | None = None,
    query: str | None = None,
    select: int | None = None,
    first: bool = False,
) -> LibraryEntry:
    if doc_id is not None:
        entry = db.get(doc_id)
        if entry is None:
            raise BrowseUsageError(f"Document not found: {doc_id}")
        return entry

    if title is not None:
        entry = db.get_by_title(title)
        if entry is None:
            raise BrowseUsageError(f"Document not found: {title}")
        return entry

    if query is not None:
        results = db.search(query)
        if not results:
            raise BrowseUsageError("No results found.")
        if len(results) == 1:
            return results[0]

        idx = 0
        if first:
            idx = 0
        elif select is not None:
            if select < 1 or select > len(results):
                raise BrowseUsageError(f"--select must be between 1 and {len(results)}")
            idx = select - 1
        else:
            raise BrowseUsageError(
                f"Query returned {len(results)} results. Use --select N or --first."
            )
        return results[idx]

    raise BrowseUsageError("No selection provided. Use --id, --title, or --query.")


def run_action(
    entry: LibraryEntry,
    *,
    action: str,
    db: Database,
    storage: LocalStorage,
    library_path: Path,
    yes: bool = False,
    dry_run: bool = False,
    no_launch: bool = False,
    set_kv: dict[str, str] | None = None,
) -> dict:
    action = action.lower()
    if action == "view":
        return {"action": "view", "entry": entry}

    if action in {"open", "find"}:
        file_path = library_path / entry.file_path
        if not file_path.exists():
            return {"action": action, "status": "failed", "reason": "file not found", "path": str(file_path)}
        cmd: list[str]
        system = platform.system()
        if action == "open":
            if system == "Darwin":
                cmd = ["open", str(file_path)]
            elif system == "Windows":
                cmd = ["cmd", "/c", "start", "", str(file_path)]
            else:
                cmd = ["xdg-open", str(file_path)]
        else:
            if system == "Darwin":
                cmd = ["open", "-R", str(file_path)]
            elif system == "Windows":
                cmd = ["explorer", "/select,", str(file_path)]
            else:
                cmd = ["xdg-open", str(file_path.parent)]

        if not no_launch:
            subprocess.Popen(cmd)
        return {"action": action, "status": "ok", "path": entry.file_path, "command": cmd, "launched": (not no_launch)}

    if action == "delete":
        if not yes and not dry_run:
            raise BrowseUsageError("Delete requires --yes or --dry-run.")
        file_path = library_path / entry.file_path
        result = {"action": "delete", "id": entry.id, "path": entry.file_path, "dry_run": dry_run}
        if dry_run:
            return {**result, "status": "preview"}
        db.delete(entry.id)
        if file_path.exists():
            file_path.unlink()
            parent = file_path.parent
            if parent != library_path and not any(parent.iterdir()):
                parent.rmdir()
        return {**result, "status": "deleted"}

    if action == "edit":
        if not set_kv:
            raise BrowseUsageError("Edit requires --set key=value (repeatable).")
        if not yes and not dry_run:
            raise BrowseUsageError("Edit requires --yes or --dry-run.")
        m = entry.metadata
        before = m.model_dump()
        for k, v in set_kv.items():
            match k:
                case "title":
                    m.title = v
                case "author":
                    m.author = v
                case "type" | "doc_type":
                    m.doc_type = DocType(v)
                case "year":
                    m.year = int(v) if v else None
                case "publisher":
                    m.publisher = v or None
                case "isbn":
                    m.isbn = v or None
                case "language":
                    m.language = v or None
                case "subject":
                    m.subject = v or None
                case "summary":
                    m.summary = v or None
                case "tags":
                    m.tags = [t.strip() for t in v.split(",") if t.strip()] if v else []
                case _:
                    raise BrowseUsageError(f"Unknown metadata field for --set: {k}")

        changes = []
        after = m.model_dump()
        for k in sorted(after.keys()):
            if after[k] != before.get(k):
                changes.append({"field": k, "before": before.get(k), "after": after[k]})

        new_dest = build_dest_path(m)
        old_path = entry.file_path
        moved = None
        if new_dest != old_path:
            old_full = library_path / old_path
            if old_full.exists():
                if not dry_run:
                    final = storage.store(old_full, new_dest)
                    old_full.unlink()
                    entry.file_path = final
                    entry.filename = Path(final).name
                moved = {"from": old_path, "to": new_dest}
            else:
                if not dry_run:
                    entry.file_path = new_dest
                    entry.filename = Path(new_dest).name
                moved = {"from": old_path, "to": new_dest, "note": "old file missing; DB path updated only"}

        if not dry_run:
            db.update(entry)

        return {
            "action": "edit",
            "applied": (not dry_run),
            "dry_run": dry_run,
            "id": entry.id,
            "changes": changes,
            "moved": moved,
            "entry": entry,
        }

    raise BrowseUsageError(f"Unknown action: {action}. Allowed: view, open, find, edit, delete.")
