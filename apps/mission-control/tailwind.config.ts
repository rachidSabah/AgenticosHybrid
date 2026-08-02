import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Semantic tokens mapped to CSS variables (see globals.css).
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        elevated: "rgb(var(--elevated) / <alpha-value>)",
        border: "rgb(var(--border) / <alpha-value>)",
        text: "rgb(var(--text) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        faint: "rgb(var(--faint) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-soft": "rgb(var(--accent-soft) / <alpha-value>)",
        ok: "rgb(var(--ok) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        danger: "rgb(var(--danger) / <alpha-value>)",
        info: "rgb(var(--info) / <alpha-value>)",
        // Chart tokens
        "chart-1": "rgb(var(--chart-1) / <alpha-value>)",
        "chart-2": "rgb(var(--chart-2) / <alpha-value>)",
        "chart-3": "rgb(var(--chart-3) / <alpha-value>)",
        "chart-4": "rgb(var(--chart-4) / <alpha-value>)",
        "chart-5": "rgb(var(--chart-5) / <alpha-value>)",
        // Focus ring
        "focus-ring": "rgb(var(--focus-ring) / <alpha-value>)",
        "focus-ring-offset": "rgb(var(--focus-ring-offset) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.25rem",
        "3xl": "1.75rem",
      },
      backdropBlur: {
        xs: "2px",
      },
      // Spring motion tokens (for Framer Motion via CSS variables)
      transitionDuration: {
        "spring-fast": "var(--spring-fast-duration, 200ms)",
        "spring-base": "var(--spring-base-duration, 300ms)",
        "spring-slow": "var(--spring-slow-duration, 500ms)",
      },
      keyframes: {
        "pulse-ring": {
          "0%": { transform: "scale(0.8)", opacity: "0.7" },
          "100%": { transform: "scale(2.4)", opacity: "0" },
        },
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "spin-slow": {
          to: { transform: "rotate(360deg)" },
        },
      },
      animation: {
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.4,0,0.6,1) infinite",
        "fade-in": "fade-in 0.25s ease-out",
        shimmer: "shimmer 2.5s linear infinite",
        "spin-slow": "spin-slow 8s linear infinite",
      },
      boxShadow: {
        glow: "0 0 0 1px rgb(var(--accent) / 0.25), 0 8px 40px -12px rgb(var(--accent) / 0.45)",
        depth: "0 1px 2px rgb(0 0 0 / 0.25), 0 8px 32px -8px rgb(0 0 0 / 0.45)",
      },
    },
  },
  plugins: [],
};

export default config;
