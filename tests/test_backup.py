from unittest.mock import patch

import pytest

from wst.backup import (
    GoogleDriveProvider,
    ICloudProvider,
    _detect_gdrive_bases,
    get_provider,
)


class TestGetProvider:
    def test_returns_icloud(self):
        provider = get_provider("icloud")
        assert isinstance(provider, ICloudProvider)

    def test_returns_gdrive(self):
        provider = get_provider("gdrive")
        assert isinstance(provider, GoogleDriveProvider)

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


class TestGoogleDriveProvider:
    def test_explicit_root_skips_detection(self, tmp_path):
        drive = tmp_path / "DriveRoot"
        drive.mkdir()
        provider = GoogleDriveProvider(root=drive)

        assert provider.is_configured()
        assert provider.gdrive_base == drive
        assert provider.dest_root == drive / "wst"

    def test_unconfigured_when_no_drive_present(self, tmp_path):
        with (
            patch("wst.backup._detect_gdrive_bases", return_value=[]),
            patch("wst.backup.get_gdrive_config", return_value=None, create=True),
        ):
            provider = GoogleDriveProvider()
            assert not provider.is_configured()

    def test_backup_file(self, tmp_path):
        provider = GoogleDriveProvider(root=tmp_path / "DriveRoot")
        source = tmp_path / "test.pdf"
        source.write_text("content")

        provider.backup_file(source, "books/test.pdf")
        dest = provider.dest_root / "books" / "test.pdf"
        assert dest.exists()
        assert dest.read_text() == "content"

    def test_backup_all(self, tmp_path):
        provider = GoogleDriveProvider(root=tmp_path / "DriveRoot")

        library = tmp_path / "library"
        (library / "books").mkdir(parents=True)
        (library / "books" / "a.pdf").write_text("a")
        (library / "wst.db").write_text("db")

        count = provider.backup_all(library, emit=False)
        assert count == 1
        assert (provider.dest_root / "books" / "a.pdf").exists()
        assert (provider.dest_root / "wst.db").exists()


class TestDetectGdriveBases:
    def test_picks_modern_macos_drive(self, tmp_path, monkeypatch):
        fake_home = tmp_path
        cs = fake_home / "Library" / "CloudStorage" / "GoogleDrive-user@example.com" / "My Drive"
        cs.mkdir(parents=True)
        monkeypatch.setattr("wst.backup.Path.home", lambda: fake_home)
        monkeypatch.setattr("wst.backup.platform.system", lambda: "Darwin")

        bases = _detect_gdrive_bases()
        assert cs in bases

    def test_returns_multiple_macos_accounts_sorted(self, tmp_path, monkeypatch):
        fake_home = tmp_path
        for email in ("z@example.com", "a@example.com"):
            (fake_home / "Library" / "CloudStorage" / f"GoogleDrive-{email}" / "My Drive").mkdir(
                parents=True
            )
        monkeypatch.setattr("wst.backup.Path.home", lambda: fake_home)
        monkeypatch.setattr("wst.backup.platform.system", lambda: "Darwin")

        bases = _detect_gdrive_bases()
        # GoogleDrive-a@... sorts before GoogleDrive-z@...
        assert len(bases) >= 2
        assert "GoogleDrive-a" in str(bases[0])

    def test_empty_when_no_drive(self, tmp_path, monkeypatch):
        monkeypatch.setattr("wst.backup.Path.home", lambda: tmp_path)
        monkeypatch.setattr("wst.backup.platform.system", lambda: "Darwin")
        assert _detect_gdrive_bases() == []


class TestGdriveConfig:
    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "wst"
        monkeypatch.setattr("wst.config.WST_HOME", fake_home)
        monkeypatch.setattr("wst.config.CONFIG_FILE", fake_home / "config.json")

        from wst.config import get_gdrive_config, save_gdrive_config

        save_gdrive_config(root="/tmp/MyDrive", subfolder="books")
        cfg = get_gdrive_config()
        assert cfg == {"root": "/tmp/MyDrive", "subfolder": "books"}
