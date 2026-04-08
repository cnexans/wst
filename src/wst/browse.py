from pathlib import Path

from InquirerPy import inquirer

from wst.db import Database
from wst.models import DocType, LibraryEntry
from wst.storage import LocalStorage, build_dest_path


def browse_library(db: Database, storage: LocalStorage, library_path: Path) -> None:
    """Interactive TUI for browsing and editing documents."""
    while True:
        entries = db.list_all()
        if not entries:
            print("Library is empty.")
            return

        choice = _select_document(entries)
        if choice is None:
            return

        _edit_document(choice, db, storage, library_path)


def _select_document(entries: list[LibraryEntry]) -> LibraryEntry | None:
    """Show a fuzzy-searchable list of documents. Returns selected entry or None."""
    choices = [
        {
            "name": _format_row(e),
            "value": e,
        }
        for e in entries
    ]

    result = inquirer.fuzzy(
        message="Search and select a document (type to filter, arrows to navigate):",
        choices=choices,
        max_height="70%",
        validate=lambda _: True,
        instruction="(ESC to quit)",
        mandatory=False,
    ).execute()

    return result


def _format_row(entry: LibraryEntry) -> str:
    """Format a single entry for the selection list."""
    m = entry.metadata
    year = str(m.year) if m.year else "----"
    doc_type = m.doc_type.value[:12].ljust(12)
    subject = (m.subject or "")[:20]
    return f"[{entry.id:>3}] {m.title[:45]:<45}  {m.author[:25]:<25}  {doc_type}  {year}  {subject}"


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
