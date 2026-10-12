"""Nhập dữ liệu từ file Excel/CSV do người dùng tải lên.

1. BCTC (Báo cáo tài chính) - hỗ trợ:
   - File mẫu của ứng dụng (có cột "key"), và
   - File xuất từ Vietstock / CafeF / FiinPro / VNDirect / SSI... dạng "chỉ tiêu × năm":
     tự nhận diện dòng chỉ tiêu theo tên tiếng Việt/tiếng Anh, cột năm và đơn vị
     (đồng / nghìn đồng / triệu đồng / tỷ đồng) rồi quy đổi về tỷ đồng.
2. Lịch sử giá - định dạng Amibroker/MetaStock (<Ticker>,<DTYYYYMMDD>,...) hoặc bảng có tiêu đề
   (Ngày, Giá mở cửa, Giá cao nhất, Giá thấp nhất, Giá đóng cửa, Khối lượng...).
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..db import get_db
from . import fundamentals


def norm(text) -> str:
    """Chuẩn hóa nhãn: bỏ dấu tiếng Việt, chữ thường, bỏ đánh số đầu dòng."""
    s = unicodedata.normalize("NFD", str(text or "")).replace("đ", "d").replace("Đ", "D")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"^[\s\-–•*+]*((\d+(\.\d+)*|[ivxlc]+|[a-h])[\.\)/:]\s*)+", "", s.strip())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%/ ]+", " ", s)).strip()


def _num(v) -> float | None:
    """Đọc số từ ô Excel/CSV: hỗ trợ 1.234.567 | 1,234,567 | 1.234,5 | 1,234.5 | (123) = -123."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("\xa0", "").replace(" ", "")
    if not s or s in {"-", "--", "n/a", "N/A"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif s.count(",") > 1 or (s.count(",") == 1 and len(s.split(",")[1]) == 3):
        s = s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    else:
        s = s.replace(",", ".")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


# --------------------------------------------------------------------------- BCTC
# (trường, [mẫu ưu tiên], [loại trừ], cộng dồn?)
FIELD_PATTERNS: list[tuple[str, list[str], list[str], bool]] = [
    ("revenue", ["doanh thu thuan ve ban hang va cung cap dich vu", "doanh thu thuan", "net revenue",
                 "net sales", "tong thu nhap hoat dong", "doanh thu hoat dong", "doanh thu"],
     ["tai chinh", "giam tru", "chua thuc hien", "khac", "tang truong", "%"], False),
    ("gross_profit", ["loi nhuan gop ve ban hang", "loi nhuan gop", "gross profit"], ["%", "bien"], False),
    ("interest_expense", ["trong do chi phi lai vay", "chi phi lai vay", "interest expense",
                          "chi phi lai va cac chi phi tuong tu"], ["%", "tra"], False),
    ("pretax_income", ["tong loi nhuan ke toan truoc thue", "loi nhuan truoc thue", "profit before tax",
                       "pre tax profit"], ["%"], False),
    ("net_income", ["loi nhuan sau thue cua co dong cua cong ty me", "loi nhuan sau thue cong ty me",
                    "co dong cua cong ty me", "loi nhuan sau thue cua co dong cong ty me",
                    "net profit attributable to", "loi nhuan sau thue thu nhap doanh nghiep",
                    "loi nhuan sau thue", "net profit after tax", "profit after tax", "net income"],
     ["chua phan phoi", "%", "khong kiem soat", "thieu so", "tang truong", "phan phoi"], False),
    ("depreciation", ["khau hao tai san co dinh", "khau hao tscd", "khau hao", "depreciation"], ["luy ke", "hao mon"], False),
    ("total_assets", ["tong cong tai san", "tong tai san", "total assets"], ["%", "ngan han", "dai han"], False),
    ("current_assets", ["tai san ngan han", "current assets", "tai san luu dong"], ["khac", "%", "dau tu"], False),
    ("cash", ["tien va cac khoan tuong duong tien", "cash and cash equivalents", "tien va tuong duong tien"],
     ["luu chuyen", "cuoi ky", "dau ky", "anh huong"], False),
    ("inventory", ["hang ton kho", "inventories", "inventory"], ["du phong", "giam gia", "bien dong", "tang giam"], False),
    ("total_liabilities", ["tong no phai tra", "no phai tra", "total liabilities", "tong cong no"],
     ["ngan han", "dai han", "khac", "%", "nguoi ban"], False),
    ("current_liabilities", ["no ngan han", "current liabilities"], ["khac", "%"], False),
    ("total_debt", ["vay va no thue tai chinh ngan han", "vay va no thue tai chinh dai han", "vay ngan han",
                    "vay dai han", "short term borrowings", "long term borrowings", "short term debt",
                    "long term debt"], ["chi phi", "lai", "tra no", "tien thu", "tien chi"], True),
    ("equity", ["tong von chu so huu", "von chu so huu", "total equity", "owners equity", "shareholders equity"],
     ["khac", "%", "tren", "tong cong nguon", "ty suat", "loi nhuan tren"], False),
    ("retained_earnings", ["loi nhuan sau thue chua phan phoi", "retained earnings", "undistributed"], [], False),
    ("operating_cf", ["luu chuyen tien thuan tu hoat dong kinh doanh", "luu chuyen tien thuan tu hoat dong san xuat kinh doanh",
                      "net cash from operating", "net cash flows from operating", "luu chuyen tien te rong tu cac hoat dong san xuat kinh doanh"],
     [], False),
    ("capex", ["tien chi de mua sam xay dung tscd", "tien chi de mua sam xay dung tai san co dinh",
               "tien chi mua sam tai san co dinh", "mua sam tai san co dinh", "purchase of fixed assets",
               "purchases of property", "capital expenditure"], ["thanh ly", "nhuong ban"], False),
    ("shares", ["so luong co phieu dang luu hanh", "so luong co phieu luu hanh", "so co phieu luu hanh",
                "shares outstanding", "co phieu pho thong dang luu hanh"], ["quy", "ky tru"], False),
    ("dps", ["co tuc moi co phieu", "co tuc tien mat moi co phieu", "dividend per share", "dps"], ["%"], False),
]
OWNER_CAPITAL = ["von gop cua chu so huu", "von dau tu cua chu so huu", "von co phan", "von dieu le", "share capital"]

UNIT_PATTERNS = [("ty dong", 1.0), ("ty vnd", 1.0), ("billion", 1.0), ("trieu dong", 1e-3), ("trieu vnd", 1e-3),
                 ("million", 1e-3), ("nghin dong", 1e-6), ("ngan dong", 1e-6), ("thousand", 1e-6),
                 ("vnd", 1e-9), ("dong", 1e-9)]


def _year_of(v) -> int | None:
    if isinstance(v, (int, float)) and 1990 <= v <= 2100 and float(v).is_integer():
        return int(v)
    if isinstance(v, (datetime, date)):
        return v.year
    s = str(v or "")
    if re.search(r"(q|quy|quý)\s*\d", s, re.I) and not re.search(r"(q|quy|quý)\s*4", s, re.I):
        return None  # bỏ qua cột quý (trừ Q4 có thể là số cả năm)
    m = re.search(r"(19|20)\d{2}", s)
    if m and len(s) <= 30:
        return int(m.group(0))
    return None


def _grids(data: bytes, filename: str) -> list[tuple[str, list[list]]]:
    name = filename.lower()
    if name.endswith((".csv", ".txt")):
        text = data.decode("utf-8-sig", errors="ignore")
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t") if text.strip() else csv.excel
        return [("csv", [row for row in csv.reader(io.StringIO(text), dialect)])]
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(c not in (None, "") for c in r)]
        if rows:
            out.append((ws.title, rows))
    return out


def _detect_unit(grid: list[list]) -> tuple[float | None, str | None]:
    for row in grid[:40]:
        for c in row:
            if not isinstance(c, str):
                continue
            n = norm(c)
            if "don vi" in n or "unit" in n or "dvt" in n:
                for pat, mult in UNIT_PATTERNS:
                    if pat in n:
                        return mult, pat
    return None, None


def _parse_grid(grid: list[list]) -> dict | None:
    # 1) tìm dòng tiêu đề chứa ≥ 2 năm
    header_idx, year_cols = None, {}
    for i, row in enumerate(grid[:60]):
        cols = {j: y for j, c in enumerate(row) if (y := _year_of(c))}
        if len(cols) >= 2 or (len(cols) == 1 and len(grid) > 5):
            if len(cols) > len(year_cols):
                header_idx, year_cols = i, cols
            if len(cols) >= 2:
                break
    if not year_cols:
        return None
    # nếu một năm xuất hiện nhiều lần (đầu kỳ/cuối kỳ), giữ cột đầu tiên
    seen, cols = set(), {}
    for j, y in sorted(year_cols.items()):
        if y not in seen:
            cols[j] = y
            seen.add(y)
    first_year_col = min(cols)
    # 2) cột "key" của file mẫu
    keys = {k for k, _, _ in fundamentals.MANUAL_FIELDS}
    key_col = None
    for j in range(first_year_col):
        hits = sum(1 for r in grid[header_idx + 1:] if j < len(r) and str(r[j] or "").strip() in keys)
        if hits >= 3:
            key_col = j
            break
    lines = []
    for r in grid[header_idx + 1:]:
        label = next((str(c) for c in r[:first_year_col] if isinstance(c, str) and c.strip()), "")
        vals = {y: _num(r[j]) if j < len(r) else None for j, y in cols.items()}
        if not label or all(v is None for v in vals.values()):
            continue
        lines.append({"label": label, "norm": norm(label),
                      "key": str(r[key_col]).strip() if key_col is not None and key_col < len(r) else None,
                      "values": vals})
    unit_mult, unit_name = _detect_unit(grid)
    mapped: dict[str, dict[int, float]] = {}
    report = []
    if key_col is not None:
        for ln in lines:
            if ln["key"] in keys:
                mapped[ln["key"]] = ln["values"]
                report.append({"field": ln["key"], "label": ln["label"]})
        unit_mult = unit_mult or 1.0
        unit_name = unit_name or "ty dong (file mẫu)"
    else:
        used = set()
        for field, patterns, excludes, summed in FIELD_PATTERNS:
            matched = []
            for pat in patterns:
                for idx, ln in enumerate(lines):
                    if idx in used or idx in matched or any(ex in ln["norm"] for ex in excludes):
                        continue
                    if ln["norm"].startswith(pat) or (len(pat) > 12 and pat in ln["norm"]):
                        matched.append(idx)
                        if not summed:
                            break
                if matched and not summed:
                    break
            if not matched:
                continue
            if summed:
                vals = {y: sum((lines[i]["values"][y] or 0) for i in matched) for y in cols.values()}
            else:
                vals = lines[matched[0]]["values"]
            used.update(matched)
            mapped[field] = vals
            report.append({"field": field, "label": " + ".join(lines[i]["label"] for i in matched)})
        cap = next((ln for ln in lines if any(ln["norm"].startswith(p) for p in OWNER_CAPITAL)), None)
        if cap and "shares" not in mapped:
            mapped["_owner_capital"] = cap["values"]
    if len([f for f in fundamentals.REQUIRED_FIELDS if f in mapped]) < 2:
        return None
    if unit_mult is None:
        # đoán đơn vị theo độ lớn của Tổng tài sản / Doanh thu
        ref = next((abs(v) for f in ("total_assets", "revenue", "equity") for v in (mapped.get(f) or {}).values() if v),
                   None)
        unit_mult, unit_name = ((1e-9, "dong (đoán)") if ref and ref > 1e10 else
                                (1e-6, "nghin dong (đoán)") if ref and ref > 1e7 else
                                (1e-3, "trieu dong (đoán)") if ref and ref > 1e5 else (1.0, "ty dong (đoán)"))
    years = []
    for y in sorted(set(cols.values())):
        row = {"year": y}
        for f, vals in mapped.items():
            v = vals.get(y)
            if v is None:
                continue
            if f == "shares":
                row[f] = v / 1e6 if abs(v) > 1e5 else v  # số CP → triệu CP
            elif f == "dps":
                row[f] = abs(v)
            elif f == "_owner_capital":
                row["shares"] = abs(v) * unit_mult * 0.1  # vốn góp (tỷ đồng) / 10.000đ mệnh giá → triệu CP
            elif f in {"capex", "interest_expense"}:
                row[f] = abs(v) * unit_mult
            else:
                row[f] = v * unit_mult
        if any(row.get(f) is not None for f in fundamentals.REQUIRED_FIELDS):
            years.append(row)
    missing = [f for f, _, _ in fundamentals.MANUAL_FIELDS if not any(f in y for y in years)]
    return {"years": years, "unit_detected": unit_name, "mapping": report, "missing_fields": missing}


def parse_financial_file(data: bytes, filename: str) -> dict:
    """Đọc file BCTC Excel/CSV → số liệu theo năm (tỷ đồng) để người dùng xem lại trước khi lưu."""
    best = None
    for sheet, grid in _grids(data, filename):
        for orientation, g in (("rows", grid), ("columns", [list(x) for x in zip(*grid)] if grid else [])):
            res = _parse_grid(g)
            if res and (best is None or len(res["mapping"]) > len(best["mapping"])):
                best = {**res, "sheet": sheet, "orientation": orientation}
    if best is None:
        raise ValueError("Không nhận diện được cấu trúc BCTC trong file (cần cột năm và các dòng chỉ tiêu). "
                         "Hãy dùng file mẫu hoặc thử tính năng AI đọc file.")
    best["fields"] = [{"key": k, "label": label, "unit": unit} for k, label, unit in fundamentals.MANUAL_FIELDS]
    best["warnings"] = []
    for y in best["years"]:
        if all(k in y for k in ("total_assets", "equity", "total_liabilities")):
            gap = abs(y["total_assets"] - y["equity"] - y["total_liabilities"])
            if gap > 0.02 * abs(y["total_assets"]):
                best["warnings"].append(f"Năm {y['year']}: Tổng tài sản ≠ Nợ phải trả + Vốn chủ sở hữu.")
    return best


def grid_as_text(data: bytes, filename: str, max_rows: int = 250, max_cols: int = 16) -> str:
    """Chuyển nội dung file thành văn bản (CSV) để AI đọc khi định dạng quá lạ."""
    parts = []
    for sheet, grid in _grids(data, filename):
        buf = io.StringIO()
        w = csv.writer(buf)
        for r in grid[:max_rows]:
            w.writerow(["" if c is None else c for c in r[:max_cols]])
        parts.append(f"### Sheet: {sheet}\n{buf.getvalue()}")
    return "\n\n".join(parts)[:150_000]


# --------------------------------------------------------------------------- file mẫu
def financial_template(ticker: str | None = None) -> bytes:
    """File Excel mẫu nhập BCTC (điền sẵn số liệu hiện có nếu chọn mã)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BCTC"
    rows_existing = []
    if ticker:
        try:
            rows_existing = fundamentals.get_financials(ticker)["rows"][-5:]
        except Exception:  # noqa: BLE001
            rows_existing = []
    years = [r["year"] for r in rows_existing] or list(range(date.today().year - 5, date.today().year))
    title_font = Font(bold=True, size=14, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="0F766E")
    head_font = Font(bold=True, color="FFFFFF")
    thin = Side(style="thin", color="CBD5E1")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=3 + len(years))
    ws.cell(1, 1, f"BÁO CÁO TÀI CHÍNH NĂM - {ticker.upper() if ticker else 'MÃ CỔ PHIẾU'}").font = title_font
    ws.cell(1, 1).fill = PatternFill("solid", fgColor="134E4A")
    ws.cell(2, 1, "Đơn vị: tỷ đồng (riêng số cổ phiếu: triệu CP; cổ tức: đồng/CP). "
                  "Không sửa cột 'key'. Có thể thêm/bớt cột năm.").font = Font(italic=True, color="475569")
    headers = ["Chỉ tiêu", "key", "Đơn vị", *years]
    for j, h in enumerate(headers, 1):
        c = ws.cell(4, j, h)
        c.fill, c.font = head_fill, head_font
        c.alignment = Alignment(horizontal="center")
    by_year = {r["year"]: r for r in rows_existing}
    for i, (key, label, unit) in enumerate(fundamentals.MANUAL_FIELDS, start=5):
        ws.cell(i, 1, label)
        ws.cell(i, 2, key).font = Font(color="94A3B8")
        ws.cell(i, 3, unit).font = Font(color="64748B")
        for j, y in enumerate(years, start=4):
            v = by_year.get(y, {}).get(key)
            c = ws.cell(i, j, round(v, 2) if isinstance(v, (int, float)) else None)
            c.number_format = "#,##0.00"
            c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
        if key in fundamentals.REQUIRED_FIELDS:
            ws.cell(i, 1).font = Font(bold=True)
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 12
    for j in range(4, 4 + len(years)):
        ws.column_dimensions[get_column_letter(j)].width = 16
    ws.freeze_panes = "D5"
    guide = wb.create_sheet("Huong_dan")
    for i, line in enumerate([
        "HƯỚNG DẪN NHẬP BÁO CÁO TÀI CHÍNH",
        "1. Nhập số liệu BCTC năm (ưu tiên BCTC hợp nhất đã kiểm toán) vào sheet 'BCTC', đơn vị tỷ đồng.",
        "2. Các dòng in đậm là bắt buộc: Doanh thu thuần, LNST, Tổng tài sản, Vốn chủ sở hữu.",
        "3. Chi phí lãi vay và Capex nhập số dương.",
        "4. Kiểm tra: Tổng tài sản = Nợ phải trả + Vốn chủ sở hữu.",
        "5. Lưu file và tải lên tại mục 'Dữ liệu & Nhập liệu' của ứng dụng.",
        "Ứng dụng cũng đọc được file xuất trực tiếp từ Vietstock, CafeF, FiinPro, VNDirect, SSI... (chỉ tiêu × năm).",
    ], start=1):
        guide.cell(i, 1, line).font = Font(bold=(i == 1), size=13 if i == 1 else 11)
    guide.column_dimensions["A"].width = 110
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- giá
PRICE_HEADERS = {
    "ticker": ["ticker", "symbol", "ma ck", "ma", "ma chung khoan", "code"],
    "date": ["dtyyyymmdd", "date", "ngay", "time", "thoi gian", "trading date"],
    "open": ["open", "gia mo cua", "mo cua"],
    "high": ["high", "gia cao nhat", "cao nhat"],
    "low": ["low", "gia thap nhat", "thap nhat"],
    "close": ["close", "gia dong cua", "dong cua", "gia dieu chinh", "adj close", "gia"],
    "volume": ["volume", "vol", "khoi luong khop lenh", "khoi luong", "kl khop lenh", "tong khoi luong"],
}


def _parse_date(v) -> str | None:
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    s = str(v or "").strip()
    if re.fullmatch(r"\d{8}", s):
        return datetime.strptime(s, "%Y%m%d").strftime("%Y-%m-%d")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_price_file(data: bytes, filename: str, default_ticker: str | None = None) -> list[tuple]:
    rows_out = []
    for _, grid in _grids(data, filename):
        header_idx, colmap = None, {}
        for i, row in enumerate(grid[:15]):
            cm = {}
            for j, c in enumerate(row):
                n = norm(str(c).strip("<>")) if c is not None else ""
                for field, names in PRICE_HEADERS.items():
                    if field not in cm and any(n == nm or (len(nm) > 4 and n.startswith(nm)) for nm in names):
                        cm[field] = j
                        break
            if {"date", "close"} <= set(cm):
                header_idx, colmap = i, cm
                break
        if header_idx is None:
            # không có tiêu đề: thử định dạng Amibroker
            colmap = {"ticker": 0, "date": 1, "open": 2, "high": 3, "low": 4, "close": 5, "volume": 6}
            header_idx = -1
        for r in grid[header_idx + 1:]:
            try:
                tk = (str(r[colmap["ticker"]]).strip().upper() if "ticker" in colmap and colmap["ticker"] < len(r)
                      else (default_ticker or "").upper())
                d = _parse_date(r[colmap["date"]])
                c = _num(r[colmap["close"]])
                o = _num(r[colmap["open"]]) if "open" in colmap else c
                h = _num(r[colmap["high"]]) if "high" in colmap else max(o or c, c)
                lo = _num(r[colmap["low"]]) if "low" in colmap else min(o or c, c)
                v = _num(r[colmap["volume"]]) if "volume" in colmap and colmap["volume"] < len(r) else 0
            except (IndexError, TypeError, ValueError):
                continue
            if not tk or not d or c is None:
                continue
            o, h, lo = o or c, h or c, lo or c
            if tk != "VNINDEX" and c < 1_000:
                o, h, lo, c = (x * 1_000 for x in (o, h, lo, c))
            rows_out.append((tk, d, o, h, lo, c, v or 0))
    return rows_out


def import_price_file(data: bytes, filename: str, default_ticker: str | None = None) -> dict:
    rows = parse_price_file(data, filename, default_ticker)
    if not rows:
        raise ValueError("Không đọc được dữ liệu giá. Cần các cột: Mã, Ngày, Mở cửa, Cao nhất, Thấp nhất, "
                         "Đóng cửa, Khối lượng (hoặc định dạng Amibroker <Ticker>,<DTYYYYMMDD>,...).")
    db = get_db()
    with db._lock:  # noqa: SLF001
        db._conn.executemany(
            "INSERT OR REPLACE INTO imported_prices(ticker,date,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)",
            rows)
        db._conn.commit()
    db.execute("DELETE FROM cache WHERE key LIKE 'hist:%'")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r[0]] = counts.get(r[0], 0) + 1
    dates = sorted(r[1] for r in rows)
    return {"rows": len(rows), "tickers": counts, "from": dates[0], "to": dates[-1]}


def imported_summary() -> list[dict]:
    return get_db().query("SELECT ticker, COUNT(*) AS rows, MIN(date) AS first, MAX(date) AS last "
                          "FROM imported_prices GROUP BY ticker ORDER BY ticker")


def delete_imported(ticker: str) -> None:
    get_db().execute("DELETE FROM imported_prices WHERE ticker=?", (ticker.upper(),))
    get_db().execute("DELETE FROM cache WHERE key LIKE 'hist:%'")
