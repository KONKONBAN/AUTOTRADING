"""Khởi động AutoTrading VN: kiểm tra môi trường, chọn cổng trống, chạy máy chủ và tự mở trình duyệt.

Được gọi bởi run.bat (Windows) / run.sh (macOS, Linux) sau khi đã cài thư viện vào .venv.
Có thể chạy trực tiếp:  .venv/bin/python launcher.py      (biến NO_BROWSER=1 để không mở trình duyệt)
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIN_PY = (3, 10)


def _utf8_console() -> None:
    """Windows: khi đầu ra bị chuyển hướng (file, tiến trình khác) Python dùng bảng mã cp1252 và sẽ lỗi khi in
    tiếng Việt có dấu. Chuyển stdout/stderr sang UTF-8 (cửa sổ console thật vốn đã là UTF-8)."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def fail(msg: str) -> None:
    print("\n[LỖI] " + msg, flush=True)
    sys.exit(1)


def read_env() -> dict[str, str]:
    """Đọc file .env (tạo từ .env.example nếu chưa có). Biến môi trường đang có được ưu tiên."""
    env_file, example = ROOT / ".env", ROOT / ".env.example"
    if not env_file.exists() and example.exists():
        shutil.copyfile(example, env_file)
        print("• Đã tạo file cấu hình .env (sửa file này để thêm ANTHROPIC_API_KEY cho AI Agent).")
    values: dict[str, str] = {}
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    values.update({k: v for k, v in os.environ.items() if k in values or k in {"HOST", "PORT"}})
    return values


def is_our_app(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as r:
            data = json.loads(r.read().decode("utf-8"))
            return bool(data.get("ok")) and "version" in data
    except Exception:  # noqa: BLE001
        return False


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host if host not in {"", "0.0.0.0"} else "0.0.0.0", port))
            return True
        except OSError:
            return False


def open_browser_when_ready(port: int) -> None:
    url = f"http://127.0.0.1:{port}"
    for _ in range(240):  # tối đa ~2 phút (lần đầu nạp thư viện có thể chậm)
        if is_our_app(port):
            if os.environ.get("NO_BROWSER") != "1":
                webbrowser.open(url)
            print(f"\n✅ AutoTrading VN đã sẵn sàng: {url}\n   (Giữ cửa sổ này mở trong khi dùng. Đóng cửa sổ hoặc bấm Ctrl+C để tắt.)\n",
                  flush=True)
            return
        time.sleep(0.5)


def main() -> None:
    _utf8_console()
    if sys.version_info < MIN_PY:
        fail(f"Cần Python {MIN_PY[0]}.{MIN_PY[1]} trở lên (đang dùng {sys.version.split()[0]}).")
    if not (ROOT / "backend" / "app" / "main.py").exists():
        fail("Không tìm thấy thư mục backend - hãy giải nén TOÀN BỘ file ZIP rồi chạy lại.")
    try:
        import fastapi  # noqa: F401
        import uvicorn
    except ImportError as exc:
        fail(f"Thiếu thư viện ({exc.name}). Hãy chạy run.bat / run.sh để cài đặt tự động.")
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        fail("Thiếu giao diện đã build (frontend/dist). Hãy tải lại mã nguồn đầy đủ từ GitHub.")

    env = read_env()
    host = env.get("HOST") or "127.0.0.1"
    port = int(env.get("PORT") or 8000)
    if is_our_app(port):
        print(f"• AutoTrading VN đang chạy sẵn ở cổng {port} - mở trình duyệt.")
        if os.environ.get("NO_BROWSER") != "1":
            webbrowser.open(f"http://127.0.0.1:{port}")
        return
    if not port_free(host, port):
        alt = next((p for p in range(port + 1, port + 50) if port_free(host, p)), None)
        if alt is None:
            fail(f"Cổng {port} đang bị chương trình khác dùng và không tìm được cổng trống.")
        print(f"• Cổng {port} đang bận - dùng cổng {alt}.")
        port = alt
    os.environ["PORT"] = str(port)  # để ứng dụng biết cổng thực tế (đường hầm cho điện thoại)
    os.environ["HOST"] = host

    print("=" * 64)
    print("  AutoTrading VN - Phân tích cổ phiếu & AI quản trị tài sản")
    print(f"  Địa chỉ trên máy này : http://127.0.0.1:{port}")
    if host in {"0.0.0.0", "::"}:
        print("  Điện thoại cùng Wi-Fi: xem trang 'Cài đặt & điện thoại' (cần đặt mật khẩu)")
    print("=" * 64, flush=True)

    sys.path.insert(0, str(ROOT / "backend"))
    os.chdir(ROOT)
    threading.Thread(target=open_browser_when_ready, args=(port,), daemon=True).start()
    try:
        uvicorn.run("app.main:app", host=host, port=port, log_level="warning")
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        fail(f"Máy chủ dừng do lỗi: {exc}")


if __name__ == "__main__":
    main()
