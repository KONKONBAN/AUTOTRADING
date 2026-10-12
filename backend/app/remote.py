"""Mở ứng dụng trên điện thoại.

1. Cùng mạng Wi-Fi: điện thoại mở http://<IP máy tính>:<cổng> (máy chủ phải lắng nghe 0.0.0.0).
2. Qua Internet (4G, ở bất cứ đâu): đường hầm nhanh Cloudflare (cloudflared, miễn phí, không cần tài khoản)
   tạo địa chỉ https://<ngẫu-nhiên>.trycloudflare.com trỏ về máy tính đang chạy ứng dụng.
   Địa chỉ đổi mỗi lần mở đường hầm; máy tính phải bật và đang chạy ứng dụng.
Cả hai cách đều bắt buộc đăng nhập tài khoản (xem auth.py).
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import tarfile
import threading
import time
from pathlib import Path

import httpx

from .config import settings

log = logging.getLogger(__name__)

BIN_DIR = settings.db_path.parent / "bin"
_RELEASE = "https://github.com/cloudflare/cloudflared/releases/latest/download/"
_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

_lock = threading.Lock()
_state: dict = {"proc": None, "url": None, "error": None, "log": [], "starting": False}


def lan_addresses() -> list[str]:
    """Các địa chỉ IPv4 mạng nội bộ của máy (để điện thoại cùng Wi-Fi truy cập)."""
    ips: set[str] = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # không gửi gói tin; chỉ để hệ điều hành chọn card mạng
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith(("127.", "169.254.")))


def _asset_name() -> tuple[str, bool]:
    """Tên file phát hành của cloudflared cho máy hiện tại → (tên, là file nén .tgz)."""
    system, machine = platform.system().lower(), platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "386" if machine in {"i386", "i686", "x86"} else "amd64"
    if system == "windows":
        return f"cloudflared-windows-{arch}.exe", False
    if system == "darwin":
        return f"cloudflared-darwin-{'arm64' if arch == 'arm64' else 'amd64'}.tgz", True
    return f"cloudflared-linux-{arch}", False


def cloudflared_path() -> Path | None:
    found = shutil.which("cloudflared")
    if found:
        return Path(found)
    exe = BIN_DIR / ("cloudflared.exe" if platform.system() == "Windows" else "cloudflared")
    return exe if exe.exists() else None


def _download() -> Path:
    """Tải cloudflared chính thức từ trang phát hành của Cloudflare trên GitHub (chỉ lần đầu)."""
    name, is_tgz = _asset_name()
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    target = BIN_DIR / ("cloudflared.exe" if platform.system() == "Windows" else "cloudflared")
    tmp = BIN_DIR / (name + ".part")
    with httpx.stream("GET", _RELEASE + name, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    if is_tgz:
        with tarfile.open(tmp) as tar:
            member = next(m for m in tar.getmembers() if m.name.endswith("cloudflared") and m.isfile())
            src = tar.extractfile(member)
            assert src is not None
            target.write_bytes(src.read())
        tmp.unlink()
    else:
        tmp.replace(target)
    target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return target


def status() -> dict:
    proc = _state["proc"]
    running = proc is not None and proc.poll() is None
    return {"running": running, "starting": _state["starting"], "url": _state["url"] if running else None,
            "error": _state["error"], "installed": cloudflared_path() is not None,
            "log": _state["log"][-12:]}


def _reader(proc: subprocess.Popen) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        with _lock:
            _state["log"] = (_state["log"] + [line])[-60:]
            m = _URL_RE.search(line)
            if m and not _state["url"]:
                _state["url"] = m.group(0)
                _state["error"] = None
    with _lock:
        if _state["proc"] is proc and not _state["error"]:
            _state["error"] = "Đường hầm đã dừng." if _state["url"] else "Không tạo được đường hầm - xem nhật ký."


def start(port: int | None = None, wait: float = 25.0) -> dict:
    """Mở đường hầm tới máy chủ cục bộ; chờ tối đa `wait` giây để nhận địa chỉ https."""
    with _lock:
        proc = _state["proc"]
        if proc is not None and proc.poll() is None:
            return status()
        _state.update(url=None, error=None, log=[], starting=True)
    try:
        exe = cloudflared_path() or _download()
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0  # type: ignore[attr-defined]
        proc = subprocess.Popen(
            [str(exe), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port or settings.port}"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            creationflags=flags)
    except Exception as exc:  # noqa: BLE001
        with _lock:
            _state.update(starting=False, error=f"Không khởi động được cloudflared: {exc}")
        return status()
    with _lock:
        _state["proc"] = proc
    threading.Thread(target=_reader, args=(proc,), daemon=True).start()
    deadline = time.time() + wait
    while time.time() < deadline and not _state["url"] and proc.poll() is None:
        time.sleep(0.25)
    with _lock:
        _state["starting"] = False
        if not _state["url"] and proc.poll() is None:
            _state["error"] = "Đang chờ Cloudflare cấp địa chỉ… bấm 'Làm mới' sau vài giây."
    return status()


def stop() -> dict:
    with _lock:
        proc = _state["proc"]
        _state.update(proc=None, url=None, error=None, starting=False)
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return status()
