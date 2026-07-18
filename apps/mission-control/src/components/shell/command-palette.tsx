"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
  const inputRef = useRef<HTMLInputElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return NAV;
    return NAV.filter(
      (n) => n.label.toLowerCase().includes(q) || n.id.includes(q) || n.hint === q,
    );
  }, [query]);

  // Focus trap and restore
  useEffect(() => {
    if (open) {
      previousActiveElement.current = document.activeElement as HTMLElement;
      setQuery("");
      setCursor(0);
      // Focus input after render
      setTimeout(() => inputRef.current?.focus(), 0);
    } else if (previousActiveElement.current) {
      previousActiveElement.current.focus();
    }
  }, [open]);

  // Keyboard navigation
  useEffect(() => {
    if (!open) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setCursor((c) => Math.min(c + 1, results.length - 1));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setCursor((c) => Math.max(c - 1, 0));
      }
      if (e.key === "Enter" && results[cursor]) {
        onSelect(results[cursor].id);
      }
      if (e.key === "Tab") {
        // Trap focus within palette
        e.preventDefault();
        if (e.shiftKey) {
          // Shift+Tab: focus last result or input
          const buttons = document.querySelectorAll('[role="option"]');
          (buttons[buttons.length - 1] as HTMLElement)?.focus();
        } else {
          // Tab: focus first result or input
          inputRef.current?.focus();
        }
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, results, cursor, onSelect, onClose]);

  // Focus trap: prevent focus from leaving the modal
  useEffect(() => {
    if (!open) return;

    const handleFocusIn = (e: FocusEvent) => {
      const modal = e.target as HTMLElement;
      const palette = modal.closest('[role="dialog"]');
      if (!palette && modal !== inputRef.current) {
        inputRef.current?.focus();
      }
    };

    document.addEventListener("focusin", handleFocusIn);
    return () => document.removeEventListener("focusin", handleFocusIn);
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-[14vh] backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          role="presentation"
        >
          <motion.div
            ref={(el) => {
              if (el) {
                el.setAttribute("role", "dialog");
                el.setAttribute("aria-modal", "true");
                el.setAttribute("aria-label", "Command Palette");
              }
            }}
            initial={{ opacity: 0, scale: 0.97, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: -8 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            onClick={(e) => e.stopPropagation()}
            className="glass-strong w-[560px] max-w-[92vw] overflow-hidden rounded-2xl shadow-depth"
          >
            <div className="flex items-center gap-2.5 border-b border-border/60 px-4 py-3">
              <Search size={16} className="text-faint" aria-hidden="true" />
              <input
                ref={inputRef}
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search views, commands…"
                className="flex-1 bg-transparent text-sm outline-none placeholder:text-faint"
                aria-label="Search views and commands"
                aria-controls="palette-results"
                aria-activedescendant={results[cursor]?.id ? `palette-option-${results[cursor].id}` : undefined}
              />
              <kbd className="rounded border border-border/70 px-1.5 text-[10px] text-faint">esc</kbd>
            </div>
            <div id="palette-results" className="max-h-[52vh] overflow-y-auto p-2" role="listbox">
              {results.map((item, i) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    id={`palette-option-${item.id}`}
                    onMouseEnter={() => setCursor(i)}
                    onClick={() => onSelect(item.id)}
                    role="option"
                    aria-selected={i === cursor}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${
                      i === cursor ? "bg-accent/12 text-text" : "text-muted"
                    }`}
                  >
                    <Icon size={16} className={i === cursor ? "text-accent" : "text-faint"} aria-hidden="true" />
                    <span className="flex-1">{item.label}</span>
                    {i === cursor && <CornerDownLeft size={14} className="text-faint" aria-hidden="true" />}
                  </button>
                );
              })}
              {results.length === 0 && (
                <div className="px-3 py-6 text-center text-sm text-faint" role="status">No matches</div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
