"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, CornerDownLeft } from "lucide-react";
import { NAV } from "./nav";

export function CommandPalette({
  open,
  onClose,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  onSelect: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return NAV;
    return NAV.filter(
      (n) => n.label.toLowerCase().includes(q) || n.id.includes(q) || n.hint === q,
    );
  }, [query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
    }
  }, [open]);

  useEffect(() => {
    setCursor(0);
  }, [query]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setCursor((c) => Math.min(c + 1, results.length - 1));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setCursor((c) => Math.max(c - 1, 0));
      }
      if (e.key === "Enter" && results[cursor]) onSelect(results[cursor].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, results, cursor, onSelect, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-[14vh] backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: -8 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            onClick={(e) => e.stopPropagation()}
            className="glass-strong w-[560px] max-w-[92vw] overflow-hidden rounded-2xl shadow-depth"
          >
            <div className="flex items-center gap-2.5 border-b border-border/60 px-4 py-3">
              <Search size={16} className="text-faint" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search views, commands…"
                className="flex-1 bg-transparent text-sm outline-none placeholder:text-faint"
              />
              <kbd className="rounded border border-border/70 px-1.5 text-[10px] text-faint">esc</kbd>
            </div>
            <div className="max-h-[52vh] overflow-y-auto p-2">
              {results.map((item, i) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    onMouseEnter={() => setCursor(i)}
                    onClick={() => onSelect(item.id)}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${
                      i === cursor ? "bg-accent/12 text-text" : "text-muted"
                    }`}
                  >
                    <Icon size={16} className={i === cursor ? "text-accent" : "text-faint"} />
                    <span className="flex-1">{item.label}</span>
                    {i === cursor && <CornerDownLeft size={14} className="text-faint" />}
                  </button>
                );
              })}
              {results.length === 0 && (
                <div className="px-3 py-6 text-center text-sm text-faint">No matches</div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
