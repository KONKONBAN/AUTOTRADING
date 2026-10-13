import { Component, createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, UploadCloud, XCircle } from "lucide-react";
import { cls, scoreColor, sourceLabel, tickerColor } from "../lib/format";

/* ------------------------------------------------------------------ data hook */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const run = useCallback(() => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    fn()
      .then((d) => id === seq.current && setData(d))
      .catch((e) => id === seq.current && setError(String(e.message ?? e)))
      .finally(() => id === seq.current && setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    run();
  }, [run]);
  return { data, error, loading, reload: run, setData };
}

/* ------------------------------------------------------------------ toast */
type ToastT = { id: number; kind: "ok" | "err" | "info"; text: string };
const ToastCtx = createContext<(kind: ToastT["kind"], text: string) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastT[]>([]);
  const push = useCallback((kind: ToastT["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, kind, text }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 5000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-wrap">
        {items.map((t) => (
          <div key={t.id} className={cls("toast", t.kind)}>
            {t.kind === "ok" ? <CheckCircle2 size={18} className="up" /> : t.kind === "err" ? <XCircle size={18} className="down" /> : <Info size={18} />}
            <div className="small">{t.text}</div>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/* ------------------------------------------------------------------ primitives */
export function Card({ title, icon, hint, actions, children, className }: {
  title?: ReactNode; icon?: ReactNode; hint?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={cls("card", className)}>
      {(title || actions) && (
        <div className="card-head">
          <div>
            {title && <h3>{icon}{title}</h3>}
            {hint && <div className="hint">{hint}</div>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Kpi({ label, value, sub, icon, valueClass }: {
  label: ReactNode; value: ReactNode; sub?: ReactNode; icon?: ReactNode; valueClass?: string;
}) {
  return (
    <div className="card kpi">
      <div className="row between">
        <span className="kpi-label">{label}</span>
        {icon && <span className="kpi-icon">{icon}</span>}
      </div>
      <div className={cls("kpi-value", valueClass)}>{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

export function Badge({ children, tone, lg }: { children: ReactNode; tone?: string; lg?: boolean }) {
  return <span className={cls("badge", tone, lg && "lg")}>{children}</span>;
}

export function Spinner() {
  return <div className="spinner" />;
}

export function Loading({ text = "Đang tải dữ liệu…", height = 160 }: { text?: string; height?: number }) {
  return (
    <div className="empty" style={{ minHeight: height, justifyContent: "center" }}>
      <Spinner />
      <span className="small">{text}</span>
    </div>
  );
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: ReactNode; children?: ReactNode }) {
  return (
    <div className="empty">
      {icon}
      <div className="bold" style={{ color: "var(--text-2)" }}>{title}</div>
      {children && <div className="small">{children}</div>}
    </div>
  );
}

export function Alert({ kind = "info", children, title }: { kind?: "info" | "warn" | "ok" | "err"; title?: ReactNode; children?: ReactNode }) {
  const Icon = kind === "warn" ? AlertTriangle : kind === "ok" ? CheckCircle2 : kind === "err" ? XCircle : Info;
  const color = kind === "warn" ? "var(--warn)" : kind === "ok" ? "var(--up)" : kind === "err" ? "var(--down)" : "var(--info)";
  return (
    <div className={cls("alert", kind)}>
      <Icon size={18} color={color} />
      <div className="col" style={{ gap: 4 }}>
        {title && <div className="bold">{title}</div>}
        {children && <div className="muted">{children}</div>}
      </div>
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <Alert kind="err" title="Không tải được dữ liệu">
      {error} {onRetry && <button className="btn sm" style={{ marginLeft: 8 }} onClick={onRetry}>Thử lại</button>}
    </Alert>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode; icon?: ReactNode }[];
}) {
  return (
    <div className="tabs">
      {items.map((it) => (
        <button key={it.value} className={cls(value === it.value && "on")} onClick={() => onChange(it.value)}>
          {it.icon}{it.label}
        </button>
      ))}
    </div>
  );
}

export function Seg<T extends string>({ value, onChange, items }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode }[];
}) {
  return (
    <div className="seg">
      {items.map((it) => (
        <button key={it.value} className={cls(value === it.value && "on")} onClick={() => onChange(it.value)}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, help, children }: { label: ReactNode; help?: ReactNode; children: ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {help && <span className="help">{help}</span>}
    </div>
  );
}

export function Switch({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return <button type="button" className={cls("switch", on && "on")} onClick={() => onChange(!on)} aria-pressed={on} />;
}

/* ------------------------------------------------------------------ score */
export function ScoreRing({ score, size = 128, label = "Điểm tổng hợp" }: { score: number; size?: number; label?: string }) {
  const stroke = 10;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const color = scoreColor(score);
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--surface-3)" strokeWidth={stroke} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - Math.max(0, Math.min(100, score)) / 100)}
          style={{ transition: "stroke-dashoffset .8s ease" }} />
      </svg>
      <div className="ring-label">
        <div className="ring-value" style={{ color }}>{Math.round(score)}</div>
        <div className="ring-sub">{label}</div>
      </div>
    </div>
  );
}

export function ScoreBar({ score, width }: { score: number; width?: number }) {
  return (
    <div className="scorebar" style={{ width }}>
      <div className="bar"><i style={{ width: `${Math.max(0, Math.min(100, score))}%`, background: scoreColor(score) }} /></div>
      <span className="mono small bold" style={{ color: scoreColor(score), minWidth: 26, textAlign: "right" }}>{Math.round(score)}</span>
    </div>
  );
}

export function PartBar({ label, value }: { label: string; value: number | null }) {
  if (value == null)
    return (
      <div className="part" title="Chưa có dữ liệu (thiếu BCTC thật)">
        <span className="muted">{label}</span>
        <div className="bar" />
        <span className="mono subtle right">—</span>
      </div>
    );
  return (
    <div className="part">
      <span className="muted">{label}</span>
      <div className="bar"><i style={{ width: `${value}%`, background: scoreColor(value) }} /></div>
      <span className="mono bold right" style={{ color: scoreColor(value) }}>{Math.round(value)}</span>
    </div>
  );
}

/** Lỗi hiển thị ở một trang không làm trắng toàn bộ ứng dụng. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error) {
    console.error("Lỗi giao diện:", error);
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card" style={{ maxWidth: 640, margin: "40px auto" }}>
        <Alert kind="err" title="Trang này gặp lỗi hiển thị">
          {this.state.error.message || String(this.state.error)}
        </Alert>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn primary" onClick={() => this.setState({ error: null })}>Thử lại</button>
          <a className="btn ghost" href="/">Về trang Tổng quan</a>
        </div>
      </div>
    );
  }
}

/* ------------------------------------------------------------------ ticker */
export function TickerLogo({ ticker, size = 32 }: { ticker: string; size?: number }) {
  return (
    <span className="ticker-logo" style={{ background: tickerColor(ticker), width: size, height: size }}>
      {ticker.slice(0, 3)}
    </span>
  );
}

export function TickerCell({ ticker, name }: { ticker: string; name?: string }) {
  return (
    <div className="ticker-cell">
      <TickerLogo ticker={ticker} />
      <div style={{ minWidth: 0 }}>
        <div className="ticker-name">{ticker}</div>
        {name && <div className="ticker-sub">{name}</div>}
      </div>
    </div>
  );
}

export function SourceBadge({ source }: { source?: string }) {
  const demo = !source || source.includes("demo") || source === "none";
  return (
    <Badge tone={demo ? "warn" : source?.includes("manual") || source === "imported" ? "info" : "up"}>
      <span className="dot" /> {sourceLabel(source)}
    </Badge>
  );
}

/* ------------------------------------------------------------------ file drop */
export function FileDrop({ accept, multiple, onFiles, title, hint, icon }: {
  accept?: string; multiple?: boolean; onFiles: (files: File[]) => void; title: ReactNode; hint?: ReactNode; icon?: ReactNode;
}) {
  const [drag, setDrag] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div
      className={cls("dropzone", drag && "drag")}
      onClick={() => ref.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const fs = Array.from(e.dataTransfer.files);
        if (fs.length) onFiles(multiple ? fs : fs.slice(0, 1));
      }}
    >
      <div className="dz-icon">{icon ?? <UploadCloud size={22} />}</div>
      <div className="bold">{title}</div>
      {hint && <div className="small subtle">{hint}</div>}
      <input ref={ref} type="file" hidden accept={accept} multiple={multiple}
        onChange={(e) => { const fs = Array.from(e.target.files ?? []); if (fs.length) onFiles(fs); e.target.value = ""; }} />
    </div>
  );
}
