import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Bot, BookOpen, Database, Filter, LayoutDashboard, LineChart, Menu, Moon, PiggyBank, RefreshCw, Search, Smartphone, Sun, Wallet, Zap,
  type LucideIcon,
} from "lucide-react";
import { api } from "../lib/api";
import { useStatus } from "../lib/status";
import { useTheme } from "../lib/theme";
import { cls, sourceLabel } from "../lib/format";
import { Badge, TickerLogo, useToast } from "./ui";

type NavItem = { to: string; label: string; icon: LucideIcon; end?: boolean; mobile?: string };
const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Thị trường",
    items: [
      { to: "/", label: "Tổng quan", icon: LayoutDashboard, end: true, mobile: "Tổng quan" },
      { to: "/stock", label: "Phân tích cổ phiếu", icon: LineChart, mobile: "Phân tích" },
      { to: "/screener", label: "Bộ lọc & xếp hạng", icon: Filter },
    ],
  },
  {
    section: "Đầu tư",
    items: [
      { to: "/portfolio", label: "Danh mục & tối ưu", icon: Wallet },
      { to: "/autotrader", label: "Giao dịch tự động", icon: Zap, mobile: "Tự động" },
    ],
  },
  {
    section: "Trợ lý",
    items: [
      { to: "/agent", label: "AI Agent tài sản", icon: Bot, mobile: "AI Agent" },
      { to: "/finance", label: "Tài chính cá nhân", icon: PiggyBank },
      { to: "/knowledge", label: "Kiến thức nền tảng", icon: BookOpen },
    ],
  },
  {
    section: "Dữ liệu & cài đặt",
    items: [
      { to: "/data", label: "Dữ liệu & nhập liệu", icon: Database },
      { to: "/settings", label: "Cài đặt & điện thoại", icon: Smartphone },
    ],
  },
];
const ALL_ITEMS = NAV.flatMap((s) => s.items);

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
        placeholder="Tìm mã cổ phiếu, tên công ty, ngành…  (Ctrl+K)"
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

export default function Layout({ children }: { children: ReactNode }) {
  const { theme, toggle } = useTheme();
  const { status, refresh } = useStatus();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [more, setMore] = useState(false);
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
          <div className="row between">
            <span>Nguồn dữ liệu</span>
            <Badge tone={demo ? "warn" : "up"}><span className={cls("dot", !demo && "pulse")} />{sourceLabel(src)}</Badge>
          </div>
          <div className="tiny subtle" style={{ marginTop: 6 }}>Cập nhật: {status?.data.last_date ?? "—"} · v{status?.version ?? ""}</div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <TickerSearch />
          <div className="grow hide-mobile" />
          {status && (
            <span className="hide-mobile">
              <Badge tone={status.ai_enabled ? "brand" : ""}><Bot size={12} /> {status.ai_enabled ? "AI Agent: bật" : "AI: chế độ cơ bản"}</Badge>
            </span>
          )}
          <button className="btn icon ghost" title="Làm mới dữ liệu" onClick={doRefresh} disabled={busy}>
            <RefreshCw size={17} className={busy ? "spin" : ""} />
          </button>
          <button className="btn icon ghost" title="Đổi giao diện sáng/tối" onClick={toggle}>
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </header>
        <main className="content">{children}</main>
      </div>
      <nav className="mobile-nav">
        {ALL_ITEMS.filter((n) => n.mobile).map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cls(isActive && "active")} onClick={() => setMore(false)}>
            <n.icon size={20} />
            {n.mobile}
          </NavLink>
        ))}
        <a href="#more" className={cls(more && "active")} onClick={(e) => { e.preventDefault(); setMore((m) => !m); }}>
          <Menu size={20} /> Thêm
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
