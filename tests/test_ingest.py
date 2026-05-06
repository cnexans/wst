import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from wst.cli import cli
from wst.ingest import IngestResult, compute_file_hash, format_metadata_display, ingest_file
from wst.models import DocType, DocumentMetadata, LibraryEntry


class TestComputeFileHash:
    def test_deterministic(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_text("hello world")
        h1 = compute_file_hash(f)
        h2 = compute_file_hash(f)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.pdf"
        f2 = tmp_path / "b.pdf"
        f1.write_text("content a")
        f2.write_text("content b")
        assert compute_file_hash(f1) != compute_file_hash(f2)


class TestFormatMetadataDisplay:
    def test_basic_display(self):
        meta = DocumentMetadata(
            title="Test Book",
            author="Author",
            doc_type=DocType.BOOK,
            year=2024,
            language="en",
            page_count=100,
            subject="CS",
            tags=["python", "testing"],
            summary="A test book about testing.",
        )
        entry = LibraryEntry(
            metadata=meta,
            filename="Author - Test Book (2024).pdf",
            original_filename="test.pdf",
            file_path="books/Author - Test Book (2024).pdf",
            file_hash="abc",
            ingested_at="2026-01-01T00:00:00Z",
        )
        output = format_metadata_display(entry)
        assert "Test Book" in output
        assert "Author" in output
        assert "2024" in output
        assert "python, testing" in output
        assert "books/" in output

    def test_display_with_optional_fields(self):
        meta = DocumentMetadata(
            title="Paper",
            author="Researcher",
            doc_type=DocType.PAPER,
            publisher="IEEE",
            isbn="978-0-123456-78-9",
        )
        entry = LibraryEntry(
            metadata=meta,
            filename="f.pdf",
            original_filename="f.pdf",
            file_path="papers/f.pdf",
            file_hash="abc",
            ingested_at="2026-01-01T00:00:00Z",
        )
        output = format_metadata_display(entry)
        assert "IEEE" in output
        assert "978-0-123456-78-9" in output


# ---------------------------------------------------------------------------
# RFC 0013 — `--format ndjson`
# ---------------------------------------------------------------------------


def _ndjson_lines(stdout: str) -> list[dict]:
    """Parse stdout assumed to be NDJSON. Ignores blank lines and non-JSON."""
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            # Click test runner may interleave warning lines on stderr; skip.
            continue
    return out


@pytest.fixture
def cfg(tmp_path):
    from wst.config import WstConfig

    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True)
    library = tmp_path / "library"
    library.mkdir(parents=True)
    return WstConfig(
        home_path=tmp_path,
        inbox_path=inbox,
        library_path=library,
        db_path=library / "wst.db",
    )


class TestNdjsonFormat:
    """Verify `wst ingest --format ndjson` emits one event-line per file plus a final summary."""

    def test_emits_summary_for_empty_inbox(self, cfg):
        runner = CliRunner()
        with patch("wst.cli.WstConfig", return_value=cfg):
            result = runner.invoke(cli, ["ingest", "--format", "ndjson"])
        assert result.exit_code == 0, result.output
        events = _ndjson_lines(result.output)
        # Empty inbox -> just the summary event with all zeros
        assert len(events) == 1
        assert events[0]["event"] == "summary"
        assert events[0]["processed"] == 0
        assert events[0]["ingested"] == 0

    def test_emits_per_file_events_with_summary(self, cfg, tmp_path):
        """Mock ingest_files to return synthetic results; assert NDJSON streaming."""
        fake_results = [
            IngestResult("a.pdf", "ingested", dest_path="books/a.pdf"),
            IngestResult("b.pdf", "skipped", reason="duplicate"),
            IngestResult(
                "c.pdf",
                "ingested",
                dest_path="books/c.pdf",
                notes=["OCR auto-applied"],
            ),
        ]
        fake_summary = {
            "processed": 3,
            "ingested": 2,
            "skipped": 1,
            "failed": 0,
            "results": fake_results,
            "elapsed_seconds": 0.1,
        }

        # Drop a placeholder file in the inbox so the "no files" branch doesn't fire
        (cfg.inbox_path / "placeholder.pdf").write_text("dummy")

        def fake_ingest_files(*args, **kwargs):
            cb = kwargs.get("per_file_callback")
            if cb:
                for r in fake_results:
                    cb(r)
            return fake_summary

        runner = CliRunner()
        with (
            patch("wst.cli.WstConfig", return_value=cfg),
            patch("wst.cli.ingest_files", side_effect=fake_ingest_files),
            patch("wst.cli.get_ai_backend", return_value=MagicMock()),
            patch("wst.cli._find_documents", return_value=[cfg.inbox_path / "placeholder.pdf"]),
        ):
            result = runner.invoke(cli, ["ingest", "--format", "ndjson"])

        assert result.exit_code == 0, result.output
        events = _ndjson_lines(result.output)
        # 3 file events + 1 summary
        file_events = [e for e in events if e["event"] == "file"]
        summary_events = [e for e in events if e["event"] == "summary"]
        assert len(file_events) == 3
        assert len(summary_events) == 1

        assert file_events[0]["filename"] == "a.pdf"
        assert file_events[0]["status"] == "ingested"
        assert file_events[0]["dest_path"] == "books/a.pdf"
        assert file_events[1]["status"] == "skipped"
        assert file_events[1]["reason"] == "duplicate"
        assert "OCR auto-applied" in file_events[2]["notes"]

        s = summary_events[0]
        assert s["processed"] == 3
        assert s["ingested"] == 2
        assert s["skipped"] == 1
        assert s["failed"] == 0

    def test_ndjson_does_not_prompt_interactively(self, cfg, tmp_path):
        """NDJSON mode forces auto-confirm — no `Accept and ingest?` prompt is emitted."""
        (cfg.inbox_path / "placeholder.pdf").write_text("dummy")

        captured_kwargs = {}

        def capture(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return {
                "processed": 0,
                "ingested": 0,
                "skipped": 0,
                "failed": 0,
                "results": [],
                "elapsed_seconds": 0.0,
            }

        runner = CliRunner()
        with (
            patch("wst.cli.WstConfig", return_value=cfg),
            patch("wst.cli.ingest_files", side_effect=capture),
            patch("wst.cli.get_ai_backend", return_value=MagicMock()),
            patch("wst.cli._find_documents", return_value=[cfg.inbox_path / "placeholder.pdf"]),
        ):
            # Pass --confirm explicitly; NDJSON should override it back to auto_confirm=True
            result = runner.invoke(cli, ["ingest", "--format", "ndjson", "--confirm"])

        assert result.exit_code == 0, result.output
        # ingest_files is invoked with auto_confirm=True (i.e. confirm flag suppressed)
        assert captured_kwargs.get("auto_confirm") is True


# ---------------------------------------------------------------------------
# RFC 0013 Q4 — OCR auto-detect inside ingest_file
# ---------------------------------------------------------------------------


class TestOcrAutoDetect:
    """Verify the OCR auto-detect step in ingest_file."""

    def _setup(self, tmp_path):
        from wst.db import Database
        from wst.storage import LocalStorage

        library = tmp_path / "library"
        library.mkdir()
        db = Database(library / "wst.db")
        storage = LocalStorage(library)
        return db, storage, library

    def _fake_metadata(self):
        return DocumentMetadata(
            title="Scanned Book",
            author="Author",
            doc_type=DocType.BOOK,
        )

    def test_warning_note_when_tools_missing(self, tmp_path):
        db, storage, _library = self._setup(tmp_path)
        path = tmp_path / "scan.pdf"
        path.write_text("dummy")

        ai = MagicMock()
        ai.generate_metadata.return_value = self._fake_metadata()

        with (
            patch("wst.ocr.needs_ocr", return_value=True),
            patch("wst.ocr.ocr_available", return_value=False),
            patch("wst.ingest.extract_doc_info", return_value=({}, "thin", 1)),
            patch("wst.ingest.write_doc_metadata"),
            patch("wst.search.upsert_entry"),
        ):
            result = ingest_file(path, ai, storage, db, auto_confirm=True)

        assert result.status == "ingested"
        assert any("OCR tools are not installed" in n for n in result.notes)
        db.close()

    def test_ocr_auto_applied_when_available(self, tmp_path):
        db, storage, _library = self._setup(tmp_path)
        path = tmp_path / "scan.pdf"
        path.write_text("dummy")

        ai = MagicMock()
        ai.generate_metadata.return_value = self._fake_metadata()

        # First extract returns thin; after OCR, the second extract returns rich.
        extract_calls = iter(
            [
                ({}, "thin", 1),
                ({}, "now full text after OCR " * 50, 1),
            ]
        )

        from wst.ocr import OcrResult

        with (
            patch("wst.ocr.needs_ocr", return_value=True),
            patch("wst.ocr.ocr_available", return_value=True),
            patch("wst.ocr.run_ocr", return_value=OcrResult("scan.pdf", "processed")),
            patch("wst.ingest.extract_doc_info", side_effect=lambda *a, **kw: next(extract_calls)),
            patch("wst.ingest.write_doc_metadata"),
            patch("wst.search.upsert_entry"),
        ):
            result = ingest_file(path, ai, storage, db, auto_confirm=True)

        assert result.status == "ingested"
        assert "OCR auto-applied" in result.notes
        db.close()

    def test_no_note_when_text_is_sufficient(self, tmp_path):
        """If needs_ocr returns False, the auto-detect block is a no-op."""
        db, storage, _library = self._setup(tmp_path)
        path = tmp_path / "regular.pdf"
        path.write_text("dummy")

        ai = MagicMock()
        ai.generate_metadata.return_value = self._fake_metadata()

        with (
            patch("wst.ocr.needs_ocr", return_value=False),
            patch("wst.ingest.extract_doc_info", return_value=({}, "rich text " * 50, 1)),
            patch("wst.ingest.write_doc_metadata"),
            patch("wst.search.upsert_entry"),
        ):
            result = ingest_file(path, ai, storage, db, auto_confirm=True)

        assert result.status == "ingested"
        assert result.notes == []
        db.close()
