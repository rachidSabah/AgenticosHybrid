"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Sparkles, GripVertical, ChevronLeft, ChevronRight } from "lucide-react";
import { NAV, NAV_GROUPS } from "./nav";

const SIDEBAR_WIDTH_KEY = "mc.sidebar.width";
const SIDEBAR_COLLAPSED_KEY = "mc.sidebar.collapsed";
const DEFAULT_WIDTH = 248;
const MIN_WIDTH = 64;
const MAX_WIDTH = 400;
const COLLAPSED_WIDTH = 56;

export function Sidebar({
  active,
  onSelect,
}: {
  active: string;
  onSelect: (id: string) => void;
}) {
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [collapsed, setCollapsed] = useState(false);
  const [hoverExpand, setHoverExpand] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const startX = useRef(0);
  const startWidth = useRef(0);
  const sidebarRef = useRef<HTMLElement>(null);

  // Load persisted state
  useEffect(() => {
    const storedW = localStorage.getItem(SIDEBAR_WIDTH_KEY);
    if (storedW) {
      const parsed = parseInt(storedW, 10);
      if (!isNaN(parsed) && parsed >= MIN_WIDTH && parsed <= MAX_WIDTH) {
        setWidth(parsed);
      }
    }
    const storedC = localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    if (storedC !== null) setCollapsed(storedC === "true");
  }, []);

  const persistWidth = useCallback((w: number) => {
    setWidth(w);
    localStorage.setItem(SIDEBAR_WIDTH_KEY, String(w));
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((c) => {
      const next = !c;
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
      return next;
    });
  }, []);

  // Resize handlers
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
    startX.current = e.clientX;
    startWidth.current = collapsed ? COLLAPSED_WIDTH : width;
  }, [collapsed, width]);

  useEffect(() => {
    if (!isResizing) return;
    const onMove = (e: MouseEvent) => {
      const newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, startWidth.current + e.clientX - startX.current));
      // Auto-collapse when dragged below threshold
      if (newWidth < 100) {
        setCollapsed(true);
        localStorage.setItem(SIDEBAR_COLLAPSED_KEY, "true");
      } else {
        setCollapsed(false);
        localStorage.setItem(SIDEBAR_COLLAPSED_KEY, "false");
        setWidth(newWidth);
        localStorage.setItem(SIDEBAR_WIDTH_KEY, String(newWidth));
      }
    };
    const onUp = () => setIsResizing(false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [isResizing]);

  const effectiveWidth = collapsed
    ? (hoverExpand ? Math.min(width, 280) : COLLAPSED_WIDTH)
    : width;

  // Icon color helper
  const iconColor = (id: string) =>
    id === active ? "text-accent" : "text-muted group-hover/sidebar-item:text-text transition-colors";

  return (
    <nav
      ref={sidebarRef}
      data-layout="sidebar"
      className="relative flex h-full flex-col border-r border-border/40 bg-surface/30 backdrop-blur-xl"
      style={{ width: effectiveWidth, minWidth: COLLAPSED_WIDTH, transition: isResizing ? "none" : "width 0.2s ease" }}
      onMouseEnter={() => collapsed && setHoverExpand(true)}
      onMouseLeave={() => collapsed && setHoverExpand(false)}
    >
      {/* Logo / header */}
      <a
        href="#"
        onClick={(e) => { e.preventDefault(); onSelect("overview"); }}
        className="flex h-14 shrink-0 items-center gap-3 border-b border-border/40 px-4"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent/20">
          <Sparkles size={16} className="text-accent" />
        </span>
        {(effectiveWidth > 80) && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="truncate text-sm font-bold tracking-tight"
          >
            AgenticOS
          </motion.span>
        )}
      </a>

      {/* Navigation groups */}
      <div className="sidebar-scroll flex-1 overflow-y-auto overflow-x-hidden py-2">
        {NAV_GROUPS.map((group) => {
          const items = NAV.filter((n) => n.group === group.id);
          if (items.length === 0) return null;
          return (
            <div key={group.id} className="mb-2">
              {/* Group label — hidden when collapsed */}
              {(effectiveWidth > 80) && (
                <div className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-faint">
                  {group.label}
                </div>
              )}
              {items.map((item) => {
                const Icon = item.icon;
                const isActive = item.id === active;
                return (
                  <button
                    key={item.id}
                    onClick={() => onSelect(item.id)}
                    data-nav-id={item.id}
                    className={`group/sidebar-item relative flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-all mx-2 ${
                      isActive
                        ? "bg-accent/15 text-accent font-medium"
                        : "text-muted hover:bg-surface/60 hover:text-text"
                    }`}
                    style={{ width: `calc(100% - 16px)` }}
                    title={collapsed ? item.label : undefined}
                    aria-current={isActive ? "page" : undefined}
                  >
                    <Icon size={18} className={iconColor(item.id)} />
                    {(effectiveWidth > 80) && (
                      <motion.span
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="truncate"
                      >
                        {item.label}
                      </motion.span>
                    )}
                    {isActive && (
                      <motion.div
                        layoutId="active-indicator"
                        className="absolute right-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-accent"
                      />
                    )}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>

      {/* Collapse toggle button */}
      <div className="flex items-center justify-end border-t border-border/40 px-2 py-2">
        <button
          onClick={toggleCollapsed}
          className="flex h-7 w-7 items-center justify-center rounded-md text-faint hover:bg-surface/60 hover:text-text transition-colors"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>

      {/* Resize handle */}
      {!collapsed && (
        <div
          className="absolute right-0 top-0 z-10 h-full w-1 cursor-col-resize hover:bg-accent/30 active:bg-accent/50 transition-colors"
          onMouseDown={onMouseDown}
        />
      )}
    </nav>
  );
}
