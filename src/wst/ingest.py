import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import click

from wst.ai import AIBackend
from wst.db import Database
from wst.document import extract_doc_info, is_supported, write_doc_metadata
from wst.models import LibraryEntry
from wst.storage import StorageBackend, build_dest_path
from wst.topics import assign_topics_single, load_vocabulary


@dataclass
class IngestResult:
    filename: str
    status: str  # "ingested", "skipped", "failed"
    reason: str = ""
    dest_path: str = ""


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


def _format_eta(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours}h {minutes:02d}m"


def _clear_line() -> None:
    click.echo("\r" + " " * 80 + "\r", nl=False)


def _show_progress(current: int, total: int, filename: str, elapsed: float) -> None:
    pct = (current / total) * 100
    if current > 0:
        avg = elapsed / current
        remaining = avg * (total - current)
        eta = f"ETA: {_format_eta(remaining)}"
    else:
        eta = "ETA: --"
    name = filename[:30] + ".." if len(filename) > 32 else filename
    line = f"[{pct:3.0f}%] {current}/{total} | {eta} | {name}"
    click.echo("\r" + line.ljust(80), nl=False)


def ingest_file(
    path: Path,
    ai: AIBackend,
    storage: StorageBackend,
    db: Database,
    auto_confirm: bool = False,
    reprocess: bool = False,
    verbose: bool = False,
    library_path: Path | None = None,
) -> IngestResult:
    """Ingest a single document file. Returns an IngestResult."""
    if verbose:
        click.echo(f"\nProcessing: {path.name}")

    # Check for duplicates
    file_hash = compute_file_hash(path)
    if db.exists_hash(file_hash):
        if not reprocess:
            if verbose:
                click.echo(f"  Skipped (duplicate): {path.name}")
            return IngestResult(path.name, "skipped", "duplicate")
        old_path = db.delete_by_hash(file_hash)
        if old_path and verbose:
            click.echo(f"  Reprocessing (replacing: {old_path})")

    # Extract document info
    try:
        existing_meta, text_sample, page_count = extract_doc_info(path)
    except Exception as e:
        if verbose:
            click.echo(f"  Error reading file: {e}")
        return IngestResult(path.name, "failed", f"Error reading file: {e}")

    # Generate metadata via AI
    if verbose:
        click.echo("  Generating metadata...")
    try:
        metadata = ai.generate_metadata(existing_meta, text_sample, path.name)
    except Exception as e:
        if verbose:
            click.echo(f"  Error generating metadata: {e}")
        return IngestResult(path.name, "failed", f"Error generating metadata: {e}")

    metadata.page_count = page_count

    # If a KMeans vocabulary exists, override the LLM-chosen topics with
    # vocabulary-constrained ones so ingested docs stay aligned with the corpus.
    vocabulary = load_vocabulary(db)
    if vocabulary:
        doc = {
            "title": metadata.title,
            "author": metadata.author,
            "tags": metadata.tags,
            "summary": (metadata.summary or "")[:300],
            "subject": metadata.subject,
        }
        constrained = assign_topics_single(ai, vocabulary, doc)
        if constrained:
            metadata.topics = constrained

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
    if verbose or not auto_confirm:
        click.echo(format_metadata_display(entry))

    if not auto_confirm:
        if not click.confirm("  Accept and ingest?", default=True):
            if verbose:
                click.echo("  Skipped.")
            return IngestResult(path.name, "skipped", "declined by user")

    # Write metadata (PDF only)
    try:
        write_doc_metadata(path, metadata.title, metadata.author, metadata.subject)
    except Exception as e:
        if verbose:
            click.echo(f"  Warning: could not write metadata: {e}")

    # Store file (copy to all backends, then remove original)
    final_path = storage.store(path, dest_path)
    entry.file_path = final_path
    path.unlink()

    # Index in DB
    entry.id = db.insert(entry)
    if verbose:
        click.echo(f"  Ingested -> {final_path}")

    # Generate cover immediately so the app shows it without requiring `wst covers`
    if library_path is not None:
        from wst.covers import ensure_cover

        ensure_cover(library_path, entry.id, metadata.isbn, entry.file_path)

    return IngestResult(path.name, "ingested", dest_path=final_path)


def _find_documents(inbox_path: Path) -> list[Path]:
    """Find all supported documents recursively."""
    return sorted(p for p in inbox_path.rglob("*") if p.is_file() and is_supported(p))


def ingest_files(
    files: list[Path],
    ai: AIBackend,
    storage: StorageBackend,
    db: Database,
    auto_confirm: bool = False,
    reprocess: bool = False,
    verbose: bool = False,
    *,
    emit: bool = True,
    progress: bool = True,
    library_path: Path | None = None,
) -> dict:
    """Ingest a list of document files.

    Returns a dict summary with keys:
      - processed, ingested, skipped, failed
      - results: list[IngestResult] (as dataclasses)
      - elapsed_seconds

    When emit=False, this function produces no stdout/stderr.
    When progress=False, no carriage-return progress line is printed.
    """
    if not files:
        if emit:
            click.echo("No supported files found.")
        return {
            "processed": 0,
            "ingested": 0,
            "skipped": 0,
            "failed": 0,
            "results": [],
            "elapsed_seconds": 0.0,
        }

    total = len(files)
    if emit:
        click.echo(f"Found {total} file(s)")

    results: list[IngestResult] = []
    start_time = time.monotonic()

    for i, doc_path in enumerate(files):
        elapsed = time.monotonic() - start_time

        if emit and progress and not verbose:
            _show_progress(i, total, doc_path.name, elapsed)

        if emit and progress and not verbose and not auto_confirm:
            # Need to clear progress line before interactive prompt
            _clear_line()

        result = ingest_file(
            doc_path, ai, storage, db, auto_confirm, reprocess, verbose, library_path
        )
        results.append(result)

    # Clear progress line
    if emit and progress and not verbose:
        _clear_line()

    # Summary
    ingested = [r for r in results if r.status == "ingested"]
    failed = [r for r in results if r.status == "failed"]
    skipped = [r for r in results if r.status == "skipped"]

    elapsed = time.monotonic() - start_time
    if emit:
        eta = _format_eta(elapsed)
        click.echo(
            f"\nDone in {eta}: "
            f"{len(ingested)} ingested, {len(skipped)} skipped, {len(failed)} failed"
        )

        if failed:
            click.echo("\nFailed:")
            for r in failed:
                click.echo(f"  - {r.filename}: {r.reason}")

        if skipped and verbose:
            click.echo("\nSkipped:")
            for r in skipped:
                click.echo(f"  - {r.filename}: {r.reason}")

    return {
        "processed": total,
        "ingested": len(ingested),
        "skipped": len(skipped),
        "failed": len(failed),
        "results": results,
        "elapsed_seconds": elapsed,
    }


def clean_inbox(inbox_path: Path) -> int:
    """Remove all remaining files from inbox. Returns count of files removed."""
    removed = 0
    for p in inbox_path.rglob("*"):
        if p.is_file():
            p.unlink()
            removed += 1
    # Remove empty subdirectories
    for p in sorted(inbox_path.rglob("*"), reverse=True):
        if p.is_dir() and not any(p.iterdir()):
            p.rmdir()
    return removed
