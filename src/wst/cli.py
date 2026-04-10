import shutil
from pathlib import Path

import click

from wst.ai import get_ai_backend
from wst.config import WstConfig
from wst.db import Database
from wst.document import is_supported
from wst.ingest import _find_documents, clean_inbox, ingest_files
from wst.models import DocType, LibraryEntry
from wst.storage import LocalStorage, build_dest_path


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """wst — organize your books and PDFs."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = WstConfig()


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path), required=False, default=None)
@click.option("--confirm", "-c", is_flag=True, help="Manually confirm metadata for each file")
@click.option("--reprocess", "-r", is_flag=True, help="Re-ingest duplicates with fresh AI metadata")
@click.option("--keep-inbox", is_flag=True, help="Don't clean inbox after processing")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed per-file processing logs")
@click.pass_context
def ingest(
    ctx: click.Context, path: Path | None, confirm: bool,
    reprocess: bool, keep_inbox: bool, verbose: bool,
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
            ingest_files(
                copied_files, ai, storage, db,
                auto_confirm=not confirm, reprocess=reprocess, verbose=verbose,
            )
        else:
            if not config.inbox_path.exists() or not any(
                p for p in config.inbox_path.rglob("*") if is_supported(p)
            ):
                click.echo(f"No supported files in inbox ({config.inbox_path}).")
                return
            docs = _find_documents(config.inbox_path)
            ingest_files(
                docs, ai, storage, db,
                auto_confirm=not confirm, reprocess=reprocess, verbose=verbose,
            )
            if not keep_inbox:
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
@click.argument("identifier")
@click.pass_context
def edit(ctx: click.Context, identifier: str) -> None:
    """Interactively edit metadata for a document.

    \b
    Shows current values and lets you change any field.
    Press Enter to keep the current value. If the document type
    changes, the file is moved to the correct folder.

    \b
    Examples:
        wst edit 1
        wst edit "Player's Handbook"
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
