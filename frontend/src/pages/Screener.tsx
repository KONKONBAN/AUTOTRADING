import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowDown, ArrowUp, Filter, Search } from "lucide-react";
import { api } from "../lib/api";
import { useStatus } from "../lib/status";
import { cls, num, pct, recTone, tone, vnd } from "../lib/format";
import { Badge, Card, ErrorBox, Loading, ScoreBar, SourceBadge, TickerCell, useAsync } from "../components/ui";

type Key = "score" | "ticker" | "price" | "change_pct" | "roe" | "pe" | "pb" | "upside" | "beta" | "perf_20d" | "technical" | "quality" | "valuation";

export default function Screener() {
  const { sectors } = useStatus();
  const nav = useNavigate();
  const [sector, setSector] = useState("");
  const [q, setQ] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [rec, setRec] = useState("");
  const [sort, setSort] = useState<{ key: Key; dir: 1 | -1 }>({ key: "score", dir: -1 });
  const res = useAsync(() => api.get(`/api/screener${sector ? `?sector=${encodeURIComponent(sector)}` : ""}`), [sector]);

  const rows = useMemo(() => {
    const list = (res.data?.results ?? []).filter((r: any) =>
      r.score >= minScore && (!rec || r.code === rec || (rec === "sell" && r.code === "reduce")) && (!q || r.ticker.includes(q.toUpperCase()) || r.name.toUpperCase().includes(q.toUpperCase())));
    const val = (r: any) => (["technical", "quality", "valuation"].includes(sort.key) ? r.parts[sort.key] : r[sort.key]);
    return [...list].sort((a, b) => {
      const x = val(a), y = val(b);
      if (typeof x === "string") return x.localeCompare(y) * sort.dir;
      return ((x ?? -1e9) - (y ?? -1e9)) * sort.dir;
    });
  }, [res.data, minScore, rec, q, sort]);

  const Th = ({ k, children, numeric }: { k: Key; children: React.ReactNode; numeric?: boolean }) => (
    <th className={cls("sortable", numeric && "num")} onClick={() => setSort((s) => ({ key: k, dir: s.key === k ? (-s.dir as 1 | -1) : -1 }))}>
      {children} {sort.key === k && (sort.dir < 0 ? <ArrowDown size={11} /> : <ArrowUp size={11} />)}
    </th>
  );
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    (res.data?.results ?? []).forEach((r: any) => (c[r.code] = (c[r.code] ?? 0) + 1));
    return c;
  }, [res.data]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Bộ lọc & xếp hạng cổ phiếu</h1>
          <p>Chấm điểm toàn bộ danh sách theo dõi bằng phân tích kỹ thuật, chất lượng cơ bản, định giá và rủi ro.</p>
        </div>
        {res.data && <Badge lg tone={res.data.market.recommended_exposure >= 0.5 ? "up" : "warn"}>Thị trường: {res.data.market.regime}</Badge>}
      </div>

      <div className="grid g4">
        {[["buy", "MUA"], ["accumulate", "TÍCH LŨY"], ["hold", "NẮM GIỮ / THEO DÕI"], ["sell", "BÁN / TRÁNH"]].map(([code, label]) => (
          <button key={code} className={cls("card kpi")} style={{ cursor: "pointer", textAlign: "left", outline: rec === code ? "2px solid var(--brand)" : "none" }}
            onClick={() => setRec(rec === code ? "" : code)}>
            <span className="kpi-label"><Badge tone={recTone(code)}>{label}</Badge></span>
            <span className="kpi-value">{(counts[code] ?? 0) + (code === "sell" ? counts["reduce"] ?? 0 : 0)}</span>
            <span className="tiny subtle">mã · bấm để lọc</span>
          </button>
        ))}
      </div>

      <Card>
        <div className="row wrap" style={{ gap: 12, marginBottom: 14 }}>
          <div className="search" style={{ maxWidth: 280 }}>
            <Search size={16} />
            <input className="input" placeholder="Tìm mã / tên…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="input" style={{ width: 220 }} value={sector} onChange={(e) => setSector(e.target.value)}>
            <option value="">Tất cả ngành</option>
            {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <div className="row" style={{ minWidth: 260 }}>
            <Filter size={15} className="subtle" />
            <span className="small muted nowrap">Điểm tối thiểu</span>
            <input type="range" min={0} max={90} step={5} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} />
            <b className="mono">{minScore}</b>
          </div>
          <div className="grow" />
          <span className="small subtle">{rows.length} mã</span>
        </div>
        {res.loading ? <Loading text="Đang chấm điểm cổ phiếu (lần đầu có thể mất vài giây)…" height={300} /> : res.error ? <ErrorBox error={res.error} onRetry={res.reload} /> : (
          <div className="table-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <Th k="ticker">Mã</Th><Th k="price" numeric>Giá</Th><Th k="change_pct" numeric>% ngày</Th><Th k="perf_20d" numeric>20 phiên</Th>
                  <Th k="score">Điểm tổng hợp</Th><th>Khuyến nghị</th>
                  <Th k="technical" numeric>KT</Th><Th k="quality" numeric>CL</Th><Th k="valuation" numeric>ĐG</Th>
                  <Th k="roe" numeric>ROE</Th><Th k="pe" numeric>P/E</Th><Th k="pb" numeric>P/B</Th><Th k="upside" numeric>Upside</Th><Th k="beta" numeric>Beta</Th>
                  <th>Xu hướng</th><th>Nguồn</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r: any) => (
                  <tr key={r.ticker} className="clickable" onClick={() => nav(`/stock/${r.ticker}`)}>
                    <td><TickerCell ticker={r.ticker} name={r.sector} /></td>
                    <td className="num mono bold">{vnd(r.price)}</td>
                    <td className={cls("num mono", tone(r.change_pct))}>{pct(r.change_pct, 2, true)}</td>
                    <td className={cls("num mono", tone(r.perf_20d))}>{pct(r.perf_20d, 1, true)}</td>
                    <td style={{ minWidth: 140 }}><ScoreBar score={r.score} /></td>
                    <td><Badge tone={recTone(r.code)}>{r.recommendation}</Badge></td>
                    <td className="num mono">{num(r.parts.technical, 0)}</td>
                    <td className="num mono">{num(r.parts.quality, 0)}</td>
                    <td className="num mono">{num(r.parts.valuation, 0)}</td>
                    <td className="num mono">{pct(r.roe)}</td>
                    <td className="num mono">{num(r.pe, 1)}</td>
                    <td className="num mono">{num(r.pb, 2)}</td>
                    <td className={cls("num mono", tone(r.upside))}>{pct(r.upside, 0, true)}</td>
                    <td className="num mono">{num(r.beta, 2)}</td>
                    <td><Badge tone={r.trend === "Tăng" ? "up" : r.trend === "Giảm" ? "down" : "ref"}>{r.trend}</Badge></td>
                    <td><SourceBadge source={r.source} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
