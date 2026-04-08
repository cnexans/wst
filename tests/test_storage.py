from wst.models import DocType, DocumentMetadata
from wst.storage import (
    CompositeStorage,
    LocalStorage,
    build_dest_path,
    sanitize_filename,
)


class TestSanitizeFilename:
    def test_removes_special_chars(self):
        assert sanitize_filename('file<>:"/\\|?*name') == "filename"

    def test_strips_dots_and_spaces(self):
        assert sanitize_filename("  hello. ") == "hello"

    def test_normal_string_unchanged(self):
        assert sanitize_filename("John Doe") == "John Doe"

    def test_empty_after_sanitize(self):
        assert sanitize_filename("***") == ""


class TestBuildDestPath:
    def test_book_with_year(self):
        meta = DocumentMetadata(
            title="Clean Code", author="Robert Martin", doc_type=DocType.BOOK, year=2008
        )
        assert build_dest_path(meta) == "books/Robert Martin - Clean Code (2008).pdf"

    def test_paper_without_year(self):
        meta = DocumentMetadata(
            title="Attention Is All You Need", author="Vaswani et al", doc_type=DocType.PAPER
        )
        assert build_dest_path(meta) == "papers/Vaswani et al - Attention Is All You Need.pdf"

    def test_class_notes(self):
        meta = DocumentMetadata(
            title="Lecture 5", author="Prof Smith", doc_type=DocType.CLASS_NOTES, year=2024
        )
        assert build_dest_path(meta) == "notes/Prof Smith - Lecture 5 (2024).pdf"

    def test_epub_extension(self):
        meta = DocumentMetadata(title="A Novel", author="Author", doc_type=DocType.NOVEL, year=2020)
        assert build_dest_path(meta, extension=".epub") == "books/Author - A Novel (2020).epub"

    def test_djvu_extension(self):
        meta = DocumentMetadata(title="Math Book", author="Author", doc_type=DocType.TEXTBOOK)
        assert build_dest_path(meta, extension=".djvu") == "books/Author - Math Book.djvu"

    def test_sanitizes_special_chars(self):
        meta = DocumentMetadata(title="What is C++?", author="Author", doc_type=DocType.BOOK)
        path = build_dest_path(meta)
        assert "?" not in path


class TestLocalStorage:
    def test_store_file(self, tmp_path):
        library = tmp_path / "library"
        storage = LocalStorage(library)

        source = tmp_path / "test.pdf"
        source.write_text("content")

        result = storage.store(source, "books/test.pdf")
        assert result == "books/test.pdf"
        assert (library / "books" / "test.pdf").exists()
        # Source should still exist (copy, not move)
        assert source.exists()

    def test_store_handles_collision(self, tmp_path):
        library = tmp_path / "library"
        storage = LocalStorage(library)

        # Create first file
        src1 = tmp_path / "a.pdf"
        src1.write_text("first")
        storage.store(src1, "books/test.pdf")

        # Store second with same dest
        src2 = tmp_path / "b.pdf"
        src2.write_text("second")
        result = storage.store(src2, "books/test.pdf")
        assert result == "books/test (1).pdf"
        assert (library / "books" / "test (1).pdf").exists()

    def test_exists(self, tmp_path):
        library = tmp_path / "library"
        storage = LocalStorage(library)

        assert not storage.exists("books/test.pdf")
        (library / "books").mkdir(parents=True)
        (library / "books" / "test.pdf").write_text("x")
        assert storage.exists("books/test.pdf")

    def test_list_files(self, tmp_path):
        library = tmp_path / "library"
        (library / "books").mkdir(parents=True)
        (library / "books" / "a.pdf").write_text("x")
        (library / "books" / "b.pdf").write_text("x")
        (library / "books" / "c.txt").write_text("x")  # not a PDF

        storage = LocalStorage(library)
        files = storage.list_files("books")
        assert len(files) == 2
        assert all(f.endswith(".pdf") for f in files)

    def test_list_files_empty(self, tmp_path):
        storage = LocalStorage(tmp_path / "library")
        assert storage.list_files() == []


class TestCompositeStorage:
    def test_stores_to_primary_and_backup(self, tmp_path):
        primary_root = tmp_path / "primary"
        backup_root = tmp_path / "backup"
        primary = LocalStorage(primary_root)
        backup = LocalStorage(backup_root)
        composite = CompositeStorage(primary, backups=[backup])

        source = tmp_path / "test.pdf"
        source.write_text("content")

        result = composite.store(source, "books/test.pdf")
        assert result == "books/test.pdf"
        assert (primary_root / "books" / "test.pdf").exists()
        assert (backup_root / "books" / "test.pdf").exists()

    def test_exists_checks_primary_only(self, tmp_path):
        primary = LocalStorage(tmp_path / "primary")
        backup = LocalStorage(tmp_path / "backup")
        composite = CompositeStorage(primary, backups=[backup])

        # File only in backup
        (tmp_path / "backup" / "books").mkdir(parents=True)
        (tmp_path / "backup" / "books" / "test.pdf").write_text("x")
        assert not composite.exists("books/test.pdf")

    def test_list_files_from_primary(self, tmp_path):
        primary_root = tmp_path / "primary"
        (primary_root / "books").mkdir(parents=True)
        (primary_root / "books" / "a.pdf").write_text("x")

        primary = LocalStorage(primary_root)
        composite = CompositeStorage(primary)
        assert len(composite.list_files("books")) == 1
