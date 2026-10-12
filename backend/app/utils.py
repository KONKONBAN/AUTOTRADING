"""Tiện ích chung."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def clean(obj: Any) -> Any:
    """Chuyển kiểu numpy/pandas/NaN về kiểu JSON hợp lệ."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [clean(v) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    return obj


def vn_num(x: float | None, digits: int = 0) -> str:
    """Số kiểu Việt Nam: 1.234.567,8"""
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "—"
    s = f"{x:,.{digits}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def vn_pct(x: float | None, digits: int = 1, sign: bool = False) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "—"
    return f"{'+' if sign and x > 0 else ''}{vn_num(x * 100, digits)}%"
