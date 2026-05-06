"""Tests for the content_preview ladder (RFC 0011)."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from wst.db import Database
from wst.document import build_content_preview
from wst.models import DocType, DocumentMetadata, LibraryEntry
from wst.storage import build_dest_path
from wst.topics import backfill_content_previews


def _make_pdf(
    path: Path,
    bodies: list[str],
    toc: list[list] | None = None,
) -> None:
    doc = fitz.open()
    for body in bodies:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(50, 50, 550, 750), body, fontsize=10)
    if toc:
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()


_LONG = (
    "This is meaningful body text about the topic of linear algebra. "
    "Vector spaces, matrices, eigenvalues and quadratic forms are all "
    "core concepts. "
) * 10


class TestBuildContentPreview:
    def test_summary_step_when_long_enough(self, tmp_path):
        path = tmp_path / "doc.pdf"
        _make_pdf(path, ["body text"])
        summary = "x" * 800
        preview, source = build_content_preview(path, summary, title="T")
        assert source == "summary"
        assert preview == summary[:1500]

    def test_intro_step_via_toc_indices(self, tmp_path):
        path = tmp_path / "doc.pdf"
        _make_pdf(
            path,
            bodies=["Cover", "Ack", _LONG, _LONG, _LONG],
            toc=[
                [1, "Cover", 1],
                [1, "Acknowledgments", 2],
                [1, "Introduction", 3],
                [1, "Chapter 1", 4],
                [1, "Chapter 2", 5],
            ],
        )
        preview, source = build_content_preview(path, "short", title="Algebra")
        assert source == "intro"
        assert preview is not None
        assert len(preview) >= 600

    def test_toc_step_when_toc_text_long_enough(self, tmp_path):
        """If TOC has enough text on its own (>=600 chars flattened), use it."""
        path = tmp_path / "doc.pdf"
        long_titles = [
            [1, f"Section {i}: {'A very descriptive heading title' * 2}", i + 1] for i in range(10)
        ]
        _make_pdf(path, [f"page {i}" for i in range(10)], toc=long_titles)
        preview, source = build_content_preview(path, "short", title="T")
        assert source == "toc"
        assert preview is not None and len(preview) >= 600

    def test_first_pages_when_no_toc(self, tmp_path):
        path = tmp_path / "doc.pdf"
        _make_pdf(path, [_LONG, _LONG, _LONG], toc=None)
        preview, source = build_content_preview(path, None, title="T")
        assert source == "first-pages"
        assert preview is not None and len(preview) >= 600

    def test_intro_via_regex_when_toc_has_no_pages(self, tmp_path):
        """When TOC entries lack usable page indices, fall back to regex on first pages."""
        path = tmp_path / "doc.pdf"
        intro_marker_text = "Introduction\n" + _LONG
        _make_pdf(path, [intro_marker_text, _LONG, _LONG], toc=None)
        preview, source = build_content_preview(path, None, title="T")
        # Either intro (regex matched in first-pages text) or first-pages
        assert source in {"intro", "first-pages"}
        assert preview is not None and len(preview) >= 600

    def test_title_only_when_file_unreadable(self, tmp_path):
        missing = tmp_path / "missing.pdf"
        preview, source = build_content_preview(
            missing, None, title="My Book", tags=["math", "algebra"]
        )
        assert source == "title-only"
        assert preview == "My Book | math, algebra"

    def test_returns_none_when_nothing_available(self, tmp_path):
        missing = tmp_path / "missing.pdf"
        preview, source = build_content_preview(missing, None)
        assert source == "none"
        assert preview is None

    def test_truncates_to_max_chars(self, tmp_path):
        path = tmp_path / "doc.pdf"
        _make_pdf(path, ["body"])
        long_summary = "x" * 5000
        preview, source = build_content_preview(path, long_summary)
        assert source == "summary"
        assert preview is not None and len(preview) == 1500


class TestBackfillContentPreviews:
    @pytest.fixture
    def db(self, tmp_path):
        database = Database(tmp_path / "test.db")
        yield database
        database.close()

    def _entry(self, file_path: str, hash_: str, summary: str | None = None) -> LibraryEntry:
        meta = DocumentMetadata(
            title="Test",
            author="Author",
            doc_type=DocType.BOOK,
            tags=[],
            summary=summary,
        )
        dest = build_dest_path(meta)
        return LibraryEntry(
            metadata=meta,
            filename=file_path,
            original_filename=file_path,
            file_path=dest if file_path == "auto" else file_path,
            file_hash=hash_,
            ingested_at="2026-01-01T00:00:00Z",
        )

    def test_backfills_existing_files(self, tmp_path, db):
        library = tmp_path / "library"
        library.mkdir()
        rel = "books/Author - Test.pdf"
        full = library / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        _make_pdf(full, [_LONG, _LONG], toc=None)

        entry = self._entry(rel, "h1", summary=None)
        entry.file_path = rel
        db.insert(entry)

        # content_preview must start NULL
        row = db.conn.execute("SELECT content_preview FROM documents WHERE id = ?", (1,)).fetchone()
        assert row["content_preview"] is None

        count = backfill_content_previews(db, library)
        assert count == 1

        row = db.conn.execute(
            "SELECT content_preview, content_preview_source FROM documents WHERE id = ?", (1,)
        ).fetchone()
        assert row["content_preview"] is not None
        assert row["content_preview_source"] in {"toc", "intro", "first-pages", "title-only"}

    def test_skips_missing_files_silently(self, tmp_path, db):
        library = tmp_path / "library"
        library.mkdir()

        entry = self._entry("missing/path.pdf", "h2")
        entry.file_path = "missing/path.pdf"
        db.insert(entry)

        count = backfill_content_previews(db, library)
        # File missing → no rows updated, no exception
        assert count == 0

    def test_idempotent_on_second_call(self, tmp_path, db):
        library = tmp_path / "library"
        library.mkdir()
        rel = "books/Author - Test.pdf"
        full = library / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        _make_pdf(full, [_LONG], toc=None)

        entry = self._entry(rel, "h1", summary="x" * 1000)
        entry.file_path = rel
        db.insert(entry)

        first = backfill_content_previews(db, library)
        second = backfill_content_previews(db, library)
        assert first == 1
        assert second == 0  # No NULL rows left to backfill
