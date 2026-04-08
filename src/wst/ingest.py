import hashlib
from datetime import UTC, datetime
from pathlib import Path

import click

from wst.ai import AIBackend
from wst.db import Database
from wst.document import SUPPORTED_EXTENSIONS, extract_doc_info, is_supported, write_doc_metadata
from wst.models import LibraryEntry
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
    reprocess: bool = False,
) -> bool:
    """Ingest a single document file. Returns True if successfully ingested."""
    click.echo(f"\nProcessing: {path.name}")

    # Check for duplicates
    file_hash = compute_file_hash(path)
    if db.exists_hash(file_hash):
        if not reprocess:
            click.echo(f"  Skipped (duplicate): {path.name}")
            return False
        old_path = db.delete_by_hash(file_hash)
        if old_path:
            click.echo(f"  Reprocessing (replacing: {old_path})")

    # Extract document info
    try:
        existing_meta, text_sample, page_count = extract_doc_info(path)
    except Exception as e:
        click.echo(f"  Error reading file: {e}")
        return False

    # Generate metadata via AI
    click.echo("  Generating metadata...")
    try:
        metadata = ai.generate_metadata(existing_meta, text_sample, path.name)
    except Exception as e:
        click.echo(f"  Error generating metadata: {e}")
        return False

    metadata.page_count = page_count

    # Build entry (preserve original extension)
    ext = path.suffix.lower()
    dest_path = build_dest_path(metadata, extension=ext)
    entry = LibraryEntry(
        metadata=metadata,
        filename=Path(dest_path).name,
        original_filename=path.name,
        file_path=dest_path,
        file_hash=file_hash,
        ingested_at=datetime.now(UTC).isoformat(),
    )

    # Show metadata and confirm
    click.echo(format_metadata_display(entry))

    if not auto_confirm:
        if not click.confirm("  Accept and ingest?", default=True):
            click.echo("  Skipped.")
            return False

    # Write metadata (PDF only)
    try:
        write_doc_metadata(path, metadata.title, metadata.author, metadata.subject)
    except Exception as e:
        click.echo(f"  Warning: could not write metadata: {e}")

    # Store file (copy to all backends, then remove original)
    final_path = storage.store(path, dest_path)
    entry.file_path = final_path
    path.unlink()

    # Index in DB
    entry.id = db.insert(entry)
    click.echo(f"  Ingested -> {final_path}")
    return True


def _find_documents(inbox_path: Path) -> list[Path]:
    """Find all supported documents recursively."""
    return sorted(p for p in inbox_path.rglob("*") if p.is_file() and is_supported(p))


def ingest_inbox(
    inbox_path: Path,
    ai: AIBackend,
    storage: StorageBackend,
    db: Database,
    auto_confirm: bool = False,
    reprocess: bool = False,
) -> tuple[int, int]:
    """Ingest all documents from inbox recursively. Returns (processed, ingested) counts."""
    docs = _find_documents(inbox_path)
    if not docs:
        click.echo("No supported files found in inbox.")
        return 0, 0

    exts = ", ".join(sorted(SUPPORTED_EXTENSIONS))
    click.echo(f"Found {len(docs)} file(s) in {inbox_path} ({exts})")
    processed = 0
    ingested = 0

    for doc_path in docs:
        processed += 1
        click.echo(f"\n[{processed}/{len(docs)}]")
        if ingest_file(doc_path, ai, storage, db, auto_confirm, reprocess):
            ingested += 1

    click.echo(f"\nDone: {ingested}/{processed} files ingested.")
    return processed, ingested
