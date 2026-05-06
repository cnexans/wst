import json
from dataclasses import dataclass, field
from pathlib import Path

WST_HOME = Path.home() / "wst"
CONFIG_FILE = WST_HOME / "config.json"


def _load_config_file() -> dict:
    """Load config.json if it exists, else return empty dict."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_config_file(data: dict) -> None:
    """Save data to config.json."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n")


def get_s3_config() -> dict | None:
    """Get S3 configuration from config.json. Returns None if not configured."""
    data = _load_config_file()
    s3 = data.get("s3")
    if not s3 or not s3.get("bucket"):
        return None
    return s3


def save_s3_config(
    bucket: str,
    access_key_id: str,
    secret_access_key: str,
    region: str = "us-east-1",
    endpoint_url: str | None = None,
    prefix: str = "",
) -> None:
    """Save S3 configuration to config.json."""
    data = _load_config_file()
    data["s3"] = {
        "bucket": bucket,
        "region": region,
        "access_key_id": access_key_id,
        "secret_access_key": secret_access_key,
    }
    if endpoint_url:
        data["s3"]["endpoint_url"] = endpoint_url
    if prefix:
        data["s3"]["prefix"] = prefix
    _save_config_file(data)


def get_gdrive_config() -> dict | None:
    """Get Google Drive configuration from config.json. Returns None if not configured."""
    data = _load_config_file()
    gdrive = data.get("gdrive")
    if not gdrive or not gdrive.get("root"):
        return None
    return gdrive


def save_gdrive_config(root: str, subfolder: str = "wst") -> None:
    """Save Google Drive configuration to config.json."""
    data = _load_config_file()
    data["gdrive"] = {"root": root, "subfolder": subfolder}
    _save_config_file(data)


@dataclass
class WstConfig:
    home_path: Path = field(default_factory=lambda: WST_HOME)
    inbox_path: Path = field(default_factory=lambda: WST_HOME / "inbox")
    library_path: Path = field(default_factory=lambda: WST_HOME / "library")
    db_path: Path = field(default_factory=lambda: WST_HOME / "library" / "wst.db")
    ai_backend: str = "claude"
    ai_model: str = "sonnet"

    def ensure_dirs(self) -> None:
        self.inbox_path.mkdir(parents=True, exist_ok=True)
        self.library_path.mkdir(parents=True, exist_ok=True)
