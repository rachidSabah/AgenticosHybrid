"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Keyboard, Command, ChevronRight } from "lucide-react";
import { NAV } from "./nav";

interface Shortcut {
  key: string;
  description: string;
  category: string;
}

const SHORTCUTS: Shortcut[] = [
  { key: "⌘K", description: "Open Command Palette", category: "Navigation" },
  { key: "⌘⇧?", description: "Show Shortcuts", category: "Navigation" },
  { key: "⌘1-9", description: "Switch to view 1-9", category: "Navigation" },
  { key: "⌘⇧K", description: "Focus Command Palette input", category: "Navigation" },
  { key: "↑/↓", description: "Navigate palette results", category: "Navigation" },
  { key: "Enter", description: "Select palette item", category: "Navigation" },
  { key: "Esc", description: "Close palette / modal", category: "Navigation" },
  { key: "Tab", description: "Cycle focus in palette", category: "Navigation" },
  { key: "←/→/↑/↓", description: "Navigate graph nodes", category: "Graph" },
  { key: "Home", description: "Select first node", category: "Graph" },
  { key: "End", description: "Select last node", category: "Graph" },
  { key: "Enter / Space", description: "Center on selected node", category: "Graph" },
  { key: "Del / Backspace", description: "Delete selected node", category: "Graph" },
  { key: "⌘T", description: "Toggle theme", category: "UI" },
  { key: "⌘B", description: "Toggle sidebar", category: "UI" },
  { key: "⌘⇧P", description: "Export pipeline/workflow", category: "Actions" },
  { key: "⌘S", description: "Save workflow draft", category: "Actions" },
];

export function ShortcutsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [selectedCategory, setSelectedCategory] = useState("All");
  const previousActiveElement = useRef<HTMLElement | null>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  const categories = ["All", ...new Set(SHORTCUTS.map((s) => s.category))];

  const filteredShortcuts = selectedCategory === "All"
    ? SHORTCUTS
    : SHORTCUTS.filter((s) => s.category === selectedCategory);

  // Focus management
  useEffect(() => {
    if (open) {
      previousActiveElement.current = document.activeElement as HTMLElement;
      setTimeout(() => modalRef.current?.focus(), 0);
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
      previousActiveElement.current?.focus();
    }
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  // Keyboard handling
  useEffect(() => {
    if (!open) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        role="presentation"
      >
        <motion.div
          ref={modalRef}
          tabIndex={-1}
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
          onClick={(e) => e.stopPropagation()}
          className="glass-strong w-[720px] max-w-[92vw] max-h-[85vh] overflow-hidden rounded-2xl shadow-depth"
          role="dialog"
          aria-modal="true"
          aria-label="Keyboard shortcuts"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border/60 px-5 py-4">
            <div className="flex items-center gap-2">
              <Keyboard size={20} className="text-accent" aria-hidden="true" />
              <h2 className="text-base font-semibold">Keyboard Shortcuts</h2>
            </div>
            <button
              onClick={onClose}
              className="grid h-8 w-8 place-items-center rounded-xl text-muted hover:text-text hover:bg-surface/50 transition-colors"
              aria-label="Close shortcuts"
            >
              <X size={18} />
            </button>
          </div>

          {/* Content */}
          <div className="flex h-[calc(100%-56px)] overflow-hidden">
            {/* Category sidebar */}
            <nav
              className="w-40 border-r border-border/60 bg-surface/30 p-3 overflow-y-auto flex-shrink-0"
              aria-label="Shortcut categories"
            >
              <ul role="listbox" aria-label="Categories" className="space-y-1">
                {categories.map((cat) => (
                  <li key={cat}>
                    <button
                      role="option"
                      aria-selected={selectedCategory === cat}
                      onClick={() => setSelectedCategory(cat)}
                      className={`w-full text-left rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                        selectedCategory === cat
                          ? "bg-accent/12 text-accent"
                          : "text-muted hover:text-text hover:bg-surface/50"
                      }`}
                    >
                      {cat}
                    </button>
                  </li>
                ))}
              </ul>
            </nav>

            {/* Shortcuts list */}
            <div className="flex-1 overflow-y-auto p-5">
              <dl className="space-y-3">
                {filteredShortcuts.map((shortcut, i) => (
                  <div
                    key={`${shortcut.category}-${shortcut.key}-${i}`}
                    className="flex items-center gap-3 rounded-lg px-3 py-2.5 bg-surface/30 hover:bg-surface/50 transition-colors"
                  >
                    <kbd className="flex items-center gap-1.5 rounded bg-elevated border border-border/60 px-2.5 py-1 text-[11px] font-mono font-medium text-text min-w-[80px] justify-center">
                      {shortcut.key.split("+").map((k, idx) => (
                        <span key={idx} className="flex items-center gap-1">
                          {k.trim()}
                          {idx < shortcut.key.split("+").length - 1 && <span className="text-faint">+</span>}
                        </span>
                      ))}
                    </kbd>
                    <dt className="flex-1 text-sm text-text">{shortcut.description}</dt>
                    <dd className="text-faint text-[11px] uppercase tracking-wide">{shortcut.category}</dd>
                  </div>
                ))}
              </dl>
              {filteredShortcuts.length === 0 && (
                <div className="flex h-32 items-center justify-center text-center text-muted">
                  No shortcuts in this category
                </div>
              )}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}