"""AI đọc tài liệu thực tế do người dùng cung cấp:

1. Ảnh chụp màn hình biểu đồ nến (theo khoảng thời gian bất kỳ) → nhận định kỹ thuật có cấu trúc,
   đối chiếu với phân tích định lượng của hệ thống trên cùng mã/giai đoạn.
2. Ảnh chụp / PDF báo cáo tài chính → trích xuất số liệu theo năm (tỷ đồng) để người dùng
   kiểm tra, chỉnh sửa và lưu làm số liệu nhập tay.
"""

from __future__ import annotations

import json
import time
from typing import Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field

from ..analysis import technical
from ..context import current_user_id
from ..data import fundamentals, providers
from ..db import get_db
from . import llm


# ---------------------------------------------------------------- chart reading
class ChartPattern(BaseModel):
    name: str = Field(description="Tên mô hình giá/nến bằng tiếng Việt, ví dụ 'Hai đáy', 'Vai đầu vai', 'Cờ tăng'")
    bias: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(description="Độ tin cậy 0-1")
    description: str


class PriceLevel(BaseModel):
    price: float
    kind: Literal["support", "resistance"]
    strength: Literal["weak", "medium", "strong"]


class ChartReading(BaseModel):
    is_price_chart: bool = Field(description="Ảnh có phải biểu đồ giá/nến chứng khoán không")
    ticker_detected: Optional[str] = None
    timeframe_detected: str = Field(description="Khung thời gian của nến: ngày/tuần/giờ...")
    period_visible: str = Field(description="Khoảng thời gian hiển thị trên biểu đồ, nếu đọc được")
    last_price_estimate: Optional[float] = Field(default=None, description="Giá đóng cửa gần nhất đọc được (VND)")
    price_unit_note: str = Field(description="Ghi chú đơn vị giá trên trục (nghìn đồng/đồng/điểm)")
    trend_short: Literal["Tăng", "Giảm", "Đi ngang"]
    trend_medium: Literal["Tăng", "Giảm", "Đi ngang"]
    patterns: list[ChartPattern]
    levels: list[PriceLevel]
    indicators_seen: list[str] = Field(description="Các chỉ báo nhìn thấy trên ảnh và giá trị/trạng thái, ví dụ 'RSI ≈ 68 - gần quá mua'")
    volume_analysis: str
    signal: Literal["MUA MẠNH", "MUA", "NẮM GIỮ", "BÁN", "BÁN MẠNH"]
    confidence: float = Field(description="Độ tin cậy tổng thể 0-1")
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    key_observations: list[str]
    risks: list[str]
    summary: str = Field(description="Tóm tắt nhận định 3-5 câu bằng tiếng Việt")


CHART_SYSTEM = """Bạn là chuyên gia phân tích kỹ thuật chứng khoán Việt Nam (HOSE/HNX/UPCoM).
Nhiệm vụ: đọc ảnh chụp màn hình biểu đồ giá do nhà đầu tư cung cấp và đưa ra nhận định có cấu trúc.
Nguyên tắc:
- Chỉ mô tả những gì thực sự nhìn thấy trên ảnh; nếu không đọc rõ con số thì để trống thay vì đoán.
- Giá trên bảng giá VN thường hiển thị theo nghìn đồng (VD 57.2 = 57.200đ). Quy đổi mọi mức giá trả về sang ĐỒNG.
- Xét xu hướng (đỉnh/đáy, đường MA), mô hình nến & mô hình giá, khối lượng, các chỉ báo hiển thị (RSI, MACD, Bollinger...).
- Áp dụng kỷ luật quản trị rủi ro: luôn đề xuất điểm cắt lỗ (≤ 7% dưới điểm mua) khi khuyến nghị mua.
- Nếu ảnh không phải biểu đồ giá, đặt is_price_chart=false và giải thích trong summary.
- Trả lời bằng tiếng Việt."""

_SIGNAL_VALUE = {"MUA MẠNH": 2, "MUA": 1, "NẮM GIỮ": 0, "BÁN": -1, "BÁN MẠNH": -2}
_CODE_VALUE = {"strong_buy": 2, "buy": 1, "hold": 0, "sell": -1, "strong_sell": -2}


def system_view(ticker: str, start: str | None = None, end: str | None = None) -> dict | None:
    """Phân tích kỹ thuật định lượng của hệ thống cho mã/giai đoạn tương ứng để đối chiếu."""
    try:
        df = providers.get_history(ticker, days=750)
        ts_end = pd.Timestamp(end).tz_localize(None) if end and pd.Timestamp(end).tzinfo else (pd.Timestamp(end) if end else None)
        ts_start = pd.Timestamp(start).tz_localize(None) if start and pd.Timestamp(start).tzinfo else (pd.Timestamp(start) if start else None)
    except Exception:  # noqa: BLE001 - mã/ngày không hợp lệ → bỏ qua phần đối chiếu của hệ thống
        return None
    if ts_end is not None and not pd.isna(ts_end):
        df = df[df.index <= ts_end]
    lookback_start = None
    if ts_start is not None and not pd.isna(ts_start):
        lookback_start = ts_start
        # giữ thêm 200 phiên trước giai đoạn để chỉ báo dài hạn có đủ dữ liệu
        pos = df.index.searchsorted(lookback_start)
        df = df.iloc[max(0, pos - 200):]
    if len(df) < 60:
        return None
    t = technical.analyze(df)
    return {"ticker": ticker.upper(), "source": df.attrs.get("source"), "as_of": df.index[-1].strftime("%Y-%m-%d"),
            "score": t["score"], "signal": t["signal"], "signal_code": t["signal_code"], "trend": t["trend"],
            "price": t["price"], "levels": t["levels"], "patterns": t["patterns"],
            "period_start": lookback_start.strftime("%Y-%m-%d") if lookback_start is not None else None}


def analyze_chart(files: list[tuple[bytes, str]], ticker: str | None = None, timeframe: str | None = None,
                  start: str | None = None, end: str | None = None, note: str | None = None) -> dict:
    content = [llm.file_block(data, mt) for data, mt in files]
    ctx = []
    if ticker:
        ctx.append(f"Mã cổ phiếu: {ticker.upper()}")
    if timeframe:
        ctx.append(f"Khung thời gian: {timeframe}")
    if start or end:
        ctx.append(f"Giai đoạn quan tâm: {start or '...'} → {end or 'nay'}")
    if note:
        ctx.append(f"Ghi chú của nhà đầu tư: {note}")
    content.append({"type": "text", "text": "Hãy phân tích (các) ảnh biểu đồ này.\n" + "\n".join(ctx)})
    reading: ChartReading = llm.parse(CHART_SYSTEM, content, ChartReading)
    result = {"ai": reading.model_dump()}
    tk = (ticker or reading.ticker_detected or "").upper().strip()
    if tk:
        sv = system_view(tk, start, end)
        if sv:
            diff = abs(_SIGNAL_VALUE[reading.signal] - _CODE_VALUE.get(sv["signal_code"], 0))
            agreement = "Đồng thuận" if diff == 0 else "Gần đồng thuận" if diff == 1 else "Trái chiều"
            result["system"] = sv
            result["comparison"] = {
                "agreement": agreement,
                "note": ("AI đọc ảnh và mô hình định lượng cho cùng nhận định - độ tin cậy cao hơn."
                         if diff <= 1 else
                         "Hai góc nhìn trái chiều - nên chờ thêm tín hiệu xác nhận trước khi giao dịch."),
            }
    cur = get_db().execute("INSERT INTO chart_analyses(user_id, created_at, ticker, timeframe, result) "
                           "VALUES(?,?,?,?,?)", (current_user_id(), time.time(), tk or None, timeframe,
                                                 json.dumps(result, ensure_ascii=False)))
    result["id"] = cur.lastrowid
    return result


def recent_chart_analyses(limit: int = 20) -> list[dict]:
    rows = get_db().query("SELECT * FROM chart_analyses WHERE user_id=? ORDER BY id DESC LIMIT ?",
                          (current_user_id(), limit))
    return [{**r, "result": json.loads(r["result"])} for r in rows]


# ---------------------------------------------------------------- financial statements
def _year_model():
    fields = {k: (Optional[float], Field(default=None, description=f"{label} ({unit})"))
              for k, label, unit in fundamentals.MANUAL_FIELDS}
    from pydantic import create_model
    return create_model("ExtractedYear", year=(int, Field(description="Năm tài chính")), **fields)


ExtractedYear = _year_model()


class ExtractedFinancials(BaseModel):
    company: Optional[str] = None
    ticker: Optional[str] = None
    report_type: str = Field(description="Hợp nhất / Riêng lẻ, kiểm toán / soát xét / chưa kiểm toán")
    original_unit: str = Field(description="Đơn vị gốc trên báo cáo (đồng, nghìn đồng, triệu đồng, tỷ đồng)")
    years: list[ExtractedYear]
    warnings: list[str] = Field(description="Các điểm chưa chắc chắn, số liệu không tìm thấy hoặc cần kiểm tra lại")


FIN_SYSTEM = """Bạn là kế toán viên/chuyên viên phân tích tài chính am hiểu Chuẩn mực kế toán Việt Nam (VAS,
Thông tư 200/2014 và Thông tư 99/2025). Nhiệm vụ: trích xuất số liệu từ ảnh chụp/PDF báo cáo tài chính
(Bảng cân đối kế toán / Báo cáo tình hình tài chính, Báo cáo KQHĐKD, Báo cáo lưu chuyển tiền tệ).

Quy tắc:
- QUY ĐỔI tất cả số tiền sang TỶ ĐỒNG (1 tỷ = 1.000.000.000 đồng). Ghi đơn vị gốc vào original_unit.
- Số cổ phiếu lưu hành: TRIỆU cổ phiếu (= vốn góp chủ sở hữu / 10.000đ mệnh giá nếu không ghi trực tiếp).
- Cổ tức mỗi cổ phiếu: ĐỒNG/CP.
- Lợi nhuận sau thuế: ưu tiên "LNST của cổ đông công ty mẹ" nếu là BCTC hợp nhất.
- Capex = "Tiền chi để mua sắm, xây dựng TSCĐ và các tài sản dài hạn khác" (ghi số dương).
- Chi phí lãi vay ghi số dương. Vay = vay và nợ thuê tài chính ngắn hạn + dài hạn.
- Mỗi cột năm (hoặc số cuối kỳ/đầu kỳ) là một phần tử trong years. Không đọc được thì để null, KHÔNG bịa số.
- Kiểm tra: Tổng tài sản = Nợ phải trả + Vốn chủ sở hữu; ghi cảnh báo nếu lệch."""


def extract_financials(files: list[tuple[bytes, str]], ticker: str | None = None) -> dict:
    content = [llm.file_block(data, mt) for data, mt in files]
    content.append({"type": "text", "text": "Trích xuất số liệu BCTC theo từng năm."
                    + (f" Mã cổ phiếu: {ticker.upper()}." if ticker else "")})
    out: ExtractedFinancials = llm.parse(FIN_SYSTEM, content, ExtractedFinancials)
    data = out.model_dump()
    data["years"] = sorted(data["years"], key=lambda y: y["year"])
    data["fields"] = [{"key": k, "label": label, "unit": unit} for k, label, unit in fundamentals.MANUAL_FIELDS]
    data["next_step"] = "Kiểm tra lại số liệu trên giao diện rồi bấm Lưu để đưa vào phân tích."
    return data


def extract_financials_from_text(text: str, ticker: str | None = None) -> dict:
    """AI đọc nội dung bảng tính (đã chuyển sang CSV) khi bộ đọc Excel tự động không nhận diện được."""
    content = [{"type": "text", "text": "Dưới đây là nội dung file Excel báo cáo tài chính (dạng CSV theo từng sheet). "
                "Trích xuất số liệu theo từng năm." + (f" Mã cổ phiếu: {ticker.upper()}." if ticker else "")
                + "\n\n" + text}]
    out: ExtractedFinancials = llm.parse(FIN_SYSTEM, content, ExtractedFinancials)
    data = out.model_dump()
    data["years"] = sorted(data["years"], key=lambda y: y["year"])
    data["fields"] = [{"key": k, "label": label, "unit": unit} for k, label, unit in fundamentals.MANUAL_FIELDS]
    return data
