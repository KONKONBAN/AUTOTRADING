import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";

export type Status = {
  version: string;
  data: { mode: string; source: string; last_date: string; live_ok: boolean; live_provider?: string; needs_manual_input: boolean; message: string; provider_health?: any; providers?: { key: string; name: string }[] };
  ai_enabled: boolean;
  ai_model: string;
  live_trading_allowed: boolean;
  autotrader: { config: any; last_run?: string };
};
export type Stock = { ticker: string; name: string; sector: string; exchange: string; in_vn30: boolean };

// universe: mọi mã niêm yết (ô tìm kiếm); watch: danh mục theo dõi mặc định (bộ lọc, tối ưu danh mục)
const Ctx = createContext<{ status: Status | null; universe: Stock[]; watch: Stock[]; sectors: string[]; refresh: () => void }>({
  status: null, universe: [], watch: [], sectors: [], refresh: () => {},
});
export const useStatus = () => useContext(Ctx);

export function StatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [universe, setUniverse] = useState<Stock[]>([]);
  const [watch, setWatch] = useState<Stock[]>([]);
  const [sectors, setSectors] = useState<string[]>([]);
  const refresh = useCallback(() => {
    api.get<Status>("/api/status").then(setStatus).catch(() => {});
  }, []);
  useEffect(() => {
    refresh();
    api.get("/api/universe").then((u) => {
      // ô tìm kiếm dùng TOÀN BỘ mã niêm yết (nếu tải được), danh mục mặc định xếp trước
      const watch: Stock[] = u.stocks;
      const known = new Set(watch.map((x) => x.ticker));
      const rest: Stock[] = (u.all ?? []).filter((x: any) => !known.has(x.ticker)).map((x: any) => ({ ...x, in_vn30: false }));
      setWatch(watch);
      setUniverse([...watch, ...rest]);
      setSectors(u.sectors);
    }).catch(() => {});
  }, [refresh]);
  return <Ctx.Provider value={{ status, universe, watch, sectors, refresh }}>{children}</Ctx.Provider>;
}
