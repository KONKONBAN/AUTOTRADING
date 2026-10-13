import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity, ArrowLeftRight, ArrowRight, Bot, Check, Database, Eye, EyeOff, Filter, Gauge, LineChart, PiggyBank, TrendingUp, Wallet, X, Zap,
} from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { api } from "../lib/api";
import { useStatus } from "../lib/status";
import { cls, money, num, pct, ptone, recTone, tone, vnd } from "../lib/format";
import { TimeChart } from "../components/Charts";
import { useAuth } from "../components/AuthGate";
import { useQuickTrade } from "../components/QuickTrade";
import { Alert, Badge, Card, Empty, ErrorBox, Loading, ScoreBar, SourceBadge, TickerCell, useAsync, useToast } from "../components/ui";

const PIE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)", "var(--chart-7)", "var(--chart-8)"];
const CASH = "var(--chart-muted)";

function greeting(): string {
  const h = new Date().getHours();
  return h < 11 ? "Chào buổi sáng" : h < 14 ? "Chào buổi trưa" : h < 18 ? "Chào buổi chiều" : "Chào buổi tối";
}

/** Tên gọi: chữ cuối trong họ tên tiếng Việt (Nguyễn Văn An → An). */
const givenName = (full: string) => full.trim().split(/\s+/).pop() || full;

function Spark({ data, tone: t }: { data: number[]; tone: string }) {
  if (data.length < 2) return null;
  const min = Math.min(...data), max = Math.max(...data), w = 120, h = 32;
  const y = (v: number) => (max === min ? h / 2 : h - 2 - ((v - min) / (max - min)) * (h - 4));
  const d = data.map((v, i) => `${i ? "L" : "M"}${((i / (data.length - 1)) * w).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const color = t === "up" ? "var(--up)" : t === "down" ? "var(--down)" : "var(--ref)";
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" width="100%" height={h} aria-hidden>
      <path d={d} fill="none" stroke={color} strokeWidth={1.6} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}

function IndexStrip() {
  const ix = useAsync(() => api.get<any[]>("/api/market/indices"), []);
  if (ix.loading) return <div className="index-strip">{[0, 1, 2, 3].map((i) => <div key={i} className="index-card skeleton" style={{ height: 96 }} />)}</div>;
  if (ix.error || !ix.data) return null;
  return (
    <div className="index-strip">
      {ix.data.map((x) => {
        const t = tone(x.change_pct);
        return (
          <div key={x.symbol} className="index-card" title={x.available ? `Phiên ${x.date} · nguồn ${x.source}` : "Chưa tải được dữ liệu chỉ số"}>
            <div className="row between"><span className="ic-name">{x.name}</span>{x.available && <Badge tone={t}>{pct(x.change_pct, 2, true)}</Badge>}</div>
            <div className={cls("ic-value", x.available && t)}>{x.available ? num(x.price, 2) : "—"}</div>
            {x.available ? (
              <>
                <div className={cls("tiny num", t)}>{x.change > 0 ? "+" : ""}{num(x.change, 2)} điểm</div>
                <Spark data={x.spark} tone={t} />
              </>
            ) : <div className="tiny subtle">Chưa có dữ liệu</div>}
          </div>
        );
      })}
    </div>
  );
}

const QUICK = [
  { to: "/stock", label: "Phân tích cổ phiếu", icon: LineChart },
  { to: "/screener", label: "Bộ lọc & xếp hạng", icon: Filter },
  { to: "#trade", label: "Đặt lệnh nhanh", icon: ArrowLeftRight },
  { to: "/portfolio", label: "Danh mục", icon: Wallet },
  { to: "/autotrader", label: "Giao dịch tự động", icon: Zap },
  { to: "/agent", label: "Hỏi trợ lý AI", icon: Bot },
  { to: "/finance", label: "Tài chính cá nhân", icon: PiggyBank },
  { to: "/data", label: "Nhập dữ liệu", icon: Database },
];

export function MarketGauge({ m }: { m: any }) {
  const pos = Math.max(0, Math.min(100, ((m.score + 6) / 12) * 100));
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="row between">
        <Badge lg tone={m.recommended_exposure >= 0.6 ? "up" : m.recommended_exposure >= 0.4 ? "ref" : "down"}>{m.regime}</Badge>
      </div>
      <div>
        <div className="gauge-track"><div className="gauge-thumb" style={{ left: `${pos}%` }} /></div>
        <div className="row between tiny subtle" style={{ marginTop: 6 }}><span>Giảm mạnh</span><span>Trung tính</span><span>Tăng mạnh</span></div>
      </div>
      <div className="row between">
        <span className="muted">Tỷ trọng cổ phiếu khuyến nghị</span>
        <span className="kpi-value" style={{ fontSize: 22 }}>{pct(m.recommended_exposure, 0)}</span>
      </div>
      <div className="bar" style={{ height: 8 }}><i style={{ width: `${m.recommended_exposure * 100}%` }} /></div>
      <div className="grid g2" style={{ gap: 10 }}>
        <div><div className="tiny subtle">Xu hướng (năm hóa)</div><div className={cls("mono bold", tone(m.trend_annualized))}>{pct(m.trend_annualized, 1, true)}</div></div>
        <div><div className="tiny subtle">Độ lệch xu hướng (z)</div><div className="mono bold">{num(m.deviation_z, 2)}</div></div>
        <div><div className="tiny subtle">Ngày phân phối (25 phiên)</div><div className={cls("mono bold", m.distribution_days >= 5 && "down")}>{m.distribution_days}</div></div>
        <div><div className="tiny subtle">RSI (14)</div><div className="mono bold">{num(m.rsi, 1)}</div></div>
      </div>
      {m.notes?.length > 0 && <ul className="small muted" style={{ margin: 0, paddingLeft: 18 }}>{m.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>}
      <div className="tiny subtle">Mô hình: {m.model}</div>
    </div>
  );
}

export default function Dashboard() {
  const { status } = useStatus();
  const { user } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const quickTrade = useQuickTrade();
  const [hide, setHide] = useState(() => {
    try { return localStorage.getItem("hide-balance") === "1"; } catch { return false; }
  });
  const toggleHide = () => setHide((h) => {
    try { localStorage.setItem("hide-balance", h ? "0" : "1"); } catch { /* bỏ qua */ }
    return !h;
  });
  const market = useAsync(() => api.get("/api/market"), []);
  const pf = useAsync(() => api.get("/api/portfolio"), []);
  const scr = useAsync(() => api.get("/api/screener"), []);
  const props = useAsync(() => api.get("/api/proposals?status=pending"), []);
  useEffect(() => {
    const reload = () => pf.reload();
    window.addEventListener("orders-changed", reload);
    return () => window.removeEventListener("orders-changed", reload);
  }, [pf.reload]);

  const decide = async (id: number, ok: boolean) => {
    try {
      const r = await api.post(`/api/proposals/${id}/${ok ? "approve" : "reject"}`);
      toast(r.status === "failed" ? "err" : "ok", r.status === "executed" ? "Đã khớp lệnh trên tài khoản giấy." : r.status === "rejected" ? "Đã từ chối đề xuất." : r.error);
      props.reload();
      pf.reload();
    } catch (e: any) {
      toast("err", e.message);
    }
  };

  const m = market.data;
  const acc = pf.data;
  const sectorAlloc = acc
    ? Object.entries(
        (acc.positions as any[]).reduce((s: Record<string, number>, p) => ({ ...s, [p.sector]: (s[p.sector] ?? 0) + p.market_value }), {})
      ).map(([name, value]) => ({ name, value: value as number }))
    : [];
  if (acc && acc.cash > 0) sectorAlloc.push({ name: "Tiền mặt", value: acc.cash });
  const mask = (s: string) => (hide ? "••••••" : s);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{greeting()}, {givenName(user.display_name)}</h1>
          <p>{new Date().toLocaleDateString("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" })} · Dữ liệu đến phiên {status?.data.last_date ?? "…"}</p>
        </div>
        <div className="row wrap">
          <SourceBadge source={status?.data.source} />
        </div>
      </div>

      {status?.data.needs_manual_input && (
        <Alert kind="warn" title="Chưa truy cập được nguồn dữ liệu tự động">
          {status.data.message}{" "}
          <Link to="/data" className="bold">Mở Dữ liệu & nhập liệu <ArrowRight size={12} /></Link>
        </Alert>
      )}

      <div className="grid g-main">
        <section className="hero-card">
          <div className="hero-label">
            <Wallet size={16} /> Tổng tài sản (tài khoản giao dịch giấy)
            <button className="eye-btn" onClick={toggleHide} title={hide ? "Hiện số dư" : "Ẩn số dư"} aria-label={hide ? "Hiện số dư" : "Ẩn số dư"}>
              {hide ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
          <div className="hero-value">{acc ? mask(vnd(acc.equity)) : "…"}<small>VND</small></div>
          {acc && (
            <div className={cls("small num", ptone(acc.total_return) === "down" ? "neg" : "pos")} style={{ marginTop: 4 }}>
              {hide ? "••" : pct(acc.total_return, 2, true)} kể từ khi bắt đầu
            </div>
          )}
          <div className="hero-stats">
            <div className="hero-stat"><span>Tiền mặt khả dụng</span><b>{acc ? mask(money(acc.cash)) : "…"}</b></div>
            <div className="hero-stat">
              <span>Lãi/lỗ chưa thực hiện</span>
              <b className={acc && !hide ? (acc.unrealized_pnl >= 0 ? "pos" : "neg") : ""}>{acc ? mask(money(acc.unrealized_pnl)) : "…"}</b>
            </div>
            <div className="hero-stat"><span>Tỷ trọng cổ phiếu</span><b>{acc ? pct(acc.exposure, 0) : "…"}</b></div>
          </div>
          <div className="hero-actions">
            <button className="btn" onClick={() => quickTrade()}><ArrowLeftRight size={15} /> Đặt lệnh</button>
            <Link to="/portfolio" className="btn"><Wallet size={15} /> Danh mục</Link>
            <Link to="/agent" className="btn hide-mobile"><Bot size={15} /> Hỏi trợ lý AI</Link>
          </div>
        </section>

        <Card title="Đề xuất lệnh chờ duyệt" icon={<Zap size={16} />} actions={<Link to="/autotrader" className="btn sm ghost">Auto-Trader</Link>}>
          {props.loading ? <Loading height={80} /> : (props.data ?? []).length === 0 ? (
            <Empty title="Không có đề xuất nào">Auto-Trader và trợ lý AI sẽ tạo đề xuất để bạn duyệt tại đây.</Empty>
          ) : (
            <div className="list">
              {props.data.slice(0, 4).map((p: any) => (
                <div key={p.id} className="list-item">
                  <Badge tone={p.side === "BUY" ? "up" : "down"}>{p.side === "BUY" ? "MUA" : "BÁN"}</Badge>
                  <div className="grow">
                    <div className="bold">{p.ticker} · <span className="num">{vnd(p.quantity)}</span> CP @ <span className="num">{vnd(p.price)}</span></div>
                    <div className="tiny subtle ellipsis" title={p.reason}>{p.reason}</div>
                  </div>
                  <button className="btn sm icon buy" title="Duyệt" onClick={() => decide(p.id, true)}><Check size={14} /></button>
                  <button className="btn sm icon" title="Từ chối" onClick={() => decide(p.id, false)}><X size={14} /></button>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <section className="card tight">
        <div className="quick-grid">
          {QUICK.map((q) => q.to === "#trade" ? (
            <button key={q.to} className="quick-item" onClick={() => quickTrade()}>
              <span className="qi-icon"><q.icon size={21} /></span>{q.label}
            </button>
          ) : (
            <Link key={q.to} to={q.to} className="quick-item">
              <span className="qi-icon"><q.icon size={21} /></span>{q.label}
            </Link>
          ))}
        </div>
      </section>

      <IndexStrip />

      <div className="grid g-main">
        <Card title="VN-Index" icon={<Activity size={16} />}
          hint={m && `Đường xu hướng log-tuyến tính lnP = a + b·t (cửa sổ 120 phiên)`}
          actions={m && (<><span className="num bold" style={{ fontSize: 20 }}>{num(m.price, 2)}</span><Badge tone={tone(m.change_pct)}>{pct(m.change_pct, 2, true)}</Badge></>)}>
          {market.loading ? <Loading height={280} /> : market.error ? <ErrorBox error={market.error} onRetry={market.reload} /> : (
            <TimeChart height={290} series={[
              { name: "VN-Index", color: "var(--chart-1)", area: true, data: m.history.map((h: any) => ({ time: h.time, value: h.close })) },
              { name: "Xu hướng", color: "var(--chart-3)", width: 1, data: m.history.filter((h: any) => h.trend).map((h: any) => ({ time: h.time, value: h.trend })) },
            ]} />
          )}
        </Card>
        <Card title="Trạng thái thị trường chung" icon={<Gauge size={16} />} hint="Market-timing + ngày phân phối">
          {m ? <MarketGauge m={m} /> : market.error ? <ErrorBox error={market.error} /> : <Loading />}
        </Card>
      </div>

      <div className="grid g-main">
        <Card title="Cổ phiếu nổi bật" icon={<TrendingUp size={16} />} hint="Xếp hạng theo điểm tổng hợp: kỹ thuật 35% · chất lượng 30% · định giá 20% · rủi ro 15%"
          actions={<Link to="/screener" className="btn sm">Xem tất cả <ArrowRight size={14} /></Link>}>
          {scr.loading ? <Loading text="Đang chấm điểm toàn bộ cổ phiếu…" /> : scr.error ? <ErrorBox error={scr.error} /> : (
            <div className="table-wrap">
              <table className="tbl">
                <thead><tr><th>Mã</th><th className="num">Giá</th><th className="num">% ngày</th><th>Điểm</th><th>Khuyến nghị</th><th className="num hide-mobile">Upside</th></tr></thead>
                <tbody>
                  {scr.data.results.slice(0, 8).map((r: any) => (
                    <tr key={r.ticker} className="clickable" onClick={() => nav(`/stock/${r.ticker}`)}>
                      <td><TickerCell ticker={r.ticker} name={r.name} /></td>
                      <td className="num">{vnd(r.price)}</td>
                      <td className={cls("num", tone(r.change_pct))}>{pct(r.change_pct, 2, true)}</td>
                      <td style={{ minWidth: 130 }}><ScoreBar score={r.score} /></td>
                      <td><Badge tone={recTone(r.code)}>{r.recommendation}</Badge></td>
                      <td className={cls("num hide-mobile", tone(r.upside))}>{pct(r.upside, 0, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Phân bổ tài sản" icon={<Wallet size={16} />} actions={<Link to="/portfolio" className="btn sm ghost">Chi tiết</Link>}>
          {!acc ? <Loading height={120} /> : (
            <div className="row" style={{ alignItems: "center" }}>
              <div style={{ width: 150, height: 150, flex: "none" }}>
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={sectorAlloc} dataKey="value" nameKey="name" innerRadius={45} outerRadius={70} paddingAngle={2} stroke="none">
                      {sectorAlloc.map((x, i) => <Cell key={i} fill={x.name === "Tiền mặt" ? CASH : PIE[i % PIE.length]} />)}
                    </Pie>
                    <Tooltip formatter={(v: any) => (hide ? "••••" : money(Number(v)))}
                      contentStyle={{ background: "var(--surface)", border: "1px solid var(--border-strong)", borderRadius: 10, boxShadow: "var(--shadow-2)", color: "var(--text)" }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="col grow" style={{ gap: 6 }}>
                {sectorAlloc.map((s, i) => (
                  <div key={s.name} className="row between small">
                    <span className="row" style={{ gap: 6, minWidth: 0 }}><i className="legend-dot" style={{ background: s.name === "Tiền mặt" ? CASH : PIE[i % PIE.length], width: 8, height: 8, borderRadius: 3, flex: "none" }} /><span className="ellipsis">{s.name}</span></span>
                    <span className="num">{pct(s.value / acc.equity, 1)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
