import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";

export type Status = {
  version: string;
  data: { mode: string; source: string; last_date: string; live_ok: boolean; live_provider?: string; needs_manual_input: boolean; message: string; provider_health?: any };
  ai_enabled: boolean;
  ai_model: string;
  live_trading_allowed: boolean;
  autotrader: { config: any; last_run?: string };
};
export type Stock = { ticker: string; name: string; sector: string; exchange: string; in_vn30: boolean };

const Ctx = createContext<{ status: Status | null; universe: Stock[]; sectors: string[]; refresh: () => void }>({
  status: null, universe: [], sectors: [], refresh: () => {},
});
export const useStatus = () => useContext(Ctx);

export function StatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [universe, setUniverse] = useState<Stock[]>([]);
  const [sectors, setSectors] = useState<string[]>([]);
  const refresh = useCallback(() => {
    api.get<Status>("/api/status").then(setStatus).catch(() => {});
  }, []);
  useEffect(() => {
    refresh();
    api.get("/api/universe").then((u) => { setUniverse(u.stocks); setSectors(u.sectors); }).catch(() => {});
  }, [refresh]);
  return <Ctx.Provider value={{ status, universe, sectors, refresh }}>{children}</Ctx.Provider>;
}
