"""Dữ liệu báo cáo tài chính năm (đơn vị: tỷ đồng; cổ phiếu: triệu CP; EPS/BVPS/DPS: đồng).

Cấu trúc theo 3 báo cáo cơ bản (FQA - Session 2; KTTC2 - Chương 4):
- Bảng cân đối kế toán: Tài sản (A) = Nợ phải trả (D) + Vốn chủ sở hữu (E)
- Báo cáo KQKD: NI = REV - COGS - OC - Int - Tax
- Báo cáo lưu chuyển tiền tệ: NCF = ICF - OCF

Nguồn: số liệu người dùng nhập/tải Excel (ưu tiên) → KBS → Vietcap. Dữ liệu DEMO mô phỏng chỉ dùng khi
DATA_MODE=demo (không bao giờ bịa BCTC khi đang dùng dữ liệu thật).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date

import numpy as np

from ..config import settings
from ..db import get_db
from . import http, universe
from .providers import _seed

log = logging.getLogger(__name__)

# Hồ sơ ngành cho dữ liệu demo: (ROA, đòn bẩy D/E, biên LN ròng, P/E mục tiêu, tăng trưởng, payout)
SECTOR_PROFILE = {
    "Ngân hàng": (0.015, 10.0, 0.30, 8.5, 0.15, 0.15),
    "Bất động sản": (0.045, 1.6, 0.22, 14.0, 0.10, 0.10),
    "Chứng khoán": (0.050, 1.4, 0.35, 15.0, 0.12, 0.30),
    "Thép & Vật liệu": (0.060, 0.9, 0.07, 12.0, 0.08, 0.15),
    "Tiêu dùng": (0.120, 0.6, 0.14, 17.0, 0.07, 0.60),
    "Bán lẻ": (0.070, 1.3, 0.04, 18.0, 0.14, 0.25),
    "Công nghệ": (0.110, 0.9, 0.13, 20.0, 0.20, 0.35),
    "Năng lượng": (0.070, 0.8, 0.08, 13.0, 0.06, 0.50),
    "Hóa chất": (0.120, 0.4, 0.18, 12.0, 0.08, 0.40),
    "Công nghiệp": (0.090, 0.5, 0.12, 14.0, 0.07, 0.45),
    "Hàng không & Logistics": (0.050, 1.8, 0.06, 16.0, 0.12, 0.20),
    "Bảo hiểm": (0.020, 5.0, 0.08, 14.0, 0.08, 0.40),
}
DEFAULT_PROFILE = (0.06, 1.0, 0.10, 13.0, 0.08, 0.30)
TAX_RATE = 0.20


def _demo(ticker: str, years: int = 6) -> list[dict]:
    meta = universe.info(ticker)
    roa0, lev0, margin0, pe0, g0, payout0 = SECTOR_PROFILE.get(meta["sector"], DEFAULT_PROFILE)
    rng = np.random.default_rng(_seed(ticker + "-fin"))
    quality = rng.normal(1.0, 0.25)  # chất lượng doanh nghiệp (ảnh hưởng ROA)
    g = g0 * rng.uniform(0.3, 1.6)
    end_year = date.today().year - 1
    total_assets = rng.uniform(5_000, 80_000) * (20 if meta["sector"] in {"Ngân hàng", "Bảo hiểm"} else 1)
    rows = []
    for k in range(years):
        year = end_year - years + 1 + k
        shock = rng.normal(0, 0.18)
        roa = max(roa0 * quality * (1 + shock), -0.03)
        lev = max(lev0 * rng.uniform(0.85, 1.15), 0.05)
        equity = total_assets / (1 + lev)
        liabilities = total_assets - equity
        debt = liabilities * (0.85 if meta["sector"] in {"Ngân hàng", "Bảo hiểm"} else rng.uniform(0.35, 0.6))
        ni = roa * total_assets
        margin = max(margin0 * rng.uniform(0.8, 1.2), 0.01)
        revenue = abs(ni) / margin if ni else total_assets * 0.3
        rd = rng.uniform(0.06, 0.10)
        interest = debt * rd if meta["sector"] not in {"Ngân hàng", "Bảo hiểm"} else 0.0
        ebt = ni / (1 - TAX_RATE)
        ebit = ebt + interest
        dep = total_assets * rng.uniform(0.02, 0.05)
        capex = dep * rng.uniform(0.8, 1.8)
        ocf = ni * rng.uniform(0.6, 1.4) + dep
        current_assets = total_assets * rng.uniform(0.35, 0.7)
        current_liab = liabilities * rng.uniform(0.5, 0.8)
        rows.append({
            "year": year, "revenue": revenue, "gross_profit": revenue * min(margin * 2.2, 0.6),
            "ebit": ebit, "interest_expense": interest, "pretax_income": ebt, "net_income": ni,
            "depreciation": dep, "total_assets": total_assets, "total_liabilities": liabilities,
            "total_debt": debt, "equity": equity, "current_assets": current_assets,
            "current_liabilities": current_liab, "inventory": current_assets * rng.uniform(0.1, 0.4),
            "cash": current_assets * rng.uniform(0.1, 0.3), "operating_cf": ocf, "capex": capex,
            "retained_earnings": equity * rng.uniform(0.15, 0.45),
        })
        total_assets *= 1 + g * rng.uniform(0.5, 1.5)
    # số cổ phiếu sao cho P/E ≈ P/E ngành ở giá tham khảo
    last_ni = max(rows[-1]["net_income"], 1.0)
    pe_target = pe0 * rng.uniform(0.7, 1.3)
    shares = last_ni * 1e9 * pe_target / meta["reference_price"] / 1e6  # triệu CP
    for r in rows:
        r["shares"] = shares
        r["eps"] = r["net_income"] * 1e9 / (shares * 1e6)
        r["bvps"] = r["equity"] * 1e9 / (shares * 1e6)
        r["dps"] = max(r["eps"] * payout0 * rng.uniform(0.6, 1.2), 0)
    return rows


# ---------------------------------------------------------------------------
# BCTC năm tự động: KBS (KB Securities) → Vietcap (VCI). TCBS đã ngừng API công khai (2026).
# Dữ liệu được dựng thành bảng "chỉ tiêu × năm" rồi đọc bằng CHÍNH bộ nhận diện chỉ tiêu tiếng Việt của tính
# năng nhập Excel (excel_import) - một bộ quy tắc duy nhất, đã kiểm thử cho cả file người dùng lẫn dữ liệu tự động.
# ---------------------------------------------------------------------------
KBS_BASE = "https://kbbuddywts.kbsec.com.vn/iis-server/investment"
VCI_IQ = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company"
VCI_HEADERS = {"Referer": "https://trading.vietcap.com.vn/", "Origin": "https://trading.vietcap.com.vn"}
FIN_YEARS = 6
Period = tuple[int, list[tuple[str, object]]]


def _kbs_statement(ticker: str, kind: str) -> list[Period]:
    """Một loại báo cáo KBS (KQKD | CDKT | LCTT) theo NĂM. API lỗi khi pageSize > 1 nên lấy từng kỳ một."""
    out: list[Period] = []
    for page in range(1, FIN_YEARS + 1):
        params: dict = {"page": page, "pageSize": 1, "type": kind, "unit": 1000, "termtype": 1}
        params.update({"code": ticker, "termType": 1} if kind == "LCTT" else {"languageid": 1})
        js = http.get_json(f"{KBS_BASE}/stock/finance-info/{ticker}", params) or {}
        head = js.get("Head") or []
        if not head:
            break
        h = head[0]
        try:
            year = int(str(h.get("YearPeriod"))[:4])
        except ValueError:
            break
        vkey = f"Value{h.get('ID') or 1}"
        lines = [(r.get("Name") or r.get("NameEn") or "", r.get(vkey, r.get("Value1")))
                 for rows in (js.get("Content") or {}).values() for r in (rows or [])]
        lines = [(n, v) for n, v in lines if n]
        if any(v not in (None, "", 0) for _, v in lines):
            out.append((year, lines))
    return out


def _grid(statements: list[list[Period]], unit_line: str | None) -> list[list]:
    years = sorted({y for st in statements for y, _ in st})
    grid: list[list] = [[unit_line]] if unit_line else []
    grid.append(["Chỉ tiêu", *years])
    for st in statements:
        values: dict[int, dict[str, object]] = {}
        order: list[str] = []
        for y, lines in st:
            for name, v in lines:
                values.setdefault(y, {}).setdefault(name, v)
                if name not in order:
                    order.append(name)
        for name in order:
            grid.append([name, *[values.get(y, {}).get(name) for y in years]])
    return grid


def _rows_from_grid(grid: list[list]) -> list[dict]:
    from .excel_import import _parse_grid  # tránh import vòng
    parsed = _parse_grid(grid)
    if not parsed:
        raise ValueError("không nhận diện được cấu trúc BCTC")
    rows = []
    for y in parsed["years"]:
        try:
            rows.append(_complete_row({k: v for k, v in y.items() if k == "year" or k in _FIELD_KEYS}))
        except ValueError:
            continue  # năm thiếu chỉ tiêu bắt buộc
    if not rows:
        raise ValueError("BCTC thiếu các chỉ tiêu bắt buộc")
    return rows[-FIN_YEARS:]


def _kbs_shares(ticker: str) -> float | None:
    """Số cổ phiếu lưu hành (triệu CP) từ hồ sơ doanh nghiệp KBS."""
    try:
        js = http.get_json(f"{KBS_BASE}/stockinfo/profile/{ticker}", {"l": 1}) or {}
        prof = js.get("data", js) if isinstance(js, dict) else {}
        n = float(prof.get("KLCPLH") or 0)
        return n / 1e6 if n > 0 else None
    except Exception:  # noqa: BLE001
        return None


def _fill_shares(rows: list[dict], shares: float | None) -> None:
    if not shares:
        return
    for i, r in enumerate(rows):
        if not r.get("shares"):
            r["shares"] = shares
            r["eps"] = r["net_income"] * 1e9 / (shares * 1e6)
            r["bvps"] = r["equity"] * 1e9 / (shares * 1e6)
            if i < len(rows) - 1:  # số CP hiện tại dùng cho năm cũ → chỉ là ước tính
                r.setdefault("estimated_fields", []).append("shares")


def _live_kbs(ticker: str) -> list[dict]:
    statements = [_kbs_statement(ticker, k) for k in ("CDKT", "KQKD", "LCTT")]
    if not statements[0] or not statements[1]:
        raise ValueError("KBS không có BCTC năm")
    rows = _rows_from_grid(_grid(statements, "Đơn vị: 1.000 VND"))
    if not rows[-1].get("shares"):
        _fill_shares(rows, _kbs_shares(ticker))
    return rows


def _live_vci(ticker: str) -> list[dict]:
    meta = (http.get_json(f"{VCI_IQ}/{ticker}/financial-statement/metrics", headers=VCI_HEADERS) or {}).get("data") or {}
    statements = []
    for section in ("BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW"):
        titles = {m["field"]: (m.get("titleVi") or m.get("fullTitleVi") or m.get("titleEn"))
                  for m in (meta.get(section) or []) if m.get("field")}
        js = http.get_json(f"{VCI_IQ}/{ticker}/financial-statement", {"section": section}, headers=VCI_HEADERS) or {}
        periods: list[Period] = []
        for rec in ((js.get("data") or {}).get("years") or []):
            if rec.get("yearReport"):
                periods.append((int(rec["yearReport"]),
                                [(titles[k], v) for k, v in rec.items() if k in titles and titles[k]]))
        statements.append(periods)
    if not statements[0] or not statements[1]:
        raise ValueError("Vietcap không có BCTC năm")
    return _rows_from_grid(_grid(statements, None))  # đơn vị: đoán theo độ lớn số liệu


def _live(ticker: str) -> tuple[list[dict], str]:
    errors = []
    for src, fn in (("kbs", _live_kbs), ("vci", _live_vci)):
        try:
            return fn(ticker), src
        except Exception as exc:  # noqa: BLE001 - thử nguồn tiếp theo
            errors.append(f"{src}: {exc}")
            log.info("BCTC %s lỗi cho %s: %s", src, ticker, exc)
    raise RuntimeError("; ".join(errors))


# ---------------------------------------------------------------------------
# Số liệu BCTC do người dùng nhập thủ công (ưu tiên cao nhất)
# ---------------------------------------------------------------------------
# (khóa, nhãn tiếng Việt, đơn vị) - dùng cho form nhập liệu trên giao diện và AI trích xuất
MANUAL_FIELDS: list[tuple[str, str, str]] = [
    ("revenue", "Doanh thu thuần", "tỷ đồng"),
    ("gross_profit", "Lợi nhuận gộp", "tỷ đồng"),
    ("interest_expense", "Chi phí lãi vay", "tỷ đồng"),
    ("pretax_income", "Lợi nhuận trước thuế", "tỷ đồng"),
    ("net_income", "Lợi nhuận sau thuế (cổ đông công ty mẹ)", "tỷ đồng"),
    ("depreciation", "Khấu hao TSCĐ", "tỷ đồng"),
    ("total_assets", "Tổng tài sản", "tỷ đồng"),
    ("current_assets", "Tài sản ngắn hạn", "tỷ đồng"),
    ("cash", "Tiền và tương đương tiền", "tỷ đồng"),
    ("inventory", "Hàng tồn kho", "tỷ đồng"),
    ("total_liabilities", "Nợ phải trả", "tỷ đồng"),
    ("current_liabilities", "Nợ ngắn hạn", "tỷ đồng"),
    ("total_debt", "Vay và nợ thuê tài chính (ngắn + dài hạn)", "tỷ đồng"),
    ("equity", "Vốn chủ sở hữu", "tỷ đồng"),
    ("retained_earnings", "Lợi nhuận sau thuế chưa phân phối", "tỷ đồng"),
    ("operating_cf", "Lưu chuyển tiền thuần từ HĐKD", "tỷ đồng"),
    ("capex", "Tiền chi mua sắm TSCĐ (capex)", "tỷ đồng"),
    ("shares", "Số cổ phiếu lưu hành", "triệu CP"),
    ("dps", "Cổ tức tiền mặt mỗi cổ phiếu", "đồng/CP"),
]
REQUIRED_FIELDS = ("revenue", "net_income", "total_assets", "equity")
_FIELD_KEYS = {k for k, _, _ in MANUAL_FIELDS}


def _complete_row(r: dict) -> dict:
    """Bổ sung các trường suy ra được từ số liệu nhập tay."""
    r = {k: (float(v) if isinstance(v, (int, float, str)) and str(v).strip() not in {"", "None"} else None)
         if k != "year" else int(v) for k, v in r.items() if k not in {"estimated_fields", "defaulted_fields"}}
    estimated: list[str] = []
    defaulted: list[str] = []  # bỏ trống → tính là 0 (không ghi lại thành số liệu "thật" khi sửa/tải file mẫu)
    for k in REQUIRED_FIELDS:
        if r.get(k) is None:
            raise ValueError(f"Năm {r.get('year')}: thiếu trường bắt buộc '{k}'")
    r.setdefault("total_liabilities", None)
    if r.get("total_liabilities") is None:
        r["total_liabilities"] = r["total_assets"] - r["equity"]
    if abs(r["total_assets"] - r["total_liabilities"] - r["equity"]) > 0.02 * r["total_assets"]:
        r["balance_warning"] = "Tổng tài sản ≠ Nợ phải trả + Vốn chủ sở hữu (lệch > 2%) - hãy kiểm tra lại."
    if r.get("current_liabilities") is None and r.get("current_assets"):
        # có tài sản ngắn hạn mà thiếu nợ ngắn hạn → ước tính như nguồn TCBS (60% nợ phải trả) và gắn cờ,
        # thay vì coi là 0 (hệ số thanh toán vô nghĩa)
        r["current_liabilities"] = r["total_liabilities"] * 0.6
        estimated.append("current_liabilities")
    for k in ("gross_profit", "interest_expense", "depreciation", "current_assets", "cash", "inventory",
              "current_liabilities", "retained_earnings", "capex", "dps"):
        if r.get(k) is None:
            defaulted.append(k)
        r[k] = r.get(k) or 0.0
    if r.get("total_debt") is None:  # 0 là hợp lệ (doanh nghiệp không vay nợ) - chỉ ước tính khi bỏ trống
        r["total_debt"] = r["total_liabilities"] * 0.5
        estimated.append("total_debt")
    if r.get("pretax_income") is None:
        r["pretax_income"] = r["net_income"] / (1 - TAX_RATE)
        estimated.append("pretax_income")
    r["ebit"] = r["pretax_income"] + r["interest_expense"]
    if r.get("operating_cf") is None:
        r["operating_cf"] = r["net_income"]
        estimated.append("operating_cf")
    if r.get("shares"):
        r["eps"] = r["net_income"] * 1e9 / (r["shares"] * 1e6)
        r["bvps"] = r["equity"] * 1e9 / (r["shares"] * 1e6)
    else:
        r["shares"] = r["eps"] = r["bvps"] = None
    r["estimated_fields"] = estimated
    r["defaulted_fields"] = defaulted
    return r


def list_manual(ticker: str) -> list[dict]:
    rows = get_db().query("SELECT year, data, updated_at FROM manual_financials WHERE ticker=? ORDER BY year",
                          (ticker.upper(),))
    return [{**json.loads(r["data"]), "year": r["year"], "updated_at": r["updated_at"]} for r in rows]


def save_manual(ticker: str, rows: list[dict]) -> list[dict]:
    ticker = ticker.upper()
    db = get_db()
    saved = []
    for raw in rows:
        clean = {k: raw.get(k) for k, _, _ in MANUAL_FIELDS}
        clean["year"] = int(raw["year"])
        _complete_row(dict(clean))  # kiểm tra hợp lệ
        db.execute("INSERT OR REPLACE INTO manual_financials(ticker, year, data, updated_at) VALUES(?,?,?,?)",
                   (ticker, clean["year"], json.dumps(clean), time.time()))
        saved.append(clean)
    db.execute("DELETE FROM cache WHERE key LIKE ?", (f"fin:{ticker}:%",))
    return saved


def delete_manual(ticker: str, year: int | None = None) -> None:
    db = get_db()
    if year is None:
        db.execute("DELETE FROM manual_financials WHERE ticker=?", (ticker.upper(),))
    else:
        db.execute("DELETE FROM manual_financials WHERE ticker=? AND year=?", (ticker.upper(), int(year)))
    db.execute("DELETE FROM cache WHERE key LIKE ?", (f"fin:{ticker.upper()}:%",))


def get_financials(ticker: str) -> dict:
    """BCTC năm của doanh nghiệp: {'source': ..., 'rows': [...], 'manual_years': [...]}.

    Số liệu nhập tay ghi đè số liệu tự động theo từng năm.
    """
    ticker = ticker.upper()
    db = get_db()
    key = f"fin:{ticker}:{settings.data_mode}"
    cached = db.cache_get(key)
    if cached:
        return cached
    result = None
    if settings.data_mode in {"auto", "live"} and ticker != "VNINDEX":
        try:
            rows, src = _live(ticker)
            result = {"source": src, "rows": rows}
        except Exception as exc:  # noqa: BLE001
            log.info("Không lấy được BCTC tự động cho %s: %s", ticker, exc)
    if result is None:
        # Chế độ dữ liệu thật: KHÔNG bịa BCTC - để trống để giao diện yêu cầu nhập tay / tải Excel
        result = ({"source": "demo", "rows": _demo(ticker)} if settings.data_mode == "demo"
                  else {"source": "none", "rows": []})
    manual = list_manual(ticker)
    result["manual_years"] = [m["year"] for m in manual]
    if manual:
        # Không bao giờ trộn số liệu thật của người dùng với số liệu DEMO bịa ra
        auto_rows = [] if result["source"] in {"demo", "none"} else result["rows"]
        by_year = {r["year"]: r for r in auto_rows}
        shares_hint = next((r.get("shares") for r in reversed(auto_rows) if r.get("shares")), None)
        for m in manual:
            m = {k: v for k, v in m.items() if k != "updated_at"}
            if not m.get("shares") and shares_hint:
                m["shares"] = shares_hint  # chỉ lấy từ nguồn thật, không bao giờ từ DEMO
            by_year[m["year"]] = _complete_row(m)
        result["rows"] = [by_year[y] for y in sorted(by_year)][-8:]
        all_manual = all(r["year"] in result["manual_years"] for r in result["rows"])
        result["source"] = "manual" if all_manual else f"manual+{result['source']}"
    db.cache_set(key, result, 600 if result["source"] == "none" else 3600 if result["source"] == "demo" else 6 * 3600)
    return result
