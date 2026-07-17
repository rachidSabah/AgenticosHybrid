"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Bell, X } from "lucide-react";
import { useStore } from "@/lib/store";

const LEVEL_COLOR: Record<string, string> = {
  info: "bg-info",
  ok: "bg-ok",
  warn: "bg-warn",
  danger: "bg-danger",
};

export function NotificationsButton() {
  const [open, setOpen] = useState(false);
  const notifs = useStore((s) => s.notifications);
  const clear = useStore((s) => s.clearNotifications);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative grid h-9 w-9 place-items-center rounded-xl border border-border/70 bg-surface/40 text-muted transition-colors hover:text-text"
        aria-label="Notifications"
      >
        <Bell size={16} />
        {notifs.length > 0 && (
          <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] font-semibold text-white">
            {notifs.length > 9 ? "9+" : notifs.length}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: -8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.98 }}
              transition={{ duration: 0.16 }}
              className="glass-strong absolute right-0 top-11 z-40 max-h-[60vh] w-80 overflow-auto rounded-2xl border border-border/70 p-2 shadow-depth"
            >
              <div className="flex items-center justify-between px-2 py-1.5">
                <span className="text-sm font-medium">Notifications</span>
                <div className="flex items-center gap-2">
                  <button className="text-[11px] text-faint hover:text-text" onClick={clear}>
                    Clear
                  </button>
                  <button className="text-faint hover:text-text" onClick={() => setOpen(false)}>
                    <X size={14} />
                  </button>
                </div>
              </div>
              <div className="space-y-1">
                {notifs.map((n) => (
                  <div key={n.id} className="flex items-start gap-2 rounded-xl px-2 py-2 hover:bg-surface/40">
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${LEVEL_COLOR[n.level]}`} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm">{n.title}</div>
                      <div className="truncate text-[11px] text-faint">{n.detail}</div>
                    </div>
                    <span className="text-[10px] text-faint">
                      {new Date(n.at).toLocaleTimeString()}
                    </span>
                  </div>
                ))}
                {notifs.length === 0 && (
                  <div className="px-2 py-6 text-center text-xs text-faint">No notifications</div>
                )}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
