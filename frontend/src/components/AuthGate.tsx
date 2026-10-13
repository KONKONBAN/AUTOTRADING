import { createContext, useContext, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { BarChart3, Bot, Lock, LogIn, ShieldCheck, UserPlus, Wallet } from "lucide-react";
import { api } from "../lib/api";
import { Alert, Loading } from "./ui";

export type User = { id: number; username: string; display_name: string; role: "admin" | "user" };
type AuthStatus = {
  setup_required: boolean; registration_open: boolean; local: boolean; setup_code_enabled?: boolean; hosted?: boolean; user: User | null;
};

const Ctx = createContext<{ user: User; refresh: () => void; logout: () => Promise<void> } | null>(null);
export const useAuth = () => {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth ngoài AuthGate");
  return v;
};

/** Mọi người dùng (kể cả trên máy tính chạy ứng dụng) đều đăng nhập bằng tài khoản riêng. */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [st, setSt] = useState<AuthStatus | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const check = () =>
    api.get<AuthStatus>("/api/auth/status").then((s) => { setSt(s); setFailed(null); })
      .catch((e) => setFailed(e.message));
  useEffect(() => {
    check();
    const onAuth = () => check();
    window.addEventListener("auth-required", onAuth);
    return () => window.removeEventListener("auth-required", onAuth);
  }, []);
  const logout = async () => {
    await api.post("/api/auth/logout").catch(() => {});
    window.location.href = "/";
  };
  if (failed)
    return (
      <AuthShell>
        <Alert kind="err" title="Không kết nối được máy chủ">{failed} - kiểm tra kết nối Internet, hoặc máy tính chạy ứng dụng còn bật không.</Alert>
        <button className="btn primary block" onClick={check}>Thử lại</button>
      </AuthShell>
    );
  if (!st) return <Loading text="Đang kết nối…" height={320} />;
  if (st.user) return <Ctx.Provider value={{ user: st.user, refresh: check, logout }}>{children}</Ctx.Provider>;
  if (st.setup_required) return <Setup local={st.local} codeEnabled={!!st.setup_code_enabled} onDone={check} />;
  return <Login registrationOpen={st.registration_open} onDone={check} />;
}

export function AuthShell({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="auth-page">
      <section className="auth-hero">
        <div className="auth-brand"><img src="/icon.svg" alt="" /><span>AutoTrading <b>VN</b></span></div>
        <h1>Quản lý tài sản và đầu tư chứng khoán có kỷ luật, dựa trên dữ liệu.</h1>
        <ul>
          <li><BarChart3 size={18} /> Phân tích kỹ thuật, cơ bản, định giá và rủi ro cho từng mã</li>
          <li><Wallet size={18} /> Danh mục, kế hoạch giao dịch và Auto-Trader trên tài khoản giấy</li>
          <li><Bot size={18} /> AI Agent quản trị tài sản và tài chính cá nhân</li>
          <li><ShieldCheck size={18} /> Dữ liệu của mỗi tài khoản được tách riêng và bảo vệ bằng mật khẩu</li>
        </ul>
        <p className="auth-note">
          Công cụ độc lập, không liên kết với bất kỳ ngân hàng hay công ty chứng khoán nào. Lệnh khớp trên tài khoản giao dịch giấy (giả lập);
          thông tin chỉ mang tính tham khảo, không phải lời khuyên đầu tư.
        </p>
      </section>
      <section className="auth-panel">
        <div className={wide ? "auth-card wide" : "auth-card"}>{children}</div>
      </section>
    </div>
  );
}

function useSubmit(fn: () => Promise<void>) {
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (ex: any) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };
  return { err, busy, run };
}

function Login({ registrationOpen, onDone }: { registrationOpen: boolean; onDone: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [pw, setPw] = useState("");
  const [remember, setRemember] = useState(true);
  const { err, busy, run } = useSubmit(async () => {
    await api.post("/api/auth/login", { username, password: pw, remember });
    onDone();
  });
  if (mode === "register") return <Register onDone={onDone} onBack={() => setMode("login")} />;
  return (
    <AuthShell>
      <form className="col" style={{ gap: 14 }} onSubmit={run}>
        <div>
          <h2>Đăng nhập</h2>
          <p className="muted small">Chào mừng trở lại! Đăng nhập để xem danh mục và phân tích của bạn.</p>
        </div>
        <label className="field"><span>Tên đăng nhập</span>
          <input className="input" autoFocus autoComplete="username" autoCapitalize="none" value={username}
            onChange={(e) => setUsername(e.target.value)} /></label>
        <label className="field"><span>Mật khẩu</span>
          <input className="input" type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} /></label>
        <label className="check"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> Ghi nhớ đăng nhập 30 ngày trên thiết bị này</label>
        {err && <Alert kind="err">{err}</Alert>}
        <button className="btn primary block lg" type="submit" disabled={busy || !username || !pw}><LogIn size={16} /> Đăng nhập</button>
        {registrationOpen ? (
          <button type="button" className="btn ghost block" onClick={() => setMode("register")}><UserPlus size={15} /> Chưa có tài khoản? Đăng ký</button>
        ) : (
          <p className="tiny subtle center">Chưa có tài khoản? Liên hệ quản trị viên của ứng dụng để được cấp.</p>
        )}
      </form>
    </AuthShell>
  );
}

function AccountFields({ v, set }: { v: { name: string; username: string; pw: string; pw2: string }; set: (k: string, x: string) => void }) {
  return (
    <>
      <label className="field"><span>Họ và tên</span>
        <input className="input" autoComplete="name" value={v.name} onChange={(e) => set("name", e.target.value)} /></label>
      <label className="field"><span>Tên đăng nhập</span>
        <input className="input" autoComplete="username" autoCapitalize="none" placeholder="vd: nguyenvana" value={v.username}
          onChange={(e) => set("username", e.target.value.toLowerCase().replace(/\s/g, ""))} />
        <small className="subtle">3-32 ký tự: chữ thường không dấu, số, dấu . _ -</small></label>
      <div className="grid g2" style={{ gap: 10 }}>
        <label className="field"><span>Mật khẩu</span>
          <input className="input" type="password" autoComplete="new-password" value={v.pw} onChange={(e) => set("pw", e.target.value)} /></label>
        <label className="field"><span>Nhập lại mật khẩu</span>
          <input className="input" type="password" autoComplete="new-password" value={v.pw2} onChange={(e) => set("pw2", e.target.value)} /></label>
      </div>
      <small className="subtle">Ít nhất 8 ký tự, có cả chữ và số.</small>
    </>
  );
}

function useAccountForm() {
  const [v, setV] = useState({ name: "", username: "", pw: "", pw2: "" });
  const set = (k: string, x: string) => setV((o) => ({ ...o, [k]: x }));
  const check = () => {
    if (v.pw !== v.pw2) throw new Error("Hai lần nhập mật khẩu không khớp.");
  };
  return { v, set, check };
}

function Setup({ local, codeEnabled, onDone }: { local: boolean; codeEnabled: boolean; onDone: () => void }) {
  const f = useAccountForm();
  const [code, setCode] = useState("");
  const { err, busy, run } = useSubmit(async () => {
    f.check();
    await api.post("/api/auth/setup", { username: f.v.username, password: f.v.pw, display_name: f.v.name, setup_code: local ? undefined : code });
    onDone();
  });
  if (!local && !codeEnabled)
    return (
      <AuthShell>
        <Alert kind="warn" title="Ứng dụng chưa được thiết lập">
          Tài khoản quản trị đầu tiên chỉ tạo được trên <b>chính máy tính chạy ứng dụng</b> (mở http://127.0.0.1:8000 trên máy đó),
          hoặc với <b>mã thiết lập</b> (biến <code>SETUP_CODE</code>) khi chạy trên máy chủ Internet.
        </Alert>
      </AuthShell>
    );
  return (
    <AuthShell wide>
      <form className="col" style={{ gap: 14 }} onSubmit={run}>
        <div>
          <span className="eyebrow"><Lock size={13} /> Thiết lập lần đầu</span>
          <h2>Tạo tài khoản quản trị</h2>
          <p className="muted small">Tài khoản này quản lý ứng dụng: tạo tài khoản cho người khác, bật truy cập từ điện thoại.
            Dữ liệu bạn đã dùng trước đây (nếu có) sẽ được chuyển vào tài khoản này.</p>
        </div>
        {!local && (
          <label className="field"><span>Mã thiết lập</span>
            <input className="input" type="password" autoComplete="off" value={code} onChange={(e) => setCode(e.target.value)} />
            <small className="subtle">Mã bạn đã đặt ở biến SETUP_CODE khi tạo máy chủ (chỉ dùng một lần cho tài khoản đầu tiên).</small></label>
        )}
        <AccountFields v={f.v} set={f.set} />
        {err && <Alert kind="err">{err}</Alert>}
        <button className="btn primary block lg" type="submit" disabled={busy || !f.v.username || !f.v.pw || (!local && !code)}>Tạo tài khoản &amp; bắt đầu</button>
      </form>
    </AuthShell>
  );
}

function Register({ onDone, onBack }: { onDone: () => void; onBack: () => void }) {
  const f = useAccountForm();
  const { err, busy, run } = useSubmit(async () => {
    f.check();
    await api.post("/api/auth/register", { username: f.v.username, password: f.v.pw, display_name: f.v.name });
    onDone();
  });
  return (
    <AuthShell wide>
      <form className="col" style={{ gap: 14 }} onSubmit={run}>
        <div>
          <h2>Tạo tài khoản</h2>
          <p className="muted small">Mỗi tài khoản có danh mục, lệnh, Auto-Trader và lịch sử trò chuyện AI riêng.</p>
        </div>
        <AccountFields v={f.v} set={f.set} />
        {err && <Alert kind="err">{err}</Alert>}
        <button className="btn primary block lg" type="submit" disabled={busy || !f.v.username || !f.v.pw}><UserPlus size={16} /> Đăng ký</button>
        <button type="button" className="btn ghost block" onClick={onBack}>Đã có tài khoản? Đăng nhập</button>
      </form>
    </AuthShell>
  );
}
