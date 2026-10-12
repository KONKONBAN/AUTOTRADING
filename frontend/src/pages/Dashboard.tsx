import { Link, useNavigate } from "react-router-dom";
import { Activity, ArrowRight, Bot, Check, Gauge, PiggyBank, TrendingUp, Wallet, X, Zap } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { api } from "../lib/api";
import { useStatus } from "../lib/status";
import { cls, money, num, pct, recTone, tone, vnd } from "../lib/format";
import { TimeChart } from "../components/Charts";
import { Alert, Badge, Card, Empty, ErrorBox, Kpi, Loading, ScoreBar, SourceBadge, TickerCell, useAsync, useToast } from "../components/ui";

const PIE = ["#14b8a6", "#3b82f6", "#a855f7", "#f59e0b", "#ef4444", "#22c55e", "#06b6d4", "#ec4899", "#84cc16", "#64748b"];

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
  const nav = useNavigate();
  const toast = useToast();
  const market = useAsync(() => api.get("/api/market"), []);
  const pf = useAsync(() => api.get("/api/portfolio"), []);
  const scr = useAsync(() => api.get("/api/screener"), []);
  const props = useAsync(() => api.get("/api/proposals?status=pending"), []);

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

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Tổng quan thị trường & tài sản</h1>
          <p>{new Date().toLocaleDateString("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" })} · Dữ liệu đến phiên {status?.data.last_date ?? "…"}</p>
        </div>
        <div className="row wrap">
          <SourceBadge source={status?.data.source} />
          <Link to="/agent" className="btn primary"><Bot size={16} /> Hỏi AI Agent</Link>
        </div>
      </div>

      {status?.data.needs_manual_input && (
        <Alert kind="warn" title="Chưa truy cập được nguồn dữ liệu tự động">
          {status.data.message}{" "}
          <Link to="/data" className="bold">Mở Dữ liệu & nhập liệu <ArrowRight size={12} /></Link>
        </Alert>
      )}

      <div className="grid g4">
        <Kpi label="Tổng tài sản" icon={<Wallet size={17} />} value={acc ? money(acc.equity) : "…"}
          sub={acc && <span className={tone(acc.total_return)}>{pct(acc.total_return, 2, true)} kể từ khi bắt đầu</span>} />
        <Kpi label="Lãi/lỗ chưa thực hiện" icon={<TrendingUp size={17} />} valueClass={acc ? tone(acc.unrealized_pnl) : ""}
          value={acc ? money(acc.unrealized_pnl) : "…"} sub={acc && <span className="muted">Đã thực hiện: <b className={tone(acc.realized_pnl)}>{money(acc.realized_pnl)}</b></span>} />
        <Kpi label="Tiền mặt khả dụng" icon={<PiggyBank size={17} />} value={acc ? money(acc.cash) : "…"}
          sub={acc && <span className="muted">{acc.positions.length} mã đang nắm giữ</span>} />
        <Kpi label="Tỷ trọng cổ phiếu" icon={<Gauge size={17} />} value={acc ? pct(acc.exposure, 0) : "…"}
          sub={m && <span className="muted">Mục tiêu theo thị trường: <b>{pct(m.recommended_exposure, 0)}</b></span>} />
      </div>

      <div className="grid g-main">
        <Card title={<>VN-Index</>} icon={<Activity size={16} />}
          hint={m && `Đường xu hướng log-tuyến tính lnP = a + b·t (cửa sổ 120 phiên)`}
          actions={m && (<><span className="mono bold" style={{ fontSize: 20 }}>{num(m.price, 2)}</span><Badge tone={tone(m.change_pct)}>{pct(m.change_pct, 2, true)}</Badge></>)}>
          {market.loading ? <Loading height={280} /> : market.error ? <ErrorBox error={market.error} onRetry={market.reload} /> : (
            <TimeChart height={290} series={[
              { name: "VN-Index", color: "#2dd4bf", area: true, data: m.history.map((h: any) => ({ time: h.time, value: h.close })) },
              { name: "Xu hướng", color: "#f59e0b", width: 1, data: m.history.filter((h: any) => h.trend).map((h: any) => ({ time: h.time, value: h.trend })) },
            ]} />
          )}
        </Card>
        <Card title="Trạng thái thị trường chung" icon={<Gauge size={16} />} hint="Market-timing + ngày phân phối">
          {m ? <MarketGauge m={m} /> : <Loading />}
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
                      <td className="num mono">{vnd(r.price)}</td>
                      <td className={cls("num mono", tone(r.change_pct))}>{pct(r.change_pct, 2, true)}</td>
                      <td style={{ minWidth: 130 }}><ScoreBar score={r.score} /></td>
                      <td><Badge tone={recTone(r.code)}>{r.recommendation}</Badge></td>
                      <td className={cls("num mono hide-mobile", tone(r.upside))}>{pct(r.upside, 0, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="col" style={{ gap: 16 }}>
          <Card title="Đề xuất lệnh chờ duyệt" icon={<Zap size={16} />} actions={<Link to="/autotrader" className="btn sm ghost">Auto-Trader</Link>}>
            {props.loading ? <Loading height={80} /> : (props.data ?? []).length === 0 ? (
              <Empty title="Không có đề xuất nào">Auto-Trader và AI Agent sẽ tạo đề xuất để bạn duyệt tại đây.</Empty>
            ) : (
              <div className="list">
                {props.data.slice(0, 5).map((p: any) => (
                  <div key={p.id} className="list-item">
                    <Badge tone={p.side === "BUY" ? "up" : "down"}>{p.side === "BUY" ? "MUA" : "BÁN"}</Badge>
                    <div className="grow">
                      <div className="bold">{p.ticker} · {vnd(p.quantity)} CP @ {vnd(p.price)}</div>
                      <div className="tiny subtle" title={p.reason} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.reason}</div>
                    </div>
                    <button className="btn sm icon buy" title="Duyệt" onClick={() => decide(p.id, true)}><Check size={14} /></button>
                    <button className="btn sm icon" title="Từ chối" onClick={() => decide(p.id, false)}><X size={14} /></button>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card title="Phân bổ tài sản" icon={<Wallet size={16} />} actions={<Link to="/portfolio" className="btn sm ghost">Chi tiết</Link>}>
            {!acc ? <Loading height={120} /> : (
              <div className="row" style={{ alignItems: "center" }}>
                <div style={{ width: 150, height: 150 }}>
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie data={sectorAlloc} dataKey="value" nameKey="name" innerRadius={45} outerRadius={70} paddingAngle={2} stroke="none">
                        {sectorAlloc.map((_, i) => <Cell key={i} fill={sectorAlloc[i].name === "Tiền mặt" ? "#64748b" : PIE[i % PIE.length]} />)}
                      </Pie>
                      <Tooltip formatter={(v: any) => money(Number(v))} contentStyle={{ background: "var(--surface-3)", border: "1px solid var(--border-strong)", borderRadius: 10 }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="col grow" style={{ gap: 6 }}>
                  {sectorAlloc.map((s, i) => (
                    <div key={s.name} className="row between small">
                      <span className="row" style={{ gap: 6 }}><i className="legend-dot" style={{ background: s.name === "Tiền mặt" ? "#64748b" : PIE[i % PIE.length], width: 8, height: 8, borderRadius: 3 }} />{s.name}</span>
                      <span className="mono">{pct(s.value / acc.equity, 1)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
