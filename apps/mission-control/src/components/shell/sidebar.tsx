"use client";

import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { NAV, NAV_GROUPS } from "./nav";

export function Sidebar({
  active,
  onSelect,
}: {
  active: string;
  onSelect: (id: string) => void;
}) {
  return (
    <aside className="glass-strong z-20 flex w-[248px] shrink-0 flex-col border-r border-border/60">
      <div className="flex items-center gap-2.5 px-5 py-4">
        <div className="relative grid h-9 w-9 place-items-center rounded-xl bg-accent/15 text-accent shadow-glow">
          <Sparkles size={18} />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-tight">Mission Control</div>
          <div className="text-[11px] text-faint">AgenticOS</div>
        </div>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-2">
        {NAV_GROUPS.map((g) => (
          <div key={g.id}>
            <div className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-faint">
              {g.label}
            </div>
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
                      className={`relative z-10 ${isActive ? "text-accent" : "text-faint group-hover:text-muted"}`}
                    />
                    <span className="relative z-10 flex-1 truncate">{item.label}</span>
                    <kbd className="relative z-10 rounded border border-border/70 px-1 text-[10px] text-faint">
                      {item.hint}
                    </kbd>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-border/60 px-4 py-3 text-[11px] text-faint">
        <span className="text-ok">●</span> live event bus
      </div>
    </aside>
  );
}
