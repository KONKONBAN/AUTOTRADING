"""AutoTrading VN - REST API (FastAPI) + phục vụ giao diện web (React build)."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, auth, remote, services
from .agent import agent as ai_agent
from .agent import knowledge, llm, vision
from .analysis import technical
from .config import settings
from .context import as_user, reset_current_user, set_current_user
from .data import excel_import, fundamentals, listing, providers, universe
from .db import get_db
from .finance import calculators, planner
from .trading import backtest, engine
from .trading import vn_rules
from .trading.broker import OrderError, get_broker, quote
from .utils import clean

log = logging.getLogger("autotrading")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class CleanJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(clean(content), ensure_ascii=False, allow_nan=False, default=str).encode("utf-8")


# ---------------------------------------------------------------- scheduler
async def autotrader_scheduler() -> None:
    """Chạy Auto-Trader mỗi ngày làm việc vào giờ cấu hình (giờ máy tính) - cho TỪNG tài khoản đã bật."""
    while True:
        try:
            now = datetime.now()
            if now.weekday() < 5:
                users = get_db().query("SELECT id FROM users WHERE disabled=0")
                for u in users:
                    with as_user(u["id"]):
                        cfg = engine.load_config()
                        last = engine.last_run() or ""
                        if (cfg.mode != "off" and now.strftime("%H:%M") >= cfg.run_time
                                and not last.startswith(date.today().isoformat())):
                            log.info("Auto-Trader: chạy chu kỳ tự động (%s) cho tài khoản #%s", cfg.mode, u["id"])
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
    remote.stop()


app = FastAPI(title="AutoTrading VN API", version=__version__, lifespan=lifespan,
              default_response_class=CleanJSONResponse)
# KHÔNG bật CORS: giao diện được phục vụ cùng địa chỉ; CORS "*" sẽ cho phép trang web lạ đọc dữ liệu
# danh mục / đặt lệnh qua trình duyệt của bạn tới máy chủ cục bộ.


@app.middleware("http")
async def access_guard(request: Request, call_next):
    """Mọi API (trừ đăng nhập/đăng ký) cần phiên đăng nhập hợp lệ; gắn tài khoản vào ngữ cảnh yêu cầu."""
    user = auth.session_user(request.cookies.get(auth.COOKIE))
    request.state.user = user
    if auth.needs_login(request.url.path) and user is None:
        code = "setup_required" if auth.user_count() == 0 else "login_required"
        return CleanJSONResponse({"detail": "Vui lòng đăng nhập.", "code": code}, status_code=401)
    # chống CSRF bổ sung: yêu cầu thay đổi dữ liệu phải đến từ chính trang của ứng dụng
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
        host = request.headers.get("host", "")
        if origin.split("://", 1)[-1].rstrip("/") != host:
            return CleanJSONResponse({"detail": "Yêu cầu không hợp lệ (khác nguồn)."}, status_code=403)
    token = set_current_user(user["id"] if user else None)
    try:
        response = await call_next(request)
    finally:
        reset_current_user(token)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response


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


# ---------------------------------------------------------------- tài khoản
class SetupIn(BaseModel):
    username: str
    password: str
    display_name: str | None = None


class LoginIn(BaseModel):
    username: str
    password: str
    remember: bool = True


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


class ProfileIn(BaseModel):
    display_name: str


class UserCreateIn(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    role: str = "user"


class UserUpdateIn(BaseModel):
    display_name: str | None = None
    role: str | None = None
    disabled: bool | None = None
    password: str | None = None


class AdminSettingsIn(BaseModel):
    allow_registration: bool


def _me(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Vui lòng đăng nhập.")
    return user


def _admin(request: Request) -> dict:
    user = _me(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Chỉ quản trị viên được thực hiện thao tác này.")
    return user


def _start_session(request: Request, response: Response, user: dict, remember: bool) -> None:
    token, ttl = auth.create_session(user["id"], remember, request.headers.get("user-agent"), auth.client_ip(request))
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(auth.COOKIE, token, max_age=ttl if remember else None, httponly=True, samesite="lax",
                        secure=https, path="/")


@app.get("/api/auth/status")
def auth_status(request: Request):
    return {"setup_required": auth.user_count() == 0, "registration_open": auth.registration_open(),
            "local": auth.is_local(request), "user": getattr(request.state, "user", None),
            "ai_enabled": settings.has_anthropic_credentials}


@app.post("/api/auth/setup")
def auth_setup(body: SetupIn, request: Request, response: Response):
    if not auth.is_local(request):
        raise HTTPException(403, "Tài khoản quản trị đầu tiên chỉ tạo được trên chính máy tính chạy ứng dụng.")
    try:
        user = auth.setup_admin(body.username, body.password, body.display_name)
    except auth.AuthError as exc:
        _bad(exc)
    _start_session(request, response, user, remember=True)
    return {"user": user}


@app.post("/api/auth/register")
def auth_register(body: SetupIn, request: Request, response: Response):
    if auth.user_count() == 0:
        raise HTTPException(400, "Hãy tạo tài khoản quản trị trước.")
    if not auth.registration_open():
        raise HTTPException(403, "Đăng ký đang tắt - liên hệ quản trị viên để được tạo tài khoản.")
    ip = auth.client_ip(request)
    if auth.login_blocked(f"reg:{ip}"):
        raise HTTPException(429, "Thao tác quá nhiều - thử lại sau.")
    auth._record_failure(f"reg:{ip}")  # noqa: SLF001 - giới hạn số tài khoản tạo từ một địa chỉ
    try:
        user = auth.create_user(body.username, body.password, body.display_name)
    except auth.AuthError as exc:
        _bad(exc)
    _start_session(request, response, user, remember=True)
    return {"user": user}


@app.post("/api/auth/login")
def auth_login(body: LoginIn, request: Request, response: Response):
    try:
        user = auth.authenticate(body.username, body.password, auth.client_ip(request))
    except auth.AuthError as exc:
        code = 429 if "quá nhiều" in str(exc) else 401
        raise HTTPException(code, str(exc)) from exc
    _start_session(request, response, user, body.remember)
    return {"user": user}


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    auth.end_session(request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@app.post("/api/auth/password")
def auth_password(body: PasswordIn, request: Request):
    me = _me(request)
    try:
        auth.change_password(me["id"], body.current_password, body.new_password, request.cookies.get(auth.COOKIE))
    except auth.AuthError as exc:
        _bad(exc)
    return {"ok": True}


@app.put("/api/auth/profile")
def auth_profile(body: ProfileIn, request: Request):
    return auth.update_user(_me(request)["id"], display_name=body.display_name)


@app.get("/api/auth/sessions")
def auth_sessions(request: Request):
    return auth.list_sessions(_me(request)["id"], request.cookies.get(auth.COOKIE))


@app.delete("/api/auth/sessions/{sid}")
def auth_revoke(sid: str, request: Request):
    try:
        auth.revoke_session(_me(request)["id"], sid)
    except auth.AuthError as exc:
        _bad(exc)
    return {"ok": True}


@app.get("/api/admin/users")
def admin_users(request: Request):
    _admin(request)
    return {"users": auth.list_users(), "allow_registration": auth.registration_open()}


@app.post("/api/admin/users")
def admin_create_user(body: UserCreateIn, request: Request):
    _admin(request)
    try:
        return auth.create_user(body.username, body.password, body.display_name, body.role)
    except auth.AuthError as exc:
        _bad(exc)


@app.patch("/api/admin/users/{uid}")
def admin_update_user(uid: int, body: UserUpdateIn, request: Request):
    me = _admin(request)
    try:
        return auth.update_user(uid, display_name=body.display_name, role=body.role, disabled=body.disabled,
                                password=body.password, acting_user_id=me["id"])
    except auth.AuthError as exc:
        _bad(exc)


@app.delete("/api/admin/users/{uid}")
def admin_delete_user(uid: int, request: Request):
    me = _admin(request)
    try:
        auth.delete_user(uid, me["id"])
    except auth.AuthError as exc:
        _bad(exc)
    return {"ok": True}


@app.put("/api/admin/settings")
def admin_settings(body: AdminSettingsIn, request: Request):
    _admin(request)
    auth.set_registration(body.allow_registration)
    return {"allow_registration": auth.registration_open()}


# ---------------------------------------------------------------- mở trên điện thoại
@app.get("/api/remote/info")
def remote_info(request: Request):
    port = request.url.port or settings.port
    return {"lan_urls": [f"http://{ip}:{port}" for ip in remote.lan_addresses()],
            "lan_enabled": settings.host in {"0.0.0.0", "::"}, "tunnel": remote.status(),
            "local": auth.is_local(request)}


@app.post("/api/remote/tunnel/start")
async def tunnel_start(request: Request):
    _admin(request)
    if not auth.is_local(request):
        raise HTTPException(403, "Chỉ bật được trên chính máy tính chạy ứng dụng.")
    return await asyncio.to_thread(remote.start, request.url.port or settings.port)


@app.post("/api/remote/tunnel/stop")
def tunnel_stop(request: Request):
    _admin(request)
    return remote.stop()


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
                           "last_run": engine.last_run()}}


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
    """Danh mục theo dõi mặc định + danh sách đầy đủ mọi mã niêm yết (dùng cho ô tìm kiếm)."""
    full = listing.stocks()
    return {"stocks": universe.list_universe(), "sectors": universe.sectors(), "vn30": universe.VN30,
            "all": [{"ticker": t, "name": v.get("name") or t, "exchange": v.get("exchange"), "sector": v.get("sector") or ""}
                    for t, v in sorted(full.items())],
            "listing_source": listing.source() if full else None}


@app.post("/api/data/listing/refresh")
def listing_refresh():
    try:
        n = len(listing.refresh())
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"count": n, "source": listing.source()}


@app.get("/api/events")
def events(request: Request, limit: int = 50):
    return get_db().query("SELECT * FROM events WHERE user_id=? ORDER BY id DESC LIMIT ?",
                          (request.state.user["id"], limit))


# ---------------------------------------------------------------- market & stocks
@app.get("/api/market")
def market():
    return services.market_overview()


@app.get("/api/market/indices")
def market_indices():
    return services.market_indices()


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
    # chuỗi ngày có múi giờ (…+07:00) → bỏ múi giờ, giữ ngày giờ địa phương (chỉ mục giá không có múi giờ)
    ts_start = ts_start.tz_localize(None) if ts_start is not None and ts_start.tzinfo else ts_start
    ts_end = ts_end.tz_localize(None) if ts_end is not None and ts_end.tzinfo else ts_end
    if (ts_start is not None and pd.isna(ts_start)) or (ts_end is not None and pd.isna(ts_end)):
        raise HTTPException(400, "Ngày không hợp lệ (định dạng YYYY-MM-DD).")
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


@app.get("/api/quote/{ticker}")
def order_quote(ticker: str):
    """Thông tin cho ô đặt lệnh nhanh: giá khớp gần nhất, tham chiếu/trần/sàn, bước giá, số dư khả dụng."""
    ticker = ticker.strip().upper()
    if not universe.is_listed(ticker) or providers.is_index(ticker):
        raise HTTPException(404, f"Mã {ticker} không có trong danh sách niêm yết.")
    try:
        q = quote(ticker)
    except (OrderError, providers.DataUnavailable) as exc:
        _bad(exc)
    acc = get_broker().account()
    pos = next((p for p in acc["positions"] if p["ticker"] == ticker), None)
    info = universe.info(ticker)
    return {**q, "ticker": ticker, "name": info["name"], "tick": vn_rules.tick_size(q["last"], q["exchange"]),
            "cash": acc["cash"], "held": pos["quantity"] if pos else 0, "sellable": pos.get("sellable", 0) if pos else 0}


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
