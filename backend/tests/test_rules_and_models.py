import numpy as np
import pytest

from app.analysis import fundamental, quant
from app.trading import vn_rules


def test_vn_price_limits_ch1_example():
    # VNM đóng cửa 57.200 → trần 61.200, sàn 53.200 (HOSE ±7%)
    lim = vn_rules.price_limits(57_200, "HOSE")
    assert lim.ceiling == 61_200 and lim.floor == 53_200


def test_tick_and_lot():
    assert vn_rules.tick_size(9_990) == 10 and vn_rules.tick_size(25_000) == 50 and vn_rules.tick_size(60_000) == 100
    assert vn_rules.tick_size(60_000, "HNX") == 100
    assert vn_rules.split_order(1530) == [1500, 30]
    assert vn_rules.round_lot(1530) == 1500


def test_trade_costs():
    buy = vn_rules.trade_costs("BUY", 100_000_000)
    sell = vn_rules.trade_costs("SELL", 100_000_000)
    assert buy["total"] == pytest.approx(150_000)
    assert sell["total"] == pytest.approx(250_000)


def test_mm_identity_holds():
    """ROE = (1 + LEV)·ROA_op − LEV·Sd phải đúng tuyệt đối với số liệu kế toán."""
    rows = [{"year": 2024, "revenue": 1000, "net_income": 80, "total_assets": 1000, "equity": 400,
             "total_liabilities": 600, "interest_expense": 30, "current_assets": 500, "current_liabilities": 300}]
    r = fundamental.ratios_by_year(rows)[0]
    rhs = (1 + r["lev"]) * r["roa_op"] - r["lev"] * r["sd"]
    assert r["roe"] == pytest.approx(rhs)
    assert r["leverage_spread"] > 0


def test_ols_and_mundlak():
    x = np.linspace(0.02, 0.2, 20)
    reg = fundamental.ols(list(x), list(0.01 + 2 * x))
    assert reg["b"] == pytest.approx(2) and reg["a"] == pytest.approx(0.01) and reg["r2"] == pytest.approx(1)
    rng = np.random.default_rng(0)
    panel = {f"F{i}": [(a, 0.02 + 1.3 * a + rng.normal(0, 0.005)) for a in rng.uniform(0.02, 0.2, 8)] for i in range(5)}
    m = quant.mundlak(panel)
    assert m["n_firms"] == 5 and m["b_within"] == pytest.approx(1.3, abs=0.15)
    assert m["w_between"] + m["w_within"] == pytest.approx(1, abs=1e-9)
