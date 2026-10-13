// Định dạng số kiểu Việt Nam: 1.234.567 ; 12,5%
const nf0 = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

export const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

export function vnd(x: unknown, digits = 0): string {
  if (!isNum(x)) return "—";
  return digits === 0 ? nf0.format(x) : new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits }).format(x);
}

export function money(x: unknown): string {
  if (!isNum(x)) return "—";
  const a = Math.abs(x);
  if (a >= 1e12) return `${nf2.format(x / 1e12)} nghìn tỷ`;
  if (a >= 1e9) return `${nf2.format(x / 1e9)} tỷ`;
  if (a >= 1e6) return `${nf1.format(x / 1e6)} tr`;
  return nf0.format(x);
}

export function pct(x: unknown, digits = 1, sign = false): string {
  if (!isNum(x)) return "—";
  // làm tròn trước để tránh hiển thị "-0,00%" với số âm rất nhỏ
  const v = Math.round(x * 100 * 10 ** digits) / 10 ** digits || 0;
  const s = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(v);
  return `${sign && v > 0 ? "+" : ""}${s}%`;
}

export function num(x: unknown, digits = 2): string {
  if (!isNum(x)) return "—";
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits }).format(x);
}

export function bn(x: unknown): string {
  // số tỷ đồng
  if (!isNum(x)) return "—";
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: Math.abs(x) >= 100 ? 0 : 1 }).format(x);
}

export const cls = (...xs: (string | false | null | undefined)[]) => xs.filter(Boolean).join(" ");

export const tone = (x: unknown) => (!isNum(x) || x === 0 ? "ref" : x > 0 ? "up" : "down");
/** Màu cho tỷ lệ % theo đúng giá trị HIỂN THỊ (đã làm tròn): tránh "0,00%" mà vẫn tô đỏ. */
export const ptone = (x: unknown, digits = 2) => (isNum(x) ? tone(Math.round(x * 100 * 10 ** digits)) : "ref");

export function scoreColor(s: number): string {
  if (s >= 72) return "var(--up)";
  if (s >= 60) return "var(--brand)";
  if (s >= 45) return "var(--ref)";
  if (s >= 35) return "var(--warn)";
  return "var(--down)";
}

export function recTone(code?: string): string {
  if (!code) return "";
  if (["buy", "strong_buy", "accumulate"].includes(code)) return "up";
  if (["sell", "strong_sell", "reduce"].includes(code)) return "down";
  return "ref";
}


export const SOURCE_LABEL: Record<string, string> = {
  demo: "DEMO",
  imported: "File nhập",
  vndirect: "VNDirect",
  ssi: "SSI FastConnect",
  dnse: "DNSE",
  kbs: "KBS",
  vci: "Vietcap",
  cafef: "CafeF",
  tcbs: "TCBS",
  manual: "Nhập tay",
  none: "Chưa có",
};
export function sourceLabel(s?: string): string {
  if (!s) return "—";
  return s
    .split("+")
    .map((p) => SOURCE_LABEL[p] ?? p)
    .join(" + ");
}
