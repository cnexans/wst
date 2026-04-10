import platform
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import click
import fitz


@dataclass
class OcrResult:
    filename: str
    status: str  # "processed", "skipped", "failed"
    reason: str = ""


def _check_ocr_dependencies() -> str | None:
    """Check OCR dependencies. Returns error message or None if all OK."""
    try:
        import ocrmypdf  # noqa: F401
    except ImportError:
        return "OCR requires the 'ocr' extra. Install it with:\n\n  pip install wst-library[ocr]\n"

    if not shutil.which("tesseract"):
        system = platform.system()
        if system == "Darwin":
            instructions = (
                "Tesseract OCR is not installed. Install it with:\n"
                "\n"
                "  brew install tesseract tesseract-lang\n"
            )
        elif system == "Linux":
            instructions = (
                "Tesseract OCR is not installed. Install it with:\n"
                "\n"
                "  # Debian/Ubuntu\n"
                "  sudo apt install tesseract-ocr tesseract-ocr-spa\n"
                "\n"
                "  # Fedora\n"
                "  sudo dnf install tesseract tesseract-langpack-spa\n"
            )
        else:
            instructions = (
                "Tesseract OCR is not installed.\n"
                "Download from: https://github.com/tesseract-ocr/tesseract\n"
            )
        return instructions

    return None


def needs_ocr(path: Path, threshold: int = 100) -> bool:
    """Check if a PDF needs OCR by counting extractable words.

    Returns True if the PDF has fewer words than the threshold,
    indicating it's likely a scanned/image-only PDF.
    """
    if path.suffix.lower() != ".pdf":
        return False
    try:
        doc = fitz.open(str(path))
        try:
            word_count = 0
            pages_to_check = min(5, len(doc))
            for i in range(pages_to_check):
                word_count += len(doc[i].get_text().split())
            return word_count < threshold
        finally:
            doc.close()
    except Exception:
        return False


def run_ocr(
    path: Path,
    output: Path | None = None,
    language: str = "spa",
    force: bool = False,
) -> OcrResult:
    """Run OCR on a single PDF file.

    If output is None, replaces the file in-place.
    Returns an OcrResult.
    """
    import ocrmypdf

    if path.suffix.lower() != ".pdf":
        return OcrResult(path.name, "skipped", "not a PDF")

    if not force and not needs_ocr(path):
        return OcrResult(path.name, "skipped", "already has text")

    in_place = output is None
    if in_place:
        output = path.with_name(path.stem + "_ocr_tmp" + path.suffix)

    try:
        ocrmypdf.ocr(
            input_file=path,
            output_file=output,
            language=language,
            force_ocr=True,
            output_type="pdf",
            progress_bar=False,
        )

        if in_place:
            output.replace(path)

        return OcrResult(path.name, "processed")
    except ocrmypdf.exceptions.MissingDependencyError as e:
        if output.exists():
            output.unlink()
        return OcrResult(path.name, "failed", str(e))
    except Exception as e:
        if output.exists():
            output.unlink()
        msg = str(e).strip().split("\n")[-1] if str(e) else "unknown error"
        return OcrResult(path.name, "failed", msg)


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


def require_ocr_dependencies() -> bool:
    """Check OCR dependencies and print instructions if missing.

    Returns True if all dependencies are available, False otherwise.
    """
    error = _check_ocr_dependencies()
    if error:
        click.echo(f"Error: {error}", err=True)
        return False
    return True


def ocr_files(
    files: list[Path],
    language: str = "spa",
    force: bool = False,
    verbose: bool = False,
) -> list[OcrResult]:
    """Run OCR on a list of PDF files with progress display."""
    if not files:
        click.echo("No PDF files found.")
        return []

    if not require_ocr_dependencies():
        return []

    total = len(files)
    click.echo(f"Found {total} PDF(s) to process (language: {language})")

    results: list[OcrResult] = []
    start_time = time.monotonic()

    for i, pdf_path in enumerate(files):
        elapsed = time.monotonic() - start_time

        if not verbose:
            _show_progress(i, total, pdf_path.name, elapsed)

        if verbose:
            click.echo(f"\nProcessing: {pdf_path.name}")

        result = run_ocr(pdf_path, language=language, force=force)
        results.append(result)

        if verbose:
            if result.status == "processed":
                click.echo(f"  OCR complete: {pdf_path.name}")
            elif result.status == "skipped":
                click.echo(f"  Skipped: {result.reason}")
            else:
                click.echo(f"  Failed: {result.reason}")

    if not verbose:
        _clear_line()

    # Summary
    processed = [r for r in results if r.status == "processed"]
    skipped = [r for r in results if r.status == "skipped"]
    failed = [r for r in results if r.status == "failed"]

    elapsed = time.monotonic() - start_time
    eta = _format_eta(elapsed)
    click.echo(
        f"\nOCR done in {eta}: "
        f"{len(processed)} processed, {len(skipped)} skipped, "
        f"{len(failed)} failed"
    )

    if failed:
        click.echo("\nFailed:")
        for r in failed:
            click.echo(f"  - {r.filename}: {r.reason}")

    return results
