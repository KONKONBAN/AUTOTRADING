import { useEffect, useState } from "react";
import { Copy, Globe, KeyRound, LogOut, RefreshCw, Smartphone, Wifi } from "lucide-react";
import qrcode from "qrcode-generator";
import { api } from "../lib/api";
import { Alert, Badge, Card, Field, Loading, useToast } from "../components/ui";

type Tunnel = { running: boolean; starting: boolean; url: string | null; error: string | null; installed: boolean; log: string[] };
type Info = { lan_urls: string[]; tunnel: Tunnel; password_set: boolean; local: boolean };
type AuthStatus = { local: boolean; password_set: boolean; password_from_env: boolean; authenticated: boolean };

function QR({ text, size = 180 }: { text: string; size?: number }) {
  const q = qrcode(0, "M");
  q.addData(text);
  q.make();
  return (
    <div style={{ background: "#fff", padding: 8, borderRadius: 12, width: size, height: size, flex: "none" }}
      dangerouslySetInnerHTML={{ __html: q.createSvgTag({ cellSize: 4, margin: 0, scalable: true }) }} />
  );
}

function UrlBox({ url }: { url: string }) {
  const toast = useToast();
  return (
    <div className="row wrap" style={{ gap: 16, alignItems: "flex-start" }}>
      <QR text={url} />
      <div className="col" style={{ minWidth: 0, flex: 1 }}>
        <div className="small muted">Quét mã QR bằng camera điện thoại, hoặc mở địa chỉ:</div>
        <a className="mono" href={url} target="_blank" rel="noreferrer" style={{ wordBreak: "break-all", fontSize: 14 }}>{url}</a>
        <div><button className="btn sm" onClick={() => navigator.clipboard?.writeText(url).then(() => toast("ok", "Đã sao chép địa chỉ"))}>
          <Copy size={13} /> Sao chép</button></div>
      </div>
    </div>
  );
}

function PasswordCard({ auth, onChanged }: { auth: AuthStatus; onChanged: () => void }) {
  const toast = useToast();
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (pw.length < 6) return toast("err", "Mật khẩu cần ít nhất 6 ký tự.");
    if (pw !== pw2) return toast("err", "Hai lần nhập mật khẩu không khớp.");
    setBusy(true);
    try {
      await api.post("/api/auth/password", { new_password: pw, current_password: cur || null });
      toast("ok", auth.password_set ? "Đã đổi mật khẩu - các thiết bị khác cần đăng nhập lại." : "Đã đặt mật khẩu.");
      setCur(""); setPw(""); setPw2("");
      onChanged();
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="1. Mật khẩu truy cập từ xa" icon={<KeyRound size={16} />}
      actions={auth.password_set ? <Badge tone="up">Đã đặt</Badge> : <Badge tone="warn">Chưa đặt</Badge>}>
      {auth.password_from_env ? (
        <Alert kind="info">Mật khẩu đang được đặt bằng <code>APP_PASSWORD</code> trong file <code>.env</code> - sửa ở đó rồi khởi động lại ứng dụng.</Alert>
      ) : (
        <div className="col" style={{ gap: 12 }}>
          <div className="small muted">Điện thoại và mọi thiết bị khác phải nhập mật khẩu này. Trên chính máy tính này bạn không cần đăng nhập.
            Hãy dùng mật khẩu mạnh (≥ 10 ký tự, có chữ và số) vì địa chỉ Internet có thể bị người khác dò thấy.</div>
          {!auth.local && auth.password_set && (
            <Field label="Mật khẩu hiện tại"><input className="input" type="password" value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
          )}
          <div className="grid g2" style={{ gap: 10 }}>
            <Field label={auth.password_set ? "Mật khẩu mới" : "Mật khẩu"}><input className="input" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
            <Field label="Nhập lại"><input className="input" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} /></Field>
          </div>
          <div><button className="btn primary" disabled={busy || !pw} onClick={save}>{auth.password_set ? "Đổi mật khẩu" : "Đặt mật khẩu"}</button></div>
        </div>
      )}
    </Card>
  );
}

export default function Settings() {
  const toast = useToast();
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [info, setInfo] = useState<Info | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => {
    api.get<AuthStatus>("/api/auth/status").then(setAuth).catch(() => {});
    api.get<Info>("/api/remote/info").then(setInfo).catch(() => {});
  };
  useEffect(load, []);
  const tunnel = async (start: boolean) => {
    setBusy(true);
    try {
      const t = await api.post<Tunnel>(`/api/remote/tunnel/${start ? "start" : "stop"}`);
      setInfo((i) => (i ? { ...i, tunnel: t } : i));
      if (start && !t.url && t.error) toast("err", t.error);
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy(false);
    }
  };
  const logout = async () => {
    await api.post("/api/auth/logout").catch(() => {});
    window.location.href = "/";
  };
  if (!auth || !info) return <Loading />;
  const t = info.tunnel;
  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="page-head">
        <div>
          <h1>Cài đặt &amp; điện thoại</h1>
          <p>Dùng ứng dụng trên điện thoại: máy tính chạy ứng dụng, điện thoại truy cập qua Wi-Fi hoặc Internet (có mật khẩu bảo vệ).</p>
        </div>
      </div>
      {!auth.local && (
        <Alert kind="info" title="Bạn đang truy cập từ xa">
          Mở/tắt truy cập Internet chỉ làm được trên máy tính chạy ứng dụng.
          <div style={{ marginTop: 8 }}><button className="btn sm" onClick={logout}><LogOut size={13} /> Đăng xuất thiết bị này</button></div>
        </Alert>
      )}
      <PasswordCard auth={auth} onChanged={load} />
      <Card title="2. Mở trên điện thoại qua Internet (4G / mọi nơi)" icon={<Globe size={16} />}
        actions={t.running ? <Badge tone="up">Đang mở</Badge> : <Badge>Đang tắt</Badge>}>
        <div className="col" style={{ gap: 12 }}>
          <div className="small muted">
            Dùng đường hầm miễn phí của Cloudflare (không cần tài khoản): tạo địa chỉ <b>https</b> trỏ về máy tính này.
            Lần đầu ứng dụng tự tải công cụ <code>cloudflared</code> chính thức (~30 MB). Máy tính phải bật và đang chạy ứng dụng;
            địa chỉ <b>đổi mỗi lần mở lại</b> - quét lại mã QR khi cần.
          </div>
          {!info.password_set && <Alert kind="warn">Hãy đặt mật khẩu ở bước 1 trước.</Alert>}
          {t.url && <UrlBox url={t.url} />}
          {t.error && !t.url && <Alert kind={t.running ? "info" : "err"}>{t.error}</Alert>}
          {auth.local && (
            <div className="row wrap">
              {!t.running ? (
                <button className="btn primary" disabled={busy || !info.password_set} onClick={() => tunnel(true)}>
                  <Globe size={15} /> {busy ? "Đang mở… (có thể mất 10-30 giây)" : "Mở truy cập qua Internet"}</button>
              ) : (
                <button className="btn" disabled={busy} onClick={() => tunnel(false)}>Tắt truy cập Internet</button>
              )}
              <button className="btn ghost" onClick={load}><RefreshCw size={14} /> Làm mới</button>
            </div>
          )}
          {t.log.length > 0 && !t.url && (
            <details><summary className="small subtle">Nhật ký cloudflared</summary>
              <pre className="tiny mono" style={{ whiteSpace: "pre-wrap", maxHeight: 180, overflow: "auto" }}>{t.log.join("\n")}</pre></details>
          )}
        </div>
      </Card>
      <Card title="3. Cùng mạng Wi-Fi ở nhà" icon={<Wifi size={16} />}>
        <div className="col" style={{ gap: 12 }}>
          <div className="small muted">
            Chỉ dùng được khi ứng dụng chạy ở chế độ mở cho mạng nội bộ (chạy <code>run.bat</code> và chọn cho phép điện thoại cùng Wi-Fi,
            hoặc đặt <code>HOST=0.0.0.0</code> trong <code>.env</code>). Windows có thể hỏi cho phép qua tường lửa - chọn <b>Mạng riêng (Private)</b>.
          </div>
          {info.lan_urls.length ? info.lan_urls.slice(0, 2).map((u) => <UrlBox key={u} url={u} />)
            : <div className="small subtle">Không tìm thấy địa chỉ mạng nội bộ.</div>}
        </div>
      </Card>
      <Card title="4. Cài như ứng dụng trên điện thoại" icon={<Smartphone size={16} />}>
        <ul className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
          <li><b>Android (Chrome)</b>: mở địa chỉ → menu ⋮ → <b>Thêm vào màn hình chính / Cài đặt ứng dụng</b>.</li>
          <li><b>iPhone (Safari)</b>: mở địa chỉ → nút Chia sẻ → <b>Thêm vào MH chính</b>.</li>
          <li>Địa chỉ Internet đổi mỗi lần mở đường hầm; muốn địa chỉ cố định hãy dùng Tailscale (miễn phí, cài trên cả máy tính và điện thoại)
            rồi mở <code>http://&lt;tên-máy-tính&gt;:8000</code>.</li>
        </ul>
      </Card>
    </div>
  );
}
