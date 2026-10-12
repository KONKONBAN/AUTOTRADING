import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Activity, BarChart3, Bot, Calculator, CandlestickChart, CheckCircle2, CircleDollarSign, FileSpreadsheet, Layers, ShieldAlert, Target, XCircle,
} from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { useStatus } from "../lib/status";
import { bn, cls, num, pct, recTone, tone, vnd } from "../lib/format";
import { PriceChart, type Overlays } from "../components/Charts";
import {
  Alert, Badge, Card, ErrorBox, Field, Loading, PartBar, ScoreRing, Seg, SourceBadge, Tabs, TickerLogo, useAsync, useToast,
} from "../components/ui";

type Tab = "chart" | "tech" | "fund" | "val" | "risk" | "plan";
const PERIODS = [
  { value: "3M", label: "3T", days: 63 }, { value: "6M", label: "6T", days: 126 }, { value: "1Y", label: "1N", days: 252 },
  { value: "2Y", label: "2N", days: 504 }, { value: "ALL", label: "Tất cả", days: 0 }, { value: "CUSTOM", label: "Tùy chọn", days: 0 },
] as const;

function Metric({ label, value, cls: c, hint }: { label: string; value: React.ReactNode; cls?: string; hint?: string }) {
  return (
    <div className="card tight flat" title={hint}>
      <div className="tiny subtle">{label}</div>
      <div className={cls("mono bold", c)} style={{ fontSize: 17, marginTop: 4 }}>{value}</div>
    </div>
  );
}

function OrderBox({ ticker, price, plan }: { ticker: string; price: number; plan: any }) {
  const toast = useToast();
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [qty, setQty] = useState<number>(plan.suggested_quantity || 100);
  const [px, setPx] = useState<number>(price);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const r = await api.post("/api/orders", {
        ticker, side, quantity: qty, price: px, reason: "Lệnh thủ công từ trang phân tích",
        stop_loss: side === "BUY" ? plan.stop_loss : null, take_profit: side === "BUY" ? plan.take_profit_1 : null,
      });
      // lệnh LO khớp tại giá thị trường (≤ giá mua đặt / ≥ giá bán đặt) → hiển thị giá khớp thực tế
      toast("ok", `Đã khớp lệnh ${side === "BUY" ? "MUA" : "BÁN"} ${vnd(r.quantity)} ${ticker} @ ${vnd(r.price)} (tài khoản giấy)`);
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy(false);
    }
  };
  const value = qty * px;
  return (
    <div className="col" style={{ gap: 12 }}>
      <Seg value={side} onChange={setSide} items={[{ value: "BUY", label: "Mua" }, { value: "SELL", label: "Bán" }]} />
      <div className="grid g2" style={{ gap: 10 }}>
        <Field label="Khối lượng (lô 100)"><input className="input mono" type="number" step={100} min={100} value={qty} onChange={(e) => setQty(Number(e.target.value))} /></Field>
        <Field label="Giá đặt (đ)"><input className="input mono" type="number" step={50} value={px} onChange={(e) => setPx(Number(e.target.value))} /></Field>
      </div>
      <div className="row between small"><span className="muted">Giá trị lệnh</span><b className="mono">{vnd(value)}đ</b></div>
      <div className="row between small"><span className="muted">Phí 0,15%{side === "SELL" ? " + thuế 0,1%" : ""}</span><span className="mono">{vnd(value * (side === "SELL" ? 0.0025 : 0.0015))}đ</span></div>
      <button className={cls("btn", side === "BUY" ? "buy" : "sell")} disabled={busy || qty <= 0} onClick={submit}>
        {side === "BUY" ? "Đặt lệnh MUA" : "Đặt lệnh BÁN"} (giao dịch giấy)
      </button>
      <div className="tiny subtle">Lệnh khớp trên tài khoản giao dịch giấy theo đúng quy định: lô 100, biên độ, bước giá, T+2.</div>
    </div>
  );
}

export default function Stock() {
  const { ticker: param } = useParams();
  const ticker = (param || "FPT").toUpperCase();
  const nav = useNavigate();
  const { universe } = useStatus();
  const [tab, setTab] = useState<Tab>("chart");
  const [period, setPeriod] = useState<string>("1Y");
  const [range, setRange] = useState<{ start: string; end: string }>({ start: "", end: "" });
  const [ov, setOv] = useState<Overlays>({ ma20: true, ma50: true, ma200: true, bb: false, volume: true });
  const [showLevels, setShowLevels] = useState(true);
  const a = useAsync(() => api.get(`/api/stocks/${ticker}/analysis`), [ticker]);
  const custom = useAsync(
    () => (period === "CUSTOM" && range.start && !(range.end && range.end < range.start)
      ? api.get(`/api/stocks/${ticker}/technical?start=${range.start}${range.end ? `&end=${range.end}` : ""}`)
      : Promise.resolve(null)),
    [ticker, period, range.start, range.end]
  );
  useEffect(() => { setTab("chart"); }, [ticker]);

  const d = a.data;
  // dữ liệu giai đoạn tùy chọn chỉ hợp lệ khi đang KHÔNG tải lại và KHÔNG lỗi (tránh hiển thị khoảng cũ)
  const cd = period === "CUSTOM" && !custom.loading && !custom.error ? custom.data : null;
  const rangeError = period === "CUSTOM" && range.start && range.end && range.end < range.start
    ? "Ngày kết thúc phải sau ngày bắt đầu." : null;
  const chart = useMemo(() => {
    if (period === "CUSTOM") return cd ? cd.chart : null;
    if (!d) return null;
    const p = PERIODS.find((x) => x.value === period);
    if (!p || !p.days) return d.chart;
    const cut = (arr: any[]) => arr.slice(-p.days);
    const c = d.chart;
    const t0 = cut(c.candles)[0]?.time;
    const after = (arr: any[]) => arr.filter((x) => x.time >= t0);
    return { ...c, candles: cut(c.candles), volume: cut(c.volume), sma20: after(c.sma20), sma50: after(c.sma50), sma200: after(c.sma200), bb_upper: after(c.bb_upper), bb_lower: after(c.bb_lower), rsi: after(c.rsi), macd: after(c.macd), macd_signal: after(c.macd_signal), macd_hist: after(c.macd_hist) };
  }, [d, period, cd]);
  const lines = useMemo(() => (d && showLevels ? [
    { price: Math.round(d.trade_plan.stop_loss), title: "Cắt lỗ", color: "#f43f5e" },
    { price: Math.round(d.trade_plan.take_profit_1), title: "Mục tiêu 1", color: "#22c55e" },
    ...(d.valuation.intrinsic_value ? [{ price: Math.round(d.valuation.intrinsic_value), title: "Giá trị nội tại", color: "#f59e0b" }] : []),
  ] : []), [d, showLevels]);

  if (a.loading) return <Loading text={`Đang phân tích ${ticker}: kỹ thuật, cơ bản, định giá, rủi ro…`} height={400} />;
  if (a.error || !d) return <ErrorBox error={a.error ?? "Không có dữ liệu"} onRetry={a.reload} />;

  const t = d.technical, f = d.fundamental, v = d.valuation, r = d.risk, c = d.composite, p = d.trade_plan;
  const tv = cd ? cd.technical : t;

  return (
    <>
      <div className="card hero">
        <div className="row wrap" style={{ gap: 24, alignItems: "stretch" }}>
          <div className="col grow" style={{ gap: 14, minWidth: 280 }}>
            <div className="row" style={{ gap: 14 }}>
              <TickerLogo ticker={ticker} size={52} />
              <div style={{ minWidth: 0 }}>
                <div className="row wrap" style={{ gap: 8 }}>
                  <h1>{ticker}</h1>
                  <Badge>{d.info.exchange}</Badge>
                  <Badge>{d.info.sector}</Badge>
                  {d.info.in_vn30 && <Badge tone="brand">VN30</Badge>}
                </div>
                <div className="muted">{d.info.name}</div>
              </div>
            </div>
            <div className="row wrap" style={{ gap: 16, alignItems: "baseline" }}>
              <span className="mono" style={{ fontSize: 34, fontWeight: 800, letterSpacing: "-0.04em" }}>{vnd(t.price)}</span>
              <span className={cls("mono bold", tone(t.change_pct))} style={{ fontSize: 16 }}>{pct(t.change_pct, 2, true)}</span>
              <span className="subtle small">Phiên {d.last_date}</span>
            </div>
            <div className="row wrap small" style={{ gap: 8 }}>
              <span className="muted">Giá:</span><SourceBadge source={d.data_sources.prices} />
              <span className="muted">BCTC:</span><SourceBadge source={d.data_sources.financials} />
              <Link to={`/data?ticker=${ticker}`} className="small"><FileSpreadsheet size={12} /> Cập nhật BCTC / dữ liệu</Link>
            </div>
            <div className="row wrap" style={{ gap: 8 }}>
              <button className="btn primary" onClick={() => setTab("plan")}><Target size={16} /> Kế hoạch & đặt lệnh</button>
              <button className="btn" onClick={() => nav(`/agent?q=${encodeURIComponent(`Phân tích chuyên sâu mã ${ticker} và cho tôi chiến lược giao dịch phù hợp`)}`)}><Bot size={16} /> Hỏi AI về {ticker}</button>
            </div>
          </div>
          <div className="row wrap" style={{ gap: 24 }}>
            <div className="col" style={{ alignItems: "center", gap: 8 }}>
              <ScoreRing score={c.score} />
              <Badge lg tone={recTone(c.code)}>{c.recommendation}</Badge>
            </div>
            <div className="col" style={{ gap: 10, minWidth: 250, justifyContent: "center" }}>
              <PartBar label="Kỹ thuật" value={c.parts.technical} />
              <PartBar label="Chất lượng" value={c.parts.quality} />
              <PartBar label="Định giá" value={c.parts.valuation} />
              <PartBar label="Rủi ro" value={c.parts.risk} />
              <div className="tiny subtle">Thị trường chung: {d.market.regime}</div>
            </div>
          </div>
        </div>
      </div>

      {(d.data_sources.prices === "demo" || d.data_sources.financials === "demo") && (
        <Alert kind="warn" title="Đang phân tích trên dữ liệu mô phỏng (DEMO)">
          Ứng dụng chưa lấy được dữ liệu thật cho {ticker}. Kết quả chỉ mang tính minh họa — hãy <Link to={`/data?ticker=${ticker}`}>tải file giá/BCTC</Link> để phân tích sát thực tế.
        </Alert>
      )}

      <div className="grid g2">
        <Card title="Điểm mạnh" icon={<CheckCircle2 size={16} color="var(--up)" />}>
          {d.summary.pros.length ? <ul className="pros-cons small" style={{ margin: 0, paddingLeft: 18 }}>{d.summary.pros.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            : <p className="muted small" style={{ margin: 0 }}>Chưa có điểm mạnh nổi bật theo các mô hình hiện tại.</p>}
        </Card>
        <Card title="Rủi ro & điểm yếu" icon={<XCircle size={16} color="var(--down)" />}>
          {d.summary.cons.length ? <ul className="pros-cons small" style={{ margin: 0, paddingLeft: 18 }}>{d.summary.cons.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            : <p className="muted small" style={{ margin: 0 }}>Chưa phát hiện điểm yếu đáng kể theo các mô hình hiện tại - vẫn luôn đặt điểm cắt lỗ và quản trị tỷ trọng.</p>}
        </Card>
      </div>

      <Tabs value={tab} onChange={setTab} items={[
        { value: "chart", label: "Biểu đồ", icon: <CandlestickChart size={15} /> },
        { value: "tech", label: "Kỹ thuật", icon: <Activity size={15} /> },
        { value: "fund", label: "Cơ bản & BCTC", icon: <Layers size={15} /> },
        { value: "val", label: "Định giá", icon: <CircleDollarSign size={15} /> },
        { value: "risk", label: "Rủi ro", icon: <ShieldAlert size={15} /> },
        { value: "plan", label: "Kế hoạch giao dịch", icon: <Target size={15} /> },
      ]} />

      {tab === "chart" && (
        <Card>
          <div className="row wrap between" style={{ marginBottom: 12, gap: 10 }}>
            <Seg value={period} onChange={setPeriod} items={PERIODS.map((x) => ({ value: x.value, label: x.label }))} />
            <div className="row wrap" style={{ gap: 6 }}>
              {(["ma20", "ma50", "ma200", "bb", "volume"] as const).map((k) => (
                <button key={k} className={cls("chip", ov[k] && "on")} onClick={() => setOv({ ...ov, [k]: !ov[k] })}>
                  {{ ma20: "MA20", ma50: "MA50", ma200: "MA200", bb: "Bollinger", volume: "Khối lượng" }[k]}
                </button>
              ))}
              <button className={cls("chip", showLevels && "on")} onClick={() => setShowLevels(!showLevels)}>Mức giá kế hoạch</button>
            </div>
          </div>
          {period === "CUSTOM" && (
            <div className="row wrap" style={{ marginBottom: 12, gap: 10 }}>
              <Field label="Từ ngày"><input className="input" type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} /></Field>
              <Field label="Đến ngày"><input className="input" type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} /></Field>
              {cd && (
                <div className="row wrap" style={{ gap: 8, alignSelf: "flex-end" }}>
                  <Badge lg tone={tone(cd.period.return)}>Sinh lời giai đoạn {pct(cd.period.return, 1, true)}</Badge>
                  <Badge lg>{cd.period.sessions} phiên</Badge>
                  <Badge lg>Cao nhất {vnd(cd.period.high)} · Thấp nhất {vnd(cd.period.low)}</Badge>
                  <Badge lg tone={recTone(cd.technical.signal_code)}>Tín hiệu cuối giai đoạn: {cd.technical.signal}</Badge>
                </div>
              )}
              {(rangeError || custom.error) && <Alert kind="err">{rangeError ?? custom.error}</Alert>}
              {!range.start && <span className="small subtle" style={{ alignSelf: "flex-end" }}>Chọn ngày bắt đầu để phân tích kỹ thuật riêng cho giai đoạn này.</span>}
            </div>
          )}
          {chart ? <PriceChart data={chart} overlays={ov} lines={lines} fit={period !== "ALL"} />
            : period === "CUSTOM" && (!range.start || rangeError || custom.error)
              ? <div className="empty" style={{ minHeight: 300, justifyContent: "center" }}>Chọn khoảng thời gian hợp lệ để xem biểu đồ.</div>
              : <Loading height={420} />}
        </Card>
      )}

      {tab === "tech" && (
        <div className="grid g-main">
          <Card title={`Tín hiệu kỹ thuật ${cd ? "(giai đoạn tùy chọn)" : ""}`} icon={<Activity size={16} />}
            actions={<><Badge lg tone={recTone(tv.signal_code)}>{tv.signal}</Badge><span className="mono bold">{num(tv.score, 0)}/100</span></>}>
            <div className="table-wrap">
              <table className="tbl">
                <thead><tr><th>Chỉ báo</th><th className="num">Giá trị</th><th>Đánh giá</th><th style={{ width: 120 }}>Tín hiệu</th></tr></thead>
                <tbody>
                  {tv.signals.map((s: any, i: number) => (
                    <tr key={i}>
                      <td className="bold">{s.name}</td>
                      <td className="num mono">{typeof s.value === "number" ? (s.unit === "pct" || (Math.abs(s.value) < 1.5 && (s.name.includes("so với") || s.name.startsWith("Độ dốc"))) ? pct(s.value, 2, true) : num(s.value, 2)) : s.value ?? ""}</td>
                      <td className="small muted">{s.note}</td>
                      <td>
                        <div className="bar" style={{ position: "relative", background: "var(--surface-3)" }}>
                          <i style={{ position: "absolute", left: s.score >= 0 ? "50%" : `${50 + s.score * 50}%`, width: `${Math.abs(s.score) * 50}%`, background: s.score >= 0 ? "var(--up)" : "var(--down)" }} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <div className="col" style={{ gap: 16 }}>
            <Card title="Hỗ trợ & kháng cự" icon={<Layers size={16} />}>
              <div className="col" style={{ gap: 8 }}>
                {tv.levels.resistances.slice().reverse().map((x: number) => <div key={"r" + x} className="row between"><Badge tone="down">Kháng cự</Badge><span className="mono bold">{vnd(x)}</span></div>)}
                <div className="row between" style={{ padding: "6px 0", borderTop: "1px dashed var(--border)", borderBottom: "1px dashed var(--border)" }}><span className="muted">Giá hiện tại</span><span className="mono bold">{vnd(tv.price)}</span></div>
                {tv.levels.supports.map((x: number) => <div key={"s" + x} className="row between"><Badge tone="up">Hỗ trợ</Badge><span className="mono bold">{vnd(x)}</span></div>)}
                <div className="row between small muted"><span>Đỉnh/đáy 52 tuần</span><span className="mono">{vnd(tv.levels.high_52w)} / {vnd(tv.levels.low_52w)}</span></div>
              </div>
            </Card>
            <Card title="Hiệu suất giá" icon={<BarChart3 size={16} />}>
              <div className="grid g3" style={{ gap: 8 }}>
                {Object.entries(tv.performance).map(([k, val]) => (
                  <div key={k} className="card tight flat center"><div className="tiny subtle">{k.replace("d", " phiên")}</div><div className={cls("mono bold", tone(val))}>{pct(val, 1, true)}</div></div>
                ))}
              </div>
            </Card>
            <Card title="Mô hình nến" icon={<CandlestickChart size={16} />}>
              {tv.patterns.length === 0 ? <div className="small subtle">Không có mô hình nến đặc biệt ở phiên gần nhất.</div> :
                tv.patterns.map((pt: any) => <div key={pt.name} className="list-item"><Badge tone={pt.bias === "bullish" ? "up" : pt.bias === "bearish" ? "down" : "ref"}>{pt.name}</Badge><span className="small muted">{pt.note}</span></div>)}
            </Card>
          </div>
        </div>
      )}

      {tab === "fund" && (
        <div className="col" style={{ gap: 16 }}>
          {(f.data_warnings ?? []).map((w: string, i: number) => <Alert key={i} kind="warn">{w}</Alert>)}
          <Card title="Chỉ tiêu tài chính theo năm" icon={<Layers size={16} />} hint="Đơn vị: tỷ đồng · ROE = NI/E, ROA = NI/TA, LEV = D/E, ROA_op = (NI + Lãi vay×(1−t))/TA, Sd = Lãi vay×(1−t)/D"
            actions={<Link className="btn sm" to={`/data?ticker=${ticker}`}><FileSpreadsheet size={14} /> Nhập/sửa BCTC</Link>}>
            <div className="table-wrap">
              <table className="tbl">
                <thead><tr><th>Năm</th><th className="num">Doanh thu</th><th className="num">LNST</th><th className="num">Tổng TS</th><th className="num">VCSH</th><th className="num">ROE</th><th className="num">ROA</th><th className="num">D/E</th><th className="num">ROA_op</th><th className="num">Sd</th><th className="num">Chênh lệch</th><th className="num">Biên LN</th><th className="num">EPS</th></tr></thead>
                <tbody>
                  {f.ratios.map((x: any) => (
                    <tr key={x.year}>
                      <td className="bold">{x.year}</td>
                      <td className="num mono">{bn(x.revenue)}</td><td className={cls("num mono", tone(x.net_income))}>{bn(x.net_income)}</td>
                      <td className="num mono">{bn(x.total_assets)}</td><td className="num mono">{bn(x.equity)}</td>
                      <td className="num mono bold">{pct(x.roe)}</td><td className="num mono">{pct(x.roa)}</td><td className="num mono">{num(x.lev, 2)}</td>
                      <td className="num mono">{pct(x.roa_op)}</td><td className="num mono">{pct(x.sd)}</td>
                      <td className={cls("num mono", tone(x.leverage_spread))}>{pct(x.leverage_spread, 1, true)}</td>
                      <td className="num mono">{pct(x.net_margin)}</td><td className="num mono">{vnd(x.eps)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <div className="grid g3">
            <Card title="Mô hình đòn bẩy MM mở rộng" icon={<Calculator size={16} />} hint={f.mm_model.equation}>
              {f.mm_model.regression ? (
                <div className="col" style={{ gap: 8 }}>
                  <div className="mono small" style={{ background: "var(--surface-2)", padding: 10, borderRadius: 10 }}>
                    ROE = {num(f.mm_model.regression.a, 4)} + {num(f.mm_model.regression.b, 3)}·ROA &nbsp; (R² = {num(f.mm_model.regression.r2, 2)})
                  </div>
                  <div className="row between small"><span className="muted">Hệ số khuếch đại b</span><b className="mono">{num(f.mm_model.regression.b, 3)}</b></div>
                  <div className="row between small"><span className="muted">Lý thuyết b* = 1 + LEV</span><b className="mono">{num(f.mm_model.b_star, 3)}</b></div>
                  <div className="row between small"><span className="muted">Trạng thái ổn định bs = E(ROE)/E(ROA)</span><b className="mono">{num(f.mm_model.bs, 3)}</b></div>
                  <div className="row between small"><span className="muted">t-stat của b</span><b className="mono">{num(f.mm_model.regression.t_b, 2)}</b></div>
                  <Alert kind={(f.mm_model.leverage_spread ?? 0) > 0 ? "ok" : "warn"}>{f.mm_model.verdict}</Alert>
                </div>
              ) : <div className="small subtle">Không đủ dữ liệu.</div>}
            </Card>
            <Card title="Phân tích DuPont" icon={<Layers size={16} />} hint={f.dupont.note}>
              <div className="col" style={{ gap: 10 }}>
                <div className="row between"><span className="muted">Biên lợi nhuận ròng</span><b className="mono">{pct(f.dupont.net_margin)}</b></div>
                <div className="row between"><span className="muted">× Vòng quay tài sản</span><b className="mono">{num(f.dupont.asset_turnover, 2)}</b></div>
                <div className="row between"><span className="muted">× Hệ số nhân vốn chủ</span><b className="mono">{num(f.dupont.equity_multiplier, 2)}</b></div>
                <div className="row between" style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}><span className="bold">= ROE</span><b className="mono" style={{ fontSize: 18, color: "var(--brand)" }}>{pct(f.dupont.roe)}</b></div>
                <div className="row between small"><span className="muted">Tăng trưởng DT / LN (CAGR)</span><b className="mono">{pct(f.quality.revenue_cagr)} / {pct(f.quality.ni_cagr)}</b></div>
              </div>
            </Card>
            <Card title={`Piotroski F-Score: ${f.piotroski.score ?? "—"}/9`} icon={<CheckCircle2 size={16} />} hint="Sức khỏe tài chính (≥ 7 là tốt)">
              <div className="col" style={{ gap: 6 }}>
                {f.piotroski.checks.map((x: any) => (
                  <div key={x.name} className="row small" style={{ gap: 8 }}>
                    {x.pass ? <CheckCircle2 size={15} color="var(--up)" /> : <XCircle size={15} color="var(--down)" />}<span className={x.pass ? "" : "muted"}>{x.name}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
          <Card title={`Điểm chất lượng cơ bản: ${num(f.quality.score, 0)}/100`} icon={<BarChart3 size={16} />}>
            <div className="grid g2" style={{ gap: 12 }}>
              {f.quality.parts.map((x: any) => (
                <div key={x.name} className="col" style={{ gap: 4 }}>
                  <div className="row between small"><span className="bold">{x.name}</span><span className="mono">{typeof x.value === "number" ? (Math.abs(x.value) < 3 && !x.name.includes("F-Score") && !x.name.includes("D/E") && !x.name.includes("OCF") && !x.name.includes("Thanh toán") ? pct(x.value) : num(x.value, 2)) : "—"}</span></div>
                  <PartBar label="" value={x.score * 100} />
                  <div className="tiny subtle">{x.note}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {tab === "val" && (
        <div className="grid g-main">
          <Card title="Giá trị nội tại theo từng mô hình" icon={<CircleDollarSign size={16} />}
            actions={<Badge lg tone={tone(v.upside)}>{v.verdict} · {pct(v.upside, 1, true)}</Badge>}>
            <div className="row wrap" style={{ gap: 24, marginBottom: 12 }}>
              <div><div className="tiny subtle">Thị giá</div><div className="mono bold" style={{ fontSize: 22 }}>{vnd(v.price)}</div></div>
              <div><div className="tiny subtle">Giá trị nội tại (bình quân gia quyền)</div><div className="mono bold" style={{ fontSize: 22, color: "var(--ref)" }}>{vnd(v.intrinsic_value)}</div></div>
              <div><div className="tiny subtle">Biên an toàn</div><div className={cls("mono bold", tone(v.upside))} style={{ fontSize: 22 }}>{pct(v.upside, 1, true)}</div></div>
            </div>
            <div style={{ height: 300 }}>
              <ResponsiveContainer>
                <BarChart data={v.models} layout="vertical" margin={{ left: 20, right: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                  <XAxis type="number" tickFormatter={(x) => vnd(x)} stroke="var(--text-3)" fontSize={11} />
                  <YAxis type="category" dataKey="model" width={170} stroke="var(--text-3)" fontSize={11} />
                  <Tooltip formatter={(x: any) => vnd(Number(x)) + "đ"} contentStyle={{ background: "var(--surface-3)", border: "1px solid var(--border-strong)", borderRadius: 10 }} />
                  <ReferenceLine x={v.price} stroke="#f43f5e" strokeDasharray="4 4" label={{ value: "Thị giá", fill: "#f43f5e", fontSize: 11, position: "top" }} />
                  <Bar dataKey="value" radius={[0, 6, 6, 0]}>
                    {v.models.map((m: any, i: number) => <Cell key={i} fill={m.value >= v.price ? "#22c55e" : "#f59e0b"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table className="tbl"><thead><tr><th>Mô hình</th><th className="num">Giá trị</th><th className="num">Trọng số</th><th>Giả định</th></tr></thead>
                <tbody>{v.models.map((m: any) => <tr key={m.model}><td className="bold">{m.model}</td><td className="num mono">{vnd(m.value)}</td><td className="num mono">{pct(m.weight, 0)}</td><td className="small muted">{m.note}</td></tr>)}</tbody>
              </table>
            </div>
          </Card>
          <div className="col" style={{ gap: 16 }}>
            <Card title="Hệ số định giá" icon={<BarChart3 size={16} />}>
              <div className="grid g2" style={{ gap: 8 }}>
                <Metric label="P/E" value={num(v.multiples.pe, 1)} /><Metric label="P/E ngành (trung vị)" value={num(v.multiples.sector_pe, 1)} />
                <Metric label="P/B" value={num(v.multiples.pb, 2)} /><Metric label="P/B ngành" value={num(v.multiples.sector_pb, 2)} />
                <Metric label="EPS (đ)" value={vnd(v.multiples.eps)} /><Metric label="BVPS (đ)" value={vnd(v.multiples.bvps)} />
                <Metric label="Cổ tức/CP" value={vnd(v.multiples.dps)} /><Metric label="Tỷ suất cổ tức" value={pct(v.multiples.dividend_yield)} />
              </div>
            </Card>
            {v.dcf?.valid && (
              <Card title="DCF - FCFF chiết khấu WACC" icon={<Calculator size={16} />}>
                <div className="col small" style={{ gap: 6 }}>
                  <div className="row between"><span className="muted">WACC</span><b className="mono">{pct(v.dcf.wacc)}</b></div>
                  <div className="row between"><span className="muted">Chi phí VCSH (CAPM)</span><b className="mono">{pct(v.dcf.cost_equity)}</b></div>
                  <div className="row between"><span className="muted">Chi phí nợ sau thuế</span><b className="mono">{pct(v.dcf.cost_debt_after_tax)}</b></div>
                  <div className="row between"><span className="muted">Tỷ trọng E / D (thị trường)</span><b className="mono">{pct(v.dcf.weights.equity, 0)} / {pct(v.dcf.weights.debt, 0)}</b></div>
                  <div className="row between"><span className="muted">Tăng trưởng giai đoạn đầu → dài hạn</span><b className="mono">{pct(v.dcf.growth)} → {pct(v.dcf.terminal_growth)}</b></div>
                  <div className="row between"><span className="muted">Giá trị DN (EV)</span><b className="mono">{bn(v.dcf.enterprise_value)} tỷ</b></div>
                  <div className="row between"><span className="muted">Tỷ trọng giá trị cuối kỳ</span><b className="mono">{pct(v.dcf.terminal_share, 0)}</b></div>
                </div>
              </Card>
            )}
            <Card title="Giả định chung" icon={<Calculator size={16} />}>
              <div className="col small" style={{ gap: 6 }}>
                <div className="row between"><span className="muted">Lãi suất phi rủi ro</span><b className="mono">{pct(v.assumptions.risk_free)}</b></div>
                <div className="row between"><span className="muted">Phần bù rủi ro thị trường</span><b className="mono">{pct(v.assumptions.mrp)}</b></div>
                <div className="row between"><span className="muted">Beta</span><b className="mono">{num(v.assumptions.beta, 2)}</b></div>
                <div className="row between"><span className="muted">Tăng trưởng bền vững g = ROE × b</span><b className="mono">{pct(v.assumptions.sustainable_growth)}</b></div>
              </div>
            </Card>
          </div>
        </div>
      )}

      {tab === "risk" && (
        <div className="col" style={{ gap: 16 }}>
          <div className="grid g4">
            <Metric label="Mức rủi ro" value={r.level} cls={r.level === "Cao" ? "down" : r.level === "Thấp" ? "up" : "ref"} />
            <Metric label="Sinh lời kép (CAGR)" value={pct(r.cagr, 1, true)} cls={tone(r.cagr)} />
            <Metric label="Độ biến động (năm)" value={pct(r.volatility)} />
            <Metric label="Sụt giảm tối đa" value={pct(r.max_drawdown)} cls="down" hint={`${r.peak_date} → ${r.trough_date}`} />
            <Metric label="Hệ số Sharpe" value={num(r.sharpe, 2)} cls={tone(r.sharpe)} />
            <Metric label="Hệ số Sortino" value={num(r.sortino, 2)} cls={tone(r.sortino)} />
            <Metric label="VaR 95% (1 ngày)" value={pct(r.var_95_daily, 2)} cls="down" />
            <Metric label="CVaR 95% (1 ngày)" value={pct(r.cvar_95_daily, 2)} cls="down" />
            <Metric label="Beta (so với VN-Index)" value={num(r.beta, 2)} />
            <Metric label="Tương quan với thị trường" value={num(r.correlation, 2)} />
            <Metric label="Lợi nhuận kỳ vọng CAPM" value={pct(r.capm_expected_return)} />
            <Metric label="Alpha Jensen" value={pct(r.jensen_alpha, 1, true)} cls={tone(r.jensen_alpha)} />
          </div>
          <Card title="Cơ cấu rủi ro" icon={<ShieldAlert size={16} />} hint="PTVĐTCK chương 2: rủi ro hệ thống (thị trường, lãi suất, sức mua) và phi hệ thống (kinh doanh, tài chính)">
            <div className="col" style={{ gap: 10 }}>
              <div className="row between small"><span>Rủi ro hệ thống (không đa dạng hóa được)</span><b className="mono">{pct(r.systematic_risk_share, 0)}</b></div>
              <div className="bar" style={{ height: 10 }}><i style={{ width: `${(r.systematic_risk_share ?? 0) * 100}%`, background: "var(--warn)" }} /></div>
              <div className="row between small"><span>Rủi ro phi hệ thống (giảm được nhờ đa dạng hóa)</span><b className="mono">{pct(r.unsystematic_risk_share, 0)}</b></div>
              <div className="bar" style={{ height: 10 }}><i style={{ width: `${(r.unsystematic_risk_share ?? 0) * 100}%`, background: "var(--info)" }} /></div>
              <div className="small muted">Phần rủi ro phi hệ thống càng lớn thì lợi ích của việc phân tán danh mục (không bỏ trứng vào một giỏ) càng cao.</div>
            </div>
          </Card>
        </div>
      )}

      {tab === "plan" && (
        <div className="grid g-main">
          <Card title="Kế hoạch giao dịch" icon={<Target size={16} />} hint={p.assumptions}>
            <div className="grid g4" style={{ gap: 10, marginBottom: 14 }}>
              <Metric label="Vùng mua" value={`${vnd(p.entry_zone[0])} – ${vnd(p.entry_zone[1])}`} />
              <Metric label="Cắt lỗ" value={`${vnd(p.stop_loss)} (${pct(p.stop_loss_pct, 1)})`} cls="down" />
              <Metric label="Mục tiêu 1" value={vnd(p.take_profit_1)} cls="up" />
              <Metric label="Mục tiêu 2" value={vnd(p.take_profit_2)} cls="up" />
              <Metric label="Lợi nhuận / rủi ro" value={`${num(p.reward_risk, 2)} : 1`} />
              <Metric label="Khối lượng đề xuất" value={`${vnd(p.suggested_quantity)} CP`} />
              <Metric label="Giá trị vị thế" value={`${vnd(p.position_value)}đ`} />
              <Metric label="ATR (biến động ngày)" value={pct(t.atr_pct, 2)} />
            </div>
            <h3 style={{ marginBottom: 8 }}>Nguyên tắc thực hiện</h3>
            <ul className="small muted" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>{p.rules.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
          </Card>
          <Card title="Đặt lệnh nhanh" icon={<CircleDollarSign size={16} />}>
            <OrderBox ticker={ticker} price={t.price} plan={p} />
          </Card>
        </div>
      )}

      <div className="row wrap small subtle" style={{ gap: 6 }}>
        Xem nhanh:
        {universe.filter((u) => u.sector === d.info.sector && u.ticker !== ticker).slice(0, 8).map((u) => (
          <Link key={u.ticker} to={`/stock/${u.ticker}`} className="chip">{u.ticker}</Link>
        ))}
      </div>
    </>
  );
}
