"""Dữ liệu báo cáo tài chính năm (đơn vị: tỷ đồng; cổ phiếu: triệu CP; EPS/BVPS/DPS: đồng).

Cấu trúc theo 3 báo cáo cơ bản (FQA - Session 2; KTTC2 - Chương 4):
- Bảng cân đối kế toán: Tài sản (A) = Nợ phải trả (D) + Vốn chủ sở hữu (E)
- Báo cáo KQKD: NI = REV - COGS - OC - Int - Tax
- Báo cáo lưu chuyển tiền tệ: NCF = ICF - OCF

Nguồn: TCBS (khi có mạng) → dự phòng dữ liệu DEMO mô phỏng theo đặc thù ngành.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date

import httpx
import numpy as np

from ..config import settings
from ..db import get_db
from . import universe
from .providers import HEADERS, HTTP_TIMEOUT, _seed

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


_tcbs_down_until = 0.0


def _tcbs(path: str, ticker: str) -> list[dict]:
    global _tcbs_down_until
    if _tcbs_down_until > time.time():
        raise RuntimeError("TCBS tạm thời không truy cập được")
    url = f"https://apipubaws.tcbs.com.vn/tcanalysis/v1/finance/{ticker}/{path}"
    try:
        r = httpx.get(url, params={"yearly": 1, "isAll": "true"}, headers=HEADERS, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
    except (httpx.TransportError, httpx.HTTPStatusError):
        _tcbs_down_until = time.time() + 300
        raise
    data = r.json()
    return data if isinstance(data, list) else data.get("data", [])


def _g(d: dict, *keys, default=None):
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return default


def _live(ticker: str) -> list[dict]:
    inc = {r["year"]: r for r in _tcbs("incomestatement", ticker)}
    bal = {r["year"]: r for r in _tcbs("balancesheet", ticker)}
    try:
        cf = {r["year"]: r for r in _tcbs("cashflow", ticker)}
    except Exception:  # noqa: BLE001
        cf = {}
    try:
        ratio = {r["year"]: r for r in _tcbs("financialratio", ticker)}
    except Exception:  # noqa: BLE001
        ratio = {}
    years = sorted(set(inc) & set(bal))[-6:]
    if not years:
        raise ValueError("TCBS không có BCTC")
    rows = []
    for y in years:
        i, b, c, q = inc[y], bal[y], cf.get(y, {}), ratio.get(y, {})
        ni = float(_g(i, "shareHolderIncome", "postTaxProfit", default=0))
        assets = float(_g(b, "asset", default=0))
        equity = float(_g(b, "equity", default=0))
        liabilities = float(_g(b, "debt", "payable", default=assets - equity))
        borrow = float(_g(b, "shortDebt", default=0) or 0) + float(_g(b, "longDebt", default=0) or 0)
        interest = abs(float(_g(i, "interestExpense", default=0) or 0))
        pretax = float(_g(i, "preTaxProfit", default=ni / (1 - TAX_RATE)))
        eps = float(_g(q, "earningPerShare", default=0) or 0)
        shares = ni * 1e9 / eps / 1e6 if eps else None
        rows.append({
            "year": int(y), "revenue": float(_g(i, "revenue", "operationIncome", default=0) or 0),
            "gross_profit": float(_g(i, "grossProfit", default=0) or 0),
            "ebit": pretax + interest, "interest_expense": interest, "pretax_income": pretax,
            "net_income": ni, "depreciation": 0.0, "total_assets": assets,
            "total_liabilities": liabilities, "total_debt": borrow or liabilities * 0.5,
            "equity": equity, "current_assets": float(_g(b, "shortAsset", default=0) or 0),
            "current_liabilities": float(_g(b, "shortDebt", default=0) or 0) or liabilities * 0.6,
            "inventory": float(_g(b, "inventory", default=0) or 0),
            "cash": float(_g(b, "cash", default=0) or 0),
            "operating_cf": float(_g(c, "fromSale", default=ni) or ni),
            "capex": abs(float(_g(c, "investCost", default=0) or 0)),
            "retained_earnings": float(_g(b, "unDistributedIncome", default=0) or 0),
            "shares": shares, "eps": eps or None,
            "bvps": float(_g(q, "bookValuePerShare", default=0) or 0) or None,
            "dps": float(_g(q, "dividend", default=0) or 0) * 10_000 / 100 if q.get("dividend") else 0.0,
        })
    shares = next((r["shares"] for r in reversed(rows) if r["shares"]), None)
    for r in rows:
        r["shares"] = r["shares"] or shares
        if r["shares"]:
            r["eps"] = r["eps"] or r["net_income"] * 1e9 / (r["shares"] * 1e6)
            r["bvps"] = r["bvps"] or r["equity"] * 1e9 / (r["shares"] * 1e6)
    return rows


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


def _complete_row(r: dict) -> dict:
    """Bổ sung các trường suy ra được từ số liệu nhập tay."""
    r = {k: (float(v) if isinstance(v, (int, float, str)) and str(v).strip() not in {"", "None"} else None)
         if k != "year" else int(v) for k, v in r.items()}
    for k in REQUIRED_FIELDS:
        if r.get(k) is None:
            raise ValueError(f"Năm {r.get('year')}: thiếu trường bắt buộc '{k}'")
    r.setdefault("total_liabilities", None)
    if r.get("total_liabilities") is None:
        r["total_liabilities"] = r["total_assets"] - r["equity"]
    if abs(r["total_assets"] - r["total_liabilities"] - r["equity"]) > 0.02 * r["total_assets"]:
        r["balance_warning"] = "Tổng tài sản ≠ Nợ phải trả + Vốn chủ sở hữu (lệch > 2%) - hãy kiểm tra lại."
    for k in ("gross_profit", "interest_expense", "depreciation", "current_assets", "cash", "inventory",
              "current_liabilities", "retained_earnings", "capex", "dps"):
        r[k] = r.get(k) or 0.0
    r["total_debt"] = r.get("total_debt") or r["total_liabilities"] * 0.5
    r["pretax_income"] = r.get("pretax_income") or r["net_income"] / (1 - TAX_RATE)
    r["ebit"] = r["pretax_income"] + r["interest_expense"]
    r["operating_cf"] = r.get("operating_cf") if r.get("operating_cf") is not None else r["net_income"]
    if r.get("shares"):
        r["eps"] = r["net_income"] * 1e9 / (r["shares"] * 1e6)
        r["bvps"] = r["equity"] * 1e9 / (r["shares"] * 1e6)
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
            result = {"source": "tcbs", "rows": _live(ticker)}
        except Exception as exc:  # noqa: BLE001
            log.info("TCBS BCTC lỗi cho %s: %s", ticker, exc)
    if result is None:
        result = {"source": "demo", "rows": _demo(ticker)}
    manual = list_manual(ticker)
    result["manual_years"] = [m["year"] for m in manual]
    if manual:
        by_year = {r["year"]: r for r in result["rows"]}
        shares_hint = next((r.get("shares") for r in reversed(result["rows"]) if r.get("shares")), None)
        for m in manual:
            m = {k: v for k, v in m.items() if k != "updated_at"}
            if not m.get("shares") and shares_hint:
                m["shares"] = shares_hint
            by_year[m["year"]] = _complete_row(m)
        rows = [by_year[y] for y in sorted(by_year)]
        # chỉ giữ chuỗi năm liên tục gần nhất có chứa số liệu nhập tay
        result["rows"] = rows[-8:]
        all_manual = all(r["year"] in result["manual_years"] for r in result["rows"])
        result["source"] = "manual" if all_manual else f"manual+{result['source']}"
    db.cache_set(key, result, 6 * 3600 if result["source"] != "demo" else 3600)
    return result
