"use client";

import { useEffect, useState, useCallback, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CommandPalette } from "./command-palette";
import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";
import { useStore } from "@/lib/store";
import { NAV } from "./nav";
import { ActiveViewCtx } from "@/lib/active-view";
import { LayoutProvider } from "@/lib/layout";

export function AppShell({ children }: { children: ReactNode }) {
  const [active, setActive] = useState("overview");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const connect = useStore((s) => s.connect);
  const disconnect = useStore((s) => s.disconnect);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  // Responsive sidebar
  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 1024;
      setIsMobile(mobile);
      if (mobile) setSidebarOpen(false);
    };
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  // Restore sidebar state
  useEffect(() => {
    if (isMobile) return;
    const stored = localStorage.getItem("mc.sidebar.open");
    if (stored !== null) setSidebarOpen(stored === "true");
  }, [isMobile]);

  const persistSidebar = useCallback((open: boolean) => {
    setSidebarOpen(open);
    if (!isMobile) localStorage.setItem("mc.sidebar.open", String(open));
  }, [isMobile]);

  // Keyboard shortcut: Cmd/Ctrl+K for command palette
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((p) => !p);
      }
      // Cmd/Ctrl+B to toggle sidebar
      if ((e.metaKey || e.ctrlKey) && e.key === "b") {
        e.preventDefault();
        persistSidebar(!sidebarOpen);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [sidebarOpen, persistSidebar]);

  return (
    <LayoutProvider>
      <div className="flex h-screen w-screen overflow-hidden bg-bg text-text">
        {/* Overlay for mobile sidebar */}
        <AnimatePresence>
          {isMobile && sidebarOpen && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
              onClick={() => setSidebarOpen(false)}
            />
          )}
        </AnimatePresence>

        {/* Sidebar */}
        <div
          className="relative z-30 shrink-0"
          data-layout="sidebar"
          style={isMobile ? { position: "fixed", left: sidebarOpen ? 0 : -280, top: 0, bottom: 0, zIndex: 50 } : {}}
        >
          <Sidebar
            active={active}
            onSelect={(id) => {
              setActive(id);
              if (isMobile) setSidebarOpen(false);
            }}
          />
        </div>

        {/* Main area */}
        <div className="flex flex-1 flex-col min-w-0">
          {/* Top bar */}
          <div data-layout="header">
            <TopBar
              active={active}
              onCommand={() => setPaletteOpen(true)}
              onMenuToggle={() => persistSidebar(!sidebarOpen)}
              showMenuButton={isMobile || !sidebarOpen}
            />
          </div>

          {/* Content area — single scroll container */}
          <main className="flex-1 overflow-auto">
            <ActiveViewCtx.Provider value={{ active, setActive }}>
              {children}
            </ActiveViewCtx.Provider>
          </main>
        </div>

        {/* Command palette */}
        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          onSelect={(id) => {
            setActive(id);
            if (isMobile) setSidebarOpen(false);
          }}
        />
      </div>
    </LayoutProvider>
  );
}
