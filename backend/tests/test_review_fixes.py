"""Kiểm thử hồi quy cho các lỗi đã sửa sau đợt review trước khi tạo PR."""
import pytest
from fastapi.testclient import TestClient

from app.agent import agent as agent_mod
from app.analysis import fundamental
from app.data import excel_import, fundamentals, providers
from app.finance import calculators, planner
from app.main import app
from app.services import sector_multiples
from app.trading import broker as broker_mod
from app.trading import engine


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ dữ liệu / Excel
def test_number_conventions():
    assert excel_import._num("1.234", "vn") == 1234
    assert excel_import._num("1,5", "vn") == 1.5
    assert excel_import._num("1.234.567,8") == pytest.approx(1_234_567.8)
    assert excel_import._num("1,234,567.8") == pytest.approx(1_234_567.8)
    assert excel_import._num("(1.200)", "vn") == -1200
    assert excel_import.detect_convention([["1.234.567", "2.345,6"]]) == "vn"
    assert excel_import.detect_convention([["1,234,567", "2,345.6"]]) == "en"


def test_unit_detection_numeric_multipliers():
    assert excel_import._detect_unit([["Đơn vị: 1.000.000 VND"]])[0] == pytest.approx(1e-3)
    assert excel_import._detect_unit([["Đơn vị tính: 1.000 đồng"]])[0] == pytest.approx(1e-6)
    assert excel_import._detect_unit([["Đơn vị: tỷ đồng"]])[0] == pytest.approx(1.0)


def test_numeric_data_rows_are_not_years():
    assert excel_import._row_years(["Doanh thu", 1900, 2000, 2100]) == {}
    assert excel_import._row_years(["Chỉ tiêu", 2022, 2023, 2024]) == {1: 2022, 2: 2023, 3: 2024}


def test_quarterly_only_file_is_rejected_with_clear_message():
    csv = ("Chỉ tiêu,Q1/2024,Q2/2024,Q3/2024,Q4/2024\n"
           "Doanh thu thuần,100,110,120,130\nLợi nhuận sau thuế,10,11,12,13\n").encode()
    with pytest.raises(ValueError, match="QUÝ"):
        excel_import.parse_financial_file(csv, "q.csv")


def test_manual_rows_never_mixed_with_demo():
    t = "VNM"
    fundamentals.delete_manual(t)
    fundamentals.save_manual(t, [{"year": 2024, "revenue": 60_000, "net_income": 9_000,
                                  "total_assets": 50_000, "equity": 35_000, "total_debt": 0}])
    fin = fundamentals.get_financials(t)
    assert fin["source"] == "manual" and [r["year"] for r in fin["rows"]] == [2024]
    row = fin["rows"][0]
    assert row["total_debt"] == 0 and "total_debt" not in row["estimated_fields"]  # 0 hợp lệ, không ước tính
    assert row["shares"] is None and row["eps"] is None  # không lấy số cổ phiếu từ DEMO
    fundamentals.delete_manual(t)


def test_demo_prices_stable_across_lengths():
    a = providers.get_history("FPT", days=200)
    b = providers.get_history("FPT", days=600)
    common = a.index.intersection(b.index)
    assert len(common) > 100
    assert (a.loc[common, "close"] == b.loc[common, "close"]).all()


# ------------------------------------------------------------------ phân tích / tài chính
def test_negative_equity_has_no_roe():
    rows = [{"year": 2024, "revenue": 100, "net_income": -20, "total_assets": 80, "equity": -10,
             "total_liabilities": 90, "interest_expense": 5}]
    r = fundamental.ratios_by_year(rows)[0]
    assert r["negative_equity"] and r["roe"] is None and r["lev"] is None


def test_irr_root_on_grid_point_and_textbook():
    assert calculators.irr([-100, 100]) == 0.0
    assert calculators.irr([-1, -0.1, -0.5, 0.8, 1.0]) == pytest.approx(0.0417, abs=5e-4)


def test_lease_salvage_cashflow():
    res = calculators.lease_vs_buy(1000, 250, 4, 0.10, tax_rate=0.2, salvage=200)
    dep = (1000 - 200) / 4
    assert res["cashflows"][-1] == pytest.approx(-dep * 0.2 - 200)


def test_planner_builds_emergency_fund_first():
    p = planner.plan(30_000_000, 20_000_000, current_savings=0, risk_profile="can_bang")
    eb = p["emergency_build"]
    assert eb["months"] == 12 and eb["monthly"] == pytest.approx(10_000_000)
    assert eb["invest_during_build"] == pytest.approx(0)
    year1 = p["projection"][0]
    assert year1["years"] == 1 and year1["invested"] == pytest.approx(0)
    assert year1["emergency_fund"] >= 120_000_000


def test_sector_multiples_exclude_self():
    from app.data import universe
    sector = universe.info("VCB")["sector"]
    with_self = sector_multiples(sector)
    without = sector_multiples(sector, exclude="VCB")
    assert without["n"] <= with_self["n"]


# ------------------------------------------------------------------ giao dịch
def test_limit_orders_and_typos():
    b = broker_mod.get_broker()
    b.reset(500_000_000)
    last = float(providers.get_history("FPT", days=60)["close"].iloc[-1])
    with pytest.raises(broker_mod.OrderError, match="thấp hơn"):
        b.place_order("FPT", "BUY", 100, last * 0.97)
    with pytest.raises(broker_mod.OrderError, match="danh sách"):
        b.place_order("FTP", "BUY", 100)
    res = b.place_order(" fpt ", "BUY", 100, last * 1.03)
    assert res["price"] == last  # luôn khớp tại giá thị trường
    b.reset(500_000_000)


def test_proposal_cannot_be_approved_twice():
    broker_mod.get_broker().reset(500_000_000)
    pid = engine.create_proposal("hpg", "buy", 100, None, "test")["proposal_id"]
    first = engine.decide_proposal(pid, True)
    assert first["status"] == "executed"
    with pytest.raises(ValueError):
        engine.decide_proposal(pid, True)
    with pytest.raises(ValueError):
        engine.create_proposal("XXXX", "BUY", 100, None, "typo")
    broker_mod.get_broker().reset(500_000_000)


# ------------------------------------------------------------------ API
def test_technical_endpoint_rejects_bad_ranges(client):
    assert client.get("/api/stocks/FPT/technical?start=abc").status_code == 400
    assert client.get("/api/stocks/FPT/technical?start=2025-06-01&end=2025-01-01").status_code == 400


def test_unknown_api_path_is_404_not_spa(client):
    assert client.get("/api/khong-ton-tai").status_code == 404


def test_upload_rejects_unsupported_file(client):
    r = client.post("/api/financials/upload", files={"file": ("bctc.pdf", b"%PDF-1.4 ...", "application/pdf")})
    assert r.status_code == 400


# ------------------------------------------------------------------ AI agent
def test_dangling_tool_use_is_closed():
    msgs = [{"role": "user", "content": "hi"},
            {"role": "assistant", "content": [{"type": "text", "text": "..."},
                                              {"type": "tool_use", "id": "t1", "name": "x", "input": {}}]}]
    agent_mod._close_dangling_tool_uses(msgs)
    assert msgs[-1]["role"] == "user" and msgs[-1]["content"][0]["tool_use_id"] == "t1"
    agent_mod._append_user(msgs, [{"type": "text", "text": "tiếp"}])
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]


def test_system_prompt_is_stable():
    assert agent_mod._system() == agent_mod._system()
    assert "Ngày hiện tại" not in agent_mod._system()[0]["text"]
