import { useEffect, useRef, useState } from "react";
import {
  ColorType, CrosshairMode, LineStyle, createChart,
  type IChartApi, type ISeriesApi, type LogicalRange, type Time,
} from "lightweight-charts";
import { cssVar, useTheme } from "../lib/theme";

type Pt = { time: string; value: number };
export type ChartData = {
  candles: { time: string; open: number; high: number; low: number; close: number }[];
  volume: { time: string; value: number; up: boolean }[];
  sma20: Pt[]; sma50: Pt[]; sma200: Pt[]; bb_upper: Pt[]; bb_lower: Pt[];
  rsi: Pt[]; macd: Pt[]; macd_signal: Pt[]; macd_hist: Pt[];
};
export type Overlays = { ma20: boolean; ma50: boolean; ma200: boolean; bb: boolean; volume: boolean };
export type PriceLine = { price: number; title: string; color: string };

function baseOptions(height: number) {
  const text = cssVar("--text-3");
  const border = cssVar("--border");
  return {
    height,
    autoSize: true,
    layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: text, fontFamily: "Be Vietnam Pro, sans-serif", fontSize: 11 },
    grid: { vertLines: { color: border, style: LineStyle.Dotted }, horzLines: { color: border, style: LineStyle.Dotted } },
    rightPriceScale: { borderColor: border, minimumWidth: 76 },  // cùng độ rộng → trục thời gian các khung thẳng hàng
    timeScale: { borderColor: border, rightOffset: 4, timeVisible: false },
    crosshair: { mode: CrosshairMode.Normal },
    localization: { locale: "vi-VN", priceFormatter: (p: number) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(p) },
  };
}

const C = { ma20: "#f59e0b", ma50: "#3b82f6", ma200: "#a855f7", bb: "#64748b" };

export function PriceChart({ data, overlays, height = 420, lines = [], showRsi = true, showMacd = true, fit = false }: {
  data: ChartData; overlays: Overlays; height?: number; lines?: PriceLine[]; showRsi?: boolean; showMacd?: boolean;
  /** true: hiển thị trọn khoảng thời gian đã chọn; false: chỉ ~180 phiên gần nhất (có thể cuộn) */
  fit?: boolean;
}) {
  const { theme } = useTheme();
  const mainRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const [legend, setLegend] = useState<{ o: number; h: number; l: number; c: number; time: string } | null>(null);

  useEffect(() => {
    if (!mainRef.current) return;
    const up = cssVar("--up");
    const down = cssVar("--down");
    const charts: IChartApi[] = [];
    // Các khung phụ (RSI, MACD) dùng CÙNG trục thời gian với nến: chèn điểm trống (whitespace) cho những
    // phiên chưa có giá trị chỉ báo, để đồng bộ theo chỉ số logic không bị lệch phiên.
    const times = data.candles.map((c) => c.time);
    const pad = <T extends { time: string }>(pts: T[]) => {
      const m = new Map(pts.map((p) => [p.time, p]));
      return times.map((t) => m.get(t) ?? { time: t });
    };
    const main = createChart(mainRef.current, baseOptions(height));
    charts.push(main);
    const candle = main.addCandlestickSeries({ upColor: up, downColor: down, borderVisible: false, wickUpColor: up, wickDownColor: down });
    candle.setData(data.candles as any);
    lines.forEach((l) => candle.createPriceLine({ price: l.price, color: l.color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: l.title }));
    const addLine = (pts: Pt[], color: string, width = 1.5, style = LineStyle.Solid) => {
      const s = main.addLineSeries({ color, lineWidth: width as any, lineStyle: style, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      s.setData(pts as any);
      return s;
    };
    if (overlays.ma20) addLine(data.sma20, C.ma20);
    if (overlays.ma50) addLine(data.sma50, C.ma50);
    if (overlays.ma200) addLine(data.sma200, C.ma200, 2);
    if (overlays.bb) {
      addLine(data.bb_upper, C.bb, 1, LineStyle.Dashed);
      addLine(data.bb_lower, C.bb, 1, LineStyle.Dashed);
    }
    if (overlays.volume) {
      const vol = main.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol", lastValueVisible: false, priceLineVisible: false });
      main.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      vol.setData(data.volume.map((v) => ({ time: v.time, value: v.value, color: v.up ? up + "66" : down + "66" })) as any);
    }
    main.subscribeCrosshairMove((p) => {
      const d = p.seriesData.get(candle as ISeriesApi<"Candlestick">) as any;
      if (d && d.open !== undefined) setLegend({ o: d.open, h: d.high, l: d.low, c: d.close, time: String(p.time) });
      else setLegend(null);
    });

    const sub = (el: HTMLDivElement | null, build: (c: IChartApi) => void) => {
      if (!el) return;
      const base = baseOptions(110);
      const ch = createChart(el, { ...base, layout: { ...base.layout, attributionLogo: false }, timeScale: { visible: false, borderColor: cssVar("--border") } } as any);
      build(ch);
      charts.push(ch);
    };
    if (showRsi) sub(rsiRef.current, (ch) => {
      const s = ch.addLineSeries({ color: "#8b5cf6", lineWidth: 2, priceLineVisible: false });
      s.setData(pad(data.rsi) as any);
      s.createPriceLine({ price: 70, color: down, lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: false, title: "" });
      s.createPriceLine({ price: 30, color: up, lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: false, title: "" });
    });
    if (showMacd) sub(macdRef.current, (ch) => {
      const h = ch.addHistogramSeries({ priceLineVisible: false });
      h.setData(pad(data.macd_hist.map((p) => ({ ...p, color: p.value >= 0 ? up + "99" : down + "99" }))) as any);
      const m = ch.addLineSeries({ color: "#0ea5e9", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
      m.setData(pad(data.macd) as any);
      const sg = ch.addLineSeries({ color: "#f59e0b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      sg.setData(pad(data.macd_signal) as any);
    });
    // đồng bộ cuộn/zoom giữa các biểu đồ
    let syncing = false;
    charts.forEach((src) =>
      src.timeScale().subscribeVisibleLogicalRangeChange((range: LogicalRange | null) => {
        if (syncing || !range) return;
        syncing = true;
        charts.forEach((dst) => dst !== src && dst.timeScale().setVisibleLogicalRange(range));
        syncing = false;
      })
    );
    const n = data.candles.length;
    main.timeScale().setVisibleLogicalRange({ from: fit ? 0 : Math.max(0, n - 180), to: n + 3 });
    return () => charts.forEach((c) => c.remove());
  }, [data, overlays, height, lines, showRsi, showMacd, fit, theme]);

  const last = data.candles[data.candles.length - 1];
  const L = legend ?? (last ? { o: last.open, h: last.high, l: last.low, c: last.close, time: last.time } : null);
  const f = (x: number) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(x);
  return (
    <div className="col" style={{ gap: 4 }}>
      <div className="chart-box">
        {L && (
          <div className="chart-legend mono">
            <span className="subtle">{L.time}</span>
            <span>O <b>{f(L.o)}</b></span><span>H <b className="up">{f(L.h)}</b></span>
            <span>L <b className="down">{f(L.l)}</b></span><span>C <b className={L.c >= L.o ? "up" : "down"}>{f(L.c)}</b></span>
            {overlays.ma20 && <span><i className="legend-dot" style={{ background: C.ma20 }} />MA20</span>}
            {overlays.ma50 && <span><i className="legend-dot" style={{ background: C.ma50 }} />MA50</span>}
            {overlays.ma200 && <span><i className="legend-dot" style={{ background: C.ma200 }} />MA200</span>}
          </div>
        )}
        <div ref={mainRef} style={{ height }} />
      </div>
      {showRsi && (<><div className="tiny subtle" style={{ paddingLeft: 4 }}>RSI (14)</div><div ref={rsiRef} style={{ height: 110 }} /></>)}
      {showMacd && (<><div className="tiny subtle" style={{ paddingLeft: 4 }}>MACD (12, 26, 9)</div><div ref={macdRef} style={{ height: 110 }} /></>)}
    </div>
  );
}

export type LineSeries = { name: string; color: string; data: { time: string; value: number }[]; area?: boolean; width?: number };

export function TimeChart({ series, height = 260, percent = false }: { series: LineSeries[]; height?: number; percent?: boolean }) {
  const { theme } = useTheme();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const ch = createChart(ref.current, {
      ...baseOptions(height),
      localization: {
        locale: "vi-VN",
        priceFormatter: (p: number) =>
          percent ? `${(p * 100).toFixed(1)}%`
            : Math.abs(p) >= 1e6 ? new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 2 }).format(p)
            : new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(p),
      },
    } as any);
    series.forEach((s) => {
      const opts = { lineWidth: (s.width ?? 2) as any, priceLineVisible: false, lastValueVisible: true };
      const ser = s.area
        ? ch.addAreaSeries({ ...opts, lineColor: s.color, topColor: s.color + "44", bottomColor: s.color + "00" })
        : ch.addLineSeries({ ...opts, color: s.color });
      ser.setData(s.data.filter((p) => Number.isFinite(p.value)).map((p) => ({ time: p.time as Time, value: p.value })));
    });
    ch.timeScale().fitContent();
    return () => ch.remove();
  }, [series, height, percent, theme]);
  return <div ref={ref} style={{ height }} />;
}
