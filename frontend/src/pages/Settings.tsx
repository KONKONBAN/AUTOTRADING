import { useEffect, useState } from "react";
import { Copy, Globe, KeyRound, LogOut, Monitor, Palette, RefreshCw, Shield, Smartphone, Trash2, UserPlus, Users, Wifi } from "lucide-react";
import qrcode from "qrcode-generator";
import { useAuth } from "../components/AuthGate";
import { Alert, Badge, Card, Field, Loading, Seg, Switch, Tabs, useToast } from "../components/ui";
import { DISCLAIMER } from "../components/Layout";
import { api } from "../lib/api";
import { useTheme } from "../lib/theme";

type Tunnel = { running: boolean; starting: boolean; url: string | null; error: string | null; installed: boolean; log: string[] };
type Info = { lan_urls: string[]; lan_enabled: boolean; tunnel: Tunnel; tunnel_enabled?: boolean; public_url?: string | null; local: boolean };
type Session = { id: string; created_at: number; last_seen_at: number; user_agent: string; ip: string; current: boolean };
type UserRow = { id: number; username: string; display_name: string; role: "admin" | "user"; disabled: boolean; created_at: number; last_login_at: number | null };

const when = (t: number | null) => (t ? new Date(t * 1000).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" }) : "—");
const device = (ua: string) =>
  /iPhone|iPad/.test(ua) ? "iPhone / iPad" : /Android/.test(ua) ? "Điện thoại Android" : /Windows/.test(ua) ? "Máy tính Windows"
    : /Mac OS/.test(ua) ? "Máy Mac" : /Linux/.test(ua) ? "Máy Linux" : "Thiết bị khác";

function QR({ text, size = 168 }: { text: string; size?: number }) {
  const q = qrcode(0, "M");
  q.addData(text);
  q.make();
  return <div className="qr" style={{ width: size, height: size }} dangerouslySetInnerHTML={{ __html: q.createSvgTag({ cellSize: 4, margin: 0, scalable: true }) }} />;
}

function UrlBox({ url }: { url: string }) {
  const toast = useToast();
  return (
    <div className="row wrap" style={{ gap: 18, alignItems: "flex-start" }}>
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

// ------------------------------------------------------------------ Tài khoản của tôi
function MyAccount() {
  const { user, refresh, logout } = useAuth();
  const toast = useToast();
  const [name, setName] = useState(user.display_name);
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const loadSessions = () => api.get<Session[]>("/api/auth/sessions").then(setSessions).catch(() => {});
  useEffect(() => { loadSessions(); }, []);
  const saveName = async () => {
    try { await api.put("/api/auth/profile", { display_name: name }); refresh(); toast("ok", "Đã lưu tên hiển thị."); }
    catch (e: any) { toast("err", e.message); }
  };
  const changePw = async () => {
    if (pw !== pw2) return toast("err", "Hai lần nhập mật khẩu mới không khớp.");
    try {
      await api.post("/api/auth/password", { current_password: cur, new_password: pw });
      setCur(""); setPw(""); setPw2("");
      toast("ok", "Đã đổi mật khẩu - các thiết bị khác đã được đăng xuất.");
      loadSessions();
    } catch (e: any) { toast("err", e.message); }
  };
  const revoke = async (id: string) => {
    await api.del(`/api/auth/sessions/${id}`).catch((e) => toast("err", e.message));
    loadSessions();
  };
  return (
    <div className="grid g2">
      <Card title="Hồ sơ" icon={<Shield size={16} />} actions={<Badge tone={user.role === "admin" ? "brand" : ""}>{user.role === "admin" ? "Quản trị viên" : "Người dùng"}</Badge>}>
        <div className="col" style={{ gap: 12 }}>
          <Field label="Tên đăng nhập"><input className="input" value={user.username} disabled /></Field>
          <Field label="Tên hiển thị"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <div className="row"><button className="btn primary" onClick={saveName} disabled={!name.trim() || name === user.display_name}>Lưu</button>
            <button className="btn ghost" onClick={logout}><LogOut size={15} /> Đăng xuất</button></div>
        </div>
      </Card>
      <Card title="Đổi mật khẩu" icon={<KeyRound size={16} />}>
        <div className="col" style={{ gap: 12 }}>
          <Field label="Mật khẩu hiện tại"><input className="input" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
          <div className="grid g2" style={{ gap: 10 }}>
            <Field label="Mật khẩu mới"><input className="input" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
            <Field label="Nhập lại"><input className="input" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} /></Field>
          </div>
          <div><button className="btn primary" disabled={!cur || !pw} onClick={changePw}>Đổi mật khẩu</button></div>
        </div>
      </Card>
      <Appearance />
      <Card className="span-2" title="Thiết bị đang đăng nhập" icon={<Monitor size={16} />}>
        {!sessions ? <Loading height={80} /> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Thiết bị</th><th>Địa chỉ IP</th><th>Đăng nhập lúc</th><th>Hoạt động gần nhất</th><th /></tr></thead>
            <tbody>{sessions.map((s) => (
              <tr key={s.id}>
                <td>{device(s.user_agent)} {s.current && <Badge tone="up">Thiết bị này</Badge>}</td>
                <td className="mono">{s.ip}</td><td>{when(s.created_at)}</td><td>{when(s.last_seen_at)}</td>
                <td className="num">{!s.current && <button className="btn sm ghost" onClick={() => revoke(s.id)}>Đăng xuất</button>}</td>
              </tr>))}
            </tbody></table></div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ Quản lý người dùng (quản trị)
function Appearance() {
  const { theme, setTheme, size, setSize } = useTheme();
  return (
    <Card className="span-2" title="Giao diện" icon={<Palette size={16} />} hint="Lưu riêng trên thiết bị này">
      <div className="row wrap" style={{ gap: 28 }}>
        <Field label="Chủ đề">
          <Seg value={theme} onChange={setTheme} items={[{ value: "light", label: "Sáng" }, { value: "dark", label: "Tối chuyên nghiệp" }]} />
        </Field>
        <Field label="Cỡ chữ">
          <Seg value={size} onChange={setSize} items={[{ value: "md", label: "Tiêu chuẩn" }, { value: "lg", label: "Chữ lớn" }]} />
        </Field>
      </div>
      <div className="tiny subtle" style={{ marginTop: 14 }}>{DISCLAIMER}</div>
    </Card>
  );
}

function UsersAdmin() {
  const { user: me } = useAuth();
  const toast = useToast();
  const [data, setData] = useState<{ users: UserRow[]; allow_registration: boolean } | null>(null);
  const [form, setForm] = useState({ display_name: "", username: "", password: "", role: "user" });
  const load = () => api.get("/api/admin/users").then(setData).catch((e) => toast("err", e.message));
  useEffect(() => { load(); }, []);
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast("ok", ok); load(); } catch (e: any) { toast("err", e.message); }
  };
  if (!data) return <Loading />;
  return (
    <div className="col" style={{ gap: 16 }}>
      <Card title="Đăng ký tài khoản" icon={<UserPlus size={16} />}>
        <div className="row between wrap">
          <div className="small muted" style={{ maxWidth: 640 }}>Cho phép người khác tự tạo tài khoản ở màn hình đăng nhập.
            Nên <b>tắt</b> khi ứng dụng đang mở ra Internet - thay vào đó hãy tự tạo tài khoản cho người thân bên dưới.</div>
          <Switch on={data.allow_registration} onChange={(v) => act(() => api.put("/api/admin/settings", { allow_registration: v }),
            v ? "Đã bật tự đăng ký" : "Đã tắt tự đăng ký")} />
        </div>
      </Card>
      <Card title="Tạo tài khoản mới" icon={<UserPlus size={16} />}>
        <div className="grid g4" style={{ gap: 10, alignItems: "end" }}>
          <Field label="Họ và tên"><input className="input" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></Field>
          <Field label="Tên đăng nhập"><input className="input" autoCapitalize="none" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase().replace(/\s/g, "") })} /></Field>
          <Field label="Mật khẩu ban đầu"><input className="input" type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
          <Field label="Vai trò"><select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option value="user">Người dùng</option><option value="admin">Quản trị viên</option></select></Field>
        </div>
        <div style={{ marginTop: 12 }}><button className="btn primary" disabled={!form.username || !form.password}
          onClick={() => act(async () => { await api.post("/api/admin/users", form); setForm({ display_name: "", username: "", password: "", role: "user" }); }, "Đã tạo tài khoản")}>
          <UserPlus size={15} /> Tạo tài khoản</button></div>
      </Card>
      <Card title={`Danh sách tài khoản (${data.users.length})`} icon={<Users size={16} />}>
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Người dùng</th><th>Vai trò</th><th>Trạng thái</th><th>Đăng nhập gần nhất</th><th className="num">Thao tác</th></tr></thead>
          <tbody>{data.users.map((u) => (
            <tr key={u.id}>
              <td><b>{u.display_name}</b><div className="tiny subtle">@{u.username}{u.id === me.id ? " · bạn" : ""}</div></td>
              <td><select className="input sm" value={u.role} disabled={u.id === me.id}
                onChange={(e) => act(() => api.patch(`/api/admin/users/${u.id}`, { role: e.target.value }), "Đã đổi vai trò")}>
                <option value="user">Người dùng</option><option value="admin">Quản trị viên</option></select></td>
              <td>{u.disabled ? <Badge tone="down">Đã khóa</Badge> : <Badge tone="up">Hoạt động</Badge>}</td>
              <td>{when(u.last_login_at)}</td>
              <td className="num"><div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                {u.id !== me.id && <button className="btn sm" onClick={() => act(() => api.patch(`/api/admin/users/${u.id}`, { disabled: !u.disabled }), u.disabled ? "Đã mở khóa" : "Đã khóa tài khoản")}>{u.disabled ? "Mở khóa" : "Khóa"}</button>}
                <button className="btn sm" onClick={() => {
                  const p = window.prompt(`Mật khẩu mới cho @${u.username} (≥ 8 ký tự, có chữ và số):`);
                  if (p) act(() => api.patch(`/api/admin/users/${u.id}`, { password: p }), "Đã đặt lại mật khẩu");
                }}>Đặt lại MK</button>
                {u.id !== me.id && <button className="btn sm ghost" title="Xóa tài khoản và toàn bộ dữ liệu" onClick={() => {
                  if (window.confirm(`Xóa @${u.username} và TOÀN BỘ danh mục, lệnh, hội thoại của tài khoản này?`))
                    act(() => api.del(`/api/admin/users/${u.id}`), "Đã xóa tài khoản");
                }}><Trash2 size={14} /></button>}
              </div></td>
            </tr>))}
          </tbody></table></div>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ Mở trên điện thoại
function Phone() {
  const { user } = useAuth();
  const toast = useToast();
  const [info, setInfo] = useState<Info | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.get<Info>("/api/remote/info").then(setInfo).catch(() => {});
  useEffect(() => { load(); }, []);
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
  if (!info) return <Loading />;
  const t = info.tunnel;
  const admin = user.role === "admin";
  const install = (
    <Card title="Cài như ứng dụng trên điện thoại" icon={<Smartphone size={16} />}>
      <ul className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
        <li><b>Android (Chrome)</b>: mở địa chỉ → menu ⋮ → <b>Thêm vào màn hình chính / Cài đặt ứng dụng</b>.</li>
        <li><b>iPhone (Safari)</b>: mở địa chỉ → nút Chia sẻ → <b>Thêm vào MH chính</b>.</li>
        <li><b>Laptop (Chrome / Edge)</b>: mở địa chỉ → biểu tượng <b>Cài đặt ứng dụng</b> ở thanh địa chỉ để có cửa sổ riêng như phần mềm.</li>
      </ul>
    </Card>
  );
  if (info.public_url)
    return (
      <div className="col" style={{ gap: 16 }}>
        <Card title="Địa chỉ web của ứng dụng" icon={<Globe size={16} />} actions={<Badge tone="up">Đang chạy trên Internet</Badge>}>
          <div className="col" style={{ gap: 12 }}>
            <div className="small muted">Mở địa chỉ này trên laptop, máy tính hay điện thoại (4G hoặc Wi-Fi) rồi <b>đăng nhập bằng tài khoản</b>. Có thể quét mã QR bằng camera điện thoại.</div>
            <UrlBox url={info.public_url} />
          </div>
        </Card>
        {install}
      </div>
    );
  return (
    <div className="col" style={{ gap: 16 }}>
      <Alert kind="info" title="Cách hoạt động">
        Máy tính chạy ứng dụng (phải đang bật); điện thoại truy cập cùng Wi-Fi rồi <b>đăng nhập bằng tài khoản</b> như trên máy tính.
        Muốn dùng ở bất cứ đâu mà không cần bật máy tính: đưa ứng dụng lên Internet theo hướng dẫn trong README (mục "Web trên Internet").
      </Alert>
      {info.tunnel_enabled && <Card title="Qua Internet - 4G, ở bất cứ đâu" icon={<Globe size={16} />} actions={t.running ? <Badge tone="up">Đang mở</Badge> : <Badge>Đang tắt</Badge>}>
        <div className="col" style={{ gap: 12 }}>
          <div className="small muted">
            Dùng đường hầm miễn phí của Cloudflare (không cần tài khoản), tạo địa chỉ <b>https</b> trỏ về máy tính này. Lần đầu ứng dụng tự tải
            công cụ <code>cloudflared</code> chính thức (~30 MB). Địa chỉ <b>đổi mỗi lần mở lại</b>.
          </div>
          {t.url && <UrlBox url={t.url} />}
          {t.error && !t.url && <Alert kind={t.running ? "info" : "err"}>{t.error}</Alert>}
          {!admin ? <div className="small subtle">Chỉ quản trị viên bật/tắt được truy cập Internet.</div>
            : !info.local ? <div className="small subtle">Bật/tắt trên chính máy tính chạy ứng dụng.</div> : (
              <div className="row wrap">
                {!t.running
                  ? <button className="btn primary" disabled={busy} onClick={() => tunnel(true)}><Globe size={15} /> {busy ? "Đang mở… (10-30 giây)" : "Mở truy cập qua Internet"}</button>
                  : <button className="btn" disabled={busy} onClick={() => tunnel(false)}>Tắt truy cập Internet</button>}
                <button className="btn ghost" onClick={load}><RefreshCw size={14} /> Làm mới</button>
              </div>
            )}
          {t.log.length > 0 && !t.url && (
            <details><summary className="small subtle">Nhật ký cloudflared</summary>
              <pre className="tiny mono" style={{ whiteSpace: "pre-wrap", maxHeight: 180, overflow: "auto" }}>{t.log.join("\n")}</pre></details>
          )}
        </div>
      </Card>}
      <Card title="Cùng mạng Wi-Fi ở nhà" icon={<Wifi size={16} />} actions={info.lan_enabled ? <Badge tone="up">Đang bật</Badge> : <Badge>Đang tắt</Badge>}>
        <div className="col" style={{ gap: 12 }}>
          {!info.lan_enabled && (
            <div className="small muted">Mặc định ứng dụng chỉ mở cho chính máy tính. Để điện thoại cùng Wi-Fi truy cập: mở file <code>.env</code> trong thư mục
              ứng dụng, thêm dòng <code>HOST=0.0.0.0</code>, lưu lại rồi chạy lại <code>run.bat</code>. Khi Windows hỏi tường lửa, chọn <b>Mạng riêng (Private)</b>.</div>
          )}
          {info.lan_enabled && (info.lan_urls.length ? info.lan_urls.slice(0, 2).map((u) => <UrlBox key={u} url={u} />)
            : <div className="small subtle">Không tìm thấy địa chỉ mạng nội bộ.</div>)}
        </div>
      </Card>
      {install}
    </div>
  );
}

export default function Settings() {
  const { user } = useAuth();
  const [tab, setTab] = useState<"me" | "users" | "phone">("me");
  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="page-head">
        <div>
          <h1>Cài đặt</h1>
          <p>Tài khoản, người dùng và truy cập từ điện thoại.</p>
        </div>
      </div>
      <Tabs value={tab} onChange={setTab} items={[
        { value: "me", label: "Tài khoản của tôi", icon: <Shield size={15} /> },
        ...(user.role === "admin" ? [{ value: "users" as const, label: "Quản lý người dùng", icon: <Users size={15} /> }] : []),
        { value: "phone", label: "Mở trên điện thoại", icon: <Smartphone size={15} /> },
      ]} />
      {tab === "me" && <MyAccount />}
      {tab === "users" && user.role === "admin" && <UsersAdmin />}
      {tab === "phone" && <Phone />}
    </div>
  );
}
