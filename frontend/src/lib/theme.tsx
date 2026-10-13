import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "dark" | "light";
type Size = "md" | "lg";
type ThemeCtx = { theme: Theme; toggle: () => void; setTheme: (t: Theme) => void; size: Size; setSize: (s: Size) => void };
const Ctx = createContext<ThemeCtx>({ theme: "light", toggle: () => {}, setTheme: () => {}, size: "md", setSize: () => {} });
export const useTheme = () => useContext(Ctx);

const META_COLOR: Record<Theme, string> = { light: "#f4f7f6", dark: "#0b1110" };

function stored<T extends string>(key: string, allowed: T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key) as T | null;
    return v && allowed.includes(v) ? v : fallback;
  } catch {
    return fallback;
  }
}

function save(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* chế độ riêng tư: bỏ qua */
  }
}

// Gắn thuộc tính lên <html> NGAY khi đổi (trước khi React vẽ lại) để biểu đồ đọc đúng màu của giao diện mới.
function apply(theme: Theme, size: Size) {
  const el = document.documentElement;
  el.dataset.theme = theme;
  el.dataset.size = size;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", META_COLOR[theme]);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => stored<Theme>("theme", ["light", "dark"], "light"));
  const [size, setSizeState] = useState<Size>(() => stored<Size>("text-size", ["md", "lg"], "md"));
  useEffect(() => apply(theme, size), [theme, size]);
  const setTheme = (t: Theme) => {
    apply(t, size);
    save("theme", t);
    setThemeState(t);
  };
  const setSize = (s: Size) => {
    apply(theme, s);
    save("text-size", s);
    setSizeState(s);
  };
  return (
    <Ctx.Provider value={{ theme, setTheme, toggle: () => setTheme(theme === "dark" ? "light" : "dark"), size, setSize }}>
      {children}
    </Ctx.Provider>
  );
}

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
