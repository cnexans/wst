import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click

from wst.ai import get_ai_backend
from wst.config import WstConfig
from wst.db import Database
from wst.document import extract_doc_info, is_supported
from wst.ingest import _find_documents, clean_inbox, ingest_files
from wst.models import DocType, LibraryEntry
from wst.storage import LocalStorage, build_dest_path

F = TypeVar("F", bound=Callable[..., Any])

FORMAT_CHOICE = click.Choice(["human", "md", "json", "yaml"], case_sensitive=False)


def _apply_command_format(ctx: click.Context, param: click.Parameter, value: str | None) -> None:
    """When a subcommand passes --format, override the group default in ctx.obj."""
    if value is not None:
        ctx.ensure_object(dict)
        ctx.obj["format"] = value.lower()


def command_format_option() -> Callable[[F], F]:
    """Add --format on subcommands (not only `wst --format … CMD`)."""

    def decorator(f: F) -> F:
        f = click.option(
            "--format",
            "_command_format",
            default=None,
            type=FORMAT_CHOICE,
            callback=_apply_command_format,
            expose_value=False,
            help=(
                "Output format for this command (overrides `wst --format`). "
                "Same as: wst --format yaml <command>"
            ),
        )(f)
        # Common typo (--formate); hidden so normal help stays clean.
        return click.option(
            "--formate",
            "_command_format_typo",
            default=None,
            type=FORMAT_CHOICE,
            callback=_apply_command_format,
            expose_value=False,
            hidden=True,
        )(f)

    return decorator


class WstCli(click.Group):
    def invoke(self, ctx: click.Context) -> object:  # type: ignore[override]
        try:
            return super().invoke(ctx)
        except Exception as e:
            fmt = None
            try:
                fmt = ctx.obj.get("format") if isinstance(ctx.obj, dict) else None
            except Exception:
                fmt = None

            if fmt in {"md", "json", "yaml"}:
                from wst.output import WstError, render_error

                if isinstance(e, WstError):
                    render_error(
                        code=e.code,
                        message=e.message,
                        details=e.details,
                        fmt=fmt,
                    )
                    raise SystemExit(e.exit_code)

                if isinstance(e, click.UsageError):
                    render_error(
                        code="usage_error",
                        message=e.format_message(),
                        details={"hint": "See `wst --help` for usage."},
                        fmt=fmt,
                    )
                    raise SystemExit(e.exit_code)

                if isinstance(e, click.ClickException):
                    render_error(
                        code="click_error",
                        message=e.format_message(),
                        details=None,
                        fmt=fmt,
                    )
                    raise SystemExit(e.exit_code)

                if isinstance(e, SystemExit):
                    render_error(
                        code="system_exit",
                        message="Command failed.",
                        details={"exit_code": e.code},
                        fmt=fmt,
                    )
                    raise

                render_error(
                    code="unexpected_error",
                    message=str(e) or e.__class__.__name__,
                    details=None,
                    fmt=fmt,
                )
                raise SystemExit(1)

            raise


@click.group(cls=WstCli)
@click.option(
    "--backend",
    "-b",
    default=None,
    type=click.Choice(["claude", "codex"], case_sensitive=False),
    help="AI backend to use (default: claude)",
)
@click.option(
    "--model", "-m", "ai_model", default=None, help="AI model to use (e.g. sonnet, opus, gpt-5.4)"
)
@click.option(
    "--format",
    "output_format",
    default="human",
    type=FORMAT_CHOICE,
    help="Output format: human (terminal), md, json, yaml (default: human)",
)
@click.pass_context
def cli(
    ctx: click.Context,
    backend: str | None,
    ai_model: str | None,
    output_format: str,
) -> None:
    """wst — organize your books and PDFs.

    \b
    Output formats:
      - --format human  : terminal-friendly output (default)
      - --format md     : markdown (machine-friendly, pasteable)
      - --format json   : structured output for scripts
      - --format yaml   : structured output for configs/pipelines

    \b
    Notes:
      - In machine formats (md/json/yaml), commands do not prompt for input.
        Use explicit flags (e.g. -y/--yes, --set key=value) or the command will fail.

    \b
    Examples:
      wst list
      wst --format json list
      wst list --format json
      wst show 3 --format yaml
      wst browse --id 3 --action view --format md

    \b
    Where --format goes:
      - After `wst`: `wst --format yaml search "foo"` (always works).
      - After the subcommand: `wst search "foo" --format yaml`
        (same; each command accepts --format).
    """
    ctx.ensure_object(dict)
    config = WstConfig()
    if backend:
        config.ai_backend = backend
    if ai_model:
        config.ai_model = ai_model
    ctx.obj["config"] = config
    ctx.obj["format"] = output_format.lower()


@cli.command()
@command_format_option()
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
    Machine output:
      - Use --format json|yaml|md for structured output.
      - In machine formats, progress bars are disabled and output is emitted once at the end.

    \b
    Examples:
        wst ingest                        # process and clean inbox
        wst ingest ~/Downloads/book.pdf   # ingest a single file
        wst ingest ~/Documents/papers/    # ingest a whole folder
        wst ingest --keep-inbox           # process inbox without cleaning
        wst ingest -v                     # verbose per-file output
        wst ingest --ocr                  # OCR scanned PDFs before ingesting
        wst ingest --format json          # structured output
    """
    config: WstConfig = ctx.obj["config"]
    fmt: str = ctx.obj.get("format", "human")
    config.ensure_dirs()

    ai = get_ai_backend(config.ai_backend, config.ai_model)
    storage = LocalStorage(config.library_path)
    db = Database(config.db_path)

    try:
        removed = 0
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

        ocr_summary = None
        if ocr:
            from wst.ocr import ocr_files as run_ocr_batch
            from wst.ocr import require_ocr_dependencies

            if not require_ocr_dependencies():
                return
            pdfs = [f for f in files_to_process if f.suffix.lower() == ".pdf"]
            if pdfs:
                if fmt == "human":
                    click.echo("\n--- OCR pass ---")
                ocr_summary = run_ocr_batch(
                    pdfs,
                    language=ocr_language,
                    verbose=verbose,
                    emit=(fmt == "human"),
                    progress=(fmt == "human"),
                )
                if fmt == "human":
                    click.echo("")

        if fmt == "human":
            click.echo("--- Ingest pass ---")

        ingest_summary = ingest_files(
            files_to_process,
            ai,
            storage,
            db,
            auto_confirm=not confirm,
            reprocess=reprocess,
            verbose=verbose,
            emit=(fmt == "human"),
            progress=(fmt == "human"),
        )

        if path is None and not keep_inbox:
            removed = clean_inbox(config.inbox_path)
            if fmt == "human" and removed > 0:
                click.echo(f"Cleaned inbox: removed {removed} remaining file(s).")

        if fmt != "human":
            from wst.output import render_ok

            render_ok(
                {
                    "ocr": ocr_summary,
                    "ingest": ingest_summary,
                    "cleaned_inbox_removed": removed,
                },
                fmt=fmt,
            )
    finally:
        db.close()


@cli.group(invoke_without_command=True)
@command_format_option()
@click.pass_context
def backup(ctx: click.Context) -> None:
    """Backup library files to a cloud provider.

    \b
    This command is interactive by default.
    For non-interactive scripting, use subcommands:
      - wst backup icloud <ID|TITLE>
      - wst backup s3 <ID|TITLE>
    """
    from wst.backup import PROVIDERS, run_backup_interactive

    if ctx.invoked_subcommand is not None:
        return

    config: WstConfig = ctx.obj["config"]
    fmt: str = ctx.obj.get("format", "human")

    if fmt != "human":
        from wst.output import WstError

        raise WstError(
            "usage_error",
            (
                "Interactive backup requires --format human. "
                "Use `wst backup icloud|s3` with an identifier, or add non-interactive flags."
            ),
            details={"hint": "Try: wst backup s3 3 --format json"},
            exit_code=2,
        )

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
@command_format_option()
@click.argument("identifier", required=False, default=None)
@click.pass_context
def backup_icloud(ctx: click.Context, identifier: str | None) -> None:
    """Backup files to iCloud Drive."""
    from wst.backup import ICloudProvider, run_backup_file, run_backup_interactive

    config: WstConfig = ctx.obj["config"]
    fmt: str = ctx.obj.get("format", "human")
    provider = ICloudProvider()
    db = Database(config.db_path)

    try:
        if fmt != "human" and not identifier:
            from wst.output import WstError

            raise WstError(
                "usage_error",
                "Non-interactive backup requires an IDENTIFIER (ID or exact title).",
                details={"hint": "Try: wst backup icloud 3 --format json"},
                exit_code=2,
            )

        if identifier:
            if fmt == "human":
                run_backup_file(provider, db, config.library_path, identifier, emit=True)
                return
            if not provider.is_configured():
                from wst.output import WstError

                raise WstError(
                    "requires_interactive",
                    "Backup provider is not configured. Run interactive configuration first.",
                    details={"hint": "Try: wst backup icloud --format human"},
                    exit_code=2,
                )
            # Avoid stdout contamination from backup module in machine formats
            run_backup_file(provider, db, config.library_path, identifier, emit=False)
            from wst.output import render_ok

            render_ok({"provider": "icloud", "identifier": identifier, "status": "ok"}, fmt=fmt)
        else:
            run_backup_interactive(provider, db, config.library_path)
    finally:
        db.close()


@backup.command("s3")
@command_format_option()
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
    fmt: str = ctx.obj.get("format", "human")
    provider = S3Provider()

    if configure:
        if fmt != "human":
            from wst.output import WstError

            raise WstError(
                "usage_error",
                "S3 configuration is interactive. Use --format human.",
                details={"hint": "Try: wst backup s3 --configure --format human"},
                exit_code=2,
            )
        provider.configure()
        return

    db = Database(config.db_path)
    try:
        if fmt != "human" and not identifier:
            from wst.output import WstError

            raise WstError(
                "usage_error",
                "Non-interactive backup requires an IDENTIFIER (ID or exact title).",
                details={"hint": "Try: wst backup s3 3 --format json"},
                exit_code=2,
            )

        if identifier:
            if fmt == "human":
                run_backup_file(provider, db, config.library_path, identifier, emit=True)
                return
            if not provider.is_configured():
                from wst.output import WstError

                raise WstError(
                    "requires_interactive",
                    "Backup provider is not configured. "
                    "Run `wst backup s3 --configure` in human mode first.",
                    details={"hint": "Try: wst backup s3 --configure --format human"},
                    exit_code=2,
                )
            run_backup_file(provider, db, config.library_path, identifier, emit=False)
            from wst.output import render_ok

            render_ok({"provider": "s3", "identifier": identifier, "status": "ok"}, fmt=fmt)
        else:
            run_backup_interactive(provider, db, config.library_path)
    finally:
        db.close()


@cli.command()
@command_format_option()
@click.option("--id", "doc_id", type=int, default=None, help="Select document by ID")
@click.option("--title", default=None, help="Select document by exact title")
@click.option(
    "--query",
    default=None,
    help="Search query to select a document (uses full-text search)",
)
@click.option(
    "--select",
    type=int,
    default=None,
    help="When --query returns multiple results, pick N (1-based)",
)
@click.option(
    "--first",
    is_flag=True,
    help="When --query returns multiple results, pick the first match",
)
@click.option(
    "--action",
    type=click.Choice(["view", "open", "find", "edit", "delete"], case_sensitive=False),
    default=None,
    help="Non-interactive action to run on the selected document",
)
@click.option("--set", "set_kv", multiple=True, help="For --action edit: key=value (repeatable)")
@click.option("--yes", "-y", is_flag=True, help="Auto-accept (delete/edit) without prompting")
@click.option("--dry-run", is_flag=True, help="Preview (delete/edit) without making changes")
@click.option(
    "--no-launch",
    is_flag=True,
    help="For open/find: don't launch apps; only output command/path",
)
@click.pass_context
def browse(
    ctx: click.Context,
    doc_id: int | None,
    title: str | None,
    query: str | None,
    select: int | None,
    first: bool,
    action: str | None,
    set_kv: tuple[str, ...],
    yes: bool,
    dry_run: bool,
    no_launch: bool,
) -> None:
    """Browse documents (interactive TUI or non-interactive actions).

    \b
    Interactive mode:
      wst browse

    \b
    Non-interactive mode (scriptable):
      wst browse --id 3 --action view --format json
      wst browse --query "Cosmos" --first --action open --no-launch --format yaml
      wst browse --id 3 --action delete --dry-run --format md
      wst browse --id 3 --action delete -y --format json
      wst browse --id 3 --action edit --set title="New" --dry-run --format json
      wst browse --id 3 --action edit --set title="New" -y --format json
    """
    from wst.browse import BrowseUsageError, browse_library, resolve_entry, run_action

    config: WstConfig = ctx.obj["config"]
    fmt: str = ctx.obj.get("format", "human")
    db = Database(config.db_path)
    storage = LocalStorage(config.library_path)

    try:
        if fmt == "human" and not any(
            [
                doc_id,
                title,
                query,
                action,
                set_kv,
                yes,
                dry_run,
                no_launch,
                select,
                first,
            ]
        ):
            browse_library(db, storage, config.library_path)
            return

        if action is None:
            # Non-interactive selection only is not useful; require an action.
            from wst.output import WstError

            raise WstError(
                "usage_error",
                "Non-interactive browse requires --action plus a selector (--id/--title/--query).",
                details={"hint": "Try: wst browse --id 3 --action view --format json"},
                exit_code=2,
            )

        try:
            entry = resolve_entry(
                db,
                doc_id=doc_id,
                title=title,
                query=query,
                select=select,
                first=first,
            )
        except BrowseUsageError as e:
            if fmt == "human":
                raise click.UsageError(str(e))
            from wst.output import WstError

            raise WstError("usage_error", str(e), exit_code=2)

        set_dict = _parse_set_kv(set_kv) if set_kv else None
        try:
            result = run_action(
                entry,
                action=action,
                db=db,
                storage=storage,
                library_path=config.library_path,
                yes=yes,
                dry_run=dry_run,
                no_launch=no_launch,
                set_kv=set_dict,
            )
        except BrowseUsageError as e:
            if fmt == "human":
                raise click.UsageError(str(e))
            from wst.output import WstError

            raise WstError("usage_error", str(e), exit_code=2)

        if fmt == "human":
            # Keep a minimal human output for non-interactive use
            click.echo(result.get("status") or "ok")
            return

        from wst.output import render_ok

        render_ok(result, fmt=fmt)
    finally:
        db.close()


@cli.command()
@command_format_option()
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
@click.pass_context
def ocr(ctx: click.Context, path: Path, language: str, force: bool, verbose: bool) -> None:
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
        wst ocr scan.pdf --format json  # structured output
    """
    from wst.ocr import ocr_files as run_ocr_batch

    fmt: str = ctx.obj.get("format", "human")

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

    summary = run_ocr_batch(
        files,
        language=language,
        force=force,
        verbose=verbose,
        emit=(fmt == "human"),
        progress=(fmt == "human"),
    )
    if fmt != "human":
        from wst.output import render_ok

        render_ok(summary, fmt=fmt)


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
@command_format_option()
@click.argument("query", default="")
@click.option("--author", "-a", default=None, help="Filter by author")
@click.option("--type", "-t", "doc_type", default=None, help="Filter by document type")
@click.option("--subject", "-s", default=None, help="Filter by subject/knowledge area")
@click.option("--topic", "-p", default=None, help="Filter by topic (partial, case-insensitive)")
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    author: str | None,
    doc_type: str | None,
    subject: str | None,
    topic: str | None,
) -> None:
    """Search documents by title, author, tags, subject, or topic."""
    config: WstConfig = ctx.obj["config"]
    fmt: str = ctx.obj.get("format", "human")
    db = Database(config.db_path)

    try:
        results = db.search(query, doc_type=doc_type, author=author, subject=subject, topic=topic)
        if not results:
            if fmt == "human":
                click.echo("No results found.")
                return
            from wst.output import render_ok

            render_ok([], fmt=fmt)
            return
        if fmt == "human":
            _print_table(results)
            return
        from wst.output import render_ok

        render_ok(results, fmt=fmt)
    finally:
        db.close()


@cli.command(name="list")
@command_format_option()
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
    fmt: str = ctx.obj.get("format", "human")
    db = Database(config.db_path)

    try:
        entries = db.list_all(doc_type=doc_type, sort_by=sort_by)
        if not entries:
            if fmt == "human":
                click.echo("Library is empty.")
                return
            from wst.output import render_ok

            render_ok([], fmt=fmt)
            return
        if fmt == "human":
            _print_table(entries)
            return
        from wst.output import render_ok

        render_ok(entries, fmt=fmt)
    finally:
        db.close()


@cli.command()
@command_format_option()
@click.argument("identifier")
@click.pass_context
def show(ctx: click.Context, identifier: str) -> None:
    """Show full metadata for a document (by ID or title)."""
    config: WstConfig = ctx.obj["config"]
    fmt: str = ctx.obj.get("format", "human")
    db = Database(config.db_path)

    try:
        entry = _find_entry(db, identifier)
        if entry is None:
            if fmt == "human":
                click.echo(f"Document not found: {identifier}")
                raise SystemExit(1)
            from wst.output import WstError

            raise WstError("not_found", f"Document not found: {identifier}", exit_code=1)

        if fmt != "human":
            from wst.output import render_ok

            render_ok(entry, fmt=fmt)
            return

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
        click.echo(f"Topics:        {', '.join(m.topics) if m.topics else 'N/A'}")
        click.echo(f"Summary:       {m.summary or 'N/A'}")
        click.echo(f"TOC:           {m.table_of_contents or 'N/A'}")
        click.echo(f"File:          {entry.file_path}")
        click.echo(f"Original file: {entry.original_filename}")
        click.echo(f"Ingested at:   {entry.ingested_at}")
    finally:
        db.close()


@cli.command()
@command_format_option()
@click.option(
    "--type",
    "-t",
    "doc_type",
    default=None,
    type=click.Choice([dt.value for dt in DocType], case_sensitive=False),
    help="Filter by document type",
)
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
    fmt: str = ctx.obj.get("format", "human")
    db = Database(config.db_path)

    try:
        entries = db.list_all(doc_type=doc_type)
        if not entries:
            if fmt == "human":
                click.echo("Library is empty.")
                return
            from wst.output import render_ok

            render_ok(
                {"total": 0, "coverage_by_field": [], "breakdown_by_type": []},
                fmt=fmt,
            )
            return

        fields = [
            "title",
            "author",
            "year",
            "publisher",
            "isbn",
            "language",
            "subject",
            "summary",
            "table_of_contents",
            "page_count",
        ]

        # Group by doc_type
        by_type: dict[str, list[LibraryEntry]] = {}
        for e in entries:
            dt = e.metadata.doc_type.value
            by_type.setdefault(dt, []).append(e)

        if fmt != "human":
            coverage_by_field = []
            for field in fields:
                filled = sum(1 for e in entries if _field_filled(e, field))
                missing = len(entries) - filled
                pct = (filled / len(entries)) * 100
                coverage_by_field.append(
                    {"field": field, "filled": filled, "missing": missing, "coverage_pct": pct}
                )

            key_fields = ["isbn", "table_of_contents", "year", "publisher", "summary"]
            breakdown_by_type = []
            for dt in sorted(by_type):
                group = by_type[dt]
                total = len(group)
                per = {}
                for f in key_fields:
                    n = sum(1 for e in group if _field_filled(e, f))
                    per[f] = (n / total) * 100 if total else 0.0
                breakdown_by_type.append({"type": dt, "total": total, **per})

            from wst.output import render_ok

            render_ok(
                {
                    "total": len(entries),
                    "coverage_by_field": coverage_by_field,
                    "breakdown_by_type": breakdown_by_type,
                },
                fmt=fmt,
            )
            return

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
@command_format_option()
@click.argument("identifier")
@click.option(
    "--enrich",
    is_flag=True,
    help="Use AI to fill missing fields (ISBN, publisher, etc.)",
)
@click.option(
    "--set",
    "set_kv",
    multiple=True,
    help=(
        "Non-interactive update in key=value form (repeatable). "
        'Example: --set title="New" --set year=2024'
    ),
)
@click.option("--yes", "-y", is_flag=True, help="Auto-accept changes without prompting")
@click.option(
    "--move/--no-move",
    default=True,
    help="When metadata changes the destination path, move the file (default: move)",
)
@click.pass_context
def edit(
    ctx: click.Context,
    identifier: str,
    enrich: bool,
    set_kv: tuple[str, ...],
    yes: bool,
    move: bool,
) -> None:
    """Edit metadata for a document (interactive or non-interactive).

    \b
    Shows current values and lets you change any field.
    Press Enter to keep the current value. If the document type
    changes, the file is moved to the correct folder.

    \b
    Use --enrich to automatically fill missing fields (ISBN,
    publisher, year) using AI and web search.

    \b
    Non-interactive mode:
      - Use --set key=value (repeatable) and -y to apply.
      - Without -y, the command performs a dry-run (no changes).

    \b
    Examples:
        wst edit 1
        wst edit "Player's Handbook"
        wst edit 42 --enrich
        wst edit 42 --enrich -y --format json
        wst edit 42 --set title="New title" --dry-run --format yaml
        wst edit 42 --set title="New title" -y --format json
    """
    config: WstConfig = ctx.obj["config"]
    fmt: str = ctx.obj.get("format", "human")
    db = Database(config.db_path)
    storage = LocalStorage(config.library_path)

    try:
        entry = _find_entry(db, identifier)
        if entry is None:
            if fmt == "human":
                click.echo(f"Document not found: {identifier}")
                raise SystemExit(1)
            from wst.output import WstError

            raise WstError("not_found", f"Document not found: {identifier}", exit_code=1)

        m = entry.metadata

        if enrich:
            if fmt != "human" and not yes:
                from wst.output import WstError

                raise WstError(
                    "usage_error",
                    "Non-interactive enrich requires --yes (or use --format human).",
                    details={"hint": "Try: wst edit <id> --enrich -y --format json"},
                    exit_code=2,
                )
            _enrich_entry(entry, config, db, confirm=(fmt == "human" and not yes))
            if fmt != "human":
                from wst.output import render_ok

                render_ok(entry, fmt=fmt)
            return

        if set_kv:
            updates = _parse_set_kv(set_kv)
            updated_entry, changes = _apply_metadata_updates(
                entry,
                updates,
                config=config,
                db=db,
                storage=storage,
                move=move,
                dry_run=not yes,
                emit=(fmt == "human"),
            )
            if fmt == "human":
                if not yes:
                    click.echo("\nDry-run complete (use -y to apply).")
                return
            from wst.output import render_ok

            render_ok(
                {
                    "applied": bool(yes),
                    "changes": changes,
                    "entry": updated_entry,
                },
                fmt=fmt,
            )
            return

        if fmt != "human":
            from wst.output import WstError

            raise WstError(
                "usage_error",
                (
                    "This command is interactive by default. "
                    "Use --set key=value (and -y) for non-interactive mode."
                ),
                details={"hint": 'Try: wst edit 1 --set title="..." -y --format json'},
                exit_code=2,
            )

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
    entry: LibraryEntry,
    config: WstConfig,
    db: Database,
    *,
    confirm: bool = True,
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

    if confirm:
        if not click.confirm("\n  Apply these changes?", default=True):
            click.echo("  Skipped.")
            return

    entry.metadata = enriched
    db.update(entry)
    click.echo("  Updated successfully.")


def _parse_set_kv(items: tuple[str, ...]) -> dict[str, str]:
    updates: dict[str, str] = {}
    for raw in items:
        if "=" not in raw:
            raise click.UsageError(f"Invalid --set value (expected key=value): {raw}")
        k, v = raw.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            raise click.UsageError(f"Invalid --set key: {raw}")
        updates[k] = v
    return updates


def _apply_metadata_updates(
    entry: LibraryEntry,
    updates: dict[str, str],
    *,
    config: WstConfig,
    db: Database,
    storage: LocalStorage,
    move: bool,
    dry_run: bool,
    emit: bool,
) -> tuple[LibraryEntry, list[dict[str, object]]]:
    m = entry.metadata
    before = m.model_dump()

    for k, v in updates.items():
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
            case "topics":
                m.topics = [t.strip() for t in v.split(",") if t.strip()] if v else []
            case _:
                raise click.UsageError(f"Unknown metadata field for --set: {k}")

    changes: list[dict[str, object]] = []
    after = m.model_dump()
    for k in sorted(after.keys()):
        if after[k] != before.get(k):
            changes.append({"field": k, "before": before.get(k), "after": after[k]})

    new_dest = build_dest_path(m)
    old_path = entry.file_path

    if move and new_dest != old_path:
        old_full = config.library_path / old_path
        if old_full.exists():
            if not dry_run:
                final = storage.store(old_full, new_dest)
                old_full.unlink()
                entry.file_path = final
                entry.filename = Path(final).name
            if emit:
                click.echo(f"\nMoved: {old_path} -> {new_dest}")
        else:
            if not dry_run:
                entry.file_path = new_dest
                entry.filename = Path(new_dest).name
            if emit:
                click.echo(f"\nWarning: old file not found at {old_path}, updated path in DB only.")

    if not dry_run:
        db.update(entry)

    return entry, changes


def _get_missing_fields(m) -> list[str]:
    return [k for k, v in m.model_dump().items() if v is None]


def _run_enrich(entry: LibraryEntry, config: WstConfig) -> tuple[list[tuple[str, object]], object]:
    """Run AI enrichment. Returns (changes, enriched_metadata)."""
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
@command_format_option()
@click.option(
    "--type",
    "doc_type",
    type=click.Choice([dt.value for dt in DocType], case_sensitive=False),
    help="Only fix documents of this type",
)
@click.option(
    "--field",
    multiple=True,
    help="Only fix documents missing this field (e.g. --field isbn --field toc)",
)
@click.option(
    "--topics",
    "fix_topics",
    is_flag=True,
    help="Assign topics (from existing vocabulary) to documents that have none",
)
@click.option("--yes", "-y", is_flag=True, help="Auto-accept all changes without prompting")
@click.option("--dry-run", is_flag=True, help="Show what would be enriched without making changes")
@click.pass_context
def fix(
    ctx: click.Context,
    doc_type: str | None,
    field: tuple[str, ...],
    fix_topics: bool,
    yes: bool,
    dry_run: bool,
) -> None:
    """Enrich all documents that have missing metadata fields.

    \b
    Scans the library for documents with missing fields (ISBN, publisher,
    year, table_of_contents, etc.) and uses AI + web search to fill them.

    \b
    Examples:
        wst fix                         # fix all documents with missing fields
        wst fix --type book             # only books
        wst fix --field isbn            # only those missing ISBN
        wst fix --field isbn --field toc
        wst fix --topics                # assign topics to docs without topics
        wst fix --dry-run               # preview what needs fixing
        wst fix -y                      # fix all docs, auto-accept
        wst fix --dry-run --format json # preview as structured output
        wst fix -y --format yaml        # run non-interactively
    """
    field_map = {"toc": "table_of_contents"}
    target_fields = [field_map.get(f, f) for f in field] if field else None

    config: WstConfig = ctx.obj["config"]
    fmt: str = ctx.obj.get("format", "human")
    db = Database(config.db_path)

    try:
        # --topics shortcut: assign topics to docs that have none
        if fix_topics:
            _fix_topics_cmd(db, config, fmt=fmt, yes=yes, dry_run=dry_run, doc_type=doc_type)
            return

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
            if fmt == "human":
                click.echo("All documents are complete. Nothing to fix.")
                return
            from wst.output import render_ok

            render_ok(
                {
                    "scanned": len(entries),
                    "to_fix": 0,
                    "fixed": 0,
                    "skipped": 0,
                    "failed": 0,
                    "results": [],
                },
                fmt=fmt,
            )
            return

        if fmt != "human" and not dry_run and not yes:
            from wst.output import WstError

            raise WstError(
                "usage_error",
                "Non-interactive fix requires -y/--yes (or use --dry-run).",
                details={"hint": "Try: wst fix -y --format json"},
                exit_code=2,
            )

        if fmt == "human":
            click.echo(f"Found {len(to_fix)} document(s) with missing fields.\n")

        if dry_run:
            preview = []
            for entry, missing in to_fix:
                m = entry.metadata
                preview.append(
                    {
                        "id": entry.id,
                        "title": m.title,
                        "type": m.doc_type.value,
                        "missing_fields": missing,
                    }
                )
            if fmt == "human":
                click.echo(f"{'ID':>4}  {'Title':<40}  {'Type':<12}  Missing fields")
                click.echo("-" * 90)
                for entry, missing in to_fix:
                    m = entry.metadata
                    title = m.title[:38] + ".." if len(m.title) > 40 else m.title
                    click.echo(
                        f"{entry.id:>4}  {title:<40}  {m.doc_type.value:<12}  {', '.join(missing)}"
                    )
                return
            from wst.output import render_ok

            render_ok(
                {
                    "scanned": len(entries),
                    "to_fix": len(to_fix),
                    "preview": preview,
                },
                fmt=fmt,
            )
            return

        fixed = 0
        failed = 0
        skipped = 0
        start = time.monotonic()
        results = []

        for i, (entry, missing) in enumerate(to_fix, 1):
            m = entry.metadata
            if fmt == "human":
                click.echo(f"\n[{i}/{len(to_fix)}] {m.title} (ID {entry.id})")
                click.echo(f"  Missing: {', '.join(missing)}")

            try:
                changes, enriched = _run_enrich(entry, config)
            except Exception as e:
                if fmt == "human":
                    click.echo(f"  Error: {e}")
                failed += 1
                results.append(
                    {
                        "id": entry.id,
                        "status": "failed",
                        "error": str(e),
                    }
                )
                continue

            if not changes:
                if fmt == "human":
                    click.echo("  No new information found.")
                skipped += 1
                results.append({"id": entry.id, "status": "skipped", "changes": []})
                continue

            if fmt == "human":
                click.echo("  Found:")
                for f_name, value in changes:
                    display = value if not isinstance(value, list) else ", ".join(value)
                    # Truncate long values like TOC for display
                    if isinstance(display, str) and len(display) > 80:
                        display = display[:77] + "..."
                    click.echo(f"    {f_name}: {display}")

            if fmt == "human" and not yes:
                if not click.confirm("  Apply?", default=True):
                    skipped += 1
                    results.append({"id": entry.id, "status": "skipped", "changes": changes})
                    continue

            entry.metadata = enriched
            db.update(entry)
            fixed += 1
            results.append({"id": entry.id, "status": "fixed", "changes": changes})
            if fmt == "human":
                click.echo("  Updated.")

        elapsed = time.monotonic() - start
        if fmt == "human":
            click.echo(
                f"\nDone in {int(elapsed)}s: {fixed} fixed, {skipped} skipped, {failed} failed"
            )
            return

        from wst.output import render_ok

        render_ok(
            {
                "scanned": len(entries),
                "to_fix": len(to_fix),
                "fixed": fixed,
                "skipped": skipped,
                "failed": failed,
                "elapsed_seconds": elapsed,
                "results": results,
            },
            fmt=fmt,
        )
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


# ---------------------------------------------------------------------------
# Topics group
# ---------------------------------------------------------------------------


@cli.group()
@command_format_option()
@click.pass_context
def topics(ctx: click.Context) -> None:
    """Manage high-level topic vocabulary and document assignments.

    \b
    Commands:
      build   Generate vocabulary from corpus and assign to all documents.
      list    Show the current topic vocabulary.
      assign  (Re)assign topics to one or all documents.
    """


@topics.command("build")
@command_format_option()
@click.option(
    "--n-topics",
    "n_topics",
    type=int,
    default=None,
    help="Number of topics to generate (default: auto-detect via silhouette score)",
)
@click.option("--yes", "-y", is_flag=True, help="Overwrite existing vocabulary without prompting")
@click.pass_context
def topics_build(ctx: click.Context, n_topics: int | None, yes: bool) -> None:
    """Generate topic vocabulary from the corpus and assign to all documents.

    \b
    Steps:
      1. Embed all documents with a multilingual sentence-transformer.
      2. Cluster with KMeans (auto-detect optimal k or use --n-topics).
      3. Name each cluster via AI.
      4. Assign 1-3 topics to every document.
      5. Save vocabulary to the database.

    \b
    Examples:
        wst topics build
        wst topics build --n-topics 12
        wst topics build -y --format json
    """
    config: WstConfig = ctx.obj["config"]
    fmt: str = ctx.obj.get("format", "human")
    db = Database(config.db_path)

    try:
        from wst.topics import assign_topics, build_vocabulary, save_vocabulary

        # Check for existing vocabulary
        existing = db.load_topics_vocabulary()
        if existing and not yes:
            if fmt != "human":
                from wst.output import WstError

                raise WstError(
                    "usage_error",
                    "Vocabulary already exists. Use -y/--yes to overwrite.",
                    details={"hint": "Try: wst topics build -y --format json"},
                    exit_code=2,
                )
            if not click.confirm(
                f"Vocabulary already exists ({len(existing)} topics). Overwrite?", default=False
            ):
                click.echo("Aborted.")
                return

        ai = get_ai_backend(config.ai_backend, config.ai_model)

        if fmt == "human":
            click.echo("Step 1/3  Embedding documents and clustering...")
        vocabulary = build_vocabulary(db, ai, n_topics=n_topics)

        if not vocabulary:
            if fmt == "human":
                click.echo("Library is empty — nothing to build.")
                return
            from wst.output import render_ok

            render_ok({"vocabulary": [], "assignments": {}}, fmt=fmt)
            return

        if fmt == "human":
            click.echo(f"          Generated {len(vocabulary)} topics: {', '.join(vocabulary)}")
            click.echo("Step 2/3  Assigning topics to documents...")

        assignments = assign_topics(db, ai, vocabulary)

        if fmt == "human":
            click.echo("Step 3/3  Saving to database...")

        save_vocabulary(db, vocabulary)

        # Persist assignments
        entries = db.list_all()
        entry_map = {e.id: e for e in entries}
        for doc_id, assigned in assignments.items():
            entry = entry_map.get(doc_id)
            if entry is None:
                continue
            entry.metadata.topics = assigned
            db.update(entry)

        if fmt == "human":
            click.echo(f"\nDone. {len(assignments)} document(s) assigned topics.")
            click.echo(f"Vocabulary ({len(vocabulary)}): {', '.join(vocabulary)}")
            return

        from wst.output import render_ok

        render_ok(
            {
                "vocabulary": vocabulary,
                "assigned_count": len(assignments),
                "assignments": {str(k): v for k, v in assignments.items()},
            },
            fmt=fmt,
        )
    finally:
        db.close()


@topics.command("list")
@command_format_option()
@click.pass_context
def topics_list(ctx: click.Context) -> None:
    """Show the current topic vocabulary.

    \b
    Examples:
        wst topics list
        wst topics list --format json
    """
    config: WstConfig = ctx.obj["config"]
    fmt: str = ctx.obj.get("format", "human")
    db = Database(config.db_path)

    try:
        vocabulary = db.load_topics_vocabulary()
        if not vocabulary:
            if fmt == "human":
                click.echo("No topic vocabulary found. Run `wst topics build` first.")
                return
            from wst.output import render_ok

            render_ok({"vocabulary": []}, fmt=fmt)
            return

        if fmt == "human":
            click.echo(f"Topic vocabulary ({len(vocabulary)} topics):")
            for i, t in enumerate(vocabulary, 1):
                click.echo(f"  {i:>3}. {t}")
            return

        from wst.output import render_ok

        render_ok({"vocabulary": vocabulary}, fmt=fmt)
    finally:
        db.close()


@topics.command("assign")
@command_format_option()
@click.option("--id", "doc_id", type=int, default=None, help="Assign topics to a single document")
@click.option("--yes", "-y", is_flag=True, help="Apply without prompting")
@click.pass_context
def topics_assign(ctx: click.Context, doc_id: int | None, yes: bool) -> None:
    """(Re)assign topics to a specific document or all documents.

    \b
    Requires a vocabulary already built with `wst topics build`.

    \b
    Examples:
        wst topics assign --id 3
        wst topics assign           # reassign all documents
        wst topics assign -y --format json
    """
    config: WstConfig = ctx.obj["config"]
    fmt: str = ctx.obj.get("format", "human")
    db = Database(config.db_path)

    try:
        from wst.topics import assign_topics

        vocabulary = db.load_topics_vocabulary()
        if not vocabulary:
            if fmt == "human":
                click.echo("No vocabulary found. Run `wst topics build` first.")
                raise SystemExit(1)
            from wst.output import WstError

            raise WstError(
                "not_found",
                "No topic vocabulary found. Run `wst topics build` first.",
                exit_code=1,
            )

        ai = get_ai_backend(config.ai_backend, config.ai_model)

        if doc_id is not None:
            entry = db.get(doc_id)
            if entry is None:
                if fmt == "human":
                    click.echo(f"Document {doc_id} not found.")
                    raise SystemExit(1)
                from wst.output import WstError

                raise WstError("not_found", f"Document {doc_id} not found.", exit_code=1)
            entries_to_assign = [entry]
        else:
            entries_to_assign = db.list_all()

        if fmt == "human" and not yes and not doc_id:
            if not click.confirm(
                f"Reassign topics for all {len(entries_to_assign)} document(s)?", default=True
            ):
                click.echo("Aborted.")
                return

        assignments = assign_topics(db, ai, vocabulary)

        entry_map = {e.id: e for e in entries_to_assign}
        updated = 0
        for eid, assigned_topics in assignments.items():
            entry = entry_map.get(eid)
            if entry is None:
                continue
            entry.metadata.topics = assigned_topics
            db.update(entry)
            updated += 1

        if fmt == "human":
            click.echo(f"Assigned topics to {updated} document(s).")
            return

        from wst.output import render_ok

        render_ok(
            {
                "updated": updated,
                "assignments": {str(k): v for k, v in assignments.items()},
            },
            fmt=fmt,
        )
    finally:
        db.close()


def _fix_topics_cmd(
    db: Database,
    config: WstConfig,
    *,
    fmt: str,
    yes: bool,
    dry_run: bool,
    doc_type: str | None,
) -> None:
    """Assign topics (from existing vocabulary) to documents that have none."""
    from wst.topics import assign_topics

    vocabulary = db.load_topics_vocabulary()
    if not vocabulary:
        if fmt == "human":
            click.echo("No vocabulary found. Run `wst topics build` first.")
            raise SystemExit(1)
        from wst.output import WstError

        raise WstError(
            "not_found",
            "No topic vocabulary found. Run `wst topics build` first.",
            exit_code=1,
        )

    entries = db.list_all(doc_type=doc_type)
    without_topics = [e for e in entries if not e.metadata.topics]

    if not without_topics:
        if fmt == "human":
            click.echo("All documents already have topics assigned.")
            return
        from wst.output import render_ok

        render_ok({"scanned": len(entries), "updated": 0}, fmt=fmt)
        return

    if fmt == "human":
        click.echo(f"Found {len(without_topics)} document(s) without topics.")

    if dry_run:
        preview = [{"id": e.id, "title": e.metadata.title} for e in without_topics]
        if fmt == "human":
            for item in preview:
                click.echo(f"  [{item['id']}] {item['title']}")
            return
        from wst.output import render_ok

        render_ok({"scanned": len(entries), "to_assign": len(without_topics), "preview": preview},
                  fmt=fmt)
        return

    if fmt != "human" and not yes:
        from wst.output import WstError

        raise WstError(
            "usage_error",
            "Non-interactive --topics fix requires -y/--yes (or use --dry-run).",
            details={"hint": "Try: wst fix --topics -y --format json"},
            exit_code=2,
        )

    ai = get_ai_backend(config.ai_backend, config.ai_model)
    assignments = assign_topics(db, ai, vocabulary)

    entry_map = {e.id: e for e in without_topics}
    updated = 0
    for doc_id, assigned_topics in assignments.items():
        entry = entry_map.get(doc_id)
        if entry is None:
            continue
        entry.metadata.topics = assigned_topics
        db.update(entry)
        updated += 1

    if fmt == "human":
        click.echo(f"Assigned topics to {updated} document(s).")
        return

    from wst.output import render_ok

    render_ok({"scanned": len(entries), "updated": updated}, fmt=fmt)
