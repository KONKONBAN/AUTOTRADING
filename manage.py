"""Quản lý tài khoản từ dòng lệnh (dùng khi quên mật khẩu hoặc chạy bằng Docker/máy chủ).

    python manage.py list-users
    python manage.py create-admin            # tạo quản trị viên (lần đầu: nhận luôn dữ liệu cũ)
    python manage.py reset-password <tên>    # đặt lại mật khẩu, mở khóa và đăng xuất mọi thiết bị

Windows: .venv\\Scripts\\python.exe manage.py reset-password <tên>
Docker:  docker exec -it <container> python manage.py create-admin
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def _ask_password() -> str:
    while True:
        pw = getpass.getpass("Mật khẩu mới (≥ 8 ký tự, có chữ và số): ")
        if pw == getpass.getpass("Nhập lại mật khẩu: "):
            return pw
        print("Hai lần nhập không khớp - thử lại.")


def main(argv: list[str] | None = None) -> int:
    _utf8()
    parser = argparse.ArgumentParser(description="Quản lý tài khoản AutoTrading VN")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-users", help="Liệt kê tài khoản")
    ca = sub.add_parser("create-admin", help="Tạo tài khoản quản trị viên")
    ca.add_argument("--username")
    ca.add_argument("--name", help="Tên hiển thị")
    rp = sub.add_parser("reset-password", help="Đặt lại mật khẩu và mở khóa một tài khoản")
    rp.add_argument("username")
    args = parser.parse_args(argv)

    from app import auth  # noqa: PLC0415 - nạp sau khi đã thêm backend vào sys.path

    try:
        if args.cmd == "list-users":
            users = auth.list_users()
            if not users:
                print("Chưa có tài khoản nào - chạy: python manage.py create-admin")
            for u in users:
                last = datetime.fromtimestamp(u["last_login_at"]).strftime("%d/%m/%Y %H:%M") if u["last_login_at"] else "chưa"
                state = " (đang khóa)" if u["disabled"] else ""
                print(f"- {u['username']:<20} {u['role']:<6} {u['display_name']}{state} · đăng nhập gần nhất: {last}")
        elif args.cmd == "create-admin":
            username = args.username or input("Tên đăng nhập: ").strip()
            name = args.name or input("Tên hiển thị (Enter để bỏ qua): ").strip() or None
            password = _ask_password()
            if auth.user_count() == 0:
                user = auth.setup_admin(username, password, name)
            else:
                user = auth.create_user(username, password, name, role="admin")
            print(f"✅ Đã tạo quản trị viên '{user['username']}'. Mở ứng dụng và đăng nhập.")
        elif args.cmd == "reset-password":
            username = auth.normalize_username(args.username)
            row = next((u for u in auth.list_users() if u["username"] == username), None)
            if not row:
                print(f"Không có tài khoản '{username}'. Dùng 'list-users' để xem danh sách.")
                return 1
            auth.update_user(row["id"], password=_ask_password(), disabled=False)
            print(f"✅ Đã đặt lại mật khẩu cho '{username}' (đã mở khóa, mọi thiết bị phải đăng nhập lại).")
            print("   Nếu vừa nhập sai quá nhiều lần, hãy khởi động lại ứng dụng để xóa lệnh chặn tạm thời.")
    except auth.AuthError as exc:
        print(f"[LỖI] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
