import pytest

from wst.db import Database
from wst.models import DocType, DocumentMetadata, LibraryEntry
from wst.storage import build_dest_path


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def _make_entry(
    title="Test Book",
    author="John Doe",
    doc_type=DocType.BOOK,
    file_hash="hash123",
    **kwargs,
):
    meta = DocumentMetadata(title=title, author=author, doc_type=doc_type, **kwargs)
    dest = build_dest_path(meta)
    return LibraryEntry(
        metadata=meta,
        filename=f"{author} - {title}.pdf",
        original_filename="original.pdf",
        file_path=dest,
        file_hash=file_hash,
        ingested_at="2026-01-01T00:00:00Z",
    )


class TestDatabase:
    def test_insert_and_get(self, db):
        entry = _make_entry()
        doc_id = db.insert(entry)
        assert doc_id == 1

        result = db.get(doc_id)
        assert result is not None
        assert result.metadata.title == "Test Book"
        assert result.metadata.author == "John Doe"
        assert result.id == 1

    def test_get_nonexistent(self, db):
        assert db.get(999) is None

    def test_exists_hash(self, db):
        assert not db.exists_hash("hash123")
        db.insert(_make_entry())
        assert db.exists_hash("hash123")
        assert not db.exists_hash("other_hash")

    def test_duplicate_hash_rejected(self, db):
        db.insert(_make_entry(file_hash="same"))
        with pytest.raises(Exception):
            db.insert(_make_entry(title="Other", file_hash="same"))

    def test_search_by_title(self, db):
        db.insert(_make_entry(title="Machine Learning Basics", file_hash="h1"))
        db.insert(_make_entry(title="Cooking Guide", file_hash="h2"))
        results = db.search("Machine Learning")
        assert len(results) == 1
        assert results[0].metadata.title == "Machine Learning Basics"

    def test_search_by_author(self, db):
        db.insert(_make_entry(author="Alice Smith", file_hash="h1"))
        db.insert(_make_entry(author="Bob Jones", file_hash="h2"))
        results = db.search("", author="Alice")
        assert len(results) == 1
        assert results[0].metadata.author == "Alice Smith"

    def test_search_by_doc_type(self, db):
        db.insert(_make_entry(doc_type=DocType.PAPER, file_hash="h1"))
        db.insert(_make_entry(doc_type=DocType.NOVEL, file_hash="h2"))
        results = db.search("", doc_type="paper")
        assert len(results) == 1

    def test_search_empty_query_no_filters(self, db):
        db.insert(_make_entry(file_hash="h1"))
        db.insert(_make_entry(title="Other", file_hash="h2"))
        results = db.search("")
        assert len(results) == 2

    def test_list_all(self, db):
        db.insert(_make_entry(title="B Book", file_hash="h1"))
        db.insert(_make_entry(title="A Book", file_hash="h2"))
        results = db.list_all()
        assert len(results) == 2
        assert results[0].metadata.title == "A Book"

    def test_list_all_filter_type(self, db):
        db.insert(_make_entry(doc_type=DocType.PAPER, file_hash="h1"))
        db.insert(_make_entry(doc_type=DocType.NOVEL, file_hash="h2"))
        results = db.list_all(doc_type="paper")
        assert len(results) == 1

    def test_list_all_sort_by_year(self, db):
        db.insert(_make_entry(title="Old", year=1990, file_hash="h1"))
        db.insert(_make_entry(title="New", year=2024, file_hash="h2"))
        results = db.list_all(sort_by="year")
        assert results[0].metadata.year == 1990

    def test_list_all_invalid_sort_falls_back(self, db):
        db.insert(_make_entry(file_hash="h1"))
        results = db.list_all(sort_by="invalid_column")
        assert len(results) == 1

    def test_get_by_title(self, db):
        db.insert(_make_entry(title="Unique Title", file_hash="h1"))
        result = db.get_by_title("Unique")
        assert result is not None
        assert result.metadata.title == "Unique Title"

    def test_get_by_title_not_found(self, db):
        assert db.get_by_title("nonexistent") is None

    def test_tags_roundtrip(self, db):
        db.insert(_make_entry(tags=["math", "algebra"], file_hash="h1"))
        result = db.get(1)
        assert result.metadata.tags == ["math", "algebra"]
