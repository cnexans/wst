import shutil
import subprocess
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


def check_ocrmypdf() -> str | None:
    """Check if ocrmypdf is available. Returns path or None."""
    path = shutil.which("ocrmypdf")
    if path:
        return path
    # Common pipx location
    pipx_path = Path.home() / ".local" / "bin" / "ocrmypdf"
    if pipx_path.exists():
        return str(pipx_path)
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
    if path.suffix.lower() != ".pdf":
        return OcrResult(path.name, "skipped", "not a PDF")

    if not force and not needs_ocr(path):
        return OcrResult(path.name, "skipped", "already has text")

    ocrmypdf_bin = check_ocrmypdf()
    if not ocrmypdf_bin:
        return OcrResult(path.name, "failed", "ocrmypdf not installed")

    in_place = output is None
    if in_place:
        output = path.with_name(path.stem + "_ocr_tmp" + path.suffix)

    cmd = [
        ocrmypdf_bin,
        "-l",
        language,
        "--force-ocr",
        "--output-type",
        "pdf",
        str(path),
        str(output),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            # Clean up failed output
            if output.exists():
                output.unlink()
            stderr = result.stderr.strip().split("\n")[-1] if result.stderr else "unknown error"
            return OcrResult(path.name, "failed", stderr)

        if in_place:
            output.replace(path)

        return OcrResult(path.name, "processed")
    except subprocess.TimeoutExpired:
        if output.exists():
            output.unlink()
        return OcrResult(path.name, "failed", "timeout (>10 min)")
    except Exception as e:
        if output.exists():
            output.unlink()
        return OcrResult(path.name, "failed", str(e))


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

    ocrmypdf_bin = check_ocrmypdf()
    if not ocrmypdf_bin:
        click.echo(
            "Error: ocrmypdf is not installed.\n"
            "Install it with: pipx install ocrmypdf\n"
            "Also install language packs: brew install tesseract-lang"
        )
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
