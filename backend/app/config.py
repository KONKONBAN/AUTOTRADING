"""Cấu hình ứng dụng, đọc từ biến môi trường (và file .env nếu có)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Nạp file .env ở thư mục gốc dự án (không ghi đè biến đã có)."""
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    agent_model: str = os.getenv("AGENT_MODEL", "claude-opus-5-5")
    agent_effort: str = os.getenv("AGENT_EFFORT", "medium")
    data_mode: str = os.getenv("DATA_MODE", "auto").lower()
    price_cache_ttl: int = int(os.getenv("PRICE_CACHE_TTL", "900"))
    paper_initial_cash: float = float(os.getenv("PAPER_INITIAL_CASH", "500000000"))
    allow_live_trading: bool = _bool("ALLOW_LIVE_TRADING", False)
    autotrader_scheduler: bool = _bool("AUTOTRADER_SCHEDULER", True)
    db_path: Path = ROOT_DIR / os.getenv("DB_PATH", "backend/data/autotrading.sqlite3")
    frontend_dist: Path = ROOT_DIR / "frontend" / "dist"

    @property
    def has_anthropic_credentials(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
                    or os.getenv("ANTHROPIC_PROFILE"))


settings = Settings()
