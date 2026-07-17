"use client";

import { Search, Sun, Moon, Circle } from "lucide-react";
import { useTheme } from "@/components/theme-provider";
import { useStore } from "@/lib/store";
import { NAV } from "./nav";
import { NotificationsButton } from "./notifications-popover";

export function TopBar({ active, onCommand }: { active: string; onCommand: () => void }) {
  const { theme, toggle } = useTheme();
  const connected = useStore((s) => s.connected);
  const notifCount = useStore((s) => s.notifications.length);
  const current = NAV.find((n) => n.id === active);

  return (
    <header className="glass z-20 flex h-14 shrink-0 items-center gap-3 border-b border-border/60 px-5">
      <div className="text-sm font-medium text-muted">
        {current?.label ?? "Mission Control"}
      </div>

      <button
        onClick={onCommand}
        className="group ml-2 flex items-center gap-2 rounded-xl border border-border/70 bg-surface/40 px-3 py-1.5 text-sm text-faint transition-colors hover:text-muted"
      >
        <Search size={14} />
        <span>Search or jump to…</span>
        <kbd className="ml-6 rounded border border-border/70 px-1.5 text-[10px]">⌘K</kbd>
      </button>

      <div className="ml-auto flex items-center gap-2">
        <div className="flex items-center gap-1.5 rounded-full border border-border/70 bg-surface/40 px-2.5 py-1 text-xs">
          <Circle
            size={8}
            className={connected ? "fill-ok text-ok" : "fill-danger text-danger"}
          />
          <span className="text-muted">{connected ? "Live" : "Offline"}</span>
        </div>

        <NotificationsButton />

        <button
          onClick={toggle}
          className="grid h-9 w-9 place-items-center rounded-xl border border-border/70 bg-surface/40 text-muted transition-colors hover:text-text"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </header>
  );
}
