"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type ChangeEvent,
} from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import {
  ArrowUp,
  Paperclip,
  Image as ImageIcon,
  Sliders,
  Sparkles,
  Zap,
  Code,
  FileText,
  AlertCircle,
  Globe,
  CheckCircle2,
  Layers,
  X,
  History,
  Bookmark,
  ChevronDown,
  Bot,
  Brain,
  Cpu,
  Shield,
  HelpCircle,
  Plus,
} from "lucide-react";

interface PromptHistoryEntry {
  id: string;
  title: string;
  content: string;
  created_at: string;
  tokens: number;
}

interface Attachment {
  id: string;
  name: string;
  type: "image" | "document" | "code" | "archive" | "data" | "other";
  size: number;
  preview?: string;
}

const HISTORY_KEY = "mc.prompt.history";
const DRAFT_KEY = "mc.prompt.draft";
const MAX_HISTORY = 50;

const CLAUDE_STYLE_STARTERS = [
  {
    id: "architect",
    title: "Design a clean architecture",
    subtitle: "Component diagrams, system flow & data contracts",
    icon: Globe,
    prompt: "Design a clean system architecture for the following requirements. Include component diagrams, data contracts, and key design decisions.\n\n## Requirements\n",
  },
  {
    id: "code-gen",
    title: "Implement a production feature",
    subtitle: "Typescript, React, & Node.js clean implementation",
    icon: Code,
    prompt: "Implement a production-grade feature with full error handling and type safety.\n\n## Feature Description\n",
  },
  {
    id: "debug",
    title: "Debug & analyze root cause",
    subtitle: "Trace error stack & suggest precise fixes",
    icon: AlertCircle,
    prompt: "Analyze the root cause of this error and provide an authoritative fix.\n\n## Error Stack / Output\n",
  },
  {
    id: "refactor",
    title: "Refactor for performance & style",
    subtitle: "Optimize runtime efficiency & readability",
    icon: Layers,
    prompt: "Refactor this code to improve performance and maintainability while preserving exact behavior.\n\n## Code\n",
  },
];

const AVAILABLE_MODELS = [
  { id: "claude-3-7-sonnet", name: "Claude 3.7 Sonnet", provider: "Anthropic", tag: "Most Intelligent" },
  { id: "claude-3-5-haiku", name: "Claude 3.5 Haiku", provider: "Anthropic", tag: "Fast & Light" },
  { id: "hermes-3-405b", name: "Hermes 3 (405B)", provider: "Nous Research", tag: "Reasoning" },
  { id: "opencode-agent", name: "OpenCode Engine", provider: "OpenAI", tag: "Autonomous" },
  { id: "gemini-2.5-pro", name: "Gemini 2.5 Pro", provider: "Google", tag: "Multimodal" },
];

export function PromptCenter() {
  const [prompt, setPrompt] = useState<string>(() => {
    try {
      return localStorage.getItem(DRAFT_KEY) || "";
    } catch {
      return "";
    }
  });

  const [history, setHistory] = useState<PromptHistoryEntry[]>(() => {
    try {
      const raw = localStorage.getItem(HISTORY_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });

  const [selectedModel, setSelectedModel] = useState(AVAILABLE_MODELS[0]);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(true);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const connected = useStore((s) => s.connected);

  // Auto-resize textarea like claude.ai
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 320)}px`;
    }
  }, [prompt]);

  // Draft auto-save
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(DRAFT_KEY, prompt);
      } catch {}
    }, 1000);
    return () => clearTimeout(timer);
  }, [prompt]);

  const saveToHistory = useCallback(() => {
    if (!prompt.trim()) return;
    const entry: PromptHistoryEntry = {
      id: `hist-${Date.now()}`,
      title: prompt.split("\n")[0]?.slice(0, 50) || "Untitled Prompt",
      content: prompt,
      created_at: new Date().toISOString(),
      tokens: Math.ceil(prompt.length / 4),
    };
    const updated = [entry, ...history.filter((h) => h.content !== prompt)].slice(0, MAX_HISTORY);
    setHistory(updated);
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
    } catch {}
  }, [prompt, history]);

  const handleSubmit = async () => {
    if (!prompt.trim() || submitting) return;
    setSubmitting(true);
    saveToHistory();
    try {
      const mission = await api.createMission({
        title: prompt.split("\n")[0]?.slice(0, 60) || "Claude Prompt Task",
        description: prompt,
        priority: "high",
        execution_mode: "hybrid",
      });
      if (mission?.id) {
        await api.startMission(mission.id);
      }
      setPrompt("");
      setAttachments([]);
    } catch (e) {
      console.error("Submission failed:", e);
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFilePick = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    for (const file of files) {
      const id = `att-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      setAttachments((prev) => [
        ...prev,
        {
          id,
          name: file.name,
          type: file.type.startsWith("image/") ? "image" : "document",
          size: file.size,
          preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined,
        },
      ]);
    }
    if (e.target) e.target.value = "";
  };

  return (
    <div className="flex h-full w-full flex-col items-center justify-between overflow-y-auto bg-[#0d0e12] px-4 py-8 text-[#e2e8f0]">
      {/* ── Top Header Navigation ── */}
      <div className="w-full max-w-4xl flex items-center justify-between">
        {/* Model Selector Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowModelPicker(!showModelPicker)}
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-xs font-semibold text-white backdrop-blur-lg hover:bg-white/10 transition shadow-sm"
          >
            <Sparkles size={15} className="text-amber-400" />
            <span>{selectedModel.name}</span>
            <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9px] text-amber-300 font-mono">
              {selectedModel.tag}
            </span>
            <ChevronDown size={14} className="text-white/50" />
          </button>

          <AnimatePresence>
            {showModelPicker && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 6 }}
                className="absolute left-0 top-11 z-50 w-64 rounded-2xl border border-white/10 bg-[#161822]/95 p-2 shadow-2xl backdrop-blur-xl"
              >
                {AVAILABLE_MODELS.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => {
                      setSelectedModel(m);
                      setShowModelPicker(false);
                    }}
                    className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-xs transition ${
                      selectedModel.id === m.id ? "bg-amber-500/15 text-amber-300 font-medium" : "text-white/80 hover:bg-white/5"
                    }`}
                  >
                    <div>
                      <div className="font-semibold">{m.name}</div>
                      <div className="text-[10px] text-white/40">{m.provider}</div>
                    </div>
                    <span className="rounded bg-white/5 px-1.5 py-0.5 text-[9px] text-white/60">
                      {m.tag}
                    </span>
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setThinkingMode(!thinkingMode)}
            className={`flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-medium transition ${
              thinkingMode
                ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                : "border-white/10 bg-white/5 text-white/60 hover:text-white"
            }`}
          >
            <Brain size={14} />
            <span>Extended Thinking</span>
          </button>

          <button
            onClick={() => setShowHistory(!showHistory)}
            className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-white/80 hover:bg-white/10 hover:text-white transition"
          >
            <History size={14} />
            <span>History</span>
          </button>
        </div>
      </div>

      {/* ── Main Center Content (Claude.ai /new style) ── */}
      <div className="my-auto w-full max-w-3xl flex flex-col items-center text-center space-y-6">
        {/* Welcome Greeting */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-2"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-4 py-1 text-xs font-medium text-amber-300">
            <Sparkles size={13} />
            Mission Control AI Assistant
          </div>
          <h1 className="text-3xl sm:text-4xl font-serif font-normal text-white tracking-tight">
            What can I help you build today?
          </h1>
        </motion.div>

        {/* ── Prompt Input Container (Claude Glass Card) ── */}
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="w-full rounded-3xl border border-white/10 bg-[#161822]/80 p-4 shadow-2xl backdrop-blur-2xl transition-all focus-within:border-amber-500/50 focus-within:ring-2 focus-within:ring-amber-500/20"
        >
          {/* Attachments preview list */}
          {attachments.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-2 text-left">
              {attachments.map((att) => (
                <div key={att.id} className="group relative flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white/90">
                  {att.preview ? (
                    <img src={att.preview} alt="" className="h-6 w-6 rounded object-cover" />
                  ) : (
                    <FileText size={14} className="text-amber-400" />
                  )}
                  <span className="truncate max-w-[140px] text-[11px] font-medium">{att.name}</span>
                  <button
                    onClick={() => setAttachments((prev) => prev.filter((a) => a.id !== att.id))}
                    className="text-white/40 hover:text-red-400 ml-1"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Prompt Textarea */}
          <textarea
            ref={textareaRef}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Reply to Mission Control or paste code..."
            rows={2}
            className="w-full resize-none bg-transparent px-2 py-1 text-sm sm:text-base text-white placeholder-white/40 outline-none font-sans leading-relaxed"
          />

          {/* Input Card Footer Actions */}
          <div className="mt-3 flex items-center justify-between pt-2 border-t border-white/5 text-xs">
            <div className="flex items-center gap-2 text-white/50">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 hover:bg-white/10 hover:text-white transition"
              >
                <Paperclip size={16} />
                <span className="text-[11px]">Add content</span>
              </button>

              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={handleFilePick}
              />
            </div>

            <div className="flex items-center gap-3">
              <span className="text-[10px] text-white/40 font-mono">
                {prompt.length} chars
              </span>

              {/* Submit Button (Claude Circular / Pill Submit) */}
              <button
                onClick={handleSubmit}
                disabled={!prompt.trim() || submitting}
                className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500 text-black hover:bg-amber-400 disabled:opacity-30 disabled:hover:bg-amber-500 transition shadow-lg shadow-amber-500/20"
              >
                {submitting ? (
                  <span className="h-4 w-4 rounded-full border-2 border-black/30 border-t-black animate-spin" />
                ) : (
                  <ArrowUp size={18} strokeWidth={2.5} />
                )}
              </button>
            </div>
          </div>
        </motion.div>

        {/* ── Claude Style Starter Prompt Cards ── */}
        <div className="grid w-full grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
          {CLAUDE_STYLE_STARTERS.map((s) => {
            const Icon = s.icon;
            return (
              <button
                key={s.id}
                onClick={() => setPrompt(s.prompt)}
                className="flex items-start gap-3 rounded-2xl border border-white/5 bg-white/[0.02] p-3.5 text-left hover:border-amber-500/30 hover:bg-white/[0.05] transition-all group"
              >
                <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-2 text-amber-400 group-hover:scale-105 transition-transform">
                  <Icon size={16} />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white/90 group-hover:text-amber-300 transition-colors">
                    {s.title}
                  </div>
                  <div className="text-[11px] text-white/40 mt-0.5">
                    {s.subtitle}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── History Drawer Modal ── */}
      <AnimatePresence>
        {showHistory && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-end bg-black/60 backdrop-blur-md p-4"
          >
            <motion.div
              initial={{ x: 300 }}
              animate={{ x: 0 }}
              exit={{ x: 300 }}
              className="h-full w-full max-w-md rounded-3xl border border-white/10 bg-[#161822] p-6 shadow-2xl flex flex-col justify-between"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div className="flex items-center gap-2">
                  <History size={18} className="text-amber-400" />
                  <h2 className="text-sm font-semibold text-white">Prompt History</h2>
                </div>
                <button onClick={() => setShowHistory(false)} className="text-white/40 hover:text-white">
                  <X size={16} />
                </button>
              </div>

              <div className="my-4 flex-1 overflow-y-auto space-y-2">
                {history.length === 0 ? (
                  <div className="py-12 text-center text-xs text-white/40">No prompts saved yet.</div>
                ) : (
                  history.map((h) => (
                    <button
                      key={h.id}
                      onClick={() => {
                        setPrompt(h.content);
                        setShowHistory(false);
                      }}
                      className="w-full rounded-2xl border border-white/5 bg-white/5 p-3 text-left hover:border-amber-500/30 hover:bg-white/10 transition"
                    >
                      <div className="truncate text-xs font-semibold text-white">{h.title}</div>
                      <div className="text-[10px] text-white/40 mt-1 flex justify-between">
                        <span>{new Date(h.created_at).toLocaleDateString()}</span>
                        <span>~{h.tokens} tokens</span>
                      </div>
                    </button>
                  ))
                )}
              </div>

              <button
                onClick={() => {
                  setHistory([]);
                  localStorage.removeItem(HISTORY_KEY);
                }}
                className="w-full rounded-xl border border-red-500/30 bg-red-500/10 py-2.5 text-xs font-semibold text-red-400 hover:bg-red-500/20 transition"
              >
                Clear History
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Footer System Status ── */}
      <div className="w-full max-w-4xl flex items-center justify-between text-[11px] text-white/40 pt-4 border-t border-white/5">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-emerald-500"}`} />
          <span>{connected ? "EventBus Live" : "Mission Control Core Active"}</span>
        </div>
        <div>Claude 3.7 & Multi-Agent Orchestration Ready</div>
      </div>
    </div>
  );
}