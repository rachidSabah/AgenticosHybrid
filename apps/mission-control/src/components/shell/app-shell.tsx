"use client";

import { useEffect, useState, useCallback, useContext, type ReactNode } from "react";
import { motion } from "framer-motion";
import { CommandPalette } from "./command-palette";
import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";
import { useStore } from "@/lib/store";
import { NAV } from "./nav";
import { ActiveViewCtx } from "@/lib/active-view";
import { LoadingScreen } from "@/components/ui/primitives";
import { useSidebar } from "@/lib/use-sidebar";
import { BackendStatus } from "@/components/backend-status";
import { ChevronLeft, ChevronRight, Bot, Brain, Activity, Settings, Shield, Cpu, HardDrive, MemoryStick } from "lucide-react";

const storeConnect = () => useStore.getState().connect();
const storeDisconnect = () => useStore.getState().disconnect();

export function AppShell({ children }: { children: ReactNode }) {
  const { collapsed: isCollapsed, toggle: toggleCollapse } = useSidebar();
  const { connected } = useStore();
  const [active, setActive] = useState("overview");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [connectingDismissed, setConnectingDismissed] = useState(false);

  useEffect(() => {
    setMounted(true);
    // Connect WebSocket — delivers live events.
    storeConnect();
    // Immediately seed agents/providers/brains from REST snapshot.
    void useStore.getState().hydrate();
    // Re-hydrate every 30s so counts stay accurate even if WS events are missed.
    const hydrateTimer = setInterval(() => {
      void useStore.getState().hydrate();
    }, 30_000);
    const timer = setTimeout(() => setConnectingDismissed(true), 1200);
    return () => {
      storeDisconnect();
      clearTimeout(timer);
      clearInterval(hydrateTimer);
    };
  }, []);

  // Global keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
        return;
      }
      // Single-key navigation when not typing
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        (target?.isContentEditable ?? false) ||
        e.metaKey ||
        e.ctrlKey ||
        e.altKey
      )
        return;
      const item = NAV.find((n) => n.hint.toLowerCase() === e.key.toLowerCase());
      if (item) setActive(item.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const open = useCallback((id: string) => {
    setActive(id);
  }, []);

  if (!mounted) return (
    <div className="grid h-screen w-screen grid-cols-[auto_1fr] overflow-hidden bg-surface text-text">
      <aside className="w-14" aria-label="sidebar-skeleton" />
      <main className="flex items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </main>
    </div>
  );

  return (
    <ActiveViewCtx.Provider value={{ active, setActive: open }}>
      <div className="grid h-screen w-screen grid-cols-[auto_1fr] overflow-hidden bg-surface text-text">
        {/* Sidebar */}
        <div
          className={`relative z-20 flex h-screen flex-col border-r border-border/30 bg-surface/50 backdrop-blur-lg transition-all duration-300 ease-in-out
            ${isCollapsed ? "w-16" : "w-64"}
          `}
        >
          <div className="flex h-14 items-center justify-between border-b border-border/30 px-4">
            {!isCollapsed && (
              <motion.div
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.1 }}
              >
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-lg bg-accent/20 flex items-center justify-center">
                    <Bot size={16} className="text-accent" />
                  </div>
                  <span className="font-semibold text-sm">Mission Control</span>
                </div>
              </motion.div>
            )}
            <button
              onClick={toggleCollapse}
              className="rounded-lg p-1.5 hover:bg-surface/30 transition"
            >
              {isCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
            </button>
          </div>

          <div className="flex-1 overflow-y-auto py-2">
            <Sidebar active={active} onSelect={open} />
          </div>

          <div className="border-t border-border/30 p-2">
            <SidebarFooter isCollapsed={isCollapsed} />
          </div>
        </div>

        {/* Main Content */}
        <main className="grid h-screen grid-rows-[auto_1fr_auto] overflow-hidden">
          {/* Backend offline indicator */}
          <BackendStatus />
          {/* Navbar */}
          <div className="flex h-14 items-center justify-between border-b border-border/30 px-4">
            <div className="flex items-center gap-2">
              <Breadcrumb />
            </div>
            <div className="flex items-center gap-2">
              <SystemStats />
            </div>
          </div>

          {/* Content Area */}
          <div className="relative overflow-hidden">
            {/* Loading overlay — visible until WebSocket connects or timeout passes */}
            {!connected && mounted && !connectingDismissed && (
              <motion.div
                initial={{ opacity: 1 }}
                animate={{ opacity: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.5, delay: 0.3 }}
                className="absolute inset-0 z-10 pointer-events-none flex items-center justify-center bg-surface/80 backdrop-blur-sm"
              >
                <div className="flex flex-col items-center gap-4">
                  <div className="h-12 w-12 rounded-full border-4 border-accent/30 border-t-accent animate-spin" />
                  <div className="text-sm font-medium text-faint">Connecting to system...</div>
                </div>
              </motion.div>
            )}

            {/* Main Content */}
            <div className="h-full overflow-auto">
              {children}
            </div>
          </div>

          {/* Footer */}
          <div className="flex h-8 items-center justify-between border-t border-border/30 px-4 text-[10px] text-faint">
            <div className="flex items-center gap-2">
              <span>© 2026 AgenticOS</span>
              <span>·</span>
              <span>v1.0.0-rc9</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-ok animate-pulse" />
                LIVE
              </span>
            </div>
          </div>
        </main>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onSelect={(id) => {
          open(id);
          setPaletteOpen(false);
        }}
      />
    </ActiveViewCtx.Provider>
  );
}

function SidebarFooter({ isCollapsed }: { isCollapsed: boolean }) {
  const { telemetry } = useStore();

  return (
    <div className="flex flex-col gap-2 p-2">
      {!isCollapsed && (
        <div className="flex items-center gap-2 text-[10px] text-faint">
          <div className="flex items-center gap-1">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-ok" />
            <span>{telemetry.agents} agents</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-warning" />
            <span>{telemetry.tasks} tasks</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-danger" />
            <span>{telemetry.errors} errors</span>
          </div>
        </div>
      )}
      <div className="flex items-center justify-center gap-2">
        <button className="rounded-lg p-1.5 hover:bg-surface/30 transition">
          <Settings size={16} className="text-faint" />
        </button>
        <button className="rounded-lg p-1.5 hover:bg-surface/30 transition">
          <Shield size={16} className="text-faint" />
        </button>
      </div>
    </div>
  );
}

function Breadcrumb() {
  const active = useContext(ActiveViewCtx);
  const navItem = NAV.find((n) => n.id === active.active) || NAV[0];

  return (
    <div className="flex items-center gap-2 text-sm font-medium">
      <navItem.icon size={16} className="text-faint" />
      <span>{navItem.label}</span>
    </div>
  );
}

// ── System Stats ──

function SystemStats() {
  const { telemetry, performance } = useStore();

  const cpu = performance?.cpu_usage_percent;
  const mem = performance?.memory_used_mb;
  const disk = performance?.disk_free_gb;

  return (
    <div className="flex items-center gap-3 text-[10px] text-faint">
      <div className="flex items-center gap-1">
        <Cpu size={12} />
        <span>{cpu != null && cpu > 0 ? `${cpu.toFixed(1)}%` : "—"}</span>
      </div>
      <div className="flex items-center gap-1">
        <MemoryStick size={12} />
        <span>{mem != null && mem > 0 ? `${mem.toFixed(0)}MB` : "—"}</span>
      </div>
      <div className="flex items-center gap-1">
        <HardDrive size={12} />
        <span>{disk != null && disk > 0 ? `${disk}GB` : "—"}</span>
      </div>
    </div>
  );
}