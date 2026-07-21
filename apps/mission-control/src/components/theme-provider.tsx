"use client";

import { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";

type RawTheme = "dark" | "light" | "system";

interface ThemeCtx {
  theme: "dark" | "light";
  raw: RawTheme;
  toggle: () => void;
  set: (t: RawTheme) => void;
}

const Ctx = createContext<ThemeCtx | null>(null);

function resolve(theme: RawTheme): "dark" | "light" {
  if (theme === "system") {
    if (typeof window === "undefined") return "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return theme;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [raw, setRaw] = useState<RawTheme>("dark");

  // Hydrate from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("mc-theme") as RawTheme | null;
    if (saved) setRaw(saved);
  }, []);

  // Resolve effective theme
  const theme = useMemo(() => resolve(raw), [raw]);

  // Listen for system color-scheme changes when in system mode
  useEffect(() => {
    if (raw !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => setRaw("system"); // triggers re-resolve
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [raw]);

  // Apply to DOM
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    localStorage.setItem("mc-theme", raw);
  }, [theme, raw]);

  const toggle = useCallback(() => setRaw((t) => (t === "dark" ? "light" : t === "light" ? "system" : "dark")), []);
  const set = useCallback((t: RawTheme) => setRaw(t), []);

  return <Ctx.Provider value={{ theme, raw, toggle, set }}>{children}</Ctx.Provider>;
}

export function useTheme() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
