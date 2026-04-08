import hashlib
from datetime import datetime, timezone
from pathlib import Path

import click

from wst.ai import AIBackend
from wst.db import Database
from wst.models import LibraryEntry
from wst.pdf import extract_pdf_info, write_pdf_metadata
from wst.storage import StorageBackend, build_dest_path


def compute_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def format_metadata_display(entry: LibraryEntry) -> str:
    m = entry.metadata
    lines = [
        f"  Title:    {m.title}",
        f"  Author:   {m.author}",
        f"  Type:     {m.doc_type.value}",
        f"  Year:     {m.year or 'N/A'}",
        f"  Language: {m.language or 'N/A'}",
        f"  Pages:    {m.page_count or 'N/A'}",
        f"  Subject:  {m.subject or 'N/A'}",
        f"  Tags:     {', '.join(m.tags) if m.tags else 'N/A'}",
        f"  Summary:  {m.summary or 'N/A'}",
        f"  Dest:     {entry.file_path}",
    ]
    if m.publisher:
        lines.insert(4, f"  Publisher: {m.publisher}")
    if m.isbn:
        lines.insert(5, f"  ISBN:     {m.isbn}")
    return "\n".join(lines)


def ingest_file(
    path: Path,
    ai: AIBackend,
    storage: StorageBackend,
    db: Database,
    auto_confirm: bool = False,
) -> bool:
    """Ingest a single PDF file. Returns True if successfully ingested."""
    click.echo(f"\nProcessing: {path.name}")

    # Check for duplicates
    file_hash = compute_file_hash(path)
    if db.exists_hash(file_hash):
        click.echo(f"  Skipped (duplicate): {path.name}")
        return False

    # Extract PDF info
    try:
        existing_meta, text_sample, page_count = extract_pdf_info(path)
    except Exception as e:
        click.echo(f"  Error reading PDF: {e}")
        return False

    # Generate metadata via AI
    click.echo("  Generating metadata...")
    try:
        metadata = ai.generate_metadata(existing_meta, text_sample, path.name)
    except Exception as e:
        click.echo(f"  Error generating metadata: {e}")
        return False

    metadata.page_count = page_count

    # Build entry
    dest_path = build_dest_path(metadata)
    entry = LibraryEntry(
        metadata=metadata,
        filename=Path(dest_path).name,
        original_filename=path.name,
        file_path=dest_path,
        file_hash=file_hash,
        ingested_at=datetime.now(timezone.utc).isoformat(),
    )

    # Show metadata and confirm
    click.echo(format_metadata_display(entry))

    if not auto_confirm:
        if not click.confirm("  Accept and ingest?", default=True):
            click.echo("  Skipped.")
            return False

    # Write metadata to PDF
    try:
        write_pdf_metadata(path, metadata.title, metadata.author, metadata.subject)
    except Exception as e:
        click.echo(f"  Warning: could not write metadata to PDF: {e}")

    # Store file (copy to all backends, then remove original)
    final_path = storage.store(path, dest_path)
    entry.file_path = final_path
    path.unlink()

    # Index in DB
    entry.id = db.insert(entry)
    click.echo(f"  Ingested -> {final_path}")
    return True


def ingest_inbox(
    inbox_path: Path,
    ai: AIBackend,
    storage: StorageBackend,
    db: Database,
    auto_confirm: bool = False,
) -> tuple[int, int]:
    """Ingest all PDFs from inbox recursively. Returns (processed, ingested) counts."""
    pdfs = sorted(inbox_path.rglob("*.pdf"))
    if not pdfs:
        click.echo("No PDF files found in inbox.")
        return 0, 0

    click.echo(f"Found {len(pdfs)} PDF(s) in {inbox_path}")
    processed = 0
    ingested = 0

    for pdf_path in pdfs:
        processed += 1
        click.echo(f"\n[{processed}/{len(pdfs)}]")
        if ingest_file(pdf_path, ai, storage, db, auto_confirm):
            ingested += 1

    click.echo(f"\nDone: {ingested}/{processed} files ingested.")
    return processed, ingested
