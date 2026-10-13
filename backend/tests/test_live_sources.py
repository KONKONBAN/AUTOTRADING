"""Nguồn dữ liệu thật (2026): giả lập phản hồi đúng định dạng của từng API - không cần Internet.

Kiểm tra: đơn vị giá (VND / nghìn đồng / điểm chỉ số), múi giờ của ngày giao dịch, chuyển nguồn khi lỗi,
bỏ qua nguồn chính thức khi chưa có khóa, ngắt mạch máy chủ lỗi, đọc BCTC KBS / Vietcap.
"""
import dataclasses
from datetime import date

import pandas as pd
import pytest

from app.data import fundamentals as fd
from app.data import http, providers

VN_MIDNIGHT_OCT9 = 1791478800  # 2026-10-09 00:00 giờ VN = 2026-10-08 17:00 UTC


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        if isinstance(self._p, Exception):
            raise self._p
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("err", request=None, response=None)


@pytest.fixture()
def route(monkeypatch):
    """route(fn): fn(method, url, params, json, headers) → payload | (payload, status)."""
    http.reset_all()
    calls = []

    def install(fn):
        def fake_request(method, url, params=None, json=None, headers=None, timeout=None, follow_redirects=None):
            calls.append({"method": method, "url": url, "params": params or {}, "json": json, "headers": headers})
            out = fn(method, url, params or {}, json, headers or {})
            return FakeResp(*out) if isinstance(out, tuple) else FakeResp(out)
        monkeypatch.setattr(http.httpx, "request", fake_request)
        return calls
    yield install
    http.reset_all()


def _bars(n=40, start=VN_MIDNIGHT_OCT9 - 86400 * 39, close=135_000.0):
    t = [start + 86400 * i for i in range(n)]
    return t, [close] * n


def test_kbs_prices_in_vnd_and_index_in_points(route):
    def fn(method, url, params, body, headers):
        rows = [{"t": f"2026-09-{d:02d} 00:00:00", "o": 134000, "h": 136000, "l": 133000, "c": 135000, "v": 1e6}
                for d in range(1, 31)] + [{"t": "2026-10-09T00:00:00+07:00", "o": 1, "h": 1, "l": 1, "c": 135500, "v": 1}]
        if "/index/VNINDEX/" in url:
            rows = [{**r, "c": 1700.5} for r in rows]
        return {"data_day": rows}
    calls = route(fn)
    df = providers._fetch_kbs("FPT", date(2026, 9, 1), date(2026, 10, 9))
    assert df["close"].iloc[-1] == 135_500 and df["date"].iloc[-1] == pd.Timestamp("2026-10-09")
    assert calls[0]["params"] == {"sdate": "01-09-2026", "edate": "09-10-2026"}
    idx = providers._fetch_kbs("VNINDEX", date(2026, 9, 1), date(2026, 10, 9))
    assert idx["close"].iloc[-1] == 1700.5 and "/index/VNINDEX/data_day" in calls[-1]["url"]


def test_vci_one_symbol_and_vietnam_timezone(route):
    t, c = _bars()

    def fn(method, url, params, body, headers):
        assert method == "POST" and body["symbols"] in (["FPT"], ["VNINDEX"]) and body["timeFrame"] == "ONE_DAY"
        assert headers["Referer"].startswith("https://trading.vietcap.com.vn")
        return [{"symbol": body["symbols"][0], "t": t, "o": c, "h": c, "l": c, "c": c, "v": [1000] * len(t)}]
    route(fn)
    df = providers._fetch_vci("FPT", date(2026, 8, 1), date(2026, 10, 9))
    assert df["date"].iloc[-1] == pd.Timestamp("2026-10-09")   # KHÔNG bị lùi về 08/10 (lỗi múi giờ cũ)
    assert df["close"].iloc[-1] == 135_000                     # VND, không nhân 1000


def test_dchart_thousand_vnd_scaled_but_not_penny_heuristic(route):
    t, _ = _bars()

    def fn(method, url, params, body, headers):
        price = 0.8 if params["symbol"] == "PENNY" else 1700.0 if params["symbol"] == "VNINDEX" else 135.0
        return {"s": "ok", "t": t, "o": [price] * 40, "h": [price] * 40, "l": [price] * 40, "c": [price] * 40,
                "v": [1] * 40}
    route(fn)
    assert providers._fetch_vndirect("FPT", date(2026, 8, 1), date(2026, 10, 9))["close"].iloc[-1] == 135_000
    assert providers._fetch_vndirect("PENNY", date(2026, 8, 1), date(2026, 10, 9))["close"].iloc[-1] == 800
    assert providers._fetch_vndirect("VNINDEX", date(2026, 8, 1), date(2026, 10, 9))["close"].iloc[-1] == 1700


def test_cafef_adjusted_prices_and_pagination(route):
    def fn(method, url, params, body, headers):
        assert params["StartDate"] == "2026-08-01"
        if params["PageIndex"] == 1:
            rows = [{"Ngay": f"{d:02d}/09/2026", "GiaMoCua": 100, "GiaCaoNhat": 110, "GiaThapNhat": 90,
                     "GiaDongCua": 100, "GiaDieuChinh": 50, "KhoiLuongKhopLenh": 10} for d in range(1, 31)]
            return {"Data": {"Data": rows}}
        return {"Data": {"Data": []}}
    calls = route(fn)
    df = providers._fetch_cafef("HPG", date(2026, 8, 1), date(2026, 10, 9))
    assert df["close"].iloc[0] == 50_000 and df["high"].iloc[0] == 55_000  # điều chỉnh theo GiaDieuChinh
    assert df.attrs["adjusted"] is True and len(calls) == 1                # < 1000 dòng → dừng phân trang


def test_keyed_sources_skipped_without_keys_and_failover(route, monkeypatch):
    t, c = _bars()

    def fn(method, url, params, body, headers):
        if "kbsec" in url:
            return {"error": "maintenance"}, 503
        if "vietcap" in url:
            return [{"t": t, "o": c, "h": c, "l": c, "c": c, "v": c}]
        raise AssertionError(f"không được gọi {url}")
    calls = route(fn)
    monkeypatch.setattr(providers, "get_db", providers.get_db)
    providers.get_db().set_kv("preferred_provider", None)
    df, src, attempts = providers.fetch_live("FPT", date(2026, 8, 1), date(2026, 10, 9))
    assert src == "vci" and [a["provider"] for a in attempts] == ["kbs", "vci"]
    assert not any("ssi.com.vn" in x["url"] or "dnse" in x["url"] for x in calls)
    assert http.host_down("https://kbbuddywts.kbsec.com.vn/x") > 0           # máy chủ lỗi bị tạm bỏ qua


def test_ssi_fastconnect_when_keys_configured(route, monkeypatch):
    s = dataclasses.replace(providers.settings, ssi_api_key="k", ssi_api_secret="s")
    monkeypatch.setattr(providers, "settings", s)
    providers._ssi_token.update(token=None, exp=0)

    def fn(method, url, params, body, headers):
        if url.endswith("/auth/token"):
            assert body == {"apiKey": "k", "apiSecret": "s"}
            return {"data": {"accessToken": "TOKEN", "expiresAt": 9_999_999_999}}
        assert headers["Authorization"] == "Bearer TOKEN" and params["timeFrame"] == "1d"
        return {"data": [{"tradingDate": f"{d:02d}/09/2026", "open": 27000, "high": 27500, "low": 26800,
                          "close": 27250, "volume": 5e6} for d in range(1, 31)]}
    route(fn)
    df = providers._fetch_ssi("HPG", date(2026, 9, 1), date(2026, 9, 30))
    assert df["close"].iloc[-1] == 27250 and df["date"].iloc[-1] == pd.Timestamp("2026-09-30")


def test_dnse_request_is_signed(route, monkeypatch):
    s = dataclasses.replace(providers.settings, dnse_api_key="KEY", dnse_api_secret="SECRET")
    monkeypatch.setattr(providers, "settings", s)
    t, _ = _bars()

    def fn(method, url, params, body, headers):
        sig = headers["X-Signature"]
        assert headers["x-api-key"] == "KEY" and 'keyId="KEY"' in sig and 'algorithm="hmac-sha256"' in sig
        assert 'headers="(request-target) date"' in sig and headers["Date"].endswith("GMT")
        assert params["type"] == "STOCK" and params["resolution"] == "1D"
        return {"t": t, "o": [23.1] * 40, "h": [23.1] * 40, "l": [23.1] * 40, "c": [23.1] * 40, "v": [1] * 40}
    route(fn)
    assert providers._fetch_dnse("HPG", date(2026, 8, 1), date(2026, 10, 9))["close"].iloc[-1] == pytest.approx(23_100)


# ------------------------------------------------------------------ BCTC tự động
_KBS = {  # đơn vị nghìn đồng (như API KBS với unit=1000): 70_000_000_000 = 70.000 tỷ
    "CDKT": [("TỔNG CỘNG TÀI SẢN", 70_000_000_000), ("A. Tài sản ngắn hạn", 40_000_000_000),
             ("I. Tiền và các khoản tương đương tiền", 9_000_000_000), ("IV. Hàng tồn kho", 4_000_000_000),
             ("C. NỢ PHẢI TRẢ", 38_000_000_000), ("I. Nợ ngắn hạn", 30_000_000_000),
             ("Vay và nợ thuê tài chính ngắn hạn", 15_000_000_000), ("Vay và nợ thuê tài chính dài hạn", 3_000_000_000),
             ("D. VỐN CHỦ SỞ HỮU", 32_000_000_000), ("1. Vốn góp của chủ sở hữu", 14_700_000_000),
             ("Lợi nhuận sau thuế chưa phân phối", 9_500_000_000)],
    "KQKD": [("3. Doanh thu thuần về bán hàng và cung cấp dịch vụ", 62_800_000_000),
             ("5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ", 24_000_000_000),
             ("Trong đó: Chi phí lãi vay", 700_000_000), ("15. Tổng lợi nhuận kế toán trước thuế", 11_000_000_000),
             ("17. Lợi nhuận sau thuế thu nhập doanh nghiệp", 9_400_000_000),
             ("Lợi nhuận sau thuế của cổ đông của Công ty mẹ", 7_800_000_000)],
    "LCTT": [("Khấu hao TSCĐ và BĐSĐT", 2_800_000_000), ("Lưu chuyển tiền thuần từ hoạt động kinh doanh", 9_100_000_000),
             ("1. Tiền chi để mua sắm, xây dựng TSCĐ và các tài sản dài hạn khác", -4_000_000_000)],
}


def test_kbs_financials_parsed_with_units_and_shares(route):
    def fn(method, url, params, body, headers):
        assert "/stock/finance-info/FPT" in url and params["pageSize"] == 1 and params["unit"] == 1000
        page, kind = params["page"], params["type"]
        if page > 3:
            return {"Head": [], "Content": {}}
        scale = 1 - 0.1 * (page - 1)
        return {"Head": [{"ID": 1, "YearPeriod": 2025 - page + 1, "TermName": "Năm"}],
                "Content": {"x": [{"ID": i, "Name": n, "Value1": v * scale}  # nghìn đồng
                                  for i, (n, v) in enumerate(_KBS[kind])]}}
    route(fn)
    rows = fd._live_kbs("FPT")
    assert [r["year"] for r in rows] == [2023, 2024, 2025]
    last = rows[-1]
    assert last["revenue"] == pytest.approx(62_800) and last["net_income"] == pytest.approx(7_800)  # tỷ, cổ đông mẹ
    assert last["total_debt"] == pytest.approx(18_000) and last["capex"] == pytest.approx(4_000)
    assert last["shares"] == pytest.approx(1_470) and last["eps"] == pytest.approx(7_800e9 / 1_470e6)
    assert last["operating_cf"] == pytest.approx(9_100) and "total_debt" not in last["estimated_fields"]


def test_bank_statement_net_income_to_parent_bank(route):
    bank = {
        "CDKT": [("TỔNG CỘNG TÀI SẢN", 2_085_000_000_000), ("TỔNG NỢ PHẢI TRẢ", 1_880_000_000_000),
                 ("VIII. Vốn và các quỹ", 205_000_000_000), ("a. Vốn điều lệ", 83_500_000_000)],
        "KQKD": [("I. Thu nhập lãi thuần", 55_000_000_000), ("Tổng thu nhập hoạt động", 68_000_000_000),
                 ("2. Chi phí lãi và các chi phí tương tự", 60_000_000_000),
                 ("XI. Tổng lợi nhuận trước thuế (IX-X)", 42_000_000_000),
                 ("XIII. Lợi nhuận sau thuế", 33_900_000_000),
                 ("XV. Lợi nhuận sau thuế của cổ đông của Ngân hàng mẹ (XIII-XIV)", 33_800_000_000)],
        "LCTT": [("Lưu chuyển tiền thuần từ hoạt động kinh doanh", 20_000_000_000)],
    }

    def fn(method, url, params, body, headers):
        if params.get("page", 1) > 1:
            return {"Head": [], "Content": {}}
        return {"Head": [{"ID": 1, "YearPeriod": 2025}],
                "Content": {"x": [{"Name": n, "Value1": v} for n, v in bank[params["type"]]]}}
    route(fn)
    r = fd._live_kbs("VCB")[-1]
    assert r["net_income"] == pytest.approx(33_800) and r["revenue"] == pytest.approx(68_000)
    assert r["equity"] == pytest.approx(205_000) and r["shares"] == pytest.approx(8_350)


def test_vci_financials_via_metrics_titles(route):
    def fn(method, url, params, body, headers):
        if url.endswith("/metrics"):
            return {"data": {"BALANCE_SHEET": [{"field": "bsa1", "titleVi": "TỔNG CỘNG TÀI SẢN"},
                                               {"field": "bsa2", "titleVi": "VỐN CHỦ SỞ HỮU"}],
                             "INCOME_STATEMENT": [{"field": "isa1", "titleVi": "Doanh thu thuần"},
                                                  {"field": "isa2", "titleVi": "Lợi nhuận sau thuế của Cổ đông công ty mẹ"}],
                             "CASH_FLOW": []}}
        data = {"BALANCE_SHEET": [{"yearReport": 2024, "bsa1": 6.0e13, "bsa2": 2.8e13},
                                  {"yearReport": 2025, "bsa1": 7.0e13, "bsa2": 3.2e13}],
                "INCOME_STATEMENT": [{"yearReport": 2024, "isa1": 5.2e13, "isa2": 6.5e12},
                                     {"yearReport": 2025, "isa1": 6.28e13, "isa2": 7.8e12}],
                "CASH_FLOW": []}[params["section"]]
        return {"data": {"years": data}}
    route(fn)
    r = fd._live_vci("FPT")[-1]
    assert r["total_assets"] == pytest.approx(70_000) and r["net_income"] == pytest.approx(7_800)  # VND → tỷ (đoán)


def test_financials_fall_back_kbs_to_vci(route, monkeypatch):
    monkeypatch.setattr(fd, "_live_kbs", lambda t: (_ for _ in ()).throw(RuntimeError("KBS lỗi")))
    monkeypatch.setattr(fd, "_live_vci", lambda t: [{"year": 2025}])
    rows, src = fd._live("FPT")
    assert src == "vci"


# ------------------------------------------------------------------ danh sách mã niêm yết
def test_full_listing_kbs_with_icb_sectors(route, monkeypatch):
    from app.data import listing, universe
    monkeypatch.setattr(listing, "settings", dataclasses.replace(listing.settings, data_mode="auto"))
    monkeypatch.setattr(listing, "_mem", None)

    def fn(method, url, params, body, headers):
        if "kbsec" in url:
            rows = [{"symbol": f"S{i:03d}", "name": f"CTCP {i}", "exchange": "HSX", "type": "stock"} for i in range(150)]
            rows += [{"symbol": "PVS", "name": "Tổng CTCP Dịch vụ Kỹ thuật Dầu khí", "exchange": "XHNF", "type": "stock"},
                     {"symbol": "BSR", "name": "Lọc hóa dầu Bình Sơn", "exchange": "UPCOM", "type": "stock"},
                     {"symbol": "E1VFVN30", "name": "ETF", "exchange": "HSX", "type": "fund"}]
            return rows
        if "search-bar" in url:
            return {"data": [{"code": "BSR", "icbLv2": {"code": "0500", "name": "Dầu khí"}}]}
        raise AssertionError(url)
    route(fn)
    stocks = listing.refresh()
    assert stocks["PVS"]["exchange"] == "HNX" and stocks["BSR"]["exchange"] == "UPCOM"
    assert "E1VFVN30" not in stocks and stocks["BSR"]["sector"] == "Dầu khí"
    assert universe.is_listed("BSR") and not universe.is_listed("ZZZZ")
    info = universe.info("BSR")
    assert info["exchange"] == "UPCOM" and info["sector"] == "Dầu khí" and info["name"].startswith("Lọc hóa dầu")
    from app.trading import vn_rules
    lim = vn_rules.price_limits(20_000, info["exchange"])
    assert lim.ceiling == pytest.approx(23_000)  # UPCoM ±15%
    monkeypatch.setattr(listing, "_mem", None)


def test_listing_falls_back_to_vietcap(route, monkeypatch):
    from app.data import listing
    monkeypatch.setattr(listing, "settings", dataclasses.replace(listing.settings, data_mode="auto"))
    monkeypatch.setattr(listing, "_mem", None)

    def fn(method, url, params, body, headers):
        if "kbsec" in url:
            return {"err": 1}, 503
        if "getAll" in url:
            return [{"symbol": f"V{i:03d}", "type": "STOCK", "board": "HSX", "organName": f"Cty {i}"} for i in range(120)]
        return {"data": []}
    route(fn)
    assert len(listing.refresh()) == 120 and listing.source() == "vci"
    monkeypatch.setattr(listing, "_mem", None)
