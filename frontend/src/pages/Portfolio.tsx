import { useState } from "react";
import { Link } from "react-router-dom";
import { History, PieChart as PieIcon, RotateCcw, Sigma, Wallet } from "lucide-react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { api } from "../lib/api";
import { useStatus } from "../lib/status";
import { cls, money, num, pct, tone, vnd } from "../lib/format";
import { TimeChart } from "../components/Charts";
import { Alert, Badge, Card, Empty, ErrorBox, Field, Kpi, Loading, Seg, TickerCell, useAsync, useToast } from "../components/ui";

function Optimizer() {
  const { universe } = useStatus();
  const toast = useToast();
  const [sel, setSel] = useState<string[]>(["FPT", "VCB", "HPG", "MWG", "GAS", "DGC"]);
  const [objective, setObjective] = useState("max_sharpe");
  const [maxW, setMaxW] = useState(0.25);
  const [capital, setCapital] = useState(300_000_000);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      setRes(await api.post("/api/portfolio/optimize", { tickers: sel, objective, max_weight: maxW, capital }));
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy(false);
    }
  };
  const toggle = (t: string) => setSel((s) => (s.includes(t) ? s.filter((x) => x !== t) : [...s, t]));
  return (
    <Card title="Tối ưu danh mục (Markowitz)" icon={<Sigma size={16} />}
      hint="Tối đa hệ số Sharpe hoặc tối thiểu phương sai, giới hạn tỷ trọng mỗi mã - 'Đừng bỏ trứng vào một giỏ'. Lợi nhuận kỳ vọng kết hợp định giá + lịch sử.">
      <div className="col" style={{ gap: 14 }}>
        <div className="row wrap" style={{ gap: 6 }}>
          {universe.map((u) => (
            <button key={u.ticker} className={cls("chip", sel.includes(u.ticker) && "on")} onClick={() => toggle(u.ticker)}>{u.ticker}</button>
          ))}
        </div>
        <div className="form-grid">
          <Field label="Mục tiêu">
            <Seg value={objective} onChange={setObjective} items={[{ value: "max_sharpe", label: "Max Sharpe" }, { value: "min_variance", label: "Min rủi ro" }]} />
          </Field>
          <Field label={`Tỷ trọng tối đa mỗi mã: ${pct(maxW, 0)}`}><input type="range" min={0.1} max={0.5} step={0.05} value={maxW} onChange={(e) => setMaxW(Number(e.target.value))} /></Field>
          <Field label="Số vốn phân bổ (đ)"><input className="input mono" type="number" step={10_000_000} value={capital} onChange={(e) => setCapital(Number(e.target.value))} /></Field>
          <div className="field" style={{ justifyContent: "flex-end" }}>
            <button className="btn primary" disabled={busy || sel.length < 2} onClick={run}>{busy ? "Đang tối ưu…" : `Tối ưu ${sel.length} mã`}</button>
          </div>
        </div>
        {res && (
          <div className="grid g-main">
            <div className="col" style={{ gap: 12 }}>
              <div className="grid g3" style={{ gap: 10 }}>
                <div className="card tight flat"><div className="tiny subtle">Lợi nhuận kỳ vọng/năm</div><div className="mono bold up" style={{ fontSize: 18 }}>{pct(res.expected_return)}</div><div className="tiny subtle">Chia đều: {pct(res.equal_weight.expected_return)}</div></div>
                <div className="card tight flat"><div className="tiny subtle">Độ biến động/năm</div><div className="mono bold" style={{ fontSize: 18 }}>{pct(res.volatility)}</div><div className="tiny subtle">Chia đều: {pct(res.equal_weight.volatility)}</div></div>
                <div className="card tight flat"><div className="tiny subtle">Sharpe</div><div className="mono bold" style={{ fontSize: 18, color: "var(--brand)" }}>{num(res.sharpe, 2)}</div><div className="tiny subtle">Chia đều: {num(res.equal_weight.sharpe, 2)}</div></div>
              </div>
              <div className="table-wrap">
                <table className="tbl">
                  <thead><tr><th>Mã</th><th>Tỷ trọng</th><th className="num">LN kỳ vọng</th><th className="num">Biến động</th><th className="num">Số CP</th><th className="num">Giá trị</th></tr></thead>
                  <tbody>
                    {(res.allocation ?? res.weights).filter((w: any) => w.weight > 0.001).map((w: any) => (
                      <tr key={w.ticker}>
                        <td><TickerCell ticker={w.ticker} /></td>
                        <td style={{ minWidth: 140 }}><div className="scorebar"><div className="bar"><i style={{ width: `${w.weight * 100}%` }} /></div><span className="mono small bold">{pct(w.weight, 1)}</span></div></td>
                        <td className={cls("num mono", tone(w.expected_return))}>{pct(w.expected_return)}</td>
                        <td className="num mono">{pct(w.volatility)}</td>
                        <td className="num mono">{vnd(w.quantity)}</td>
                        <td className="num mono">{money(w.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div>
              <div className="small bold" style={{ marginBottom: 6 }}>Đường biên hiệu quả</div>
              <div style={{ height: 280 }}>
                <ResponsiveContainer>
                  <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis type="number" dataKey="volatility" name="Rủi ro" tickFormatter={(x) => pct(x, 0)} stroke="var(--text-3)" fontSize={11} />
                    <YAxis type="number" dataKey="return" name="Lợi nhuận" tickFormatter={(x) => pct(x, 0)} stroke="var(--text-3)" fontSize={11} />
                    <ZAxis range={[40, 40]} />
                    <Tooltip formatter={(x: any) => pct(Number(x))} contentStyle={{ background: "var(--surface-3)", border: "1px solid var(--border-strong)", borderRadius: 10 }} />
                    <Scatter name="Biên hiệu quả" data={res.frontier} fill="#0ea5e9" line={{ stroke: "#0ea5e9" }} />
                    <Scatter name="Từng mã" data={res.weights.map((w: any) => ({ volatility: w.volatility, return: w.expected_return }))} fill="#94a3b8" />
                    <Scatter name="Danh mục tối ưu" data={[{ volatility: res.volatility, return: res.expected_return }]} fill="#22c55e" shape="star" />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
              <div className="tiny subtle">Ngôi sao xanh: danh mục tối ưu · Chấm xám: từng cổ phiếu · Đường xanh: biên hiệu quả.</div>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

export default function Portfolio() {
  const toast = useToast();
  const pf = useAsync(() => api.get("/api/portfolio"), []);
  const [cash, setCash] = useState(500_000_000);
  const reset = async () => {
    if (!confirm(`Đặt lại tài khoản giao dịch giấy với ${vnd(cash)}đ? Toàn bộ vị thế và lịch sử lệnh sẽ bị xóa.`)) return;
    try {
      await api.post("/api/portfolio/reset", { initial_cash: cash });
      toast("ok", "Đã đặt lại tài khoản.");
      pf.reload();
    } catch (e: any) {
      toast("err", e.message);
    }
  };
  const acc = pf.data;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Danh mục & tối ưu hóa</h1>
          <p>Tài khoản giao dịch giấy mô phỏng sát quy định thị trường Việt Nam (lô 100, phí 0,15%, thuế bán 0,1%, T+2).</p>
        </div>
        <div className="row wrap">
          <input className="input mono" style={{ width: 170 }} type="number" step={10_000_000} value={cash} onChange={(e) => setCash(Number(e.target.value))} />
          <button className="btn" onClick={reset}><RotateCcw size={15} /> Đặt lại tài khoản</button>
        </div>
      </div>
      {pf.loading ? <Loading /> : pf.error ? <ErrorBox error={pf.error} onRetry={pf.reload} /> : (
        <>
          <div className="grid g4">
            <Kpi label="Tổng tài sản (NAV)" icon={<Wallet size={17} />} value={money(acc.equity)} sub={<span className={tone(acc.total_return)}>{pct(acc.total_return, 2, true)} · vốn đầu {money(acc.initial_cash)}</span>} />
            <Kpi label="Giá trị cổ phiếu" value={money(acc.market_value)} sub={<span className="muted">Tỷ trọng {pct(acc.exposure, 0)}</span>} />
            <Kpi label="Lãi/lỗ" value={money(acc.unrealized_pnl + acc.realized_pnl)} valueClass={tone(acc.unrealized_pnl + acc.realized_pnl)}
              sub={<span className="muted">Chưa TH {money(acc.unrealized_pnl)} · Đã TH {money(acc.realized_pnl)}</span>} />
            <Kpi label="Sụt giảm từ đỉnh" value={pct(acc.drawdown, 1)} valueClass={acc.drawdown < -0.1 ? "down" : ""} sub={<span className="muted">Kill-switch Auto-Trader: −15%</span>} />
          </div>
          {acc.equity_history.length > 1 && (
            <Card title="Diễn biến tài sản" icon={<History size={16} />}>
              <TimeChart height={240} series={[{ name: "NAV", color: "#2dd4bf", area: true, data: acc.equity_history.map((h: any) => ({ time: h.date, value: h.equity })) }]} />
            </Card>
          )}
          <Card title="Vị thế đang nắm giữ" icon={<PieIcon size={16} />} actions={<Link to="/autotrader" className="btn sm">Auto-Trader</Link>}>
            {acc.positions.length === 0 ? (
              <Empty title="Chưa có vị thế nào">Đặt lệnh từ trang phân tích cổ phiếu, duyệt đề xuất của Auto-Trader hoặc nhờ AI Agent lập kế hoạch.</Empty>
            ) : (
              <div className="table-wrap">
                <table className="tbl">
                  <thead><tr><th>Mã</th><th className="num">KL</th><th className="num">Khả dụng (T+2)</th><th className="num">Giá vốn</th><th className="num">Thị giá</th><th className="num">Giá trị</th><th className="num">Lãi/lỗ</th><th className="num">Tỷ trọng</th><th className="num">Cắt lỗ</th></tr></thead>
                  <tbody>
                    {acc.positions.map((p: any) => (
                      <tr key={p.ticker}>
                        <td><Link to={`/stock/${p.ticker}`}><TickerCell ticker={p.ticker} name={p.sector} /></Link></td>
                        <td className="num mono">{vnd(p.quantity)}</td>
                        <td className="num mono">{vnd(p.sellable)}</td>
                        <td className="num mono">{vnd(p.avg_price)}</td>
                        <td className="num mono bold">{vnd(p.market_price)}</td>
                        <td className="num mono">{money(p.market_value)}</td>
                        <td className={cls("num mono", tone(p.unrealized_pnl))}>{money(p.unrealized_pnl)} <span className="small">({pct(p.unrealized_pct, 1, true)})</span></td>
                        <td className="num mono">{pct(p.weight, 1)}</td>
                        <td className="num mono down">{vnd(p.stop_loss)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <Optimizer />
          <Card title="Lịch sử lệnh" icon={<History size={16} />}>
            {acc.orders.length === 0 ? <Empty title="Chưa có lệnh nào" /> : (
              <div className="table-wrap" style={{ maxHeight: 420 }}>
                <table className="tbl">
                  <thead><tr><th>Thời gian</th><th>Lệnh</th><th>Mã</th><th className="num">KL</th><th className="num">Giá</th><th className="num">Phí + thuế</th><th>Nguồn</th><th>Lý do</th></tr></thead>
                  <tbody>
                    {acc.orders.map((o: any) => (
                      <tr key={o.id}>
                        <td className="small nowrap">{new Date(o.created_at * 1000).toLocaleString("vi-VN")}</td>
                        <td><Badge tone={o.side === "BUY" ? "up" : "down"}>{o.side === "BUY" ? "MUA" : "BÁN"}</Badge></td>
                        <td className="bold">{o.ticker}</td>
                        <td className="num mono">{vnd(o.quantity)}</td>
                        <td className="num mono">{vnd(o.price)}</td>
                        <td className="num mono">{vnd(o.fee + o.tax)}</td>
                        <td><Badge tone={o.source === "autotrader" ? "brand" : o.source === "agent" ? "info" : ""}>{o.source}</Badge></td>
                        <td className="small muted">{o.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <Alert kind="info" title="Giao dịch tiền thật">
            Ứng dụng mặc định dùng tài khoản giấy. Để kết nối công ty chứng khoán (SSI FastConnect, DNSE, VPS…), cần cài đặt adapter broker trong
            backend và bật ALLOW_LIVE_TRADING - xem README.
          </Alert>
        </>
      )}
    </>
  );
}
