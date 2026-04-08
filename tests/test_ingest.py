from wst.ingest import compute_file_hash, format_metadata_display
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
