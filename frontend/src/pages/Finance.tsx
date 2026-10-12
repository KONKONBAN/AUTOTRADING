import { useState } from "react";
import { Calculator, ClipboardCheck, Plus, PiggyBank, Target, Trash2 } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { isNum, money, num, pct, vnd } from "../lib/format";
import { Alert, Badge, Card, Field, Kpi, Seg, Tabs, useAsync, useToast } from "../components/ui";

const PIE = ["#14b8a6", "#3b82f6", "#f59e0b", "#eab308", "#64748b"];
const tt = { background: "var(--surface-3)", border: "1px solid var(--border-strong)", borderRadius: 10 };

function Planner() {
  const toast = useToast();
  const [f, setF] = useState({ monthly_income: 30_000_000, monthly_expenses: 18_000_000, essential_expenses: 12_000_000, current_savings: 50_000_000, age: 28, risk_profile: "can_bang", emergency_months: 6 });
  const [debts, setDebts] = useState([{ name: "Thẻ tín dụng", amount: 15_000_000, rate: 0.28 }]);
  const [goals, setGoals] = useState([{ name: "Mua nhà", amount: 2_000_000_000, years: 8 }, { name: "Quỹ hưu trí", amount: 5_000_000_000, years: 25 }]);
  const [res, setRes] = useState<any>(null);
  const run = async () => {
    try {
      setRes(await api.post("/api/finance/plan", { ...f, debts, goals }));
    } catch (e: any) {
      toast("err", e.message);
    }
  };
  const nf = (k: keyof typeof f, label: string, step = 1_000_000) => (
    <Field label={label}><input className="input mono" type="number" step={step} value={f[k] as number} onChange={(e) => setF({ ...f, [k]: Number(e.target.value) })} /></Field>
  );
  return (
    <div className="col" style={{ gap: 16 }}>
      <Card title="Thông tin tài chính của bạn" icon={<PiggyBank size={16} />} actions={<button className="btn primary" onClick={run}>Lập kế hoạch</button>}>
        <div className="form-grid">
          {nf("monthly_income", "Thu nhập/tháng (đ)")}
          {nf("monthly_expenses", "Tổng chi tiêu/tháng (đ)")}
          {nf("essential_expenses", "Chi tiêu thiết yếu/tháng (đ)")}
          {nf("current_savings", "Tiền tiết kiệm hiện có (đ)", 10_000_000)}
          {nf("age", "Tuổi", 1)}
          {nf("emergency_months", "Quỹ dự phòng (số tháng)", 1)}
          <Field label="Khẩu vị rủi ro">
            <select className="input" value={f.risk_profile} onChange={(e) => setF({ ...f, risk_profile: e.target.value })}>
              <option value="than_trong">Thận trọng</option><option value="can_bang">Cân bằng</option><option value="tang_truong">Tăng trưởng</option>
            </select>
          </Field>
        </div>
        <div className="grid g2" style={{ marginTop: 16 }}>
          <div className="col" style={{ gap: 8 }}>
            <div className="row between"><b>Các khoản nợ</b><button className="btn sm" onClick={() => setDebts([...debts, { name: "Khoản vay", amount: 0, rate: 0.1 }])}><Plus size={13} /> Thêm</button></div>
            {debts.map((d, i) => (
              <div key={i} className="row" style={{ gap: 6 }}>
                <input className="input" value={d.name} onChange={(e) => setDebts(debts.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                <input className="input mono" type="number" value={d.amount} title="Dư nợ (đ)" onChange={(e) => setDebts(debts.map((x, j) => (j === i ? { ...x, amount: Number(e.target.value) } : x)))} />
                <input className="input mono" style={{ width: 90 }} type="number" step={0.5} value={+(d.rate * 100).toFixed(2)} title="Lãi suất %/năm" onChange={(e) => setDebts(debts.map((x, j) => (j === i ? { ...x, rate: Number(e.target.value) / 100 } : x)))} />
                <span className="small subtle">%</span>
                <button className="btn sm icon ghost" onClick={() => setDebts(debts.filter((_, j) => j !== i))}><Trash2 size={13} /></button>
              </div>
            ))}
          </div>
          <div className="col" style={{ gap: 8 }}>
            <div className="row between"><b>Mục tiêu tài chính</b><button className="btn sm" onClick={() => setGoals([...goals, { name: "Mục tiêu mới", amount: 100_000_000, years: 3 }])}><Plus size={13} /> Thêm</button></div>
            {goals.map((g, i) => (
              <div key={i} className="row" style={{ gap: 6 }}>
                <input className="input" value={g.name} onChange={(e) => setGoals(goals.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                <input className="input mono" type="number" value={g.amount} title="Số tiền (đ)" onChange={(e) => setGoals(goals.map((x, j) => (j === i ? { ...x, amount: Number(e.target.value) } : x)))} />
                <input className="input mono" style={{ width: 80 }} type="number" value={g.years} title="Số năm" onChange={(e) => setGoals(goals.map((x, j) => (j === i ? { ...x, years: Number(e.target.value) } : x)))} />
                <span className="small subtle">năm</span>
                <button className="btn sm icon ghost" onClick={() => setGoals(goals.filter((_, j) => j !== i))}><Trash2 size={13} /></button>
              </div>
            ))}
          </div>
        </div>
      </Card>
      {res && (
        <>
          <div className="grid g4">
            <Kpi label="Thặng dư mỗi tháng" value={money(res.summary.surplus)} valueClass={res.summary.surplus > 0 ? "up" : "down"} sub={<span className="muted">Tỷ lệ tiết kiệm {pct(res.summary.savings_rate, 0)}</span>} />
            <Kpi label="Quỹ dự phòng mục tiêu" value={money(res.emergency_fund.target)} sub={<span className={res.emergency_fund.gap > 0 ? "down" : "up"}>{res.emergency_fund.gap > 0 ? `Còn thiếu ${money(res.emergency_fund.gap)}` : "Đã đủ"}</span>} />
            <Kpi label="Có thể đầu tư/tháng" value={money(res.investable_monthly)} sub={<span className="muted">LN kỳ vọng danh mục {pct(res.portfolio_expected_return)}/năm</span>} />
            <Kpi label="Con số tự do tài chính" value={money(res.summary.fire_number)} sub={<span className="muted">= 25 × chi tiêu năm (quy tắc 4%)</span>} />
          </div>
          <div className="grid g3">
            <Card title="Ngân sách 50/30/20" icon={<ClipboardCheck size={16} />}>
              {[["needs", "Thiết yếu (50%)"], ["wants", "Mong muốn (30%)"], ["savings", "Tiết kiệm & đầu tư (20%)"]].map(([k, l]) => {
                const b = res.budget_50_30_20[k];
                const ok = k === "savings" ? b.actual >= b.target : b.actual <= b.target;
                return (
                  <div key={k} className="col" style={{ gap: 4, marginBottom: 12 }}>
                    <div className="row between small"><span>{l}</span><span className="mono"><b className={ok ? "up" : "down"}>{money(b.actual)}</b> / {money(b.target)}</span></div>
                    <div className="bar" style={{ height: 8 }}><i style={{ width: `${Math.min(100, (b.actual / Math.max(b.target, 1)) * 100)}%`, background: ok ? "var(--up)" : "var(--down)" }} /></div>
                  </div>
                );
              })}
            </Card>
            <Card title={`Phân bổ tài sản · ${res.risk_profile.label}`} icon={<PiggyBank size={16} />}>
              <div style={{ height: 180 }}>
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={res.allocation} dataKey="weight" nameKey="asset" innerRadius={50} outerRadius={80} paddingAngle={2} stroke="none">
                      {res.allocation.map((_: any, i: number) => <Cell key={i} fill={PIE[i % PIE.length]} />)}
                    </Pie>
                    <Tooltip formatter={(v: any) => pct(Number(v), 0)} contentStyle={tt} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              {res.allocation.map((a: any, i: number) => (
                <div key={a.asset} className="row between small" style={{ padding: "3px 0" }}>
                  <span className="row" style={{ gap: 6 }}><i className="legend-dot" style={{ background: PIE[i % PIE.length], width: 8, height: 8 }} />{a.asset}</span>
                  <span className="mono">{pct(a.weight, 0)} · {money(a.monthly_amount)}/th</span>
                </div>
              ))}
            </Card>
            <Card title="Dự phóng tài sản" icon={<Target size={16} />} hint="Đầu tư đều đặn hằng tháng theo danh mục khuyến nghị">
              <div style={{ height: 240 }}>
                <ResponsiveContainer>
                  <BarChart data={res.projection}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="years" tickFormatter={(y) => `${y} năm`} stroke="var(--text-3)" fontSize={11} />
                    <YAxis tickFormatter={(v) => money(v)} stroke="var(--text-3)" fontSize={10} width={70} />
                    <Tooltip formatter={(v: any) => money(Number(v))} labelFormatter={(y) => `Sau ${y} năm`} contentStyle={tt} />
                    <Bar dataKey="value" fill="#14b8a6" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>
          <div className="grid g2">
            <Card title="Mục tiêu tài chính" icon={<Target size={16} />}>
              <div className="table-wrap">
                <table className="tbl">
                  <thead><tr><th>Mục tiêu</th><th className="num">Số tiền</th><th className="num">Thời hạn</th><th className="num">Cần tiết kiệm/tháng</th><th>Khả thi</th></tr></thead>
                  <tbody>{res.goals.map((g: any, i: number) => (
                    <tr key={i}><td className="bold">{g.name}</td><td className="num mono">{money(g.amount)}</td><td className="num mono">{g.years} năm</td><td className="num mono">{money(g.monthly_saving)}</td>
                      <td><Badge tone={g.feasible ? "up" : "down"}>{g.feasible ? "Khả thi" : "Cần điều chỉnh"}</Badge></td></tr>
                  ))}</tbody>
                </table>
              </div>
            </Card>
            <Card title="Lời khuyên" icon={<ClipboardCheck size={16} />}>
              <div className="col" style={{ gap: 8 }}>{res.advice.map((a: string, i: number) => <Alert key={i} kind={i === 0 && res.summary.surplus <= 0 ? "err" : "info"}>{a}</Alert>)}</div>
              {res.debts_priority.length > 0 && <div className="small muted" style={{ marginTop: 10 }}>Thứ tự trả nợ (lãi cao trước): {res.debts_priority.map((d: any) => `${d.name} (${pct(d.rate, 1)})`).join(" → ")}</div>}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function RiskQuiz() {
  const q = useAsync(() => api.get("/api/finance/risk-questions"), []);
  const [ans, setAns] = useState<Record<string, number>>({});
  const [res, setRes] = useState<any>(null);
  const submit = async () => setRes(await api.post("/api/finance/risk-profile", ans));
  return (
    <Card title="Trắc nghiệm khẩu vị rủi ro" icon={<ClipboardCheck size={16} />}>
      <div className="col" style={{ gap: 16 }}>
        {(q.data ?? []).map((x: any) => (
          <div key={x.id} className="col" style={{ gap: 8 }}>
            <b>{x.q}</b>
            <div className="row wrap" style={{ gap: 6 }}>
              {x.options.map(([label, v]: [string, number]) => (
                <button key={label} className={`chip ${ans[x.id] === v ? "on" : ""}`} onClick={() => setAns({ ...ans, [x.id]: v })}>{label}</button>
              ))}
            </div>
          </div>
        ))}
        <button className="btn primary" style={{ alignSelf: "flex-start" }} disabled={Object.keys(ans).length < (q.data?.length ?? 5)} onClick={submit}>Xem kết quả</button>
        {res && <Alert kind="ok" title={`Khẩu vị rủi ro của bạn: ${res.label} (${res.score}/${res.max} điểm)`}>Dùng kết quả này ở tab "Kế hoạch tài chính" để nhận phân bổ tài sản phù hợp.</Alert>}
      </div>
    </Card>
  );
}

type F = [string, string, number | string, ("pct" | "num" | "list" | "bool" | "select")?, string[]?];
const CALCS: Record<string, { label: string; fields: F[]; note?: string }> = {
  compound_interest: { label: "Lãi kép", fields: [["pv", "Số tiền gốc (đ)", 100_000_000], ["rate", "Lãi suất năm (%)", 7, "pct"], ["periods", "Số năm", 5], ["m", "Số lần ghép lãi/năm", 12]] },
  simple_interest: { label: "Lãi đơn", fields: [["pv", "Số tiền gốc (đ)", 100_000_000], ["rate", "Lãi suất mỗi kỳ (%)", 7, "pct"], ["periods", "Số kỳ", 3]] },
  annuity: { label: "Chuỗi tiền tệ đều (PV/FV)", fields: [["payment", "Số tiền mỗi kỳ (đ)", 5_000_000], ["rate", "Lãi suất mỗi kỳ (%)", 0.6, "pct"], ["n", "Số kỳ", 60], ["due", "Phát sinh đầu kỳ", 0, "bool"]] },
  savings_payment: { label: "Tiết kiệm đều để đạt mục tiêu", fields: [["target_fv", "Số tiền mục tiêu (đ)", 1_000_000_000], ["rate", "Lãi suất mỗi kỳ (%)", 0.6, "pct"], ["n", "Số kỳ (tháng)", 120]] },
  loan_schedule: { label: "Lịch trả nợ vay", fields: [["principal", "Số tiền vay (đ)", 1_000_000_000], ["rate", "Lãi suất mỗi kỳ (%)", 0.8, "pct"], ["n", "Số kỳ (tháng)", 120], ["method", "Phương thức", "annuity", "select", ["annuity", "equal_principal"]]] },
  discount_bill: { label: "Chiết khấu thương phiếu", fields: [["face", "Mệnh giá (đ)", 500_000_000], ["rate", "Lãi suất chiết khấu năm (%)", 9, "pct"], ["days", "Số ngày còn lại", 60], ["fee", "Hoa hồng (đ)", 0]] },
  project_appraisal: { label: "Thẩm định dự án NPV / IRR / MIRR", fields: [["cashflows", "Dòng tiền (năm 0, 1, 2…) cách nhau dấu phẩy", "-1000, 300, 300, 300, 300, 300", "list"], ["rate", "Tỷ lệ chiết khấu / WACC (%)", 10, "pct"]], note: "VD CFA: −1.000 tỷ, 300 tỷ × 5 năm, WACC 10% → NPV = +137,2 tỷ" },
  wacc: { label: "Chi phí vốn bình quân WACC", fields: [["equity_value", "Giá trị thị trường VCSH", 6000], ["debt_value", "Giá trị nợ vay", 4000], ["cost_equity", "Chi phí VCSH re (%)", 15, "pct"], ["cost_debt", "Chi phí nợ trước thuế rd (%)", 8, "pct"], ["tax_rate", "Thuế TNDN (%)", 20, "pct"]], note: "VD: 60% × 15% + 40% × 8% × (1 − 20%) = 11,56%" },
  capm: { label: "CAPM - chi phí vốn chủ", fields: [["rf", "Lãi suất phi rủi ro (%)", 3, "pct"], ["beta", "Beta", 1.1], ["mrp", "Phần bù rủi ro thị trường (%)", 8, "pct"]] },
  bond_price: { label: "Định giá trái phiếu", fields: [["face", "Mệnh giá (đ)", 1_000_000], ["coupon_rate", "Lãi suất coupon (%)", 8, "pct"], ["market_rate", "Lãi suất thị trường (%)", 10, "pct"], ["years", "Số năm đến đáo hạn", 15], ["freq", "Số lần trả lãi/năm", 1]], note: "VD Ch.3: TP Thiên Hương coupon 8%, LS thị trường 10%, 15 năm" },
  bond_ytm: { label: "Lợi suất đáo hạn YTM", fields: [["price", "Giá thị trường (đ)", 1_035_000], ["face", "Mệnh giá (đ)", 1_000_000], ["coupon_rate", "Coupon (%)", 10, "pct"], ["years", "Số năm còn lại", 2], ["freq", "Số lần trả lãi/năm", 1]], note: "VD Ch.3: YTM ≈ 8,04%" },
  convertible_bond: { label: "Trái phiếu chuyển đổi", fields: [["face", "Mệnh giá (đ)", 1_000_000], ["conversion_price", "Giá chuyển đổi (đ)", 40_000], ["stock_price", "Thị giá cổ phiếu (đ)", 50_000]] },
  lease_vs_buy: { label: "Thuê tài chính hay vay mua", fields: [["asset_cost", "Giá mua tài sản (đ)", 1_000_000_000], ["lease_payment", "Tiền thuê mỗi năm (đ)", 260_000_000], ["years", "Thời hạn (năm)", 5], ["pre_tax_debt_rate", "Lãi vay trước thuế (%)", 10, "pct"], ["tax_rate", "Thuế TNDN (%)", 20, "pct"], ["salvage", "Giá trị thanh lý (đ)", 0]] },
};

function fmtResult(k: string, v: any): string {
  if (typeof v === "string") return v;
  if (typeof v === "boolean") return v ? "Có" : "Không";
  if (!isNum(v)) return "—";
  if (/rate|yield|irr|wacc|we$|wd$|wp$|after_tax/.test(k) || k === "result_pct") return pct(v, 2);
  if (/ratio|index|duration|macaulay|modified|payback/.test(k)) return num(v, 3);
  return vnd(v, Math.abs(v) < 100 ? 4 : 0);
}

function Calculators() {
  const toast = useToast();
  const [calc, setCalc] = useState("project_appraisal");
  const [vals, setVals] = useState<Record<string, any>>({});
  const [res, setRes] = useState<any>(null);
  const def = CALCS[calc];
  const get = (f: F) => (vals[`${calc}.${f[0]}`] ?? f[2]);
  const run = async () => {
    const params: Record<string, any> = {};
    def.fields.forEach((f) => {
      const v = get(f);
      params[f[0]] = f[3] === "pct" ? Number(v) / 100 : f[3] === "list" ? String(v).split(/[,;\s]+/).filter(Boolean).map(Number) : f[3] === "bool" ? Boolean(Number(v)) : f[3] === "select" ? v : Number(v);
    });
    try {
      const r = await api.post("/api/finance/calc", { calculator: calc, params });
      setRes(r.result);
    } catch (e: any) {
      toast("err", e.message);
    }
  };
  const flat = res === null ? [] : typeof res === "object" ? Object.entries(res).filter(([k, v]) => k !== "schedule" && k !== "cashflows" && typeof v !== "object") : [["Kết quả", res]];
  return (
    <div className="grid g-main">
      <Card title="Máy tính tài chính" icon={<Calculator size={16} />} hint="Theo giáo trình Toán tài chính, PTVĐTCK chương 3, CFA (DCF & WACC), TCDN chương 9">
        <div className="row wrap" style={{ gap: 6, marginBottom: 14 }}>
          {Object.entries(CALCS).map(([k, c]) => <button key={k} className={`chip ${calc === k ? "on" : ""}`} onClick={() => { setCalc(k); setRes(null); }}>{c.label}</button>)}
        </div>
        <div className="form-grid">
          {def.fields.map((f) => (
            <Field key={f[0]} label={f[1]}>
              {f[3] === "select" ? (
                <select className="input" value={get(f)} onChange={(e) => setVals({ ...vals, [`${calc}.${f[0]}`]: e.target.value })}>
                  {f[4]!.map((o) => <option key={o} value={o}>{o === "annuity" ? "Trả góp đều" : o === "equal_principal" ? "Gốc đều, lãi giảm dần" : o}</option>)}
                </select>
              ) : f[3] === "bool" ? (
                <Seg value={String(get(f))} onChange={(v) => setVals({ ...vals, [`${calc}.${f[0]}`]: v })} items={[{ value: "0", label: "Cuối kỳ" }, { value: "1", label: "Đầu kỳ" }]} />
              ) : (
                <input className="input mono" type={f[3] === "list" ? "text" : "number"} step="any" value={get(f)} onChange={(e) => setVals({ ...vals, [`${calc}.${f[0]}`]: e.target.value })} />
              )}
            </Field>
          ))}
        </div>
        {def.note && <div className="small subtle" style={{ marginTop: 10 }}>{def.note}</div>}
        <button className="btn primary" style={{ marginTop: 14 }} onClick={run}><Calculator size={15} /> Tính</button>
      </Card>
      <Card title="Kết quả" icon={<ClipboardCheck size={16} />}>
        {res === null ? <div className="small subtle">Nhập thông số và bấm Tính.</div> : (
          <div className="col" style={{ gap: 8 }}>
            {flat.map(([k, v]) => (
              <div key={k} className="row between" style={{ borderBottom: "1px dashed var(--border)", padding: "6px 0" }}>
                <span className="muted small">{LABELS[k] ?? k}</span><b className="mono">{fmtResult(k, v)}</b>
              </div>
            ))}
            {res?.duration && <div className="row between small"><span className="muted">Duration Macaulay / Modified</span><b className="mono">{num(res.duration.macaulay, 3)} / {num(res.duration.modified, 3)}</b></div>}
            {res?.schedule && (
              <div className="table-wrap" style={{ maxHeight: 300, marginTop: 8 }}>
                <table className="tbl"><thead><tr><th>Kỳ</th><th className="num">Trả</th><th className="num">Lãi</th><th className="num">Gốc</th><th className="num">Dư nợ</th></tr></thead>
                  <tbody>{res.schedule.map((r: any) => <tr key={r.period}><td>{r.period}</td><td className="num mono">{vnd(r.payment)}</td><td className="num mono">{vnd(r.interest)}</td><td className="num mono">{vnd(r.principal)}</td><td className="num mono">{vnd(r.balance)}</td></tr>)}</tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}

const LABELS: Record<string, string> = {
  fv: "Giá trị tương lai (FV)", pv: "Giá trị hiện tại (PV)", interest: "Tiền lãi", effective_rate: "Lãi suất hiệu dụng/năm",
  npv: "NPV", irr: "IRR", mirr: "MIRR (tái đầu tư theo WACC)", profitability_index: "Chỉ số sinh lời PI", payback: "Thời gian hoàn vốn (năm)", decision: "Quyết định",
  wacc: "WACC", we: "Tỷ trọng VCSH", wd: "Tỷ trọng nợ", wp: "Tỷ trọng CP ưu đãi", after_tax_cost_debt: "Chi phí nợ sau thuế",
  price: "Giá trái phiếu", pv_coupons: "PV tiền lãi coupon", pv_face: "PV mệnh giá", current_yield: "Lợi suất hiện hành CY", status: "So với mệnh giá",
  conversion_ratio: "Tỷ lệ chuyển đổi", conversion_value: "Giá trị chuyển đổi", premium: "Chênh lệch so với mệnh giá", should_convert: "Nên chuyển đổi",
  discount: "Tiền chiết khấu", fee: "Hoa hồng", proceeds: "Số tiền nhận được", actual_rate: "Lãi suất thực tế",
  total_interest: "Tổng tiền lãi", total_paid: "Tổng tiền phải trả", nal: "Lợi ích ròng của thuê (NAL)", discount_rate: "Tỷ lệ chiết khấu rd(1−t)",
  "Kết quả": "Kết quả",
};

export default function Finance() {
  const [tab, setTab] = useState<"plan" | "risk" | "calc">("plan");
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Quản trị tài chính cá nhân</h1>
          <p>Ngân sách, quỹ dự phòng, trả nợ, mục tiêu và phân bổ tài sản - cùng bộ máy tính tài chính theo giáo trình.</p>
        </div>
      </div>
      <Tabs value={tab} onChange={setTab} items={[
        { value: "plan", label: "Kế hoạch tài chính", icon: <PiggyBank size={15} /> },
        { value: "risk", label: "Khẩu vị rủi ro", icon: <ClipboardCheck size={15} /> },
        { value: "calc", label: "Máy tính tài chính", icon: <Calculator size={15} /> },
      ]} />
      {tab === "plan" && <Planner />}
      {tab === "risk" && <RiskQuiz />}
      {tab === "calc" && <Calculators />}
    </>
  );
}
