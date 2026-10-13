"""Cấu hình ứng dụng, đọc từ biến môi trường (và file .env nếu có)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Nạp file .env ở thư mục gốc dự án (không ghi đè biến đã có)."""
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return
    # utf-8-sig: file .env lưu bằng Notepad có thể có BOM ở đầu - không được làm hỏng tên biến đầu tiên
    for raw in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# Toàn bộ logic thị trường (ngày giao dịch, T+2, giờ chạy Auto-Trader) theo giờ Việt Nam. Máy chủ trên Internet
# thường chạy giờ UTC → đặt múi giờ tiến trình UTC+7 (Việt Nam không có giờ mùa hè). Windows dùng giờ máy tính.
if hasattr(time, "tzset") and not os.environ.get("TZ"):
    os.environ["TZ"] = "ICT-7"
    time.tzset()


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
    # Nguồn dữ liệu CHÍNH THỨC (tùy chọn): SSI FastConnect v3, DNSE OpenAPI - đăng ký tại CTCK tương ứng
    ssi_api_key: str = os.getenv("SSI_API_KEY", "").strip()
    ssi_api_secret: str = os.getenv("SSI_API_SECRET", "").strip()
    dnse_api_key: str = os.getenv("DNSE_API_KEY", "").strip()
    dnse_api_secret: str = os.getenv("DNSE_API_SECRET", "").strip()
    port: int = int(os.getenv("PORT", "8000"))
    host: str = os.getenv("HOST", "127.0.0.1")
    frontend_dist: Path = ROOT_DIR / "frontend" / "dist"

    @property
    def has_anthropic_credentials(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
                    or os.getenv("ANTHROPIC_PROFILE"))


settings = Settings()
