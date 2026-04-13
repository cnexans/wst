import shutil
import time
from pathlib import Path

import click

from wst.ai import get_ai_backend
from wst.config import WstConfig
from wst.db import Database
from wst.document import extract_doc_info, is_supported
from wst.ingest import _find_documents, clean_inbox, format_metadata_display, ingest_files
from wst.models import DocType, LibraryEntry
from wst.storage import LocalStorage, build_dest_path


@click.group()
@click.option("--backend", "-b", default=None,
              type=click.Choice(["claude", "codex"], case_sensitive=False),
              help="AI backend to use (default: claude)")
@click.option("--model", "-m", "ai_model", default=None,
              help="AI model to use (e.g. sonnet, opus, gpt-5.4)")
@click.pass_context
def cli(ctx: click.Context, backend: str | None, ai_model: str | None) -> None:
    """wst — organize your books and PDFs."""
    ctx.ensure_object(dict)
    config = WstConfig()
    if backend:
        config.ai_backend = backend
    if ai_model:
        config.ai_model = ai_model
    ctx.obj["config"] = config


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path), required=False, default=None)
@click.option("--confirm", "-c", is_flag=True, help="Manually confirm metadata for each file")
@click.option("--reprocess", "-r", is_flag=True, help="Re-ingest duplicates with fresh AI metadata")
@click.option("--keep-inbox", is_flag=True, help="Don't clean inbox after processing")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed per-file processing logs")
@click.option("--ocr", is_flag=True, help="Auto-OCR scanned PDFs before processing")
@click.option(
    "--ocr-language",
    default="spa",
    help="OCR language code (default: spa)",
)
@click.pass_context
def ingest(
    ctx: click.Context,
    path: Path | None,
    confirm: bool,
    reprocess: bool,
    keep_inbox: bool,
    verbose: bool,
    ocr: bool,
    ocr_language: str,
) -> None:
    """Ingest PDFs into the library.

    \b
    Without arguments, processes all files in ~/wst/inbox/ and cleans it afterwards.
    With a PATH argument (file or directory), ingests only those files
    (copies them to inbox for processing, without touching other inbox files).

    \b
    Examples:
        wst ingest                        # process and clean inbox
        wst ingest ~/Downloads/book.pdf   # ingest a single file
        wst ingest ~/Documents/papers/    # ingest a whole folder
        wst ingest --keep-inbox           # process inbox without cleaning
        wst ingest -v                     # verbose per-file output
        wst ingest --ocr                  # OCR scanned PDFs before ingesting
    """
    config: WstConfig = ctx.obj["config"]
    config.ensure_dirs()

    ai = get_ai_backend(config.ai_backend, config.ai_model)
    storage = LocalStorage(config.library_path)
    db = Database(config.db_path)

    try:
        if path is not None:
            copied_files = _copy_to_inbox(path, config.inbox_path)
            if not copied_files:
                click.echo("No supported files found at the given path.")
                return
            click.echo(f"Copied {len(copied_files)} file(s) to inbox.")
            files_to_process = copied_files
        else:
            if not config.inbox_path.exists() or not any(
                p for p in config.inbox_path.rglob("*") if is_supported(p)
            ):
                click.echo(f"No supported files in inbox ({config.inbox_path}).")
                return
            files_to_process = _find_documents(config.inbox_path)

        if ocr:
            from wst.ocr import ocr_files as run_ocr_batch
            from wst.ocr import require_ocr_dependencies

            if not require_ocr_dependencies():
                return
            pdfs = [f for f in files_to_process if f.suffix.lower() == ".pdf"]
            if pdfs:
                click.echo("\n--- OCR pass ---")
                run_ocr_batch(
                    pdfs,
                    language=ocr_language,
                    verbose=verbose,
                )
                click.echo("")

        click.echo("--- Ingest pass ---")
        ingest_files(
            files_to_process,
            ai,
            storage,
            db,
            auto_confirm=not confirm,
            reprocess=reprocess,
            verbose=verbose,
        )

        if path is None and not keep_inbox:
            removed = clean_inbox(config.inbox_path)
            if removed > 0:
                click.echo(f"Cleaned inbox: removed {removed} remaining file(s).")
    finally:
        db.close()


@cli.group(invoke_without_command=True)
@click.pass_context
def backup(ctx: click.Context) -> None:
    """Backup library files to a cloud provider."""
    from wst.backup import PROVIDERS, run_backup_interactive

    if ctx.invoked_subcommand is not None:
        return

    config: WstConfig = ctx.obj["config"]

    # Interactive provider selection
    from InquirerPy import inquirer

    provider_names = list(PROVIDERS.keys())
    choice = inquirer.select(
        message="Choose backup provider:",
        choices=provider_names,
    ).execute()

    provider = PROVIDERS[choice]()
    db = Database(config.db_path)
    try:
        run_backup_interactive(provider, db, config.library_path)
    finally:
        db.close()


@backup.command("icloud")
@click.argument("identifier", required=False, default=None)
@click.pass_context
def backup_icloud(ctx: click.Context, identifier: str | None) -> None:
    """Backup files to iCloud Drive."""
    from wst.backup import ICloudProvider, run_backup_file, run_backup_interactive

    config: WstConfig = ctx.obj["config"]
    provider = ICloudProvider()
    db = Database(config.db_path)

    try:
        if identifier:
            run_backup_file(provider, db, config.library_path, identifier)
        else:
            run_backup_interactive(provider, db, config.library_path)
    finally:
        db.close()


@backup.command("s3")
@click.argument("identifier", required=False, default=None)
@click.option("--configure", is_flag=True, help="Configure S3 credentials")
@click.pass_context
def backup_s3(
    ctx: click.Context,
    identifier: str | None,
    configure: bool,
) -> None:
    """Backup files to S3 (or S3-compatible storage).

    \b
    Works with AWS S3, Cloudflare R2, Backblaze B2, MinIO, etc.
    Credentials are stored in ~/wst/config.json.

    \b
    Examples:
        wst backup s3 --configure       # set up credentials
        wst backup s3                    # interactive backup
        wst backup s3 3                  # backup document by ID
        wst backup s3 "Cosmos"           # backup document by title
    """
    from wst.backup import S3Provider, run_backup_file, run_backup_interactive

    config: WstConfig = ctx.obj["config"]
    provider = S3Provider()

    if configure:
        provider.configure()
        return

    db = Database(config.db_path)
    try:
        if identifier:
            run_backup_file(provider, db, config.library_path, identifier)
        else:
            run_backup_interactive(provider, db, config.library_path)
    finally:
        db.close()


@cli.command()
@click.pass_context
def browse(ctx: click.Context) -> None:
    """Interactive browser for viewing and editing documents."""
    from wst.browse import browse_library

    config: WstConfig = ctx.obj["config"]
    db = Database(config.db_path)
    storage = LocalStorage(config.library_path)

    try:
        browse_library(db, storage, config.library_path)
    finally:
        db.close()


@cli.command()
@click.argument(
    "path",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--language",
    "-l",
    default="spa",
    help="OCR language code (default: spa). Use + for multiple: spa+eng",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force OCR even if the PDF already has extractable text",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed per-file processing logs",
)
def ocr(path: Path, language: str, force: bool, verbose: bool) -> None:
    """Run OCR on scanned PDFs to make them searchable.

    \b
    Adds an invisible text layer to scanned PDFs using ocrmypdf.
    Skips PDFs that already have extractable text (use --force to override).
    Requires ocrmypdf: pipx install ocrmypdf

    \b
    Examples:
        wst ocr scan.pdf                # OCR a single file
        wst ocr ~/scans/                # OCR all PDFs in a folder
        wst ocr scan.pdf -l eng         # OCR in English
        wst ocr scan.pdf -l spa+eng     # OCR in Spanish and English
        wst ocr scan.pdf --force        # Force OCR even if text exists
    """
    from wst.ocr import ocr_files as run_ocr_batch

    if path.is_file():
        if path.suffix.lower() != ".pdf":
            click.echo("Only PDF files can be OCR'd.")
            return
        files = [path]
    elif path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
        if not files:
            click.echo("No PDF files found in the given directory.")
            return
    else:
        click.echo("Path must be a file or directory.")
        return

    run_ocr_batch(files, language=language, force=force, verbose=verbose)


def _copy_to_inbox(source: Path, inbox: Path) -> list[Path]:
    """Copy supported files from source to inbox. Returns list of copied file paths in inbox."""
    inbox.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    files = []
    if source.is_file():
        if is_supported(source):
            files = [source]
    elif source.is_dir():
        files = [p for p in source.rglob("*") if p.is_file() and is_supported(p)]

    for pdf in files:
        dest = inbox / pdf.name
        if dest.exists():
            stem, suffix = dest.stem, dest.suffix
            counter = 1
            while dest.exists():
                dest = inbox / f"{stem} ({counter}){suffix}"
                counter += 1
        shutil.copy2(str(pdf), str(dest))
        copied.append(dest)
    return copied


@cli.command()
@click.argument("query", default="")
@click.option("--author", "-a", default=None, help="Filter by author")
@click.option("--type", "-t", "doc_type", default=None, help="Filter by document type")
@click.option("--subject", "-s", default=None, help="Filter by subject/knowledge area")
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    author: str | None,
    doc_type: str | None,
    subject: str | None,
) -> None:
    """Search documents by title, author, tags, or subject."""
    config: WstConfig = ctx.obj["config"]
    db = Database(config.db_path)

    try:
        results = db.search(query, doc_type=doc_type, author=author, subject=subject)
        if not results:
            click.echo("No results found.")
            return
        _print_table(results)
    finally:
        db.close()


@cli.command(name="list")
@click.option("--type", "-t", "doc_type", default=None, help="Filter by document type")
@click.option(
    "--sort",
    "-s",
    "sort_by",
    default="title",
    type=click.Choice(["title", "author", "year"]),
    help="Sort by field",
)
@click.pass_context
def list_cmd(ctx: click.Context, doc_type: str | None, sort_by: str) -> None:
    """List all documents in the library."""
    config: WstConfig = ctx.obj["config"]
    db = Database(config.db_path)

    try:
        entries = db.list_all(doc_type=doc_type, sort_by=sort_by)
        if not entries:
            click.echo("Library is empty.")
            return
        _print_table(entries)
    finally:
        db.close()


@cli.command()
@click.argument("identifier")
@click.pass_context
def show(ctx: click.Context, identifier: str) -> None:
    """Show full metadata for a document (by ID or title)."""
    config: WstConfig = ctx.obj["config"]
    db = Database(config.db_path)

    try:
        entry = _find_entry(db, identifier)
        if entry is None:
            click.echo(f"Document not found: {identifier}")
            raise SystemExit(1)

        m = entry.metadata
        click.echo(f"ID:            {entry.id}")
        click.echo(f"Title:         {m.title}")
        click.echo(f"Author:        {m.author}")
        click.echo(f"Type:          {m.doc_type.value}")
        click.echo(f"Year:          {m.year or 'N/A'}")
        click.echo(f"Publisher:     {m.publisher or 'N/A'}")
        click.echo(f"ISBN:          {m.isbn or 'N/A'}")
        click.echo(f"Language:      {m.language or 'N/A'}")
        click.echo(f"Pages:         {m.page_count or 'N/A'}")
        click.echo(f"Subject:       {m.subject or 'N/A'}")
        click.echo(f"Tags:          {', '.join(m.tags) if m.tags else 'N/A'}")
        click.echo(f"Summary:       {m.summary or 'N/A'}")
        click.echo(f"TOC:           {m.table_of_contents or 'N/A'}")
        click.echo(f"File:          {entry.file_path}")
        click.echo(f"Original file: {entry.original_filename}")
        click.echo(f"Ingested at:   {entry.ingested_at}")
    finally:
        db.close()


@cli.command()
@click.option("--type", "-t", "doc_type", default=None,
              type=click.Choice([dt.value for dt in DocType], case_sensitive=False),
              help="Filter by document type")
@click.pass_context
def stats(ctx: click.Context, doc_type: str | None) -> None:
    """Show metadata coverage statistics.

    \b
    Displays how complete the metadata is across all documents,
    broken down by document type and field.

    \b
    Examples:
        wst stats
        wst stats --type textbook
    """
    config: WstConfig = ctx.obj["config"]
    db = Database(config.db_path)

    try:
        entries = db.list_all(doc_type=doc_type)
        if not entries:
            click.echo("Library is empty.")
            return

        fields = ["title", "author", "year", "publisher", "isbn",
                   "language", "subject", "summary", "table_of_contents", "page_count"]

        # Group by doc_type
        by_type: dict[str, list[LibraryEntry]] = {}
        for e in entries:
            dt = e.metadata.doc_type.value
            by_type.setdefault(dt, []).append(e)

        # Overall coverage per field
        click.echo(f"\nTotal documents: {len(entries)}\n")
        click.echo(f"  {'Field':<22} {'Filled':>6} {'Missing':>7} {'Coverage':>9}")
        click.echo("  " + "-" * 48)
        for field in fields:
            filled = sum(1 for e in entries if _field_filled(e, field))
            missing = len(entries) - filled
            pct = (filled / len(entries)) * 100
            bar = _coverage_bar(pct)
            click.echo(f"  {field:<22} {filled:>6} {missing:>7} {pct:>6.1f}%  {bar}")

        # Per-type breakdown
        key_fields = ["isbn", "table_of_contents", "year", "publisher", "summary"]
        headers = ["ISBN", "TOC", "Year", "Publisher", "Summary"]
        click.echo(f"\n  {'Type':<16} {'Total':>5}  {'  '.join(f'{h:>9}' for h in headers)}")
        click.echo("  " + "-" * (24 + 11 * len(headers)))
        for dt in sorted(by_type):
            group = by_type[dt]
            total = len(group)
            pcts = []
            for f in key_fields:
                n = sum(1 for e in group if _field_filled(e, f))
                pcts.append(f"{(n / total) * 100:>6.0f}%")
            click.echo(f"  {dt:<16} {total:>5}  {'  '.join(f'{p:>9}' for p in pcts)}")
        click.echo()
    finally:
        db.close()


def _field_filled(entry: LibraryEntry, field: str) -> bool:
    val = getattr(entry.metadata, field, None)
    return val is not None and val != "" and val != []


def _pct_str(filled: int, total: int) -> str:
    pct = (filled / total) * 100 if total else 0
    return f"{filled}/{total} {pct:.0f}%"


def _coverage_bar(pct: float, width: int = 15) -> str:
    filled = int(pct / 100 * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"


@cli.command()
@click.argument("identifier")
@click.option("--enrich", is_flag=True, help="Use AI to fill missing fields (ISBN, publisher, etc.)")
@click.pass_context
def edit(ctx: click.Context, identifier: str, enrich: bool) -> None:
    """Interactively edit metadata for a document.

    \b
    Shows current values and lets you change any field.
    Press Enter to keep the current value. If the document type
    changes, the file is moved to the correct folder.

    \b
    Use --enrich to automatically fill missing fields (ISBN,
    publisher, year) using AI and web search.

    \b
    Examples:
        wst edit 1
        wst edit "Player's Handbook"
        wst edit 42 --enrich
    """
    config: WstConfig = ctx.obj["config"]
    db = Database(config.db_path)
    storage = LocalStorage(config.library_path)

    try:
        entry = _find_entry(db, identifier)
        if entry is None:
            click.echo(f"Document not found: {identifier}")
            raise SystemExit(1)

        m = entry.metadata

        if enrich:
            _enrich_entry(entry, config, db)
            return

        click.echo(f"\nEditing: {m.title} (ID {entry.id})")
        click.echo("Press Enter to keep current value.\n")

        m.title = _prompt_field("Title", m.title)
        m.author = _prompt_field("Author", m.author)
        m.doc_type = _prompt_doc_type(m.doc_type)
        year_str = _prompt_field("Year", str(m.year) if m.year else "")
        m.year = int(year_str) if year_str else None
        m.publisher = _prompt_field("Publisher", m.publisher or "") or None
        m.isbn = _prompt_field("ISBN", m.isbn or "") or None
        m.language = _prompt_field("Language", m.language or "") or None
        m.subject = _prompt_field("Subject", m.subject or "") or None
        tags_str = _prompt_field("Tags (comma-separated)", ", ".join(m.tags))
        m.tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        m.summary = _prompt_field("Summary", m.summary or "") or None

        # Rebuild destination path and move if needed
        new_dest = build_dest_path(m)
        old_path = entry.file_path

        if new_dest != old_path:
            old_full = config.library_path / old_path
            if old_full.exists():
                final = storage.store(old_full, new_dest)
                old_full.unlink()
                entry.file_path = final
                entry.filename = Path(final).name
                click.echo(f"\nMoved: {old_path} -> {final}")
            else:
                entry.file_path = new_dest
                entry.filename = Path(new_dest).name
                click.echo(f"\nWarning: old file not found at {old_path}, updated path in DB only.")
        else:
            click.echo("")

        db.update(entry)
        click.echo("Updated successfully.")
    finally:
        db.close()


def _enrich_entry(
    entry: LibraryEntry, config: WstConfig, db: Database
) -> None:
    m = entry.metadata
    missing = _get_missing_fields(m)

    if not missing:
        click.echo(f"\n{m.title}: all fields already populated, nothing to enrich.")
        return

    click.echo(f"\nEnriching: {m.title} (ID {entry.id})")
    click.echo(f"Missing fields: {', '.join(missing)}")

    changes, enriched = _run_enrich(entry, config)

    if not changes:
        click.echo("  AI could not find any additional information.")
        return

    click.echo("\n  Found:")
    for field, value in changes:
        display = value if not isinstance(value, list) else ", ".join(value)
        click.echo(f"    {field}: {display}")

    if not click.confirm("\n  Apply these changes?", default=True):
        click.echo("  Skipped.")
        return

    entry.metadata = enriched
    db.update(entry)
    click.echo("  Updated successfully.")


def _get_missing_fields(m: "DocumentMetadata") -> list[str]:
    return [k for k, v in m.model_dump().items() if v is None]


def _run_enrich(
    entry: LibraryEntry, config: WstConfig
) -> tuple[list[tuple[str, object]], "DocumentMetadata"]:
    """Run AI enrichment. Returns (changes, enriched_metadata)."""
    from wst.models import DocumentMetadata  # noqa: F811

    m = entry.metadata
    missing = _get_missing_fields(m)

    file_path = config.library_path / entry.file_path
    text_sample = ""
    if file_path.exists():
        try:
            _, text_sample, _ = extract_doc_info(file_path)
        except Exception:
            click.echo("  Warning: could not read file for text context.")

    ai = get_ai_backend(config.ai_backend, config.ai_model)
    click.echo("  Searching with AI...")

    enriched = ai.enrich_metadata(m, text_sample)

    changes = []
    old_dump = m.model_dump()
    new_dump = enriched.model_dump()
    for field in missing:
        if new_dump[field] != old_dump[field]:
            changes.append((field, new_dump[field]))

    return changes, enriched


def _find_entry(db: Database, identifier: str) -> LibraryEntry | None:
    entry = None
    if identifier.isdigit():
        entry = db.get(int(identifier))
    if entry is None:
        entry = db.get_by_title(identifier)
    return entry


def _prompt_field(label: str, current: str) -> str:
    value = click.prompt(f"  {label}", default=current, show_default=True)
    return value.strip()


def _prompt_doc_type(current: DocType) -> DocType:
    types = list(DocType)
    click.echo(f"  Type [{current.value}]:")
    for i, dt in enumerate(types, 1):
        marker = " <-" if dt == current else ""
        click.echo(f"    {i}. {dt.value}{marker}")
    choice = click.prompt("  Choose number or Enter to keep", default="", show_default=False)
    if choice and choice.isdigit() and 1 <= int(choice) <= len(types):
        return types[int(choice) - 1]
    return current


@cli.command()
@click.option("--type", "doc_type", type=click.Choice([dt.value for dt in DocType], case_sensitive=False), help="Only fix documents of this type")
@click.option("--field", multiple=True, help="Only fix documents missing this field (e.g. --field isbn --field toc)")
@click.option("--yes", "-y", is_flag=True, help="Auto-accept all changes without prompting")
@click.option("--dry-run", is_flag=True, help="Show what would be enriched without making changes")
@click.pass_context
def fix(ctx: click.Context, doc_type: str | None, field: tuple[str, ...], yes: bool, dry_run: bool) -> None:
    """Enrich all documents that have missing metadata fields.

    \b
    Scans the library for documents with missing fields (ISBN, publisher,
    year, table_of_contents, etc.) and uses AI + web search to fill them.

    \b
    Examples:
        wst fix                         # fix all documents with missing fields
        wst fix --type textbook         # only textbooks
        wst fix --field isbn            # only those missing ISBN
        wst fix --field isbn --field toc
        wst fix --dry-run               # preview what needs fixing
        wst fix --type novel -y         # fix all novels, auto-accept
    """
    field_map = {"toc": "table_of_contents"}
    target_fields = [field_map.get(f, f) for f in field] if field else None

    config: WstConfig = ctx.obj["config"]
    db = Database(config.db_path)

    try:
        entries = db.list_all(doc_type=doc_type)

        # Filter to entries with missing fields
        to_fix = []
        for entry in entries:
            missing = _get_missing_fields(entry.metadata)
            if target_fields:
                missing = [f for f in missing if f in target_fields]
            if missing:
                to_fix.append((entry, missing))

        if not to_fix:
            click.echo("All documents are complete. Nothing to fix.")
            return

        click.echo(f"Found {len(to_fix)} document(s) with missing fields.\n")

        if dry_run:
            click.echo(f"{'ID':>4}  {'Title':<40}  {'Type':<12}  Missing fields")
            click.echo("-" * 90)
            for entry, missing in to_fix:
                m = entry.metadata
                title = m.title[:38] + ".." if len(m.title) > 40 else m.title
                click.echo(f"{entry.id:>4}  {title:<40}  {m.doc_type.value:<12}  {', '.join(missing)}")
            return

        fixed = 0
        failed = 0
        skipped = 0
        start = time.monotonic()

        for i, (entry, missing) in enumerate(to_fix, 1):
            m = entry.metadata
            click.echo(f"\n[{i}/{len(to_fix)}] {m.title} (ID {entry.id})")
            click.echo(f"  Missing: {', '.join(missing)}")

            try:
                changes, enriched = _run_enrich(entry, config)
            except Exception as e:
                click.echo(f"  Error: {e}")
                failed += 1
                continue

            if not changes:
                click.echo("  No new information found.")
                skipped += 1
                continue

            click.echo("  Found:")
            for f_name, value in changes:
                display = value if not isinstance(value, list) else ", ".join(value)
                # Truncate long values like TOC for display
                if isinstance(display, str) and len(display) > 80:
                    display = display[:77] + "..."
                click.echo(f"    {f_name}: {display}")

            if not yes:
                if not click.confirm("  Apply?", default=True):
                    skipped += 1
                    continue

            entry.metadata = enriched
            db.update(entry)
            fixed += 1
            click.echo("  Updated.")

        elapsed = time.monotonic() - start
        click.echo(f"\nDone in {int(elapsed)}s: {fixed} fixed, {skipped} skipped, {failed} failed")
    finally:
        db.close()


def _print_table(entries: list) -> None:
    """Print a simple table of entries."""
    click.echo(f"{'ID':>4}  {'Title':<40}  {'Author':<25}  {'Type':<12}  {'Year':>4}")
    click.echo("-" * 93)
    for e in entries:
        m = e.metadata
        title = m.title[:38] + ".." if len(m.title) > 40 else m.title
        author = m.author[:23] + ".." if len(m.author) > 25 else m.author
        year = str(m.year) if m.year else "N/A"
        click.echo(f"{e.id:>4}  {title:<40}  {author:<25}  {m.doc_type.value:<12}  {year:>4}")
