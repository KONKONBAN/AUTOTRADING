"""Kiểm thử công thức bằng chính các ví dụ trong tài liệu (PTVĐTCK, CFA, Toán tài chính, FQA)."""
import pytest

from app.analysis import risk
from app.finance import calculators as c


def test_holding_period_return_vd1():
    # Mua 95.000, cổ tức 15.000, bán 120.000 → tổng lời 40 triệu / 1.000 CP
    r = risk.holding_period_return(95_000, 120_000, 15_000)
    assert r["total_return"] * 95_000 * 1000 == pytest.approx(40_000_000)
    assert r["dividend_yield"] == pytest.approx(15_000 / 95_000)


def test_cumulative_and_geometric_vd4_vd5():
    rets = [0.11, -0.05, 0.09]
    assert risk.cumulative_return(rets) == pytest.approx(0.1494, abs=1e-4)  # ≈ 15%
    assert risk.geometric_mean_return(rets) == pytest.approx(0.047, abs=1e-3)  # ≈ 4,7%
    assert risk.arithmetic_mean_return(rets) == pytest.approx(0.05)


def test_irr_vd6():
    assert c.irr([-1, -0.1, -0.5, 0.8, 1.0]) == pytest.approx(0.0417, abs=1e-3)


def test_expected_return_scenarios():
    s = risk.scenario_analysis(28_000, [
        {"prob": 0.3, "price": 40_000, "dividend": 6_000},
        {"prob": 0.4, "price": 32_000, "dividend": 3_500},
        {"prob": 0.3, "price": 15_000, "dividend": 2_000},
    ])
    assert s["expected_return"] == pytest.approx(0.1821, abs=1e-3)  # 18,22%
    assert s["std_dev"] > 0


def test_bond_examples_ch3():
    assert c.bond_ytm(1_035_000, 1_000_000, 0.10, 2) == pytest.approx(0.08036, abs=1e-4)
    assert c.bond_price(1_000_000, 0.10, 0.10, 5)["price"] == pytest.approx(1_000_000)
    assert c.bond_price(1_000_000, 0.08, 0.10, 15)["price"] < 1_000_000  # coupon < LS thị trường → dưới mệnh giá
    cy = c.bond_price(1_000_000, 0.10, 0.08, 2)
    assert cy["status"].startswith("cao hơn")
    cv = c.convertible_bond(1_000_000, 40_000, 50_000)
    assert cv["conversion_ratio"] == 25 and cv["conversion_value"] == 1_250_000 and cv["should_convert"]
    assert c.zero_coupon_price(1_000_000, 0.10, 20) == pytest.approx(148_643.6, rel=1e-4)


def test_cfa_npv_and_wacc():
    res = c.project_appraisal([-1000] + [300] * 5, 0.10)
    assert res["npv"] == pytest.approx(137.2, abs=0.1)
    assert res["decision"].startswith("CHẤP NHẬN")
    w = c.wacc(6000, 4000, 0.15, 0.08, 0.20)
    assert w["wacc"] == pytest.approx(0.1156)


def test_fqa_compound_variable_rates():
    assert c.compound_variable_rates(100, [0.06, 0.07, 0.08]) == pytest.approx(122.4936, abs=1e-3)


def test_annuities_and_loans():
    a = c.annuity(1_000, 0.1, 3)
    assert a["fv"] == pytest.approx(3_310)
    pay = c.annuity_payment(1_000_000, 0.01, 12)
    sched = c.loan_schedule(1_000_000, 0.01, 12)
    assert sched["schedule"][-1]["balance"] == pytest.approx(0, abs=1e-6)
    assert sched["schedule"][0]["payment"] == pytest.approx(pay)
    eq = c.loan_schedule(1_200, 0.01, 12, "equal_principal")
    assert eq["schedule"][0]["principal"] == pytest.approx(100)


def test_discount_bill():
    r = c.discount_bill(100_000_000, 0.09, 60)
    assert r["discount"] == pytest.approx(1_500_000)


def test_lease_vs_buy_sign():
    cheap_lease = c.lease_vs_buy(1_000_000, 150_000, 5, 0.10)
    pricey_lease = c.lease_vs_buy(1_000_000, 400_000, 5, 0.10)
    assert cheap_lease["nal"] > 0 > pricey_lease["nal"]
