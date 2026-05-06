import re
from pathlib import Path

import fitz

SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".djvu"}

# RFC 0011 — content_preview ladder
DEFAULT_PREVIEW_TARGET = 600
DEFAULT_PREVIEW_MAX = 1500

# Front-matter TOC entries that don't carry topical signal — skip when picking
# the introductory chapter (Q4: prefer TOC page indices over the regex fallback).
_FRONT_MATTER_RE = re.compile(
    r"^("
    r"cover|portada"
    r"|copyright|cr[eé]ditos|credits"
    r"|acknowledg(?:e?ments?)?|agradecimientos"
    r"|dedicat(?:ion|oria)?"
    r"|table\s+of\s+contents|contents"
    r"|[íi]ndice|sumario"
    r"|list\s+of\s+(?:figures|tables|illustrations)"
    r"|frontispiece|half[-\s]?title|title\s+page|t[íi]tulo"
    r"|colophon|colof[óo]n"
    r")\s*$",
    re.IGNORECASE,
)

# Regex fallback (Q4): when TOC has no usable page indices, look for an
# introductory heading in the first-pages text and slice from there.
_INTRO_HEADING_RE = re.compile(
    r"^\s*(introducci[óo]n|introduction|prefacio|preface|pr[óo]logo|"
    r"cap[íi]tulo\s+1|chapter\s+1)\b",
    re.IGNORECASE | re.MULTILINE,
)


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def extract_doc_info(path: Path, max_pages: int = 5) -> tuple[dict, str, int]:
    """Extract existing metadata, text from first N pages, and total page count.

    Returns (metadata_dict, text_sample, page_count).
    Supports PDF, EPUB, and DJVU formats via PyMuPDF.
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


def build_content_preview(
    path: Path,
    summary: str | None,
    title: str | None = None,
    tags: list[str] | None = None,
    *,
    target_chars: int = DEFAULT_PREVIEW_TARGET,
    max_chars: int = DEFAULT_PREVIEW_MAX,
) -> tuple[str | None, str]:
    """Pick a content preview using a deterministic ladder (RFC 0011).

    Returns ``(preview, source)`` where ``source`` is one of:
    ``summary``, ``toc``, ``intro``, ``first-pages``, ``title-only``, ``none``.

    The ladder picks the first source that yields ≥ ``target_chars``. The
    chosen text is truncated to ``max_chars`` so very long TOCs don't dominate
    the topic embedding.
    """
    if summary and len(summary) >= target_chars:
        return summary[:max_chars], "summary"

    try:
        doc = fitz.open(str(path))
    except Exception:
        return _title_only_fallback(title, tags, max_chars)

    try:
        page_count = len(doc)

        toc = doc.get_toc() or []
        toc_text = _flatten_toc(toc)
        if len(toc_text) >= target_chars:
            return toc_text[:max_chars], "toc"

        intro_text = _extract_intro_via_toc(doc, toc, page_count, max_chars)
        if intro_text and len(intro_text) >= target_chars:
            return intro_text[:max_chars], "intro"

        first_pages_text = _extract_first_pages(doc, max_pages=5).strip()
        if first_pages_text:
            intro_via_regex = _intro_via_regex(first_pages_text)
            if intro_via_regex and len(intro_via_regex) >= target_chars:
                return intro_via_regex[:max_chars], "intro"
            if len(first_pages_text) >= target_chars:
                return first_pages_text[:max_chars], "first-pages"

        return _title_only_fallback(title, tags, max_chars)
    finally:
        doc.close()


def _title_only_fallback(
    title: str | None, tags: list[str] | None, max_chars: int
) -> tuple[str | None, str]:
    parts = []
    if title:
        parts.append(title)
    if tags:
        parts.append(", ".join(tags))
    text = " | ".join(p for p in parts if p).strip()
    if not text:
        return None, "none"
    return text[:max_chars], "title-only"


def _flatten_toc(toc: list) -> str:
    lines: list[str] = []
    for entry in toc:
        if not entry or len(entry) < 2:
            continue
        level = entry[0] if isinstance(entry[0], int) else 1
        title = entry[1]
        if not isinstance(title, str):
            continue
        title = title.strip()
        if not title:
            continue
        indent = "  " * max(0, level - 1)
        lines.append(f"{indent}{title}")
    return "\n".join(lines)


def _extract_intro_via_toc(
    doc, toc: list, page_count: int, max_chars: int, *, max_pages: int = 10
) -> str | None:
    """Locate the first non-front-matter TOC entry and return its page-range text.

    Returns None when the TOC has no usable page indices (caller falls back to
    the regex match per Q4).
    """
    if not toc:
        return None

    candidates = [
        e
        for e in toc
        if isinstance(e, list | tuple)
        and len(e) >= 3
        and e[0] == 1
        and isinstance(e[2], int)
        and e[2] >= 1
    ]
    if not candidates:
        candidates = [
            e
            for e in toc
            if isinstance(e, list | tuple) and len(e) >= 3 and isinstance(e[2], int) and e[2] >= 1
        ]
    if not candidates:
        return None

    body_idx: int | None = None
    for i, entry in enumerate(candidates):
        title = (entry[1] or "").strip()
        if title and not _FRONT_MATTER_RE.match(title):
            body_idx = i
            break
    if body_idx is None:
        return None

    start_page = max(0, candidates[body_idx][2] - 1)
    if body_idx + 1 < len(candidates):
        end_page = candidates[body_idx + 1][2] - 1
    else:
        end_page = page_count
    end_page = min(end_page, start_page + max_pages, page_count)
    if end_page <= start_page:
        end_page = min(start_page + 1, page_count)

    parts: list[str] = []
    total = 0
    for p in range(start_page, end_page):
        try:
            text = doc[p].get_text()
        except Exception:
            continue
        if not text:
            continue
        parts.append(text)
        total += len(text)
        if total >= max_chars:
            break
    joined = "\n".join(parts).strip()
    return joined or None


def _extract_first_pages(doc, max_pages: int = 5) -> str:
    parts: list[str] = []
    page_count = len(doc)
    for i in range(min(max_pages, page_count)):
        try:
            parts.append(doc[i].get_text())
        except Exception:
            continue
    return "\n".join(parts)


def _intro_via_regex(text: str) -> str | None:
    match = _INTRO_HEADING_RE.search(text)
    if not match:
        return None
    return text[match.start() :]


def write_doc_metadata(path: Path, title: str, author: str, subject: str | None = None) -> None:
    """Write basic metadata fields into the document (PDF only)."""
    if path.suffix.lower() != ".pdf":
        return
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
