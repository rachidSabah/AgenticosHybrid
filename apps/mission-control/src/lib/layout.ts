"use client";

/**
 * Universal Responsive Layout Engine.
 *
 * Measures all layout regions (viewport, sidebar, header, notifications)
 * and provides reactive CSS custom properties + hooks so every component
 * can adapt without manual media queries.
 *
 * Features:
 *  - ResizeObserver-based measurement (no layout thrashing)
 *  - Exposes CSS custom properties on :root for fluid sizing
 *  - Export hooks: useViewport, useContentRect, useBreakpoint
 *  - Container query support via data attributes
 *  - Auto-fit / auto-fill grid helpers
 */

import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from "react";

// ── Breakpoints matching Tailwind ──
export const BREAKPOINTS = {
  mobile: 640,
  tablet: 1024,
  desktop: 1280,
  wide: 1536,
} as const;

export type Breakpoint = keyof typeof BREAKPOINTS;

// ── Layout snapshot ──
export interface LayoutSnapshot {
  /** Window inner width */
  vw: number;
  /** Window inner height */
  vh: number;
  /** Sidebar width (0 if collapsed) */
  sidebarWidth: number;
  /** Whether sidebar is in icon-only mode */
  sidebarCollapsed: boolean;
  /** Top bar / header height */
  headerHeight: number;
  /** Notification panel width (0 if closed) */
  notifPanelWidth: number;
  /** Available content width after subtracting fixed panels */
  contentWidth: number;
  /** Available content height */
  contentHeight: number;
  /** Current breakpoint */
  breakpoint: Breakpoint;
  /** Columns for auto-grid at this breakpoint */
  gridColumns: number;
  /** Whether reduced motion is preferred */
  prefersReducedMotion: boolean;
}

const DEFAULT_SNAPSHOT: LayoutSnapshot = {
  vw: 1920,
  vh: 1080,
  sidebarWidth: 248,
  sidebarCollapsed: false,
  headerHeight: 56,
  notifPanelWidth: 0,
  contentWidth: 1672,
  contentHeight: 1024,
  breakpoint: "wide",
  gridColumns: 12,
  prefersReducedMotion: false,
};

// ── Context ──
const LayoutCtx = createContext<LayoutSnapshot>(DEFAULT_SNAPSHOT);
export const useLayout = () => useContext(LayoutCtx);

// ── Individual hooks ──
export function useViewport() {
  const { vw, vh } = useLayout();
  return { width: vw, height: vh };
}

export function useBreakpoint() {
  const { breakpoint } = useLayout();
  return breakpoint;
}

export function useContentRect() {
  const { contentWidth, contentHeight } = useLayout();
  return { width: contentWidth, height: contentHeight };
}

/** Returns the optimal column count for responsive grids */
export function useGridCols(maxCols = 12): number {
  const { gridColumns } = useLayout();
  return Math.min(gridColumns, maxCols);
}

// ── Helper: compute breakpoint ──
function getBreakpoint(w: number): Breakpoint {
  if (w < BREAKPOINTS.mobile) return "mobile";
  if (w < BREAKPOINTS.tablet) return "tablet";
  if (w < BREAKPOINTS.desktop) return "desktop";
  if (w < BREAKPOINTS.wide) return "wide";
  return "wide";
}

function getGridCols(bp: Breakpoint): number {
  switch (bp) {
    case "mobile": return 1;
    case "tablet": return 4;
    case "desktop": return 8;
    case "wide": return 12;
  }
}

// ── Provider ──
export function LayoutProvider({ children }: { children: ReactNode }) {
  const [snap, setSnap] = useState<LayoutSnapshot>(DEFAULT_SNAPSHOT);
  const sidebarEl = useRef<HTMLElement | null>(null);
  const headerEl = useRef<HTMLElement | null>(null);
  const notifEl = useRef<HTMLElement | null>(null);
  const rafId = useRef(0);

  const measure = useCallback(() => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Find sidebar element (data-layout="sidebar")
    if (!sidebarEl.current) sidebarEl.current = document.querySelector('[data-layout="sidebar"]');
    if (!headerEl.current) headerEl.current = document.querySelector('[data-layout="header"]');
    if (!notifEl.current) notifEl.current = document.querySelector('[data-layout="notif-panel"]');

    const sidebarWidth = sidebarEl.current?.offsetWidth ?? 248;
    const sidebarCollapsed = sidebarWidth < 80;
    const headerHeight = headerEl.current?.offsetHeight ?? 56;
    const notifPanelWidth = notifEl.current?.offsetWidth ?? 0;

    const breakpoint = getBreakpoint(vw);

    setSnap({
      vw,
      vh,
      sidebarWidth,
      sidebarCollapsed,
      headerHeight,
      notifPanelWidth,
      contentWidth: vw - sidebarWidth - notifPanelWidth,
      contentHeight: vh - headerHeight,
      breakpoint,
      gridColumns: getGridCols(breakpoint),
      prefersReducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    });
  }, []);

  useEffect(() => {
    // Initial measurement after mount
    requestAnimationFrame(() => measure());

    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(rafId.current);
      rafId.current = requestAnimationFrame(measure);
    });

    ro.observe(document.documentElement);

    // Also listen for orientation changes
    window.addEventListener("orientationchange", measure);

    // Media query for reduced motion
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    mq.addEventListener("change", measure);

    return () => {
      ro.disconnect();
      window.removeEventListener("orientationchange", measure);
      mq.removeEventListener("change", measure);
      cancelAnimationFrame(rafId.current);
    };
  }, [measure]);

  // Write CSS custom properties
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--mc-vw", `${snap.vw}px`);
    root.style.setProperty("--mc-vh", `${snap.vh}px`);
    root.style.setProperty("--mc-sidebar-w", `${snap.sidebarWidth}px`);
    root.style.setProperty("--mc-header-h", `${snap.headerHeight}px`);
    root.style.setProperty("--mc-notif-w", `${snap.notifPanelWidth}px`);
    root.style.setProperty("--mc-content-w", `${snap.contentWidth}px`);
    root.style.setProperty("--mc-content-h", `${snap.contentHeight}px`);
    root.style.setProperty("--mc-grid-cols", `${snap.gridColumns}`);
    root.dataset.mcBreakpoint = snap.breakpoint;
    root.dataset.mcSidebarCollapsed = String(snap.sidebarCollapsed);
  }, [snap]);

  return <LayoutCtx.Provider value={snap}>{children}</LayoutCtx.Provider>;
}

// ── Responsive Grid Component ──
export function ResponsiveGrid({
  children,
  className = "",
  minColWidth = 280,
  maxCols: _maxCols,
  gap = 4,
}: {
  children: ReactNode;
  className?: string;
  minColWidth?: number;
  maxCols?: number;
  gap?: number;
}) {
  const cols = useGridCols(_maxCols ?? 12);

  return (
    <div
      className={className}
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
        gap: `${gap * 0.25}rem`,
      }}
    >
      {children}
    </div>
  );
}

// ── Fluid Sizing Helpers ──

/** Clamp between min and max with fluid scaling based on viewport */
export function fluid(
  minSize: number,
  maxSize: number,
  minVw = 1366,
  maxVw = 2560,
): string {
  const slope = (maxSize - minSize) / (maxVw - minVw);
  const intercept = minSize - slope * minVw;
  return `clamp(${minSize}px, ${slope * 100}vw + ${intercept}px, ${maxSize}px)`;
}

/** Minmax for grid tracks */
export function autoFill(min: number, max: number | "1fr" = "1fr") {
  return `repeat(auto-fill, minmax(${min}px, ${max}))`;
}

export function autoFit(min: number, max: number | "1fr" = "1fr") {
  return `repeat(auto-fit, minmax(${min}px, ${max}))`;
}

// ── Container Query hook ──
export function useContainerWidth(ref: React.RefObject<HTMLElement | null>) {
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      setWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);

  return width;
}
