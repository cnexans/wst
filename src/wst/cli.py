import shutil
from pathlib import Path

import click

from wst.ai import get_ai_backend
from wst.config import WstConfig
from wst.db import Database
from wst.ingest import ingest_inbox
from wst.storage import LocalStorage


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """wst — organize your books and PDFs."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = WstConfig()


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path), required=False, default=None)
@click.option("--confirm", "-c", is_flag=True, help="Manually confirm metadata for each file")
@click.pass_context
def ingest(ctx: click.Context, path: Path | None, confirm: bool) -> None:
    """Ingest PDFs into the library.

    \b
    Without arguments, processes all PDFs in ~/wst/inbox/.
    With a PATH argument (file or directory), copies PDFs to the inbox first,
    then processes them.

    \b
    Examples:
        wst ingest                        # process inbox
        wst ingest ~/Downloads/book.pdf   # ingest a single file
        wst ingest ~/Documents/papers/    # ingest a whole folder
    """
    config: WstConfig = ctx.obj["config"]
    config.ensure_dirs()

    if path is not None:
        copied = _copy_to_inbox(path, config.inbox_path)
        if copied == 0:
            click.echo("No PDF files found at the given path.")
            return
        click.echo(f"Copied {copied} PDF(s) to inbox.")

    if not config.inbox_path.exists() or not any(config.inbox_path.rglob("*.pdf")):
        click.echo(f"No PDFs in inbox ({config.inbox_path}).")
        return

    ai = get_ai_backend(config.ai_backend, config.ai_model)
    storage = LocalStorage(config.library_path)
    db = Database(config.db_path)

    try:
        ingest_inbox(config.inbox_path, ai, storage, db, auto_confirm=not confirm)
    finally:
        db.close()


def _copy_to_inbox(source: Path, inbox: Path) -> int:
    """Copy PDF(s) from source to inbox. Returns count of files copied."""
    inbox.mkdir(parents=True, exist_ok=True)
    count = 0
    pdfs = []
    if source.is_file():
        if source.suffix.lower() == ".pdf":
            pdfs = [source]
    elif source.is_dir():
        pdfs = list(source.rglob("*.pdf"))

    for pdf in pdfs:
        dest = inbox / pdf.name
        if dest.exists():
            stem, suffix = dest.stem, dest.suffix
            counter = 1
            while dest.exists():
                dest = inbox / f"{stem} ({counter}){suffix}"
                counter += 1
        shutil.copy2(str(pdf), str(dest))
        count += 1
    return count


@cli.command()
@click.argument("query", default="")
@click.option("--author", "-a", default=None, help="Filter by author")
@click.option("--type", "-t", "doc_type", default=None, help="Filter by document type")
@click.pass_context
def search(ctx: click.Context, query: str, author: str | None, doc_type: str | None) -> None:
    """Search documents by title, author, tags, or subject."""
    config: WstConfig = ctx.obj["config"]
    db = Database(config.db_path)

    try:
        results = db.search(query, doc_type=doc_type, author=author)
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
        # Try as ID first
        entry = None
        if identifier.isdigit():
            entry = db.get(int(identifier))
        if entry is None:
            entry = db.get_by_title(identifier)
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
