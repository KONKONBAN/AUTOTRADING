import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  CandlestickChart, CheckCircle2, Database, Download, FileImage, FileSpreadsheet, Plus, RefreshCw, Save, Trash2, Wifi, WifiOff, XCircle,
} from "lucide-react";
import { api, download } from "../lib/api";
import { useStatus } from "../lib/status";
import { bn, cls, num, pct, recTone, sourceLabel, tone, vnd } from "../lib/format";
import { Alert, Badge, Card, Empty, Field, FileDrop, Loading, SourceBadge, Tabs, useAsync, useToast } from "../components/ui";

type Tab = "sources" | "prices" | "fin" | "chart";

/* ------------------------------------------------------------------ nguồn tự động */
function Sources() {
  const { status, refresh } = useStatus();
  const toast = useToast();
  const [res, setRes] = useState<any[] | null>(status?.data.provider_health?.results ?? null);
  const [busy, setBusy] = useState(false);
  const check = async () => {
    setBusy(true);
    try {
      const r = await api.post("/api/data/health-check");
      setRes(r.results);
      refresh();
      toast(r.any_ok ? "ok" : "err", r.any_ok ? "Đã kết nối được nguồn dữ liệu tự động." : "Không nguồn nào truy cập được - hãy nhập dữ liệu thủ công.");
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy(false);
    }
  };
  const providers = [
    { key: "vndirect", name: "VNDirect (dchart)" }, { key: "ssi", name: "SSI iBoard" }, { key: "tcbs", name: "TCBS" },
    { key: "vps", name: "VPS" }, { key: "vietstock", name: "Vietstock" }, { key: "cafef", name: "CafeF" },
  ];
  return (
    <div className="col" style={{ gap: 16 }}>
      <Alert kind={status?.data.needs_manual_input ? "warn" : status?.data.source === "demo" ? "info" : "ok"} title={`Chế độ dữ liệu: ${status?.data.mode?.toUpperCase()} · Nguồn đang dùng: ${sourceLabel(status?.data.source)}`}>
        {status?.data.message}
      </Alert>
      <Card title="Chuỗi nguồn dữ liệu tự động" icon={<Database size={16} />}
        hint="Ứng dụng tự động thử lần lượt các nguồn; nguồn nào lỗi sẽ chuyển sang nguồn kế tiếp. Chỉ khi tất cả đều lỗi mới cần nhập thủ công."
        actions={<button className="btn primary sm" onClick={check} disabled={busy}><RefreshCw size={14} className={busy ? "spin" : ""} /> {busy ? "Đang kiểm tra…" : "Kiểm tra kết nối"}</button>}>
        <div className="grid g3">
          {providers.map((p, i) => {
            const r = res?.find((x) => x.provider === p.key);
            return (
              <div key={p.key} className="card tight flat row" style={{ gap: 12 }}>
                <span className="kpi-icon" style={{ background: r ? (r.ok ? "var(--up-soft)" : "var(--down-soft)") : undefined, color: r ? (r.ok ? "var(--up)" : "var(--down)") : undefined }}>
                  {r ? (r.ok ? <Wifi size={17} /> : <WifiOff size={17} />) : <span className="mono small">{i + 1}</span>}
                </span>
                <div className="grow" style={{ minWidth: 0 }}>
                  <div className="bold">{p.name}</div>
                  <div className="tiny subtle" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {!r ? "Chưa kiểm tra" : r.ok ? `OK · ${r.rows} phiên · đến ${r.last_date} · ${r.ms}ms` : `Lỗi: ${r.error}`}
                  </div>
                </div>
                {r && (r.ok ? <CheckCircle2 size={18} color="var(--up)" /> : <XCircle size={18} color="var(--down)" />)}
              </div>
            );
          })}
        </div>
      </Card>
      <Card title="Thứ tự ưu tiên dữ liệu" icon={<Database size={16} />}>
        <ol className="small muted" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
          <li><b>Dữ liệu bạn tự nhập</b> (file giá CSV/Excel, BCTC Excel/ảnh/PDF) - luôn được ưu tiên cao nhất.</li>
          <li><b>Nguồn tự động</b>: VNDirect → SSI iBoard → TCBS → VPS → Vietstock → CafeF (nguồn thành công gần nhất được ưu tiên ở lần sau).</li>
          <li><b>Dữ liệu DEMO</b> mô phỏng - chỉ dùng khi không có hai nguồn trên, luôn được gắn nhãn cảnh báo.</li>
        </ol>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ giá */
function Prices({ ticker }: { ticker: string }) {
  const toast = useToast();
  const list = useAsync(() => api.get("/api/prices/imported"), []);
  const [tk, setTk] = useState(ticker);
  const upload = async (files: File[]) => {
    const form = new FormData();
    form.append("file", files[0]);
    if (tk) form.append("ticker", tk);
    try {
      const r = await api.form("/api/prices/upload", form);
      toast("ok", `Đã nhập ${vnd(r.rows)} phiên (${Object.keys(r.tickers).join(", ")}) từ ${r.from} đến ${r.to}.`);
      list.reload();
    } catch (e: any) {
      toast("err", e.message);
    }
  };
  return (
    <div className="grid g-main">
      <Card title="Tải lên lịch sử giá" icon={<CandlestickChart size={16} />} hint="CSV hoặc Excel (.xlsx) - xuất từ Amibroker/MetaStock, CafeF, Vietstock, các bảng giá CTCK…">
        <div className="col" style={{ gap: 12 }}>
          <Field label="Mã cổ phiếu (khi file không có cột mã)"><input className="input" value={tk} onChange={(e) => setTk(e.target.value.toUpperCase())} placeholder="VD: FPT" /></Field>
          <FileDrop accept=".csv,.txt,.xlsx,.xlsm" onFiles={upload} title="Kéo thả hoặc bấm để chọn file giá" hint="Hỗ trợ: <Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume> hoặc bảng có tiêu đề Ngày / Mở cửa / Cao nhất / Thấp nhất / Đóng cửa / Khối lượng" icon={<FileSpreadsheet size={22} />} />
          <Alert kind="info">Giá theo nghìn đồng (VD 57.2) sẽ tự quy đổi sang đồng. Dữ liệu nhập được ưu tiên hơn nguồn tự động cho mã tương ứng.</Alert>
        </div>
      </Card>
      <Card title="Dữ liệu giá đã nhập" icon={<Database size={16} />}>
        {list.loading ? <Loading height={80} /> : (list.data ?? []).length === 0 ? <Empty title="Chưa nhập dữ liệu giá nào" /> : (
          <div className="list">
            {list.data.map((r: any) => (
              <div key={r.ticker} className="list-item">
                <Link to={`/stock/${r.ticker}`} className="bold">{r.ticker}</Link>
                <span className="small muted grow">{vnd(r.rows)} phiên · {r.first} → {r.last}</span>
                <button className="btn sm icon ghost" onClick={async () => { await api.del(`/api/prices/imported/${r.ticker}`); list.reload(); }}><Trash2 size={14} /></button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ BCTC */
type Row = Record<string, any>;

function FinGrid({ fields, rows, setRows }: { fields: any[]; rows: Row[]; setRows: (r: Row[]) => void }) {
  const years = rows.map((r) => r.year);
  const setCell = (year: number, key: string, v: string) =>
    setRows(rows.map((r) => (r.year === year ? { ...r, [key]: v === "" ? null : Number(v) } : r)));
  const addYear = () => {
    const y = years.length ? Math.max(...years) + 1 : new Date().getFullYear() - 1;
    setRows([...rows, { year: y }].sort((a, b) => a.year - b.year));
  };
  return (
    <div className="table-wrap" style={{ maxHeight: 560 }}>
      <table className="tbl">
        <thead>
          <tr>
            <th style={{ minWidth: 260 }}>Chỉ tiêu</th><th>Đơn vị</th>
            {rows.map((r) => (
              <th key={r.year} className="num">
                <div className="row" style={{ justifyContent: "flex-end", gap: 4 }}>
                  <input className="input mono" style={{ width: 74, height: 28, textAlign: "right" }} type="number" value={r.year}
                    onChange={(e) => setRows(rows.map((x) => (x === r ? { ...x, year: Number(e.target.value) } : x)))} />
                  <button className="btn sm icon ghost" title="Xóa cột" onClick={() => setRows(rows.filter((x) => x !== r))}><Trash2 size={12} /></button>
                </div>
              </th>
            ))}
            <th><button className="btn sm" onClick={addYear}><Plus size={13} /> Năm</button></th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f) => (
            <tr key={f.key}>
              <td className={cls(f.required && "bold")}>{f.label}{f.required && <span className="down"> *</span>}</td>
              <td className="tiny subtle nowrap">{f.unit}</td>
              {rows.map((r) => (
                <td key={r.year} className="num" style={{ padding: "4px 6px" }}>
                  <input className="input mono" style={{ height: 30, textAlign: "right", minWidth: 110 }} type="number" step="any"
                    value={r[f.key] ?? ""} onChange={(e) => setCell(r.year, f.key, e.target.value)} />
                </td>
              ))}
              <td />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Financials({ ticker, setTicker }: { ticker: string; setTicker: (t: string) => void }) {
  const toast = useToast();
  const { universe, status } = useStatus();
  const fields = useAsync(() => api.get("/api/financials/fields"), []);
  const fin = useAsync(() => api.get(`/api/financials/${ticker}`), [ticker]);
  const [draft, setDraft] = useState<Row[] | null>(null);
  const [meta, setMeta] = useState<any>(null);
  const [busy, setBusy] = useState("");
  const [useAi, setUseAi] = useState(false);
  useEffect(() => { setDraft(null); setMeta(null); }, [ticker]);

  const loadPreview = (r: any, method: string) => {
    setDraft(r.years.map((y: any) => ({ ...y })));
    setMeta({ method, unit: r.unit_detected ?? r.original_unit, mapping: r.mapping, warnings: r.warnings ?? [], missing: r.missing_fields, company: r.company, report_type: r.report_type });
    toast("ok", `Đã đọc ${r.years.length} năm số liệu - hãy kiểm tra lại rồi bấm Lưu.`);
  };
  const uploadExcel = async (files: File[]) => {
    setBusy("excel");
    const form = new FormData();
    form.append("file", files[0]);
    form.append("ticker", ticker);
    form.append("use_ai", String(useAi));
    try {
      const r = await api.form("/api/financials/upload", form);
      loadPreview(r, r.method === "ai" ? "AI đọc file Excel" : "Bộ đọc Excel tự động");
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy("");
    }
  };
  const uploadImages = async (files: File[]) => {
    setBusy("ai");
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    form.append("ticker", ticker);
    try {
      loadPreview(await api.form("/api/financials/extract", form), "AI đọc ảnh/PDF");
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy("");
    }
  };
  const editExisting = () => {
    if (!fin.data) return;
    const keys = (fields.data ?? []).map((f: any) => f.key);
    const src: string = fin.data.source;
    // không bao giờ nạp số liệu DEMO bịa ra vào bản nháp (sẽ thành "nhập tay" khi lưu)
    const real = src === "demo" ? [] : src.includes("demo")
      ? fin.data.rows.filter((r: any) => fin.data.manual_years.includes(r.year)) : fin.data.rows;
    const rows = real.length ? real : [{ year: new Date().getFullYear() - 1 }];
    setDraft(rows.map((r: any) => Object.fromEntries([["year", r.year], ...keys.map((k: string) => [k, r[k] ?? null])])));
    setMeta({ method: real.length ? "Chỉnh sửa số liệu hiện có" : "Nhập tay số liệu mới", warnings: [] });
  };
  const MONEY_KEYS_EXCLUDED = new Set(["year", "shares", "dps"]);
  const rescale = (factor: number) => {
    if (!draft) return;
    setDraft(draft.map((r) => Object.fromEntries(Object.entries(r).map(([k, v]) =>
      [k, MONEY_KEYS_EXCLUDED.has(k) || typeof v !== "number" ? v : v * factor]))));
  };
  const save = async () => {
    if (!draft) return;
    try {
      await api.put(`/api/financials/${ticker}/manual`, { rows: draft });
      toast("ok", `Đã lưu BCTC ${ticker} - phân tích sẽ dùng số liệu này.`);
      setDraft(null);
      fin.reload();
    } catch (e: any) {
      toast("err", e.message);
    }
  };
  const removeManual = async () => {
    if (!confirm(`Xóa toàn bộ số liệu nhập tay của ${ticker}?`)) return;
    await api.del(`/api/financials/${ticker}/manual`);
    fin.reload();
  };

  return (
    <div className="col" style={{ gap: 16 }}>
      <Card>
        <div className="row wrap" style={{ gap: 12, alignItems: "flex-end" }}>
          <Field label="Mã cổ phiếu">
            <select className="input" style={{ width: 260 }} value={ticker} onChange={(e) => setTicker(e.target.value)}>
              {universe.map((u) => <option key={u.ticker} value={u.ticker}>{u.ticker} - {u.name}</option>)}
            </select>
          </Field>
          {fin.data && <div className="row" style={{ gap: 6 }}><span className="small muted">Nguồn BCTC hiện tại:</span><SourceBadge source={fin.data.source} /></div>}
          <div className="grow" />
          <button className="btn" onClick={() => download(`/api/financials/template?ticker=${ticker}`)}><Download size={15} /> Tải file Excel mẫu ({ticker})</button>
          <button className="btn" onClick={editExisting}><FileSpreadsheet size={15} /> Sửa trực tiếp</button>
          {fin.data?.manual?.length > 0 && <button className="btn ghost" onClick={removeManual}><Trash2 size={15} /> Xóa số liệu nhập tay</button>}
        </div>
      </Card>

      <div className="grid g2">
        <Card title="Tải file Excel / CSV báo cáo tài chính" icon={<FileSpreadsheet size={16} />}
          hint="File mẫu của ứng dụng hoặc file xuất từ Vietstock, CafeF, FiinPro, VNDirect, SSI… (chỉ tiêu × năm)">
          <div className="col" style={{ gap: 10 }}>
            <FileDrop accept=".xlsx,.xlsm,.csv" onFiles={uploadExcel} title={busy === "excel" ? "Đang đọc file…" : "Kéo thả file Excel BCTC"} hint="Tự nhận diện chỉ tiêu tiếng Việt/Anh, cột năm và đơn vị (đồng/nghìn/triệu/tỷ)" icon={<FileSpreadsheet size={22} />} />
            <label className="row small muted" style={{ gap: 8 }}>
              <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} disabled={!status?.ai_enabled} />
              Dùng AI đọc file (cho định dạng đặc biệt){!status?.ai_enabled && " - cần API key"}
            </label>
          </div>
        </Card>
        <Card title="AI đọc ảnh chụp / PDF báo cáo tài chính" icon={<FileImage size={16} />} hint="Chụp màn hình BCTC hoặc tải file PDF - AI trích xuất số liệu để bạn kiểm tra">
          {status?.ai_enabled ? (
            <FileDrop accept="image/png,image/jpeg,image/webp,application/pdf" multiple onFiles={uploadImages}
              title={busy === "ai" ? "AI đang đọc báo cáo… (10-60 giây)" : "Kéo thả ảnh / PDF BCTC"} hint="Có thể chọn nhiều ảnh: bảng cân đối, KQKD, lưu chuyển tiền tệ" icon={<FileImage size={22} />} />
          ) : <Alert kind="warn">Cần cấu hình ANTHROPIC_API_KEY để AI đọc ảnh/PDF. Bạn vẫn có thể dùng file Excel hoặc nhập tay.</Alert>}
        </Card>
      </div>

      {draft && fields.data && (
        <Card title={`Xem lại & chỉnh sửa trước khi lưu · ${meta?.method ?? ""}`} icon={<Save size={16} />}
          hint={[meta?.company, meta?.report_type, meta?.unit && `Đơn vị gốc: ${meta.unit} → quy đổi tỷ đồng`].filter(Boolean).join(" · ")}
          actions={<>
            <button className="btn sm" title="Số liệu đang nhỏ hơn thực tế 1000 lần" onClick={() => rescale(1000)}>×1000</button>
            <button className="btn sm" title="Số liệu đang lớn hơn thực tế 1000 lần" onClick={() => rescale(0.001)}>÷1000</button>
            <button className="btn ghost" onClick={() => setDraft(null)}>Hủy</button>
            <button className="btn primary" onClick={save}><Save size={15} /> Lưu vào hệ thống</button></>}>
          <div className="col" style={{ gap: 10 }}>
            {meta?.warnings?.map((w: string, i: number) => <Alert key={i} kind="warn">{w}</Alert>)}
            {meta?.missing?.length > 0 && <div className="small subtle">Chưa tìm thấy: {meta.missing.map((k: string) => fields.data.find((f: any) => f.key === k)?.label ?? k).join(", ")}</div>}
            <FinGrid fields={fields.data} rows={draft} setRows={setDraft} />
          </div>
        </Card>
      )}

      <Card title={`Số liệu BCTC đang dùng cho phân tích ${ticker}`} icon={<Database size={16} />} hint="Đơn vị: tỷ đồng · Cột có nhãn 'Nhập tay' là số liệu bạn đã cung cấp">
        {fin.loading ? <Loading /> : fin.data && (
          <div className="table-wrap">
            <table className="tbl">
              <thead><tr><th>Chỉ tiêu</th>{fin.data.rows.map((r: any) => <th key={r.year} className="num">{r.year} {fin.data.manual_years.includes(r.year) && <Badge tone="info">Nhập tay</Badge>}</th>)}</tr></thead>
              <tbody>
                {(fields.data ?? []).map((f: any) => (
                  <tr key={f.key}><td className={cls(f.required && "bold")}>{f.label}</td>{fin.data.rows.map((r: any) => <td key={r.year} className="num mono">{f.key === "dps" ? vnd(r[f.key]) : bn(r[f.key])}</td>)}</tr>
                ))}
                <tr><td className="bold">ROE</td>{fin.data.ratios.map((r: any) => <td key={r.year} className="num mono bold">{pct(r.roe)}</td>)}</tr>
                <tr><td className="bold">ROA</td>{fin.data.ratios.map((r: any) => <td key={r.year} className="num mono">{pct(r.roa)}</td>)}</tr>
                <tr><td className="bold">D/E</td>{fin.data.ratios.map((r: any) => <td key={r.year} className="num mono">{num(r.lev, 2)}</td>)}</tr>
                <tr><td className="bold">EPS (đ)</td>{fin.data.ratios.map((r: any) => <td key={r.year} className="num mono">{vnd(r.eps)}</td>)}</tr>
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ ảnh biểu đồ */
function ChartReader({ ticker }: { ticker: string }) {
  const toast = useToast();
  const { status } = useStatus();
  // chỉ điền sẵn mã khi người dùng mở từ trang của một mã cụ thể; để trống thì AI tự nhận diện mã trên ảnh
  const [form, setForm] = useState({ ticker, timeframe: "Ngày (D)", start: "", end: "", note: "" });
  const [files, setFiles] = useState<File[]>([]);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const history = useAsync(() => api.get("/api/charts/history?limit=10"), []);
  const run = async () => {
    if (!files.length) return toast("err", "Hãy chọn ít nhất 1 ảnh biểu đồ.");
    setBusy(true);
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    Object.entries(form).forEach(([k, v]) => v && fd.append(k, v));
    try {
      setRes(await api.form("/api/charts/analyze", fd));
      history.reload();
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy(false);
    }
  };
  const ai = res?.ai;
  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="grid g-main">
        <Card title="Phân tích ảnh chụp biểu đồ nến" icon={<FileImage size={16} />} hint="Chụp màn hình biểu đồ (TradingView, bảng giá CTCK, Vietstock…) trong khoảng thời gian bạn quan tâm">
          {!status?.ai_enabled && <div style={{ marginBottom: 12 }}><Alert kind="warn">Tính năng này cần ANTHROPIC_API_KEY (AI đọc hình ảnh).</Alert></div>}
          <div className="col" style={{ gap: 12 }}>
            <FileDrop accept="image/png,image/jpeg,image/webp" multiple onFiles={(fs) => setFiles([...files, ...fs])} title="Kéo thả ảnh biểu đồ nến" hint="PNG/JPG/WEBP · có thể chọn nhiều khung thời gian" icon={<CandlestickChart size={22} />} />
            {files.length > 0 && (
              <div className="row wrap" style={{ gap: 8 }}>
                {files.map((f, i) => (
                  <div key={i} className="card tight flat" style={{ padding: 6 }}>
                    <img src={URL.createObjectURL(f)} alt="" style={{ height: 70, borderRadius: 8, display: "block" }} />
                    <button className="btn sm ghost" style={{ width: "100%" }} onClick={() => setFiles(files.filter((_, j) => j !== i))}>Bỏ</button>
                  </div>
                ))}
              </div>
            )}
            <div className="form-grid">
              <Field label="Mã cổ phiếu (để đối chiếu)"><input className="input" placeholder="Để trống: AI tự nhận diện mã trên ảnh" value={form.ticker} onChange={(e) => setForm({ ...form, ticker: e.target.value.toUpperCase() })} /></Field>
              <Field label="Khung thời gian nến"><input className="input" value={form.timeframe} onChange={(e) => setForm({ ...form, timeframe: e.target.value })} /></Field>
              <Field label="Từ ngày"><input className="input" type="date" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} /></Field>
              <Field label="Đến ngày"><input className="input" type="date" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} /></Field>
            </div>
            <Field label="Ghi chú / câu hỏi thêm"><textarea className="input" rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="VD: Tôi đang giữ giá vốn 115.000, có nên bán không?" /></Field>
            <button className="btn primary" onClick={run} disabled={busy || !status?.ai_enabled}>{busy ? "AI đang đọc biểu đồ…" : "Phân tích ảnh"}</button>
          </div>
        </Card>
        <Card title="Phân tích gần đây" icon={<Database size={16} />}>
          {(history.data ?? []).length === 0 ? <Empty title="Chưa có" /> : (
            <div className="list">
              {history.data.map((h: any) => (
                <div key={h.id} className="list-item" style={{ cursor: "pointer" }} onClick={() => setRes(h.result)}>
                  <Badge tone={recTone({ "MUA MẠNH": "buy", MUA: "buy", "NẮM GIỮ": "hold", BÁN: "sell", "BÁN MẠNH": "sell" }[h.result.ai.signal as string])}>{h.result.ai.signal}</Badge>
                  <span className="bold">{h.ticker ?? "—"}</span>
                  <span className="small subtle grow">{h.timeframe}</span>
                  <span className="tiny subtle">{new Date(h.created_at * 1000).toLocaleDateString("vi-VN")}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
      {ai && (
        <div className="grid g-main">
          <Card title="Nhận định của AI từ ảnh biểu đồ" icon={<CandlestickChart size={16} />}
            actions={<><Badge lg tone={["MUA", "MUA MẠNH"].includes(ai.signal) ? "up" : ["BÁN", "BÁN MẠNH"].includes(ai.signal) ? "down" : "ref"}>{ai.signal}</Badge><Badge lg>Tin cậy {pct(ai.confidence, 0)}</Badge></>}>
            {!ai.is_price_chart && <Alert kind="warn">Ảnh có vẻ không phải biểu đồ giá.</Alert>}
            <p style={{ marginBottom: 12 }}>{ai.summary}</p>
            <div className="grid g3" style={{ gap: 10, marginBottom: 12 }}>
              <div className="card tight flat"><div className="tiny subtle">Xu hướng ngắn hạn</div><div className={cls("bold", ai.trend_short === "Tăng" ? "up" : ai.trend_short === "Giảm" ? "down" : "ref")}>{ai.trend_short}</div></div>
              <div className="card tight flat"><div className="tiny subtle">Xu hướng trung hạn</div><div className={cls("bold", ai.trend_medium === "Tăng" ? "up" : ai.trend_medium === "Giảm" ? "down" : "ref")}>{ai.trend_medium}</div></div>
              <div className="card tight flat"><div className="tiny subtle">Khung / giai đoạn</div><div className="bold small">{ai.timeframe_detected} · {ai.period_visible}</div></div>
              <div className="card tight flat"><div className="tiny subtle">Điểm mua</div><div className="mono bold">{vnd(ai.entry)}</div></div>
              <div className="card tight flat"><div className="tiny subtle">Cắt lỗ</div><div className="mono bold down">{vnd(ai.stop_loss)}</div></div>
              <div className="card tight flat"><div className="tiny subtle">Chốt lời</div><div className="mono bold up">{vnd(ai.take_profit)}</div></div>
            </div>
            <div className="grid g2">
              <div>
                <h3 style={{ marginBottom: 8 }}>Mô hình nhận diện</h3>
                {ai.patterns.map((p: any, i: number) => (
                  <div key={i} className="list-item" style={{ alignItems: "flex-start" }}>
                    <Badge tone={p.bias === "bullish" ? "up" : p.bias === "bearish" ? "down" : "ref"}>{p.name}</Badge>
                    <span className="small muted grow">{p.description}</span><span className="tiny subtle">{pct(p.confidence, 0)}</span>
                  </div>
                ))}
              </div>
              <div>
                <h3 style={{ marginBottom: 8 }}>Hỗ trợ / kháng cự</h3>
                {ai.levels.map((l: any, i: number) => (
                  <div key={i} className="row between small" style={{ padding: "5px 0" }}>
                    <Badge tone={l.kind === "support" ? "up" : "down"}>{l.kind === "support" ? "Hỗ trợ" : "Kháng cự"} · {l.strength}</Badge><b className="mono">{vnd(l.price)}</b>
                  </div>
                ))}
              </div>
            </div>
            <h3 style={{ margin: "12px 0 6px" }}>Quan sát chính</h3>
            <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{ai.key_observations.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            {ai.indicators_seen.length > 0 && <><h3 style={{ margin: "12px 0 6px" }}>Chỉ báo trên ảnh</h3><ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{ai.indicators_seen.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></>}
            <div className="small muted" style={{ marginTop: 8 }}><b>Khối lượng:</b> {ai.volume_analysis}</div>
            <h3 style={{ margin: "12px 0 6px" }}>Rủi ro</h3>
            <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{ai.risks.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
          </Card>
          <Card title="Đối chiếu với mô hình định lượng" icon={<Database size={16} />}>
            {res.system ? (
              <div className="col" style={{ gap: 10 }}>
                <Badge lg tone={res.comparison.agreement === "Trái chiều" ? "down" : "up"}>{res.comparison.agreement}</Badge>
                <div className="small muted">{res.comparison.note}</div>
                <div className="row between"><span className="muted">Tín hiệu hệ thống</span><Badge tone={recTone(res.system.signal_code)}>{res.system.signal}</Badge></div>
                <div className="row between"><span className="muted">Điểm kỹ thuật</span><b className="mono">{num(res.system.score, 0)}/100</b></div>
                <div className="row between"><span className="muted">Xu hướng</span><b>{res.system.trend}</b></div>
                <div className="row between"><span className="muted">Giá tại {res.system.as_of}</span><b className="mono">{vnd(res.system.price)}</b></div>
                <div className="row between"><span className="muted">Nguồn dữ liệu</span><SourceBadge source={res.system.source} /></div>
                {ai.last_price_estimate && <div className="row between"><span className="muted">Giá AI đọc được</span><b className={cls("mono", tone(ai.last_price_estimate - res.system.price))}>{vnd(ai.last_price_estimate)}</b></div>}
                <Link className="btn" to={`/stock/${(res.system.ticker ?? (form.ticker || ai.ticker_detected) ?? "").toUpperCase()}`}>Mở phân tích đầy đủ</Link>
              </div>
            ) : <Empty title="Chưa có mã để đối chiếu">Nhập mã cổ phiếu để so sánh với tín hiệu định lượng của hệ thống.</Empty>}
          </Card>
        </div>
      )}
    </div>
  );
}

export default function DataCenter() {
  const [params] = useSearchParams();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) || (params.get("ticker") ? "fin" : "sources"));
  const [ticker, setTicker] = useState((params.get("ticker") || "FPT").toUpperCase());
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dữ liệu & nhập liệu</h1>
          <p>Tự động lấy dữ liệu từ nhiều nguồn; khi không truy cập được, bạn có thể tải Excel/CSV, ảnh hoặc PDF để phân tích sát thực tế.</p>
        </div>
      </div>
      <Tabs value={tab} onChange={setTab} items={[
        { value: "sources", label: "Nguồn tự động", icon: <Wifi size={15} /> },
        { value: "fin", label: "Báo cáo tài chính", icon: <FileSpreadsheet size={15} /> },
        { value: "prices", label: "Lịch sử giá", icon: <CandlestickChart size={15} /> },
        { value: "chart", label: "Ảnh biểu đồ nến", icon: <FileImage size={15} /> },
      ]} />
      {tab === "sources" && <Sources />}
      {tab === "prices" && <Prices ticker={ticker} />}
      {tab === "fin" && <Financials ticker={ticker} setTicker={setTicker} />}
      {tab === "chart" && <ChartReader ticker={(params.get("ticker") ?? "").toUpperCase()} />}
    </>
  );
}
