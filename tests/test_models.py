import pytest
from pydantic import ValidationError

from wst.models import DOCTYPE_FOLDER, DocType, DocumentMetadata, LibraryEntry


class TestDocType:
    def test_all_doc_types_have_folder(self):
        for dt in DocType:
            assert dt in DOCTYPE_FOLDER

    def test_folder_values(self):
        assert DOCTYPE_FOLDER[DocType.BOOK] == "libros"
        assert DOCTYPE_FOLDER[DocType.NOVEL] == "libros"
        assert DOCTYPE_FOLDER[DocType.TEXTBOOK] == "libros"
        assert DOCTYPE_FOLDER[DocType.PAPER] == "papers"
        assert DOCTYPE_FOLDER[DocType.CLASS_NOTES] == "notas"
        assert DOCTYPE_FOLDER[DocType.EXERCISES] == "ejercicios"
        assert DOCTYPE_FOLDER[DocType.GUIDE_THEORY] == "guias"
        assert DOCTYPE_FOLDER[DocType.GUIDE_PRACTICE] == "guias"


class TestDocumentMetadata:
    def test_minimal_metadata(self):
        meta = DocumentMetadata(title="Test", author="Author", doc_type=DocType.BOOK)
        assert meta.title == "Test"
        assert meta.author == "Author"
        assert meta.year is None
        assert meta.tags == []

    def test_full_metadata(self):
        meta = DocumentMetadata(
            title="Test Book",
            author="John Doe",
            doc_type=DocType.TEXTBOOK,
            year=2024,
            publisher="Publisher",
            isbn="978-0-123456-78-9",
            language="en",
            tags=["math", "algebra"],
            page_count=300,
            summary="A test book",
            table_of_contents="Ch1, Ch2",
            subject="Mathematics",
        )
        assert meta.year == 2024
        assert len(meta.tags) == 2
        assert meta.language == "en"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            DocumentMetadata(title="Test", author="Author")  # missing doc_type

    def test_doc_type_from_string(self):
        meta = DocumentMetadata(title="T", author="A", doc_type="paper")
        assert meta.doc_type == DocType.PAPER

    def test_invalid_doc_type(self):
        with pytest.raises(ValidationError):
            DocumentMetadata(title="T", author="A", doc_type="invalid")


class TestLibraryEntry:
    def test_create_entry(self):
        meta = DocumentMetadata(title="T", author="A", doc_type=DocType.BOOK)
        entry = LibraryEntry(
            metadata=meta,
            filename="A - T.pdf",
            original_filename="file.pdf",
            file_path="libros/A - T.pdf",
            file_hash="abc123",
            ingested_at="2026-01-01T00:00:00Z",
        )
        assert entry.id is None
        assert entry.metadata.title == "T"
        assert entry.file_hash == "abc123"
