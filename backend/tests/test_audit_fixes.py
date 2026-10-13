"""Kiểm thử hồi quy cho các lỗi tìm thấy ở vòng rà soát bảo mật & giao dịch."""
import asyncio
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

import pandas as pd
import pytest
from conftest import login
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import auth, main
from app.context import as_user, current_user_id
from app.data import providers
from app.db import get_db
from app.trading import backtest, engine, vn_rules
from app.trading.broker import OrderError, get_broker, quote


def _user(role: str = "user") -> tuple[dict, str]:
    pw = "matkhau-" + uuid.uuid4().hex[:6]
    return auth.create_user("a" + uuid.uuid4().hex[:8], pw, role=role), pw


def _auto_mode(monkeypatch):
    """DATA_MODE=auto cho mọi module đang giữ tham chiếu tới settings (dataclass bất biến)."""
    import dataclasses
    import sys

    from app.config import settings
    auto = dataclasses.replace(settings, data_mode="auto")
    for name, mod in list(sys.modules.items()):
        if name.startswith("app") and getattr(mod, "settings", None) is settings:
            monkeypatch.setattr(mod, "settings", auto)


def _hist(closes: list[float], end: date | None = None) -> pd.DataFrame:
    idx = pd.bdate_range(end=pd.Timestamp(end or date.today()), periods=len(closes))
    df = pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1e6}, index=idx)
    df.index.name = "date"
    df.attrs["source"] = "kbs"
    return df


# ------------------------------------------------------------------ bảo mật
def test_shared_market_data_is_admin_only():
    with TestClient(main.app) as c:
        u, pw = _user()
        login(c, u["username"], pw)
        csv = "Ticker,Date,Open,High,Low,Close,Volume\n" + "\n".join(
            f"FPT,2026{m:02d}{d:02d},1,1,1,1000,100" for m in range(1, 4) for d in range(1, 15))
        assert c.post("/api/prices/upload", files={"file": ("p.csv", csv)}).status_code == 403
        assert c.delete("/api/prices/imported/FPT").status_code == 403
        assert c.put("/api/financials/FPT/manual", json={"rows": [{"year": 2025, "revenue": 1}]}).status_code == 403
        assert c.delete("/api/financials/FPT/manual").status_code == 403
        assert c.post("/api/data/listing/refresh").status_code == 403
        assert c.get("/api/financials/FPT").status_code == 200  # vẫn xem được


def _request(peer: str, headers: dict[str, str]) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "client": (peer, 1234), "server": ("x", 80),
                    "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()], "query_string": b""})


def test_client_ip_ignores_spoofed_headers_from_lan():
    spoof = {"X-Real-IP": "1.2.3.4", "X-Forwarded-For": "5.6.7.8", "CF-Connecting-IP": "9.9.9.9"}
    assert auth.client_ip(_request("192.168.1.50", spoof)) == "192.168.1.50"
    assert auth.client_ip(_request("127.0.0.1", {"CF-Connecting-IP": "113.161.1.2"})) == "113.161.1.2"  # cloudflared


def test_parallel_login_attempts_respect_lockout(monkeypatch):
    auth._failures.clear()
    calls = []

    def slow_verify(password, stored):
        calls.append(1)
        time.sleep(0.02)
        return False

    monkeypatch.setattr(auth, "_verify_password", slow_verify)
    errors = []

    def attempt():
        try:
            auth.authenticate("nan-nhan", "sai", "10.0.0.9")
        except auth.AuthError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=attempt) for _ in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    auth._failures.clear()
    assert len(calls) == auth.MAX_FAILURES  # chỉ 8 lần thử được kiểm tra mật khẩu, còn lại bị chặn
    assert sum("quá nhiều lần" in e for e in errors) == 30 - auth.MAX_FAILURES


def test_autotrader_config_rejects_nan_and_bad_time():
    with pytest.raises(ValueError):
        engine.save_config({"risk_per_trade": "nan"})
    with pytest.raises(ValueError):
        engine.save_config({"max_weight": 5})
    with pytest.raises(ValueError):
        engine.save_config({"run_time": "25:99"})
    assert engine.load_config().risk_per_trade == pytest.approx(0.015)


def test_scheduler_isolates_failing_account(monkeypatch):
    a, _ = _user()
    b, _ = _user()
    for u in (a, b):
        with as_user(u["id"]):
            engine.save_config({"mode": "suggest", "run_time": "09:00"})
    ran = []

    def fake_cycle(cfg):
        if current_user_id() == a["id"]:
            raise RuntimeError("thiếu dữ liệu")
        ran.append(current_user_id())
        return {}

    monkeypatch.setattr(engine, "run_cycle", fake_cycle)
    monday = datetime(2026, 10, 12, 14, 30)
    asyncio.run(main.run_due_autotrader(monday))
    assert b["id"] in ran
    asyncio.run(main.run_due_autotrader(monday + timedelta(minutes=1)))  # không thử lại mỗi phút
    assert ran.count(b["id"]) == 1
    with as_user(a["id"]):
        assert engine.last_attempt().startswith("2026-10-12")
    for u in (a, b):
        with as_user(u["id"]):
            engine.save_config({"mode": "off"})


# ------------------------------------------------------------------ giao dịch
def test_price_limits_exact_for_all_exchanges():
    assert vn_rules.price_limits(28_000, "UPCOM").ceiling == 32_200
    assert vn_rules.price_limits(6_000, "UPCOM").ceiling == 6_900
    assert vn_rules.price_limits(57_200, "HOSE").ceiling == 61_200
    for ex, band in (("HOSE", Decimal("0.07")), ("HNX", Decimal("0.10")), ("UPCOM", Decimal("0.15"))):
        for ref in range(1_000, 120_001, 700):
            ref = vn_rules.round_to_tick(ref, ex)
            lim = vn_rules.price_limits(ref, ex)
            c, f = Decimal(str(ref)) * (1 + band), Decimal(str(ref)) * (1 - band)
            tc, tf = Decimal(int(vn_rules.tick_size(float(c), ex))), Decimal(int(vn_rules.tick_size(float(f), ex)))
            assert lim.ceiling == float((c / tc).to_integral_value(ROUND_FLOOR) * tc), (ex, ref)
            assert lim.floor == float((f / tf).to_integral_value(ROUND_CEILING) * tf), (ex, ref)


def test_off_tick_limit_never_rounded_against_user():
    b = get_broker()
    b.reset(500_000_000)
    last = quote("FPT")["last"]
    filled = b.place_order("FPT", "BUY", 100, last + 40)  # 40đ lệch bước giá: làm tròn XUỐNG về giá thị trường
    assert filled["price"] == last
    with pytest.raises(OrderError):
        b.place_order("FPT", "BUY", 100, last - 40)  # làm tròn xuống dưới giá thị trường → không khớp
    b.reset(500_000_000)


def test_quote_reference_and_staleness(monkeypatch):
    friday = date(2026, 10, 9)
    monkeypatch.setattr(providers, "get_history", lambda t, days=60: _hist([30_000, 32_100], end=friday))
    monkeypatch.setattr(providers, "today_vn", lambda: date(2026, 10, 10))  # thứ Bảy
    q = quote("FPT")
    assert q["reference"] == 32_100 and q["limits"].ceiling == 34_300  # tham chiếu phiên thứ Hai
    monkeypatch.setattr(providers, "today_vn", lambda: friday)  # đang trong phiên thứ Sáu
    assert quote("FPT")["reference"] == 30_000
    monkeypatch.setattr(providers, "today_vn", lambda: friday + timedelta(days=40))
    with pytest.raises(OrderError, match="đã cũ"):
        quote("FPT")


def test_stale_imported_file_does_not_hide_live_prices(monkeypatch):
    db = get_db()
    old_end = date.today() - timedelta(days=200)
    days = pd.bdate_range(end=pd.Timestamp(old_end), periods=40)
    db.execute("DELETE FROM imported_prices WHERE ticker='ZZQ'")
    for d in days:
        db.execute("INSERT INTO imported_prices(ticker, date, open, high, low, close, volume) VALUES(?,?,?,?,?,?,?)",
                   ("ZZQ", d.strftime("%Y-%m-%d"), 1, 1, 1, 21_500, 100))
    live = _hist([27_000] * 50).reset_index()
    _auto_mode(monkeypatch)
    monkeypatch.setattr(providers, "fetch_live", lambda t, s, e: (live, "kbs", []))
    db.execute("DELETE FROM cache WHERE key LIKE 'hist:ZZQ:%'")
    assert providers.get_history("ZZQ").attrs["source"] == "kbs"

    def down(t, s, e):
        raise providers.DataUnavailable("mất mạng")

    monkeypatch.setattr(providers, "fetch_live", down)
    db.execute("DELETE FROM cache WHERE key LIKE 'hist:ZZQ:%'")
    assert providers.get_history("ZZQ").attrs["source"] == "imported"  # nguồn tự động lỗi: dùng file cũ, không DEMO
    db.execute("DELETE FROM imported_prices WHERE ticker='ZZQ'")
    db.execute("DELETE FROM cache WHERE key LIKE 'hist:ZZQ:%'")


def test_stock_dividend_adjusts_lot_instead_of_fake_loss(monkeypatch):
    b = get_broker()
    b.reset(500_000_000)
    uid = current_user_id()
    buy_day = (pd.Timestamp(date.today()) - pd.offsets.BDay(30)).date()
    db = get_db()
    db.execute("INSERT INTO lots(user_id, ticker, quantity, price, buy_date, stop_loss, highest, anchor_date, anchor_close) "
               "VALUES(?,?,?,?,?,?,?,?,?)",
               (uid, "HPG", 1000, 27_000, buy_day.isoformat(), 25_110, 27_500,
                (pd.Timestamp(buy_day) - pd.offsets.BDay(1)).strftime("%Y-%m-%d"), 27_000))
    # chuỗi giá đã điều chỉnh sau khi chia cổ tức 10% bằng cổ phiếu: mọi giá quá khứ × 1/1,1
    adjusted = _hist([27_000 / 1.1] * 60 + [24_550])
    monkeypatch.setattr(providers, "get_history", lambda t, days=60: adjusted)
    pos = next(p for p in b.positions() if p["ticker"] == "HPG")
    assert pos["quantity"] == 1100
    assert pos["cost"] == pytest.approx(27_000_000)
    assert pos["stop_loss"] == pytest.approx(25_110 / 1.1)
    assert pos["unrealized_pct"] == pytest.approx(24_550 * 1100 / 27_000_000 - 1)
    b.positions()  # lần sau không điều chỉnh lặp lại
    assert next(p for p in b.positions() if p["ticker"] == "HPG")["quantity"] == 1100
    b.reset(500_000_000)


def test_demo_fallback_prices_never_drive_autotrader(monkeypatch):
    b = get_broker()
    b.reset(500_000_000)
    uid = current_user_id()
    buy_day = (pd.Timestamp(date.today()) - pd.offsets.BDay(10)).date().isoformat()
    get_db().execute("INSERT INTO lots(user_id, ticker, quantity, price, buy_date, highest) VALUES(?,?,?,?,?,?)",
                     (uid, "FPT", 1000, 95_000, buy_day, 96_000))
    _auto_mode(monkeypatch)

    def down(t, s, e):
        raise providers.DataUnavailable("mất mạng")

    monkeypatch.setattr(providers, "fetch_live", down)
    get_db().execute("DELETE FROM cache WHERE key LIKE 'hist:%'")
    main.services.clear_caches()
    plan = engine.plan_cycle(engine.AutoTraderConfig(mode="suggest"))
    assert not [a for a in plan["actions"] if a["ticker"] == "FPT"]
    assert any("FPT: chưa có giá thật" in n for n in plan["notes"])
    lot = get_db().query_one("SELECT highest FROM lots WHERE user_id=? AND ticker='FPT'", (uid,))
    assert lot["highest"] == 96_000  # đỉnh giá không bị ghi giá DEMO
    pos = next(p for p in b.positions() if p["ticker"] == "FPT")
    assert pos["market_price"] == pytest.approx(95_000) and not pos["price_ok"]
    b.snapshot_equity()
    assert not get_db().query("SELECT * FROM equity_history WHERE user_id=?", (uid,))
    get_db().execute("DELETE FROM cache WHERE key LIKE 'hist:%'")
    main.services.clear_caches()
    b.reset(500_000_000)


def test_backtest_rejects_unknown_tickers_and_reports_sources():
    with pytest.raises(ValueError, match="không hợp lệ"):
        backtest.run_backtest(tickers=["FPT", "HPGG"], days=400)
    r = backtest.run_backtest(tickers=["FPT", "HPG"], days=400)
    assert r["skipped_demo"] == [] and set(r["sources"]) == {"FPT", "HPG", "VNINDEX"}
