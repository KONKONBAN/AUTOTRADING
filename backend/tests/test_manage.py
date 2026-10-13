"""Công cụ dòng lệnh manage.py: tạo quản trị viên, đặt lại mật khẩu (khi quên / chạy bằng Docker)."""
import importlib.util
from pathlib import Path

from app import auth

_spec = importlib.util.spec_from_file_location("manage", Path(__file__).resolve().parents[2] / "manage.py")
manage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(manage)


def _answers(monkeypatch, *passwords):
    it = iter(passwords)
    monkeypatch.setattr(manage.getpass, "getpass", lambda prompt="": next(it))


def test_create_admin_and_reset_password(monkeypatch, capsys):
    _answers(monkeypatch, "matkhau-cli-1", "matkhau-cli-1")
    assert manage.main(["create-admin", "--username", "Quan.Tri", "--name", "Quản trị CLI"]) == 0
    user = auth.authenticate("quan.tri", "matkhau-cli-1", "cli-test")
    assert user["role"] == "admin"

    auth.update_user(user["id"], disabled=True)
    # lần nhập lại sai → hỏi lại; sau đó đặt mật khẩu mới, mở khóa, đăng xuất mọi thiết bị
    _answers(monkeypatch, "matkhau-moi-2", "khac-nhau-9", "matkhau-moi-2", "matkhau-moi-2")
    assert manage.main(["reset-password", "quan.tri"]) == 0
    assert "Hai lần nhập không khớp" in capsys.readouterr().out
    again = auth.authenticate("quan.tri", "matkhau-moi-2", "cli-test")
    assert not again["disabled"]

    assert manage.main(["reset-password", "khong-ton-tai"]) == 1
    _answers(monkeypatch, "ngan", "ngan")
    assert manage.main(["create-admin", "--username", "admin2", "--name", "x"]) == 1   # mật khẩu yếu → báo lỗi
    assert manage.main(["list-users"]) == 0
    assert "quan.tri" in capsys.readouterr().out
