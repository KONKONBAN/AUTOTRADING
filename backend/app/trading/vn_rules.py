"""Quy định giao dịch cổ phiếu niêm yết tại Việt Nam (PTVĐTCK - Chương 1, mục 1.3).

- Lô chẵn: 100 cổ phiếu (HOSE/HNX). Khối lượng lẻ (VD 1.530 CP) phải tách lệnh: 1.500 + 30 lô lẻ.
- Biên độ dao động: HOSE ±7%, HNX ±10%, UPCoM ±15% so với giá tham chiếu.
- Bước giá HOSE: <10.000đ: 10đ | 10.000-49.950đ: 50đ | >=50.000đ: 100đ. HNX/UPCoM: 100đ.
- Phí giao dịch trả công ty chứng khoán: 0,15% - 0,3% giá trị giao dịch (mua & bán).
- Thuế TNCN khi bán: 0,1% giá trị giao dịch.
- Thanh toán: cổ phiếu mua về sau T+2 (tài liệu ghi T+1.5: về lúc 11h30 ngày T+2) mới bán được.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

LOT_SIZE = 100
SELL_TAX_RATE = 0.001
DEFAULT_FEE_RATE = 0.0015
SETTLEMENT_DAYS = 2

PRICE_BANDS = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}


def tick_size(price: float, exchange: str = "HOSE") -> float:
    """Bước giá (VND) theo sàn và vùng giá."""
    if exchange.upper() != "HOSE":
        return 100.0
    if price < 10_000:
        return 10.0
    if price < 50_000:
        return 50.0
    return 100.0


_EPS = 1e-9  # 28.000 × 1,15 = 32.199,999… trong dấu phẩy động: không được làm tròn xuống thành 32.100


def round_to_tick(price: float, exchange: str = "HOSE", mode: str = "nearest") -> float:
    step = tick_size(price, exchange)
    q = price / step
    n = {"nearest": math.floor(q + 0.5), "down": math.floor(q + _EPS), "up": math.ceil(q - _EPS)}[mode]
    return float(n * step)


def on_tick(price: float, exchange: str = "HOSE") -> bool:
    q = price / tick_size(price, exchange)
    return abs(q - round(q)) < 1e-6


@dataclass
class PriceLimits:
    reference: float
    ceiling: float
    floor: float


def price_limits(reference: float, exchange: str = "HOSE") -> PriceLimits:
    """Giá trần / sàn từ giá tham chiếu (giá đóng cửa phiên trước).

    Ví dụ (Chương 1): VNM đóng cửa 57.200 → tham chiếu 57.200, trần 61.200, sàn 53.200.
    """
    band = PRICE_BANDS.get(exchange.upper(), 0.07)
    ceiling = round_to_tick(reference * (1 + band), exchange, "down")
    floor = round_to_tick(reference * (1 - band), exchange, "up")
    return PriceLimits(reference=reference, ceiling=ceiling, floor=floor)


def round_lot(quantity: float) -> int:
    """Làm tròn xuống lô chẵn 100 cổ phiếu."""
    return int(quantity // LOT_SIZE * LOT_SIZE)


def split_order(quantity: int) -> list[int]:
    """Tách lệnh hợp lệ: phần lô chẵn và phần lô lẻ (VD 1530 → [1500, 30])."""
    even = round_lot(quantity)
    odd = quantity - even
    return [q for q in (even, odd) if q > 0]


def trade_costs(side: str, value: float, fee_rate: float = DEFAULT_FEE_RATE) -> dict:
    """Chi phí giao dịch: phí CTCK (mua & bán) + thuế TNCN 0,1% (chỉ khi bán)."""
    fee = value * fee_rate
    tax = value * SELL_TAX_RATE if side.upper() == "SELL" else 0.0
    return {"fee": fee, "tax": tax, "total": fee + tax}


def advance_payment_fee(amount: float, annual_rate: float = 0.15, days: int = 2) -> float:
    """Phí ứng trước tiền bán chứng khoán = số tiền × lãi suất năm/365 × số ngày."""
    return amount * annual_rate / 365 * days
