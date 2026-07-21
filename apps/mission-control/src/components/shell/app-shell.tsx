"use client";

import { useEffect, useState, useCallback, type ReactNode } from "react";
import { motion } from "framer-motion";
import { CommandPalette } from "./command-palette";
import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";
import { useStore } from "@/lib/store";
import { NAV } from "./nav";
import { ActiveViewCtx } from "@/lib/active-view";

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

  // Global keyboard shortcuts.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
        return;
      }
      // Single-key navigation when not typing.
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || e.metaKey || e.ctrlKey) return;
      const item = NAV.find((n) => n.hint.toLowerCase() === e.key.toLowerCase());
      if (item) setActive(item.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const open = useCallback((id: string) => {
    setActive(id);
    if (isMobile) setSidebarOpen(false);
  }, [isMobile]);

  const shell = (
    <div className="relative h-screen w-screen overflow-hidden text-text">
      <div className="app-backdrop" />
      <div className="relative z-10 flex h-full">
        <motion.aside
          initial={isMobile && !sidebarOpen ? { x: -300, opacity: 0 } : { opacity: 0 }}
          animate={isMobile ? (sidebarOpen ? { x: 0, opacity: 1 } : { x: -300, opacity: 0 }) : { opacity: 1 }}
          exit={isMobile ? { x: -300, opacity: 0 } : { opacity: 0 }}
          transition={{ duration: 0.22, ease: "easeOut" }}
          className={`z-30 h-full ${isMobile ? "fixed inset-y-0 left-0" : ""}`}
        >
          <Sidebar active={active} onSelect={open} />
        </motion.aside>

        {isMobile && sidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-20 bg-black/40 lg:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        <div className="flex min-w-0 flex-1 flex-col lg:ml-0">
          <TopBar
            active={active}
            onCommand={() => setPaletteOpen(true)}
            onMenuToggle={() => setSidebarOpen(!sidebarOpen)}
            showMenuButton={isMobile}
          />
          <main className="relative min-h-0 flex-1 overflow-hidden">
            <motion.div
              layoutId="active-view"
              key={active}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="h-full"
            >
              {children}
            </motion.div>
          </main>
        </div>
      </div>
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onSelect={(id) => {
          open(id);
          setPaletteOpen(false);
        }}
      />
    </div>
  );

  return <ActiveViewCtx.Provider value={active}>{shell}</ActiveViewCtx.Provider>;
}
