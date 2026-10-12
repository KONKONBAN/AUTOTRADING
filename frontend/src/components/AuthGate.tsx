import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Lock, LogIn } from "lucide-react";
import { api } from "../lib/api";
import { Alert, Loading } from "./ui";

type AuthStatus = { local: boolean; password_set: boolean; password_from_env: boolean; authenticated: boolean };

/** Trên máy tính chạy ứng dụng: vào thẳng. Từ điện thoại / Internet: phải đăng nhập bằng mật khẩu. */
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
  if (failed) return <Screen><Alert kind="err" title="Không kết nối được máy chủ">{failed} - kiểm tra máy tính chạy ứng dụng còn bật không.</Alert>
    <button className="btn primary" onClick={check}>Thử lại</button></Screen>;
  if (!st) return <Loading text="Đang kết nối…" height={320} />;
  if (st.authenticated) return <>{children}</>;
  return <Login status={st} onDone={check} />;
}

function Screen({ children }: { children: ReactNode }) {
  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 16, background: "var(--bg)" }}>
      <div className="card col" style={{ width: "100%", maxWidth: 380, gap: 16 }}>
        <div className="row" style={{ gap: 10 }}>
          <img src="/icon.svg" alt="" width={36} height={36} />
          <div><b style={{ fontSize: 17 }}>AutoTrading VN</b><div className="small muted">Quản trị tài sản thông minh</div></div>
        </div>
        {children}
      </div>
    </div>
  );
}

function Login({ status, onDone }: { status: AuthStatus; onDone: () => void }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!pw) return;
    setBusy(true);
    setErr(null);
    try {
      await api.post("/api/auth/login", { password: pw });
      onDone();
    } catch (ex: any) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };
  if (!status.password_set)
    return (
      <Screen>
        <Alert kind="warn" title="Chưa đặt mật khẩu truy cập từ xa">
          Để bảo vệ dữ liệu đầu tư, ứng dụng chỉ cho truy cập từ điện thoại sau khi đặt mật khẩu.
          Trên <b>máy tính đang chạy ứng dụng</b>, mở <b>Cài đặt &amp; điện thoại</b> → đặt mật khẩu, rồi tải lại trang này.
        </Alert>
        <button className="btn" onClick={onDone}>Tải lại</button>
      </Screen>
    );
  return (
    <Screen>
      <form className="col" style={{ gap: 12 }} onSubmit={submit}>
        <div className="row" style={{ gap: 8 }}><Lock size={16} /><b>Đăng nhập để tiếp tục</b></div>
        <input className="input" type="password" autoFocus autoComplete="current-password" placeholder="Mật khẩu"
          value={pw} onChange={(e) => setPw(e.target.value)} />
        {err && <Alert kind="err">{err}</Alert>}
        <button className="btn primary" type="submit" disabled={busy || !pw}><LogIn size={15} /> Đăng nhập</button>
        <div className="tiny subtle">Phiên đăng nhập được ghi nhớ 30 ngày trên thiết bị này.</div>
      </form>
    </Screen>
  );
}
