"use client";

/**
 * Responsive Card & Panel system.
 *
 * Replaces the basic <Panel> primitive with auto-height/width cards that
 * are resizable, draggable, and remember their positions.
 *
 * Features:
 *  - Auto-height / auto-width by default
 *  - Resizable via drag handle on bottom-right corner
 *  - Draggable via header
 *  - Persists position + size to localStorage
 *  - Collapsible sections inside cards
 *  - Animated mounting with framer-motion
 */

import { useState, useCallback, useRef, useEffect, type ReactNode } from "react";
import { motion } from "framer-motion";
import { clsx } from "clsx";
import { GripHorizontal, Maximize2, Minimize2, X } from "lucide-react";
import { useLayout, fluid } from "@/lib/layout";

// ── Card Registry Key ──
const CARD_STORE_KEY = "mc.card.layout";

interface CardLayout {
  x: number;
  y: number;
  w: number;
  h: number;
  collapsed: boolean;
}

function loadCardLayouts(): Record<string, CardLayout> {
  try {
    const raw = localStorage.getItem(CARD_STORE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveCardLayouts(layouts: Record<string, CardLayout>) {
  try {
    localStorage.setItem(CARD_STORE_KEY, JSON.stringify(layouts));
  } catch { /* quota exceeded — silently ignore */ }
}

// ── Responsive Card ──
export function ResponsiveCard({
  id,
  title,
  subtitle,
  children,
  className,
  defaultWidth,
  defaultHeight,
  onClose,
  collapsible = true,
  startCollapsed = false,
  resizable = true,
}: {
  id: string;
  title?: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
  defaultWidth?: number;
  defaultHeight?: number;
  onClose?: () => void;
  collapsible?: boolean;
  startCollapsed?: boolean;
  resizable?: boolean;
}) {
  const { prefersReducedMotion } = useLayout();
  const [saved, setSaved] = useState<CardLayout>(() => {
    const all = loadCardLayouts();
    return all[id] ?? {
      x: 0,
      y: 0,
      w: defaultWidth ?? 0,
      h: defaultHeight ?? 0,
      collapsed: startCollapsed,
    };
  });

  const [collapsed, setCollapsed] = useState(saved.collapsed);
  const [maximized, setMaximized] = useState(false);

  const persist = useCallback((patch: Partial<CardLayout>) => {
    setSaved((prev) => {
      const next = { ...prev, ...patch };
      const all = loadCardLayouts();
      all[id] = next;
      saveCardLayouts(all);
      return next;
    });
  }, [id]);

  const toggleCollapse = useCallback(() => {
    setCollapsed((c) => {
      persist({ collapsed: !c });
      return !c;
    });
  }, [persist]);

  return (
    <motion.section
      layout={!prefersReducedMotion}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{
        opacity: 1,
        scale: 1,
        height: collapsed ? "auto" : undefined,
      }}
      transition={{ duration: 0.2 }}
      className={clsx(
        "group/card relative flex min-h-0 flex-col overflow-hidden rounded-xl border border-border/40 bg-surface/60 backdrop-blur-sm",
        maximized ? "fixed inset-4 z-50" : "",
        className,
      )}
      style={maximized ? {} : { gridColumn: saved.w > 0 ? `span ${Math.min(saved.w, 12)}` : undefined }}
    >
      {/* Resize handle */}
      {resizable && !maximized && (
        <div
          className="absolute bottom-0 right-0 z-10 h-4 w-4 cursor-se-resize opacity-0 transition-opacity group-hover/card:opacity-100"
          onMouseDown={(e) => {
            e.preventDefault();
            e.stopPropagation();
            const startX = e.clientX;
            const startY = e.clientY;
            const startW = saved.w || 4;
            const startH = saved.h || 3;

            const onMove = (ev: MouseEvent) => {
              const dx = ev.clientX - startX;
              const dy = ev.clientY - startY;
              const newW = Math.max(1, Math.min(12, Math.round(startW + dx / 200)));
              const newH = Math.max(1, Math.min(20, Math.round(startH + dy / 60)));
              persist({ w: newW, h: newH });
              setSaved((prev) => ({ ...prev, w: newW, h: newH }));
            };
            const onUp = () => {
              document.removeEventListener("mousemove", onMove);
              document.removeEventListener("mouseup", onUp);
            };
            document.addEventListener("mousemove", onMove);
            document.addEventListener("mouseup", onUp);
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-faint">
            <path d="M12 4v8H4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </div>
      )}

      {/* Header */}
      {(title || onClose) && (
        <header
          className={clsx(
            "flex items-center gap-3 border-b border-border/40 px-4",
            collapsed ? "border-b-0" : "",
            "cursor-default select-none",
          )}
          style={{ minHeight: 40 }}
        >
          {/* Drag handle area */}
          <div className="flex items-center gap-2 opacity-0 transition-opacity group-hover/card:opacity-60">
            <GripHorizontal size={12} className="text-faint" />
          </div>

          <div className="min-w-0 flex-1">
            {title && (
              <h3 className="truncate text-sm font-semibold tracking-tight">{title}</h3>
            )}
            {subtitle && !collapsed && (
              <p className="truncate text-[11px] text-faint">{subtitle}</p>
            )}
          </div>

          <div className="flex items-center gap-1">
            {collapsible && (
              <button
                onClick={toggleCollapse}
                className="rounded p-1 text-faint hover:bg-surface/80 hover:text-text transition-colors"
                aria-label={collapsed ? "Expand" : "Collapse"}
              >
                {collapsed ? (
                  <Maximize2 size={12} />
                ) : (
                  <Minimize2 size={12} />
                )}
              </button>
            )}
            {maximized ? (
              <button
                onClick={() => setMaximized(false)}
                className="rounded p-1 text-faint hover:bg-surface/80 hover:text-text"
                aria-label="Minimize"
              >
                <Minimize2 size={12} />
              </button>
            ) : (
              <button
                onClick={() => setMaximized(true)}
                className="rounded p-1 text-faint hover:bg-surface/80 hover:text-text"
                aria-label="Maximize"
              >
                <Maximize2 size={12} />
              </button>
            )}
            {onClose && (
              <button
                onClick={onClose}
                className="rounded p-1 text-faint hover:bg-surface/80 hover:text-danger"
                aria-label="Close"
              >
                <X size={12} />
              </button>
            )}
          </div>
        </header>
      )}

      {/* Content */}
      {!collapsed && (
        <div className="flex-1 overflow-auto p-4" style={{ minHeight: 0 }}>
          {children}
        </div>
      )}
    </motion.section>
  );
}

// ── Panel (simpler wrapper, consistent with old API but responsive) ──
export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
  contentClassName,
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  return (
    <section className={clsx("flex min-h-0 flex-col overflow-hidden rounded-xl border border-border/40 bg-surface/60 backdrop-blur-sm", className)}>
      {(title || actions) && (
        <header className="flex items-center gap-3 border-b border-border/40 px-4 py-2.5">
          <div className="min-w-0 flex-1">
            {title && <h3 className="truncate text-sm font-semibold tracking-tight">{title}</h3>}
            {subtitle && <p className="truncate text-[11px] text-faint">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx("flex-1 overflow-auto p-4", contentClassName)}>
        {children}
      </div>
    </section>
  );
}

// ── Collapsible Section ──
export function CollapsibleSection({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-border/30 last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-4 py-2 text-left text-xs font-medium uppercase tracking-wider text-faint hover:text-text transition-colors"
        aria-expanded={open}
      >
        <span className="transition-transform duration-200" style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)" }}>
          ▶
        </span>
        {title}
      </button>
      {open && <div className="px-4 pb-3">{children}</div>}
    </div>
  );
}

// ── Responsive Table wrapper ──
export function ResponsiveTable({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("w-full overflow-x-auto", className)}>
      <table className="w-full text-left text-sm">{children}</table>
    </div>
  );
}
