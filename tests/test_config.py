from pathlib import Path

from wst.config import WST_HOME, WstConfig


class TestWstConfig:
    def test_defaults(self):
        config = WstConfig()
        assert config.home_path == WST_HOME
        assert config.inbox_path == WST_HOME / "inbox"
        assert config.library_path == WST_HOME / "library"
        assert config.db_path == WST_HOME / "library" / "wst.db"
        assert config.ai_backend == "claude"
        assert config.ai_model == "sonnet"

    def test_custom_paths(self):
        config = WstConfig(
            home_path=Path("/tmp/wst"),
            inbox_path=Path("/tmp/wst/in"),
            library_path=Path("/tmp/wst/lib"),
            db_path=Path("/tmp/wst/lib/test.db"),
        )
        assert config.inbox_path == Path("/tmp/wst/in")

    def test_ensure_dirs(self, tmp_path):
        config = WstConfig(
            inbox_path=tmp_path / "inbox",
            library_path=tmp_path / "library",
        )
        assert not config.inbox_path.exists()
        assert not config.library_path.exists()
        config.ensure_dirs()
        assert config.inbox_path.exists()
        assert config.library_path.exists()
