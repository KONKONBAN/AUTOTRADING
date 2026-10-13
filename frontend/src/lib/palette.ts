import { useMemo } from "react";
import { cssVar, useTheme } from "./theme";

/** Bảng màu biểu đồ dẫn xuất từ màu thương hiệu (xanh ngọc, xám xanh, vàng đồng…), không dùng màu cầu vồng.
 *  Màu tăng/giảm/tham chiếu theo quy ước bảng giá Việt Nam, chỉ dùng cho dữ liệu giá. */
export type Palette = {
  brand: string; up: string; down: string; ref: string; muted: string; grid: string; text: string;
  cat: string[]; cash: string; ma20: string; ma50: string; ma200: string; bb: string;
};

export function readPalette(): Palette {
  const v = (name: string, fallback: string) => cssVar(name) || fallback;
  const cat = [
    v("--chart-1", "#0a7a63"), v("--chart-2", "#5b6b8c"), v("--chart-3", "#b8913a"), v("--chart-4", "#7fa79a"),
    v("--chart-5", "#c9b48a"), v("--chart-6", "#3e7c93"), v("--chart-7", "#8c6f5b"), v("--chart-8", "#a3b1ad"),
  ];
  const muted = v("--chart-muted", "#8a9993");
  return {
    brand: v("--brand", "#0a7a63"), up: v("--up", "#0a7f3f"), down: v("--down", "#d42a32"), ref: v("--ref", "#8f6800"),
    muted, grid: v("--border", "#e3eae7"), text: v("--text-3", "#5f6f69"),
    cat, cash: muted, ma20: cat[2], ma50: cat[1], ma200: v("--chart-ma200", "#7a3e9d"), bb: muted,
  };
}

/** Bảng màu theo giao diện hiện tại (tính lại khi đổi sáng/tối). */
export function usePalette(): Palette {
  const { theme } = useTheme();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(readPalette, [theme]);
}
