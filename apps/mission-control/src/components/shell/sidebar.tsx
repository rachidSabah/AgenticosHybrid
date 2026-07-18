"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Sparkles, GripVertical } from "lucide-react";
import { NAV, NAV_GROUPS } from "./nav";

const SIDEBAR_WIDTH_KEY = "mc.sidebar.width";
const DEFAULT_WIDTH = 248;
const MIN_WIDTH = 64;
const MAX_WIDTH = 400;

export function Sidebar({
  active,
  onSelect,
}: {
  active: string;
  onSelect: (id: string) => void;
}) {
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [isResizing, setIsResizing] = useState(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

  // Load persisted width
  useEffect(() => {
    const stored = localStorage.getItem(SIDEBAR_WIDTH_KEY);
    if (stored) {
      const parsed = parseInt(stored, 10);
      if (!isNaN(parsed) && parsed >= MIN_WIDTH && parsed <= MAX_WIDTH) {
        setWidth(parsed);
      }
    }
  }, []);

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizing(true);
    startX.current = e.clientX;
    startWidth.current = width;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;
      const delta = e.clientX - startX.current;
      const newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, startWidth.current + delta));
      setWidth(newWidth);
    };

    const handleMouseUp = () => {
      if (isResizing) {
        setIsResizing(false);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        localStorage.setItem(SIDEBAR_WIDTH_KEY, width.toString());
      }
    };

    if (isResizing) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing, width]);

  const isCollapsed = width <= MIN_WIDTH + 8;

  return (
    <aside
      className="glass-strong z-20 flex flex-col border-r border-border/60 transition-all duration-200 ease-out"
      style={{ width: `${width}px`, minWidth: `${MIN_WIDTH}px`, maxWidth: `${MAX_WIDTH}px` }}
    >
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-border/60 flex-shrink-0">
        <div className="relative grid h-9 w-9 place-items-center rounded-xl bg-accent/15 text-accent shadow-glow">
          <Sparkles size={18} />
        </div>
        {!isCollapsed && (
          <div className="leading-tight overflow-hidden">
            <div className="text-sm font-semibold tracking-tight truncate">Mission Control</div>
            <div className="text-[11px] text-faint truncate">AgenticOS</div>
          </div>
        )}
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-2" style={{ minWidth: 0 }}>
        {NAV_GROUPS.map((g) => (
          <div key={g.id}>
            {!isCollapsed && (
              <div className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-faint">
                {g.label}
              </div>
            )}
            <div className="space-y-0.5">
              {NAV.filter((n) => n.group === g.id).map((item) => {
                const Icon = item.icon;
                const isActive = active === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onSelect(item.id)}
                    className={`group relative flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-sm transition-colors ${
                      isActive ? "text-text" : "text-muted hover:text-text"
                    }`}
                    title={isCollapsed ? item.label : undefined}
                    aria-label={isCollapsed ? item.label : undefined}
                  >
                    {isActive && (
                      <motion.div
                        layoutId="nav-active"
                        className="absolute inset-0 rounded-xl bg-accent/12 ring-1 ring-accent/30"
                        transition={{ type: "spring", stiffness: 500, damping: 38 }}
                      />
                    )}
                    <Icon
                      size={16}
                      className={`relative z-10 flex-shrink-0 ${isActive ? "text-accent" : "text-faint group-hover:text-muted"}`}
                    />
                    {!isCollapsed && (
                      <span className="relative z-10 flex-1 truncate">{item.label}</span>
                    )}
                    {!isCollapsed && (
                      <kbd className="relative z-10 flex-shrink-0 rounded border border-border/70 px-1 text-[10px] text-faint">
                        {item.hint}
                      </kbd>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {!isCollapsed && (
        <div className="border-t border-border/60 px-4 py-3 text-[11px] text-faint">
          <span className="text-ok">●</span> live event bus
        </div>
      )}

      {/* Resize handle */}
      <div
        onMouseDown={handleMouseDown}
        className="relative h-px w-full cursor-col-resize bg-transparent hover:bg-accent/20 transition-colors group"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") {
            e.preventDefault();
            setWidth((w) => Math.min(MAX_WIDTH, w + 16));
          } else if (e.key === "ArrowLeft") {
            e.preventDefault();
            setWidth((w) => Math.max(MIN_WIDTH, w - 16));
          }
        }}
        style={{ touchAction: "none" }}
      >
        <div className="absolute right-0 top-1/2 -translate-y-1/2 w-1 h-8 -translate-x-1/2 rounded-full bg-border/60 group-hover:bg-accent/40 transition-colors" />
      </div>
    </aside>
  );
}
