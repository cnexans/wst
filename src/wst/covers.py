"""Book cover fetching and caching for wst library."""

import urllib.request
from pathlib import Path

import fitz

COVERS_DIR_NAME = ".covers"
OPENLIBRARY_URL = "https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"
MIN_COVER_SIZE = 100


def get_covers_dir(library_path: Path) -> Path:
    covers_dir = library_path / COVERS_DIR_NAME
    covers_dir.mkdir(exist_ok=True)
    return covers_dir


def get_cached_cover(library_path: Path, doc_id: int) -> Path | None:
    covers_dir = get_covers_dir(library_path)
    for ext in ("jpg", "png"):
        path = covers_dir / f"{doc_id}.{ext}"
        if path.exists():
            return path
    return None


def fetch_cover_by_isbn(isbn: str) -> bytes | None:
    clean_isbn = isbn.replace("-", "")
    url = OPENLIBRARY_URL.format(isbn=clean_isbn)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wst-library/0.6.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            if len(data) > MIN_COVER_SIZE:
                return data
    except Exception:
        pass
    return None


def render_pdf_first_page(pdf_path: Path, width: int = 300) -> bytes | None:
    try:
        doc = fitz.open(str(pdf_path))
        page = doc[0]
        zoom = width / page.rect.width
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        data = pix.tobytes("jpeg")
        doc.close()
        return data
    except Exception:
        return None


def ensure_cover(library_path: Path, doc_id: int, isbn: str | None, file_path: str) -> Path | None:
    cached = get_cached_cover(library_path, doc_id)
    if cached:
        return cached

    covers_dir = get_covers_dir(library_path)
    cover_path = covers_dir / f"{doc_id}.jpg"

    if isbn:
        data = fetch_cover_by_isbn(isbn)
        if data:
            cover_path.write_bytes(data)
            return cover_path

    pdf_path = library_path / file_path
    if pdf_path.exists():
        data = render_pdf_first_page(pdf_path)
        if data:
            cover_path.write_bytes(data)
            return cover_path

    return None
