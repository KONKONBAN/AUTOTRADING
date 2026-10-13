import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowLeftRight, Bot, BookOpen, Database, Filter, LayoutDashboard, LineChart, LogOut, Menu, Moon, PiggyBank, RefreshCw, Search,
  Settings as SettingsIcon, Sun, Wallet, Zap, type LucideIcon,
} from "lucide-react";
import { api } from "../lib/api";
import { useStatus } from "../lib/status";
import { useTheme } from "../lib/theme";
import { cls, sourceLabel } from "../lib/format";
import { useAuth } from "./AuthGate";
import { useQuickTrade } from "./QuickTrade";
import { Badge, ErrorBoundary, TickerLogo, useToast } from "./ui";

export const DISCLAIMER = "AutoTrading VN là công cụ độc lập, không liên kết với bất kỳ ngân hàng hay công ty chứng khoán nào. "
  + "Lệnh được khớp trên tài khoản giao dịch giấy (giả lập); thông tin chỉ mang tính tham khảo, không phải khuyến nghị đầu tư.";

type NavItem = { to: string; label: string; icon: LucideIcon; end?: boolean; mobile?: string };
const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Thị trường",
    items: [
      { to: "/", label: "Tổng quan", icon: LayoutDashboard, end: true, mobile: "Trang chủ" },
      { to: "/stock", label: "Phân tích cổ phiếu", icon: LineChart, mobile: "Phân tích" },
      { to: "/screener", label: "Bộ lọc & xếp hạng", icon: Filter },
    ],
  },
  {
    section: "Đầu tư",
    items: [
      { to: "/portfolio", label: "Danh mục & tối ưu", icon: Wallet },
      { to: "/autotrader", label: "Giao dịch tự động", icon: Zap },
    ],
  },
  {
    section: "Trợ lý",
    items: [
      { to: "/agent", label: "AI Agent tài sản", icon: Bot, mobile: "Trợ lý AI" },
      { to: "/finance", label: "Tài chính cá nhân", icon: PiggyBank },
      { to: "/knowledge", label: "Kiến thức nền tảng", icon: BookOpen },
    ],
  },
  {
    section: "Dữ liệu & cài đặt",
    items: [
      { to: "/data", label: "Dữ liệu & nhập liệu", icon: Database },
      { to: "/settings", label: "Cài đặt & tài khoản", icon: SettingsIcon },
    ],
  },
];
const ALL_ITEMS = NAV.flatMap((s) => s.items);
const MOBILE = ALL_ITEMS.filter((n) => n.mobile);

function TickerSearch() {
  const { universe } = useStatus();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const ref = useRef<HTMLInputElement>(null);
  const results = useMemo(() => {
    const s = q.trim().toUpperCase();
    if (!s) return universe.slice(0, 8);
    // khớp chính xác mã trước, rồi mã bắt đầu bằng chuỗi tìm, rồi các kết quả khác (tránh FPT → FRT)
    const rank = (u: { ticker: string }) => (u.ticker === s ? 0 : u.ticker.startsWith(s) ? 1 : u.ticker.includes(s) ? 2 : 3);
    return universe
      .filter((u) => u.ticker.includes(s) || u.name.toUpperCase().includes(s) || u.sector.toUpperCase().includes(s))
      .sort((a, b) => rank(a) - rank(b))
      .slice(0, 10);
  }, [q, universe]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const go = (t: string) => {
    nav(`/stock/${t}`);
    setQ("");
    setOpen(false);
    ref.current?.blur();
  };
  return (
    <div className="search">
      <Search size={17} />
      <input
        ref={ref}
        className="input"
        placeholder={window.innerWidth < 920 ? "Tìm mã cổ phiếu…" : "Tìm mã cổ phiếu, công ty, ngành…  (Ctrl+K)"}
        value={q}
        onChange={(e) => { setQ(e.target.value); setIdx(0); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setIdx((i) => Math.min(i + 1, results.length - 1));
          if (e.key === "ArrowUp") setIdx((i) => Math.max(i - 1, 0));
          if (e.key === "Enter") {
            const t = results[idx]?.ticker ?? q.trim().toUpperCase();
            if (t) go(t);
          }
        }}
      />
      {open && results.length > 0 && (
        <div className="search-pop">
          {results.map((r, i) => (
            <div key={r.ticker} className={cls("search-item", i === idx && "on")} onMouseDown={() => go(r.ticker)}>
              <TickerLogo ticker={r.ticker} size={28} />
              <div className="grow">
                <div className="bold">{r.ticker} <span className="subtle small">· {r.exchange}</span></div>
                <div className="tiny subtle" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.name}</div>
              </div>
              <Badge>{r.sector}</Badge>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Avatar({ name, size = 34 }: { name: string; size?: number }) {
  const parts = name.trim().split(/\s+/);
  const initials = ((parts.length > 1 ? parts[parts.length - 2][0] : "") + (parts[parts.length - 1]?.[0] ?? "?")).toUpperCase();
  return <span className="avatar-chip" style={{ width: size, height: size, fontSize: size * 0.38 }}>{initials}</span>;
}

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const { theme, toggle } = useTheme();
  const { status, refresh } = useStatus();
  const toast = useToast();
  const quickTrade = useQuickTrade();
  const [busy, setBusy] = useState(false);
  const [more, setMore] = useState(false);
  useEffect(() => setMore(false), [location.pathname]);
  const src = status?.data.source;
  const demo = src === "demo";
  const doRefresh = async () => {
    setBusy(true);
    try {
      await api.post("/api/data/refresh");
      refresh();
      toast("ok", "Đã làm mới dữ liệu - đang tải lại số liệu mới nhất.");
      setTimeout(() => window.location.reload(), 400);
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <img src="/icon.svg" alt="" />
          <div>
            <div className="brand-name">AutoTrading <span>VN</span></div>
            <div className="brand-sub">Quản trị tài sản thông minh</div>
          </div>
        </div>
        <button className="btn primary block" style={{ margin: "0 2px 6px", width: "auto" }} onClick={() => quickTrade()}>
          <ArrowLeftRight size={16} /> Đặt lệnh nhanh
        </button>
        {NAV.map((s) => (
          <div key={s.section}>
            <div className="nav-section">{s.section}</div>
            {s.items.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cls("nav-link", isActive && "active")}>
                <n.icon size={18} /> {n.label}
                {n.to === "/agent" && status && <span className="badge" style={{ marginLeft: "auto" }}>{status.ai_enabled ? "AI" : "Cơ bản"}</span>}
              </NavLink>
            ))}
          </div>
        ))}
        <div className="sidebar-foot">
          <div className="user-card">
            <button className="user-link" onClick={() => nav("/settings")} title="Cài đặt tài khoản">
              <Avatar name={user.display_name} />
              <span className="grow" style={{ minWidth: 0 }}>
                <b className="ellipsis">{user.display_name}</b>
                <span className="tiny subtle">{user.role === "admin" ? "Quản trị viên" : "Nhà đầu tư"} · @{user.username}</span>
              </span>
            </button>
            <button className="btn icon ghost sm" title="Đăng xuất" onClick={logout}><LogOut size={15} /></button>
          </div>
          <div className="row between" style={{ marginTop: 10 }}>
            <span>Nguồn dữ liệu</span>
            <Badge tone={demo || src === "none" ? "warn" : "up"}><span className={cls("dot", !demo && "pulse")} />{sourceLabel(src)}</Badge>
          </div>
          <div className="tiny subtle" style={{ marginTop: 6 }}>Phiên gần nhất: {status?.data.last_date ?? "—"} · v{status?.version ?? ""}</div>
          <div className="tiny subtle" style={{ marginTop: 8, lineHeight: 1.45 }} title={DISCLAIMER}>Công cụ độc lập · giao dịch giả lập · không phải khuyến nghị đầu tư.</div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <NavLink to="/" className="show-mobile" title="Tổng quan"><img src="/icon.svg" alt="AutoTrading VN" width={32} height={32} style={{ borderRadius: 9 }} /></NavLink>
          <TickerSearch />
          <div className="grow hide-mobile" />
          {status && (
            <span className="status-chip hide-mobile" title={status.data.message}>
              <span className={cls("dot", !demo && src !== "none" && "pulse")} style={{ color: demo || src === "none" ? "var(--warn)" : "var(--up)" }} />
              Dữ liệu: <b>{sourceLabel(src)}</b> · {status.data.last_date ?? "—"}
            </span>
          )}
          {status && (
            <span className="status-chip hide-mobile" title={status.ai_enabled ? `Mô hình: ${status.ai_model}` : "Chưa cấu hình khóa AI - dùng chế độ cơ bản"}>
              <Bot size={14} style={{ color: status.ai_enabled ? "var(--brand)" : "var(--text-3)" }} /> {status.ai_enabled ? "AI: bật" : "AI: cơ bản"}
            </span>
          )}
          <button className="btn icon ghost" title="Làm mới dữ liệu" onClick={doRefresh} disabled={busy}>
            <RefreshCw size={17} className={busy ? "spin" : ""} />
          </button>
          <button className="btn icon ghost" title="Đổi giao diện sáng/tối" onClick={toggle}>
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <button className="show-mobile avatar-btn" title="Tài khoản" onClick={() => nav("/settings")}><Avatar name={user.display_name} size={32} /></button>
        </header>
        <main className="content"><ErrorBoundary key={location.pathname}>{children}</ErrorBoundary></main>
      </div>
      <nav className="mobile-nav" aria-label="Điều hướng chính">
        {MOBILE.slice(0, 2).map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cls(isActive && "active")}>
            <n.icon size={21} />
            {n.mobile}
          </NavLink>
        ))}
        <button className="center-action" onClick={() => { setMore(false); quickTrade(); }}>
          <span className="ca-btn"><ArrowLeftRight size={22} /></span>
          Đặt lệnh
        </button>
        {MOBILE.slice(2).map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cls(isActive && "active")}>
            <n.icon size={21} />
            {n.mobile}
          </NavLink>
        ))}
        <a href="#more" className={cls(more && "active")} onClick={(e) => { e.preventDefault(); setMore((m) => !m); }}>
          <Menu size={21} /> Thêm
        </a>
      </nav>
      {more && (
        <div className="mobile-more" onClick={() => setMore(false)}>
          <div className="card" onClick={(e) => e.stopPropagation()}>
            {ALL_ITEMS.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cls("nav-link", isActive && "active")} onClick={() => setMore(false)}>
                <n.icon size={18} /> {n.label}
              </NavLink>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
