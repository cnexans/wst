from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WstConfig:
    inbox_path: Path = field(default_factory=lambda: Path("./inbox"))
    library_path: Path = field(default_factory=lambda: Path("./library"))
    db_path: Path = field(default_factory=lambda: Path("./library/wst.db"))
    ai_backend: str = "claude"
    ai_model: str = "sonnet"

    def ensure_dirs(self) -> None:
        self.inbox_path.mkdir(parents=True, exist_ok=True)
        self.library_path.mkdir(parents=True, exist_ok=True)
