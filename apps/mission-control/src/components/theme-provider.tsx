"use client";

import { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";

type RawTheme = "dark" | "light" | "system";

export type AccentColor = string; // hex, e.g. "#6e8cff"

interface ThemeCtx {
  theme: "dark" | "light";
  raw: RawTheme;
  toggle: () => void;
  set: (t: RawTheme) => void;
  accent: AccentColor;
  setAccent: (c: AccentColor) => void;
  resetAccent: () => void;
}

const Ctx = createContext<ThemeCtx | null>(null);

// Built-in accent presets (hex). The DEFAULT_ACCENT is the token accent
// (RGB triple below) so the app looks unchanged until the user picks one.
export const ACCENT_PRESETS: AccentColor[] = [
  "#6e8cff", // default indigo (matches --accent dark)
  "#00d4ff", // cyan
  "#10b981", // emerald
  "#a855f7", // purple
  "#f43f5e", // rose
  "#f59e0b", // amber
  "#22d3ee", // sky
  "#4ade80", // green
  "#fb7185", // pink
  "#60a5fa", // blue
  "#c084fc", // violet
  "#fbbf24", // gold
];

export const DEFAULT_ACCENT = "#6e8cff";

// Convert "#rrggbb" → "r g b" for CSS var (--accent: R G B).
function hexToRgbTriple(hex: string): string | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
}

function resolve(theme: RawTheme): "dark" | "light" {
  if (theme === "system") {
    if (typeof window === "undefined") return "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return theme;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [raw, setRaw] = useState<RawTheme>("dark");
  const [accent, setAccentState] = useState<AccentColor>(DEFAULT_ACCENT);

  // Hydrate from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("mc-theme") as RawTheme | null;
    if (saved) setRaw(saved);
    const savedAccent = localStorage.getItem("mc-accent");
    if (savedAccent && /^#?[0-9a-f]{6}$/i.test(savedAccent)) setAccentState(savedAccent);
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

  // Apply theme class to DOM
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    localStorage.setItem("mc-theme", raw);
  }, [theme, raw]);

  // Apply custom accent to DOM — overrides --accent (and soft variant) with
  // the user's chosen color so every page using the accent token updates.
  useEffect(() => {
    const root = document.documentElement;
    const triple = hexToRgbTriple(accent);
    if (triple) {
      root.style.setProperty("--accent", triple);
      // Derive a soft accent (low-alpha tint) from the chosen color.
      root.style.setProperty("--accent-soft", triple);
      localStorage.setItem("mc-accent", accent);
    }
  }, [accent]);

  const toggle = useCallback(() => setRaw((t) => (t === "dark" ? "light" : t === "light" ? "system" : "dark")), []);
  const set = useCallback((t: RawTheme) => setRaw(t), []);
  const setAccent = useCallback((c: AccentColor) => setAccentState(c), []);
  const resetAccent = useCallback(() => setAccentState(DEFAULT_ACCENT), []);

  return <Ctx.Provider value={{ theme, raw, toggle, set, accent, setAccent, resetAccent }}>{children}</Ctx.Provider>;
}

export function useTheme() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
