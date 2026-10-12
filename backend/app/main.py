"""AutoTrading VN - REST API (FastAPI) + phục vụ giao diện web (React build)."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, services
from .agent import agent as ai_agent
from .agent import knowledge, llm, vision
from .analysis import technical
from .config import settings
from .data import excel_import, fundamentals, providers, universe
from .db import get_db
from .finance import calculators, planner
from .trading import backtest, engine
from .trading.broker import OrderError, get_broker
from .utils import clean

log = logging.getLogger("autotrading")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class CleanJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(clean(content), ensure_ascii=False, allow_nan=False, default=str).encode("utf-8")


# ---------------------------------------------------------------- scheduler
async def autotrader_scheduler() -> None:
    """Chạy Auto-Trader mỗi ngày làm việc vào giờ cấu hình (giờ máy chủ)."""
    while True:
        try:
            cfg = engine.load_config()
            now = datetime.now()
            last = get_db().get_kv("autotrader_last_run") or ""
            if (cfg.mode != "off" and now.weekday() < 5 and now.strftime("%H:%M") >= cfg.run_time
                    and not last.startswith(date.today().isoformat())):
                log.info("Auto-Trader: chạy chu kỳ tự động (%s)", cfg.mode)
                services.clear_caches()
                await asyncio.to_thread(engine.run_cycle, cfg)
        except Exception:  # noqa: BLE001
            log.exception("Lỗi scheduler Auto-Trader")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_db()
    task = asyncio.create_task(autotrader_scheduler()) if settings.autotrader_scheduler else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="AutoTrading VN API", version=__version__, lifespan=lifespan,
              default_response_class=CleanJSONResponse)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _bad(exc: Exception, code: int = 400):
    raise HTTPException(status_code=code, detail=str(exc)) from exc


async def _read_files(files: list[UploadFile] | None) -> list[tuple[bytes, str]]:
    out = []
    for f in files or []:
        data = await f.read()
        mt = f.content_type or ""
        name = (f.filename or "").lower()
        if mt in {"", "application/octet-stream"}:
            mt = ("application/pdf" if name.endswith(".pdf") else "image/png" if name.endswith(".png")
                  else "image/jpeg" if name.endswith((".jpg", ".jpeg")) else "image/webp" if name.endswith(".webp")
                  else mt)
        out.append((data, mt))
    return out


# ---------------------------------------------------------------- system
@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


@app.get("/api/status")
def status():
    return {"version": __version__, "data": providers.data_status(),
            "ai_enabled": settings.has_anthropic_credentials, "ai_model": settings.agent_model,
            "live_trading_allowed": settings.allow_live_trading,
            "autotrader": {"config": engine.load_config().__dict__,
                           "last_run": get_db().get_kv("autotrader_last_run")}}


@app.post("/api/data/health-check")
def data_health(ticker: str = "FPT"):
    res = providers.provider_health(ticker)
    services.clear_caches()
    get_db().execute("DELETE FROM cache WHERE key LIKE 'hist:%' OR key LIKE 'fin:%'")
    return {"results": res, "any_ok": any(r["ok"] for r in res)}


@app.post("/api/data/refresh")
def data_refresh():
    services.clear_caches()
    get_db().execute("DELETE FROM cache")
    return {"ok": True}


@app.get("/api/universe")
def get_universe():
    return {"stocks": universe.list_universe(), "sectors": universe.sectors(), "vn30": universe.VN30}


@app.get("/api/events")
def events(limit: int = 50):
    return get_db().query("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))


# ---------------------------------------------------------------- market & stocks
@app.get("/api/market")
def market():
    return services.market_overview()


@app.get("/api/stocks/{ticker}/analysis")
def stock_analysis(ticker: str, equity: float = 100_000_000):
    try:
        return services.analyze_stock(ticker.upper(), equity=equity)
    except providers.DataUnavailable as exc:
        _bad(exc, 503)


@app.get("/api/stocks/{ticker}/technical")
def stock_technical(ticker: str, start: str | None = None, end: str | None = None):
    """Phân tích kỹ thuật theo khoảng thời gian tùy chọn."""
    try:
        ts_start = pd.Timestamp(start) if start else None
        ts_end = pd.Timestamp(end) if end else None
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "Ngày không hợp lệ (định dạng YYYY-MM-DD).") from exc
    if ts_start is not None and ts_end is not None and ts_start > ts_end:
        raise HTTPException(400, "Ngày bắt đầu phải trước ngày kết thúc.")
    df = providers.get_history(ticker.upper(), days=1500)
    if ts_end is not None:
        df = df[df.index <= ts_end]
    view = df
    if ts_start is not None:
        view = df[df.index >= ts_start]
        pos = df.index.searchsorted(ts_start)
        df = df.iloc[max(0, pos - 200):]
    if view.empty:
        raise HTTPException(400, "Không có phiên giao dịch nào trong khoảng thời gian đã chọn.")
    if len(df) < 60:
        raise HTTPException(400, "Không đủ dữ liệu trong khoảng thời gian đã chọn (cần ≥ 60 phiên).")
    res = technical.analyze(df)
    chart = technical.chart_series(df, limit=len(view) if start else 400)
    perf = float(view["close"].iloc[-1] / view["close"].iloc[0] - 1) if len(view) > 1 else None
    return {"ticker": ticker.upper(), "source": df.attrs.get("source"), "technical": res, "chart": chart,
            "period": {"start": view.index[0].strftime("%Y-%m-%d"), "end": view.index[-1].strftime("%Y-%m-%d"),
                       "sessions": len(view), "return": perf,
                       "high": float(view["high"].max()), "low": float(view["low"].min())}}


@app.get("/api/screener")
def screener(sector: str | None = None):
    return {"results": services.screen(sector), "market": {
        k: services.market_overview()[k] for k in ("regime", "recommended_exposure")}}


@app.get("/api/sectors/{sector}/analysis")
def sector(sector: str):
    return services.sector_analysis(sector)


# ---------------------------------------------------------------- financial statements
class ManualRows(BaseModel):
    rows: list[dict[str, Any]]


@app.get("/api/financials/fields")
def financial_fields():
    return [{"key": k, "label": label, "unit": unit, "required": k in fundamentals.REQUIRED_FIELDS}
            for k, label, unit in fundamentals.MANUAL_FIELDS]


@app.get("/api/financials/template")
def financial_template(ticker: str | None = None):
    data = excel_import.financial_template(ticker)
    name = f"BCTC_mau_{ticker.upper() if ticker else 'trong'}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/financials/{ticker}")
def financials(ticker: str):
    fin = fundamentals.get_financials(ticker)
    from .analysis import fundamental
    return {"ticker": ticker.upper(), "source": fin["source"], "manual_years": fin.get("manual_years", []),
            "rows": fin["rows"], "ratios": fundamental.ratios_by_year(fin["rows"]),
            "manual": fundamentals.list_manual(ticker)}


@app.put("/api/financials/{ticker}/manual")
def save_financials(ticker: str, body: ManualRows):
    try:
        saved = fundamentals.save_manual(ticker, body.rows)
    except (ValueError, KeyError, TypeError) as exc:
        _bad(exc)
    services.clear_caches()
    return {"saved": saved}


@app.delete("/api/financials/{ticker}/manual")
def delete_financials(ticker: str, year: int | None = None):
    fundamentals.delete_manual(ticker, year)
    services.clear_caches()
    return {"ok": True}


@app.post("/api/financials/upload")
async def upload_financials(file: UploadFile = File(...), ticker: str | None = Form(None),
                            use_ai: bool = Form(False)):
    """Đọc file Excel/CSV BCTC → bản xem trước (chưa lưu). Nếu không nhận diện được và có AI → AI đọc."""
    data = await file.read()
    name = file.filename or "bctc.xlsx"
    if not use_ai:
        try:
            return {"method": "parser", **excel_import.parse_financial_file(data, name)}
        except excel_import.FileFormatError as exc:
            _bad(exc)  # file hỏng / sai định dạng: AI cũng không đọc được
        except ValueError as exc:
            if not settings.has_anthropic_credentials:
                _bad(exc)
    try:
        text = excel_import.grid_as_text(data, name)
        return {"method": "ai", **vision.extract_financials_from_text(text, ticker)}
    except (llm.AIUnavailable, llm.AIRefusal, RuntimeError, ValueError) as exc:
        _bad(exc)


@app.post("/api/financials/extract")
async def extract_financials(files: list[UploadFile] = File(...), ticker: str | None = Form(None)):
    """AI đọc ảnh chụp / PDF BCTC → bản xem trước số liệu (chưa lưu)."""
    try:
        return {"method": "ai_vision", **vision.extract_financials(await _read_files(files), ticker)}
    except (llm.AIUnavailable, llm.AIRefusal, RuntimeError, ValueError) as exc:
        _bad(exc)


# ---------------------------------------------------------------- price data import
@app.post("/api/prices/upload")
async def upload_prices(file: UploadFile = File(...), ticker: str | None = Form(None)):
    try:
        res = excel_import.import_price_file(await file.read(), file.filename or "prices.csv", ticker)
    except ValueError as exc:
        _bad(exc)
    services.clear_caches()
    return res


@app.get("/api/prices/imported")
def imported_prices():
    return excel_import.imported_summary()


@app.delete("/api/prices/imported/{ticker}")
def delete_prices(ticker: str):
    excel_import.delete_imported(ticker)
    services.clear_caches()
    return {"ok": True}


# ---------------------------------------------------------------- chart screenshot analysis
@app.post("/api/charts/analyze")
async def analyze_chart(files: list[UploadFile] = File(...), ticker: str | None = Form(None),
                        timeframe: str | None = Form(None), start: str | None = Form(None),
                        end: str | None = Form(None), note: str | None = Form(None)):
    try:
        return vision.analyze_chart(await _read_files(files), ticker or None, timeframe, start or None,
                                    end or None, note)
    except (llm.AIUnavailable, llm.AIRefusal, RuntimeError, ValueError) as exc:
        _bad(exc)


@app.get("/api/charts/history")
def chart_history(limit: int = 20):
    return vision.recent_chart_analyses(limit)


# ---------------------------------------------------------------- portfolio & orders
class OrderIn(BaseModel):
    ticker: str
    side: str
    quantity: int
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""


class ResetIn(BaseModel):
    initial_cash: float = Field(default_factory=lambda: settings.paper_initial_cash, gt=0)


class OptimizeIn(BaseModel):
    tickers: list[str]
    objective: str = "max_sharpe"
    max_weight: float = 0.25
    capital: float | None = None


@app.get("/api/portfolio")
def portfolio():
    acc = get_broker().account()
    acc["orders"] = get_broker().orders(50)
    return acc


@app.post("/api/portfolio/reset")
def portfolio_reset(body: ResetIn):
    get_broker().reset(body.initial_cash)
    return get_broker().account()


@app.post("/api/orders")
def place_order(body: OrderIn):
    try:
        return get_broker().place_order(body.ticker, body.side, body.quantity, body.price, source="manual",
                                        reason=body.reason, stop_loss=body.stop_loss, take_profit=body.take_profit)
    except OrderError as exc:
        _bad(exc)


@app.get("/api/orders")
def list_orders(limit: int = 200):
    return get_broker().orders(limit)


@app.post("/api/portfolio/optimize")
def optimize(body: OptimizeIn):
    from .agent.tools import t_optimize_portfolio
    try:
        # đường biên hiệu quả lấy từ CÙNG lần tối ưu (cùng vector lợi nhuận kỳ vọng) với danh mục tối ưu
        return t_optimize_portfolio(body.tickers, body.objective, body.max_weight, body.capital, keep_frontier=True)
    except ValueError as exc:
        _bad(exc)


# ---------------------------------------------------------------- auto trader
class RunIn(BaseModel):
    mode: str | None = None


@app.get("/api/autotrader/config")
def at_config():
    return engine.load_config().__dict__


@app.put("/api/autotrader/config")
def at_save(body: dict[str, Any]):
    try:
        return engine.save_config(body).__dict__
    except (ValueError, TypeError) as exc:
        _bad(exc)


@app.post("/api/autotrader/plan")
def at_plan():
    services.clear_caches()
    return engine.plan_cycle()


@app.post("/api/autotrader/run")
def at_run(body: RunIn):
    services.clear_caches()
    mode = body.mode or engine.load_config().mode
    if mode not in {"off", "suggest", "auto_paper"}:
        raise HTTPException(400, "mode không hợp lệ")
    return engine.run_cycle(force_mode=mode)


@app.get("/api/proposals")
def proposals(status: str | None = "pending"):
    return engine.list_proposals(status or None)


@app.post("/api/proposals/{pid}/approve")
def approve(pid: int):
    try:
        return engine.decide_proposal(pid, True)
    except ValueError as exc:
        _bad(exc)


@app.post("/api/proposals/{pid}/reject")
def reject(pid: int):
    try:
        return engine.decide_proposal(pid, False)
    except ValueError as exc:
        _bad(exc)


class BacktestIn(BaseModel):
    tickers: list[str] | None = None
    initial_cash: float = 500_000_000
    min_score: float = 60
    max_positions: int = 8
    max_weight: float = 0.20
    risk_per_trade: float = 0.015
    trailing_stop_pct: float = 0.10
    max_stop_pct: float = 0.07
    use_market_filter: bool = True


@app.post("/api/backtest")
def run_bt(body: BacktestIn):
    try:
        return backtest.run_backtest(**body.model_dump())
    except ValueError as exc:
        _bad(exc)


# ---------------------------------------------------------------- AI agent
@app.post("/api/agent/chat")
async def agent_chat(message: str = Form(...), session_id: str | None = Form(None),
                     files: list[UploadFile] | None = File(None)):
    try:
        attachments = await _read_files(files)
        return await asyncio.to_thread(ai_agent.chat, message, session_id or None, attachments)
    except ValueError as exc:
        _bad(exc)


@app.get("/api/agent/sessions")
def agent_sessions():
    return ai_agent.list_sessions()


@app.get("/api/agent/sessions/{sid}")
def agent_session(sid: str):
    return {"id": sid, "messages": ai_agent.transcript(sid)}


@app.delete("/api/agent/sessions/{sid}")
def agent_delete(sid: str):
    ai_agent.delete_session(sid)
    return {"ok": True}


# ---------------------------------------------------------------- personal finance & calculators
class PlanIn(BaseModel):
    monthly_income: float
    monthly_expenses: float
    current_savings: float = 0
    essential_expenses: float | None = None
    age: int | None = None
    risk_profile: str = "can_bang"
    emergency_months: int = 6
    debts: list[dict] = []
    goals: list[dict] = []


class CalcIn(BaseModel):
    calculator: str
    params: dict[str, Any]


@app.post("/api/finance/plan")
def finance_plan(body: PlanIn):
    return planner.plan(**body.model_dump())


@app.get("/api/finance/risk-questions")
def risk_questions():
    return planner.RISK_QUESTIONS


@app.post("/api/finance/risk-profile")
def risk_profile(answers: dict[str, int]):
    return planner.risk_profile_from_answers(answers)


@app.post("/api/finance/calc")
def finance_calc(body: CalcIn):
    from .agent.tools import CALCULATORS
    fn = CALCULATORS.get(body.calculator)
    if not fn:
        raise HTTPException(404, f"Không có công cụ {body.calculator}")
    try:
        return {"calculator": body.calculator, "result": fn(**body.params)}
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        _bad(exc)


@app.get("/api/knowledge")
def get_knowledge():
    return {"topics": knowledge.TOPICS}


# ---------------------------------------------------------------- frontend (SPA)
_dist = settings.frontend_dist
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    _dist_root = _dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Không tìm thấy API")
        target = (_dist_root / path).resolve()
        # chống path traversal: chỉ phục vụ file nằm TRONG thư mục build của giao diện
        if path and target.is_relative_to(_dist_root) and target.is_file():
            return FileResponse(target)
        return FileResponse(_dist_root / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {"message": "API đang chạy. Hãy build giao diện: cd frontend && npm install && npm run build",
                "docs": "/docs"}
