import { useEffect, useState } from "react";
import { Check, FlaskConical, Pause, Play, ShieldCheck, Sparkles, X, Zap } from "lucide-react";
import { api } from "../lib/api";
import { cls, money, num, pct, tone, vnd } from "../lib/format";
import { TimeChart } from "../components/Charts";
import { Alert, Badge, Card, Empty, Field, Loading, Switch, useAsync, useToast } from "../components/ui";

const MODES = [
  { value: "off", title: "Tắt", icon: Pause, desc: "Không chạy tự động. Bạn vẫn có thể xem kế hoạch." },
  { value: "suggest", title: "Đề xuất (khuyên dùng)", icon: ShieldCheck, desc: "Hệ thống tạo đề xuất lệnh, bạn duyệt từng lệnh trước khi khớp." },
  { value: "auto_paper", title: "Tự động - tài khoản giấy", icon: Zap, desc: "Tự động khớp lệnh trên tài khoản giấy để kiểm chứng chiến lược." },
];

function ActionTable({ actions }: { actions: any[] }) {
  if (!actions.length) return <Empty title="Không có hành động nào trong chu kỳ này" />;
  return (
    <div className="table-wrap">
      <table className="tbl">
        <thead><tr><th>Lệnh</th><th>Mã</th><th className="num">KL</th><th className="num">Giá</th><th className="num">Cắt lỗ</th><th>Lý do</th><th>Kết quả</th></tr></thead>
        <tbody>
          {actions.map((a, i) => (
            <tr key={i}>
              <td><Badge tone={a.side === "BUY" ? "up" : "down"}>{a.side === "BUY" ? "MUA" : "BÁN"}</Badge></td>
              <td className="bold">{a.ticker}</td>
              <td className="num mono">{vnd(a.quantity)}</td>
              <td className="num mono">{vnd(a.price)}</td>
              <td className="num mono down">{vnd(a.stop_loss)}</td>
              <td className="small muted">{a.reason}</td>
              <td>{a.error ? <Badge tone="down">{a.error}</Badge> : a.result ? <Badge tone="up">Đã khớp</Badge> : a.proposal_id ? <Badge tone="info">Chờ duyệt #{a.proposal_id}</Badge> : <Badge>Kế hoạch</Badge>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Backtest() {
  const toast = useToast();
  const [params, setParams] = useState({ min_score: 60, max_positions: 8, max_weight: 0.2, risk_per_trade: 0.015, trailing_stop_pct: 0.1, max_stop_pct: 0.07, use_market_filter: true, initial_cash: 500_000_000 });
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      setRes(await api.post("/api/backtest", params));
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy(false);
    }
  };
  const set = (k: string, v: any) => setParams({ ...params, [k]: v });
  return (
    <Card title="Kiểm định chiến lược (Backtest)" icon={<FlaskConical size={16} />} hint="Chạy lại cùng bộ quy tắc trên dữ liệu lịch sử nhóm VN30, so sánh với VN-Index">
      <div className="form-grid" style={{ marginBottom: 14 }}>
        <Field label={`Điểm kỹ thuật tối thiểu: ${params.min_score}`}><input type="range" min={50} max={80} step={1} value={params.min_score} onChange={(e) => set("min_score", Number(e.target.value))} /></Field>
        <Field label={`Số mã tối đa: ${params.max_positions}`}><input type="range" min={3} max={15} value={params.max_positions} onChange={(e) => set("max_positions", Number(e.target.value))} /></Field>
        <Field label={`Trailing stop: ${pct(params.trailing_stop_pct, 0)}`}><input type="range" min={0.05} max={0.25} step={0.01} value={params.trailing_stop_pct} onChange={(e) => set("trailing_stop_pct", Number(e.target.value))} /></Field>
        <Field label={`Cắt lỗ tối đa: ${pct(params.max_stop_pct, 0)}`}><input type="range" min={0.03} max={0.15} step={0.01} value={params.max_stop_pct} onChange={(e) => set("max_stop_pct", Number(e.target.value))} /></Field>
        <Field label="Lọc theo thị trường chung"><div className="row"><Switch on={params.use_market_filter} onChange={(v) => set("use_market_filter", v)} /><span className="small muted">{params.use_market_filter ? "Bật" : "Tắt"}</span></div></Field>
        <div className="field" style={{ justifyContent: "flex-end" }}><button className="btn primary" onClick={run} disabled={busy}>{busy ? "Đang chạy…" : <><Play size={15} /> Chạy backtest</>}</button></div>
      </div>
      {busy && <Loading text="Đang mô phỏng giao dịch từng phiên…" />}
      {res && !busy && (
        <div className="col" style={{ gap: 14 }}>
          <div className="grid g4" style={{ gap: 10 }}>
            {[
              ["Tổng lợi nhuận", pct(res.metrics.total_return, 1, true), tone(res.metrics.total_return), `VN-Index: ${pct(res.benchmark.total_return, 1, true)}`],
              ["CAGR", pct(res.metrics.cagr, 1, true), tone(res.metrics.cagr), `VN-Index: ${pct(res.benchmark.cagr, 1, true)}`],
              ["Sụt giảm tối đa", pct(res.metrics.max_drawdown, 1), "down", `VN-Index: ${pct(res.benchmark.max_drawdown, 1)}`],
              ["Sharpe", num(res.metrics.sharpe, 2), tone(res.metrics.sharpe), `VN-Index: ${num(res.benchmark.sharpe, 2)}`],
              ["Số giao dịch", String(res.metrics.n_trades), "", `Nắm giữ TB ${num(res.metrics.avg_holding_days, 0)} phiên`],
              ["Tỷ lệ thắng", pct(res.metrics.win_rate, 0), "", `Profit factor ${num(res.metrics.profit_factor, 2)}`],
              ["Lãi TB / lệnh thắng", pct(res.metrics.avg_win, 1, true), "up", ""],
              ["Lỗ TB / lệnh thua", pct(res.metrics.avg_loss, 1, true), "down", ""],
            ].map(([l, v, c, s]) => (
              <div key={l} className="card tight flat"><div className="tiny subtle">{l}</div><div className={cls("mono bold", c)} style={{ fontSize: 18 }}>{v}</div><div className="tiny subtle">{s}</div></div>
            ))}
          </div>
          <TimeChart height={280} series={[
            { name: "Chiến lược", color: "var(--chart-1)", area: true, data: res.equity_curve.map((c: any) => ({ time: c.date, value: c.equity })) },
            { name: "VN-Index", color: "var(--chart-muted)", width: 1, data: res.equity_curve.map((c: any) => ({ time: c.date, value: c.benchmark_equity })) },
          ]} />
          <div className="row small subtle" style={{ gap: 14 }}><span><i className="legend-dot" style={{ background: "var(--chart-1)" }} />Chiến lược</span><span><i className="legend-dot" style={{ background: "var(--chart-muted)" }} />Mua & nắm giữ VN-Index</span><span>Nguồn dữ liệu: {res.data_source}</span></div>
          {res.skipped_demo?.length > 0 && <Alert kind="warn">Bỏ qua {res.skipped_demo.length} mã chưa có giá thật (nguồn dữ liệu lỗi, đang là DEMO): {res.skipped_demo.join(", ")}.</Alert>}
          <Alert kind="info">{res.disclaimer}</Alert>
          <div className="table-wrap" style={{ maxHeight: 320 }}>
            <table className="tbl">
              <thead><tr><th>Mã</th><th>Mua</th><th>Bán</th><th className="num">Giá mua</th><th className="num">Giá bán</th><th className="num">Lãi/lỗ</th><th>Lý do bán</th></tr></thead>
              <tbody>{res.trades.slice().reverse().map((t: any, i: number) => (
                <tr key={i}><td className="bold">{t.ticker}</td><td className="small">{t.entry_date}</td><td className="small">{t.exit_date}</td><td className="num mono">{vnd(t.entry)}</td><td className="num mono">{vnd(t.exit)}</td><td className={cls("num mono", tone(t.return))}>{pct(t.return, 1, true)}</td><td className="small">{t.reason}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}

export default function AutoTrader() {
  const toast = useToast();
  const cfgQ = useAsync(() => api.get("/api/autotrader/config"), []);
  const props = useAsync(() => api.get("/api/proposals?status=pending"), []);
  const [cfg, setCfg] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState("");
  useEffect(() => { if (cfgQ.data) setCfg(cfgQ.data); }, [cfgQ.data]);

  const save = async (next = cfg) => {
    try {
      setCfg(await api.put("/api/autotrader/config", next));
      toast("ok", "Đã lưu cấu hình Auto-Trader.");
    } catch (e: any) {
      toast("err", e.message);
    }
  };
  const act = async (kind: "plan" | "run") => {
    setBusy(kind);
    try {
      const r = kind === "plan" ? await api.post("/api/autotrader/plan") : await api.post("/api/autotrader/run", {});
      setResult(r);
      props.reload();
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy("");
    }
  };
  const decide = async (id: number, ok: boolean) => {
    try {
      const r = await api.post(`/api/proposals/${id}/${ok ? "approve" : "reject"}`);
      toast(r.status === "failed" ? "err" : "ok", r.status === "executed" ? "Đã khớp lệnh." : r.status === "rejected" ? "Đã từ chối." : r.error);
      props.reload();
    } catch (e: any) {
      toast("err", e.message);
    }
  };
  if (!cfg) return <Loading />;
  const set = (k: string, v: any) => setCfg({ ...cfg, [k]: v });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Giao dịch tự động</h1>
          <p>Thực thi kỷ luật quy trình đầu tư 4 bước: chọn cổ phiếu → thời điểm mua → thời điểm bán → quản trị rủi ro.</p>
        </div>
        <div className="row wrap">
          <button className="btn" onClick={() => act("plan")} disabled={!!busy}><Sparkles size={15} /> {busy === "plan" ? "Đang lập…" : "Xem kế hoạch"}</button>
          <button className="btn primary" onClick={() => act("run")} disabled={!!busy || cfg.mode === "off"}><Play size={15} /> {busy === "run" ? "Đang chạy…" : "Chạy chu kỳ ngay"}</button>
        </div>
      </div>

      <div className="grid g3">
        {MODES.map((m) => (
          <button key={m.value} className="card" style={{ textAlign: "left", cursor: "pointer", outline: cfg.mode === m.value ? "2px solid var(--brand)" : "none", background: cfg.mode === m.value ? "var(--brand-soft)" : undefined }}
            onClick={() => save({ ...cfg, mode: m.value })}>
            <div className="row" style={{ gap: 10, marginBottom: 6 }}>
              <span className="kpi-icon"><m.icon size={17} /></span><h3>{m.title}</h3>
              {cfg.mode === m.value && <Badge tone="brand">Đang dùng</Badge>}
            </div>
            <div className="small muted">{m.desc}</div>
          </button>
        ))}
      </div>

      <div className="grid g-main">
        <Card title="Tham số chiến lược & quản trị rủi ro" icon={<ShieldCheck size={16} />} actions={<button className="btn sm primary" onClick={() => save()}>Lưu cấu hình</button>}>
          <div className="form-grid">
            <Field label="Phạm vi cổ phiếu" help="ALL, VN30 hoặc danh sách mã: FPT,HPG,MWG">
              <input className="input" value={cfg.universe} onChange={(e) => set("universe", e.target.value)} />
            </Field>
            <Field label="Giờ chạy hằng ngày" help="Trong phiên liên tục (T2-T6)"><input className="input" type="time" value={cfg.run_time} onChange={(e) => set("run_time", e.target.value)} /></Field>
            <Field label={`Điểm tổng hợp tối thiểu để mua: ${cfg.min_score}`}><input type="range" min={50} max={90} value={cfg.min_score} onChange={(e) => set("min_score", Number(e.target.value))} /></Field>
            <Field label={`Điểm kỹ thuật tối thiểu: ${cfg.min_technical}`}><input type="range" min={40} max={80} value={cfg.min_technical} onChange={(e) => set("min_technical", Number(e.target.value))} /></Field>
            <Field label={`Số mã tối đa: ${cfg.max_positions}`}><input type="range" min={2} max={15} value={cfg.max_positions} onChange={(e) => set("max_positions", Number(e.target.value))} /></Field>
            <Field label={`Tỷ trọng tối đa/mã: ${pct(cfg.max_weight, 0)}`}><input type="range" min={0.05} max={0.4} step={0.01} value={cfg.max_weight} onChange={(e) => set("max_weight", Number(e.target.value))} /></Field>
            <Field label={`Rủi ro tối đa/lệnh: ${pct(cfg.risk_per_trade, 1)} vốn`}><input type="range" min={0.005} max={0.03} step={0.0025} value={cfg.risk_per_trade} onChange={(e) => set("risk_per_trade", Number(e.target.value))} /></Field>
            <Field label={`Cắt lỗ tối đa: ${pct(cfg.max_stop_pct, 0)}`}><input type="range" min={0.03} max={0.15} step={0.01} value={cfg.max_stop_pct} onChange={(e) => set("max_stop_pct", Number(e.target.value))} /></Field>
            <Field label={`Trailing stop: ${pct(cfg.trailing_stop_pct, 0)}`}><input type="range" min={0.05} max={0.25} step={0.01} value={cfg.trailing_stop_pct} onChange={(e) => set("trailing_stop_pct", Number(e.target.value))} /></Field>
            <Field label={`Kill-switch: ngưng mua khi sụt ${pct(cfg.max_drawdown_halt, 0)}`}><input type="range" min={0.05} max={0.4} step={0.01} value={cfg.max_drawdown_halt} onChange={(e) => set("max_drawdown_halt", Number(e.target.value))} /></Field>
            <Field label="Điều chỉnh theo thị trường chung"><div className="row"><Switch on={cfg.use_market_filter} onChange={(v) => set("use_market_filter", v)} /><span className="small muted">Tỷ trọng CP theo VN-Index</span></div></Field>
          </div>
        </Card>
        <Card title="Đề xuất chờ duyệt" icon={<Check size={16} />}>
          {props.loading ? <Loading height={80} /> : (props.data ?? []).length === 0 ? <Empty title="Không có đề xuất">Chạy chu kỳ ở chế độ "Đề xuất" hoặc nhờ AI Agent.</Empty> : (
            <div className="list" style={{ maxHeight: 460, overflowY: "auto" }}>
              {props.data.map((p: any) => (
                <div key={p.id} className="list-item" style={{ alignItems: "flex-start" }}>
                  <Badge tone={p.side === "BUY" ? "up" : "down"}>{p.side === "BUY" ? "MUA" : "BÁN"}</Badge>
                  <div className="grow">
                    <div className="bold">{p.ticker} · {vnd(p.quantity)} CP @ {vnd(p.price)}</div>
                    <div className="tiny subtle">{p.reason}</div>
                    <div className="tiny subtle">Nguồn: {p.source === "agent" ? "AI Agent" : "Auto-Trader"} · {money(p.quantity * (p.price ?? 0))}</div>
                  </div>
                  <div className="col" style={{ gap: 6 }}>
                    <button className="btn sm buy" onClick={() => decide(p.id, true)}><Check size={13} /> Duyệt</button>
                    <button className="btn sm" onClick={() => decide(p.id, false)}><X size={13} /> Bỏ</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {result && (
        <Card title={`Kết quả chu kỳ · ${result.time}`} icon={<Zap size={16} />}
          actions={<><Badge tone="info">{result.market.regime}</Badge><Badge>Mục tiêu CP {pct(result.market.exposure_target, 0)}</Badge></>}>
          <div className="col" style={{ gap: 12 }}>
            {result.notes.map((n: string, i: number) => <Alert key={i} kind={n.includes("KILL") ? "err" : "info"}>{n}</Alert>)}
            <ActionTable actions={result.executed?.length ? result.executed : result.proposed?.length ? result.proposed : result.actions} />
          </div>
        </Card>
      )}

      <Backtest />
    </>
  );
}
