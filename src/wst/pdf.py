from pathlib import Path

import fitz


def extract_pdf_info(path: Path, max_pages: int = 5) -> tuple[dict, str, int]:
    """Extract existing metadata, text from first N pages, and total page count.

    Returns (metadata_dict, text_sample, page_count).
    """
    doc = fitz.open(str(path))
    try:
        meta = doc.metadata or {}
        page_count = len(doc)
        pages_to_read = min(max_pages, page_count)
        text_parts = []
        for i in range(pages_to_read):
            text_parts.append(doc[i].get_text())
        text_sample = "\n".join(text_parts)
        return meta, text_sample, page_count
    finally:
        doc.close()


def write_pdf_metadata(path: Path, title: str, author: str, subject: str | None = None) -> None:
    """Write basic metadata fields into the PDF."""
    doc = fitz.open(str(path))
    try:
        meta = doc.metadata or {}
        meta["title"] = title
        meta["author"] = author
        if subject:
            meta["subject"] = subject
        doc.set_metadata(meta)
        doc.saveIncr()
    finally:
        doc.close()
