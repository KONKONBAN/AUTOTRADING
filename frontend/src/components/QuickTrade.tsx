import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, X } from "lucide-react";
import { api } from "../lib/api";
import { useStatus } from "../lib/status";
import { cls, money, pct, tickFor, vnd } from "../lib/format";
import { Alert, Field, Seg, Spinner, TickerLogo, useToast } from "./ui";

type Quote = {
  ticker: string; name: string; exchange: string; last: number; reference: number; tick: number;
  limits: { reference: number; ceiling: number; floor: number }; cash: number; held: number; sellable: number;
};

const Ctx = createContext<(ticker?: string, side?: "BUY" | "SELL") => void>(() => {});
/** Mở ô đặt lệnh nhanh từ bất kỳ đâu (nút giữa thanh điều hướng điện thoại, trang Tổng quan…). */
export const useQuickTrade = () => useContext(Ctx);

const FEE = 0.0015;
const SELL_TAX = 0.001;

// Màu giá theo quy ước bảng giá: trần tím, sàn xanh lơ, tham chiếu vàng, tăng xanh, giảm đỏ.
function priceTone(p: number, q: Quote): string {
  if (p >= q.limits.ceiling) return "ceil";
  if (p <= q.limits.floor) return "floor";
  if (Math.abs(p - q.limits.reference) < 1e-6) return "ref";
  return p > q.limits.reference ? "up" : "down";
}

function Sheet({ initial, side: side0, onClose }: { initial: string; side: "BUY" | "SELL"; onClose: () => void }) {
  const { universe } = useStatus();
  const toast = useToast();
  const nav = useNavigate();
  const [input, setInput] = useState(initial);
  const [ticker, setTicker] = useState(initial);
  const [q, setQ] = useState<Quote | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [side, setSide] = useState<"BUY" | "SELL">(side0);
  const [qty, setQty] = useState(100);
  const [px, setPx] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (!ticker) return;
    let alive = true;
    setLoading(true);
    setErr(null);
    setQ(null);
    api.get<Quote>(`/api/quote/${encodeURIComponent(ticker)}`)
      .then((r) => { if (alive) { setQ(r); setPx(r.last); } })
      .catch((e) => alive && setErr(e.message))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [ticker]);

  const pick = () => {
    const t = input.trim().toUpperCase();
    if (t) setTicker(t);
  };
  const value = qty * px;
  const cost = value * (side === "BUY" ? FEE : FEE + SELL_TAX);
  const maxBuy = q && px > 0 ? Math.floor(q.cash / (px * (1 + FEE)) / 100) * 100 : 0;
  const outOfBand = q ? px > q.limits.ceiling || px < q.limits.floor : false;
  const tick = q ? tickFor(px || q.last, q.exchange) : 100;
  const offTick = q ? Math.abs(px / tick - Math.round(px / tick)) > 1e-6 : false;
  const problem = !q ? null
    : qty <= 0 || qty % 100 !== 0 ? "Khối lượng phải là bội số của 100 (lô chẵn)."
    : outOfBand ? `Giá phải nằm trong biên độ ${vnd(q.limits.floor)} – ${vnd(q.limits.ceiling)}.`
    : offTick ? `Giá phải theo bước giá ${vnd(tick)}đ.`
    : side === "BUY" && px < q.last ? `Giá mua thấp hơn giá khớp gần nhất ${vnd(q.last)} - lệnh LO sẽ chưa khớp (tài khoản giấy không giữ lệnh chờ).`
    : side === "SELL" && px > q.last ? `Giá bán cao hơn giá khớp gần nhất ${vnd(q.last)} - lệnh LO sẽ chưa khớp (tài khoản giấy không giữ lệnh chờ).`
    : side === "BUY" && value * (1 + FEE) > q.cash ? "Không đủ tiền mặt khả dụng."
    : side === "SELL" && qty > q.sellable ? `Chỉ bán được ${vnd(q.sellable)} CP (cổ phiếu về tài khoản sau T+2).`
    : null;

  const submit = async () => {
    if (!q || problem) return;
    setBusy(true);
    try {
      const r = await api.post("/api/orders", { ticker: q.ticker, side, quantity: qty, price: px, reason: "Lệnh từ ô đặt lệnh nhanh" });
      toast("ok", `Đã khớp lệnh ${side === "BUY" ? "MUA" : "BÁN"} ${vnd(r.quantity)} ${q.ticker} @ ${vnd(r.price)} (tài khoản giao dịch giấy)`);
      window.dispatchEvent(new Event("orders-changed"));
      onClose();
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="sheet-backdrop" onMouseDown={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Đặt lệnh nhanh" onMouseDown={(e) => e.stopPropagation()}>
        <div className="sheet-grip" />
        <div className="row between">
          <div>
            <h2>Đặt lệnh nhanh</h2>
            <div className="tiny subtle">Tài khoản giao dịch giấy · lô 100 · T+2</div>
          </div>
          <button className="btn icon ghost" onClick={onClose} title="Đóng"><X size={18} /></button>
        </div>

        <form className="row" onSubmit={(e) => { e.preventDefault(); pick(); }}>
          <input className="input" list="qt-tickers" placeholder="Nhập mã, ví dụ FPT" value={input} autoFocus={!initial}
            onChange={(e) => setInput(e.target.value.toUpperCase())} onBlur={pick} style={{ textTransform: "uppercase" }} />
          <datalist id="qt-tickers">{universe.slice(0, 2000).map((u) => <option key={u.ticker} value={u.ticker}>{u.name}</option>)}</datalist>
          <button className="btn" type="submit">Xem giá</button>
        </form>

        {loading && <div className="row" style={{ justifyContent: "center", padding: 18 }}><Spinner /></div>}
        {err && <Alert kind="err" title={`Không lấy được giá ${ticker}`}>{err}</Alert>}
        {q && (
          <>
            <div className="quote-head">
              <TickerLogo ticker={q.ticker} size={40} />
              <div className="grow" style={{ minWidth: 0 }}>
                <div className="bold">{q.ticker} <span className="subtle small">· {q.exchange}</span></div>
                <div className="tiny subtle ellipsis">{q.name}</div>
              </div>
              <div className="right">
                <div className={cls("num bold", priceTone(q.last, q))} style={{ fontSize: 20 }}>{vnd(q.last)}</div>
                <div className={cls("num small", priceTone(q.last, q))}>{pct(q.last / q.reference - 1, 2, true)}</div>
              </div>
            </div>
            <div className="quote-limits">
              <button type="button" onClick={() => setPx(q.limits.ceiling)}><span>Trần</span><b className="num ceil">{vnd(q.limits.ceiling)}</b></button>
              <button type="button" onClick={() => setPx(q.limits.reference)}><span>Tham chiếu</span><b className="num ref">{vnd(q.limits.reference)}</b></button>
              <button type="button" onClick={() => setPx(q.limits.floor)}><span>Sàn</span><b className="num floor">{vnd(q.limits.floor)}</b></button>
            </div>
            <Seg value={side} onChange={setSide} items={[{ value: "BUY", label: "Mua" }, { value: "SELL", label: "Bán" }]} />
            <div className="grid g2" style={{ gap: 10 }}>
              <Field label="Khối lượng (CP)" help={side === "BUY" ? `Mua tối đa ≈ ${vnd(maxBuy)} CP` : `Có thể bán: ${vnd(q.sellable)} / đang giữ ${vnd(q.held)}`}>
                <input className="input num" type="number" inputMode="numeric" step={100} min={100} value={qty} onChange={(e) => setQty(Math.max(0, Math.floor(Number(e.target.value) || 0)))} />
              </Field>
              <Field label="Giá đặt (đ)" help={`Bước giá ${vnd(tick)}đ`}>
                <input className="input num" type="number" inputMode="decimal" step={tick} value={px} onChange={(e) => setPx(Number(e.target.value) || 0)} />
              </Field>
            </div>
            <div className="quote-sum">
              <div className="row between small"><span className="muted">Giá trị lệnh</span><b className="num">{vnd(value)}đ</b></div>
              <div className="row between small"><span className="muted">Phí 0,15%{side === "SELL" ? " + thuế 0,1%" : ""}</span><span className="num">{vnd(cost)}đ</span></div>
              <div className="row between small"><span className="muted">Tiền mặt khả dụng</span><span className="num">{money(q.cash)}</span></div>
            </div>
            {problem && <div className="small down">{problem}</div>}
            <button className={cls("btn lg block", side === "BUY" ? "buy" : "sell")} disabled={busy || !!problem} onClick={submit}>
              {busy ? "Đang gửi lệnh…" : `${side === "BUY" ? "Mua" : "Bán"} ${vnd(qty)} ${q.ticker} · ${vnd(value)}đ`}
            </button>
            <button className="btn ghost sm" style={{ alignSelf: "center" }} onClick={() => { onClose(); nav(`/stock/${q.ticker}`); }}>
              Xem phân tích {q.ticker} <ArrowRight size={14} />
            </button>
          </>
        )}
        {!ticker && !loading && <div className="small subtle">Nhập mã cổ phiếu để xem giá trần/sàn/tham chiếu và đặt lệnh.</div>}
      </div>
    </div>
  );
}

export function QuickTradeProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ ticker: string; side: "BUY" | "SELL"; key: number } | null>(null);
  const open = useCallback((ticker = "", side: "BUY" | "SELL" = "BUY") => setState({ ticker: ticker.toUpperCase(), side, key: Date.now() }), []);
  return (
    <Ctx.Provider value={open}>
      {children}
      {state && <Sheet key={state.key} initial={state.ticker} side={state.side} onClose={() => setState(null)} />}
    </Ctx.Provider>
  );
}
