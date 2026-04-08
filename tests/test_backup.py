import pytest

from wst.backup import ICloudProvider, get_provider


class TestGetProvider:
    def test_returns_icloud(self):
        provider = get_provider("icloud")
        assert isinstance(provider, ICloudProvider)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown backup provider"):
            get_provider("nonexistent")


class TestICloudProvider:
    def test_backup_file(self, tmp_path):
        provider = ICloudProvider()
        provider.dest_root = tmp_path / "icloud" / "wst"

        source = tmp_path / "test.pdf"
        source.write_text("content")

        provider.backup_file(source, "books/test.pdf")
        dest = provider.dest_root / "books" / "test.pdf"
        assert dest.exists()
        assert dest.read_text() == "content"

    def test_backup_file_creates_dirs(self, tmp_path):
        provider = ICloudProvider()
        provider.dest_root = tmp_path / "icloud" / "wst"

        source = tmp_path / "test.pdf"
        source.write_text("content")

        provider.backup_file(source, "papers/sub/test.pdf")
        assert (provider.dest_root / "papers" / "sub" / "test.pdf").exists()

    def test_backup_all(self, tmp_path):
        provider = ICloudProvider()
        provider.dest_root = tmp_path / "icloud" / "wst"

        library = tmp_path / "library"
        (library / "books").mkdir(parents=True)
        (library / "papers").mkdir(parents=True)
        (library / "books" / "a.pdf").write_text("a")
        (library / "papers" / "b.pdf").write_text("b")
        (library / "wst.db").write_text("db")

        count = provider.backup_all(library)
        assert count == 2
        assert (provider.dest_root / "books" / "a.pdf").exists()
        assert (provider.dest_root / "papers" / "b.pdf").exists()
        assert (provider.dest_root / "wst.db").exists()

    def test_backup_all_empty_library(self, tmp_path):
        provider = ICloudProvider()
        provider.dest_root = tmp_path / "icloud" / "wst"

        library = tmp_path / "library"
        library.mkdir()

        count = provider.backup_all(library)
        assert count == 0

    def test_backup_overwrites_existing(self, tmp_path):
        provider = ICloudProvider()
        provider.dest_root = tmp_path / "icloud" / "wst"

        source = tmp_path / "test.pdf"
        source.write_text("v1")
        provider.backup_file(source, "books/test.pdf")

        source.write_text("v2")
        provider.backup_file(source, "books/test.pdf")

        dest = provider.dest_root / "books" / "test.pdf"
        assert dest.read_text() == "v2"
