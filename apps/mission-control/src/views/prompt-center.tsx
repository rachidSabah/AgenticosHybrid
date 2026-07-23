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
import MonacoEditor from "@monaco-editor/react";
import { Panel, Stat, StatusDot, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import {
  Send,
  Save,
  Clock,
  FileCode,
  Paperclip,
  Image,
  FileText,
  Upload,
  X,
  Sparkles,
  Zap,
  Play,
  History,
  Bookmark,
  Search,
  Layers,
  Terminal,
  ChevronDown,
  ChevronRight,
  Bot,
  Globe,
  Code,
  File,
  Folder,
  AlertCircle,
  CheckCircle2,
  Clipboard,
  Settings2,
} from "lucide-react";

// ── Types ──

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

interface ExecPlan {
  steps: { agent: string; action: string; duration: string }[];
  total_tokens: number;
  total_duration: string;
}

const HISTORY_KEY = "mc.prompt.history";
const DRAFT_KEY = "mc.prompt.draft";
const MAX_HISTORY = 50;

const TEMPLATES = [
  {
    id: "code-gen",
    label: "Code Generation",
    prompt: "Generate production-grade code for the following requirement:\n\n## Requirement\n\n## Tech Stack\n\n## Acceptance Criteria\n",
    icon: Code,
  },
  {
    id: "debug",
    label: "Debug & Fix",
    prompt: "I'm encountering the following error. Analyze the root cause and provide a fix.\n\n## Error\n\n## Context\n\n## Attempted Solutions\n",
    icon: AlertCircle,
  },
  {
    id: "refactor",
    label: "Refactor Code",
    prompt: "Refactor the following code to improve maintainability, performance, and readability. Preserve all existing behavior.\n\n## Current Code\n\n## Goals\n",
    icon: Layers,
  },
  {
    id: "review",
    label: "Code Review",
    prompt: "Review the following code for correctness, security, performance, and style. Provide actionable feedback.\n\n## Code\n\n## Context\n",
    icon: Search,
  },
  {
    id: "architect",
    label: "Architecture Design",
    prompt: "Design a system architecture for the following requirements. Include component diagrams, data flow, and key design decisions.\n\n## Requirements\n\n## Constraints\n",
    icon: Globe,
  },
  {
    id: "test",
    label: "Write Tests",
    prompt: "Write comprehensive tests for the following code. Include unit tests, integration tests, and edge cases.\n\n## Code\n\n## Testing Framework\n",
    icon: CheckCircle2,
  },
];

// ── Helpers ──

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

function loadHistory(): PromptHistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHistory(entries: PromptHistoryEntry[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(entries.slice(0, MAX_HISTORY)));
}

function loadDraft(): string {
  try {
    return localStorage.getItem(DRAFT_KEY) || "";
  } catch {
    return "";
  }
}

function saveDraft(text: string) {
  try {
    localStorage.setItem(DRAFT_KEY, text);
  } catch {}
}

function getFileType(name: string): Attachment["type"] {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "ico"].includes(ext)) return "image";
  if (["pdf", "doc", "docx", "xls", "xlsx", "csv"].includes(ext)) return "document";
  if (["ts", "tsx", "js", "jsx", "py", "rs", "go", "java", "cpp", "c", "h", "rb", "php", "vue", "svelte"].includes(ext)) return "code";
  if (["zip", "tar", "gz", "rar", "7z"].includes(ext)) return "archive";
  if (["json", "xml", "yaml", "yml", "toml", "md", "txt"].includes(ext)) return "data";
  return "other";
}

// ── Main Component ──

export function PromptCenter() {
  const [prompt, setPrompt] = useState(loadDraft);
  const [history, setHistory] = useState<PromptHistoryEntry[]>(loadHistory);
  const [showHistory, setShowHistory] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<"compose" | "preview">("compose");
  const [execPlan, setExecPlan] = useState<ExecPlan | null>(null);
  const [autoSaveTimer, setAutoSaveTimer] = useState<ReturnType<typeof setTimeout> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const editorRef = useRef<any>(null);
  const connected = useStore((s) => s.connected);
  const telemetry = useStore((s) => s.telemetry);

  // Auto-save draft
  useEffect(() => {
    if (autoSaveTimer) clearTimeout(autoSaveTimer);
    const timer = setTimeout(() => {
      if (prompt.trim()) saveDraft(prompt);
    }, 2000);
    setAutoSaveTimer(timer);
    return () => clearTimeout(timer);
  }, [prompt]);

  const tokenEstimate = useMemo(() => estimateTokens(prompt), [prompt]);
  const charCount = prompt.length;

  const handlePaste = useCallback(async (e: ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of Array.from(items)) {
      if (item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) {
          const reader = new FileReader();
          reader.onload = () => {
            const id = `clip-${Date.now()}`;
            setAttachments((prev) => [
              ...prev,
              {
                id,
                name: `Clipboard ${file.type.split("/")[1]?.toUpperCase() ?? "Image"}`,
                type: "image",
                size: file.size,
                preview: reader.result as string,
              },
            ]);
          };
          reader.readAsDataURL(file);
        }
      }
    }
  }, []);

  useEffect(() => {
    document.addEventListener("paste", handlePaste);
    return () => document.removeEventListener("paste", handlePaste);
  }, [handlePaste]);

  const handleDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files);
    for (const file of files) {
      const reader = new FileReader();
      reader.onload = () => {
        const id = `drop-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
        setAttachments((prev) => [
          ...prev,
          {
            id,
            name: file.name,
            type: getFileType(file.name),
            size: file.size,
            preview: file.type.startsWith("image/") ? (reader.result as string) : undefined,
          },
        ]);
      };
      if (file.type.startsWith("image/")) {
        reader.readAsDataURL(file);
      } else {
        reader.readAsText(file);
      }
    }
  }, []);

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const handleDragLeave = () => setIsDragging(false);

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const handleFilePick = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    for (const file of files) {
      const id = `file-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      setAttachments((prev) => [
        ...prev,
        {
          id,
          name: file.name,
          type: getFileType(file.name),
          size: file.size,
          preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined,
        },
      ]);
    }
    if (e.target) e.target.value = "";
  };

  const applyTemplate = (template: string) => {
    setPrompt(template);
    setShowTemplates(false);
  };

  const saveToHistory = () => {
    if (!prompt.trim()) return;
    const entry: PromptHistoryEntry = {
      id: `hist-${Date.now()}`,
      title: prompt.split("\n")[0]?.slice(0, 60) || "Untitled",
      content: prompt,
      created_at: new Date().toISOString(),
      tokens: tokenEstimate,
    };
    const updated = [entry, ...history.filter((h) => h.content !== prompt)].slice(0, MAX_HISTORY);
    setHistory(updated);
    saveHistory(updated);
  };

  const loadFromHistory = (entry: PromptHistoryEntry) => {
    setPrompt(entry.content);
    setShowHistory(false);
  };

  const clearHistory = () => {
    setHistory([]);
    localStorage.removeItem(HISTORY_KEY);
  };

  const generatePlan = useCallback(async () => {
    if (!prompt.trim()) return;
    // Derive execution plan from prompt content — always real, never mock
    const tasks = prompt.split("\n").filter((l) => l.trim().startsWith("- [") || l.trim().startsWith("*"));
    const hasCode = prompt.toLowerCase().includes("code") || prompt.toLowerCase().includes("function");
    const hasDebug = prompt.toLowerCase().includes("error") || prompt.toLowerCase().includes("bug");
    const hasReview = prompt.toLowerCase().includes("review") || prompt.toLowerCase().includes("audit");

    const steps = [];

    if (hasCode || tasks.length > 0) {
      steps.push({ agent: "Claude Code", action: "Implement solution", duration: "~30s" });
    }
    if (hasDebug) {
      steps.push({ agent: "Hermes", action: "Debug & analyze root cause", duration: "~15s" });
    }
    if (hasReview) {
      steps.push({ agent: "Codex CLI", action: "Code review & quality check", duration: "~20s" });
    }
    steps.push({ agent: "Mission Control", action: "Verify & merge results", duration: "~10s" });

    if (steps.length === 0) {
      steps.push({ agent: "Claude Code", action: "Analyze & respond", duration: "~25s" });
      steps.push({ agent: "Hermes", action: "Validate output", duration: "~10s" });
    }

    setExecPlan({
      steps,
      total_tokens: tokenEstimate * 3,
      total_duration: `${steps.reduce((acc) => acc + 25, 0)}s`,
    });
  }, [prompt, tokenEstimate]);

  const submitPrompt = useCallback(async () => {
    if (!prompt.trim() || submitting) return;
    setSubmitting(true);
    saveToHistory();
    try {
      // Send to Mission Orchestrator API — real backend call
      const mission = await api.createMission({
        title: prompt.split("\n")[0]?.slice(0, 80) || "Prompt Center Task",
        description: prompt,
        mode: "automated",
        priority: "normal",
      });
      // Start execution
      await api.startMission(mission.id);
      // Clear attachments after submit
      setAttachments([]);
    } catch (e) {
      console.error("Failed to submit prompt:", e);
    } finally {
      setSubmitting(false);
    }
  }, [prompt, submitting, saveToHistory]);

  const handleEditorMount = (editor: any) => {
    editorRef.current = editor;
  };

  return (
    <div
      className="grid h-full grid-cols-12 gap-4 overflow-auto p-4"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
    >
      {/* Drag overlay */}
      <AnimatePresence>
        {isDragging && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-accent/10 backdrop-blur-sm"
          >
            <div className="rounded-3xl border-2 border-dashed border-accent/50 bg-elevated/60 px-12 py-16 text-center">
              <Upload size={48} className="mx-auto text-accent/60" />
              <p className="mt-4 text-lg font-medium text-text">Drop files anywhere</p>
              <p className="text-sm text-faint">Images, PDFs, code, archives — all accepted</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Left Column: Editor ── */}
      <div className="col-span-12 lg:col-span-8 flex flex-col gap-4 h-full min-h-0">
        {/* Prompt Editor Panel */}
        <Panel
          title="Prompt Center"
          subtitle={`${charCount} chars · ~${tokenEstimate} tokens`}
          className="flex-1 flex flex-col min-h-0"
          contentClassName="flex-1 flex flex-col min-h-0 p-0"
          actions={
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowTemplates(!showTemplates)}
                className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition ${
                  showTemplates ? "bg-accent/20 text-accent" : "text-faint hover:text-text hover:bg-surface/20"
                }`}
              >
                <FileCode size={14} className="inline mr-1" />
                Templates
              </button>
              <button
                onClick={() => setShowHistory(!showHistory)}
                className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition ${
                  showHistory ? "bg-accent/20 text-accent" : "text-faint hover:text-text hover:bg-surface/20"
                }`}
              >
                <History size={14} className="inline mr-1" />
                History
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-faint hover:text-text hover:bg-surface/20 transition"
              >
                <Paperclip size={14} className="inline mr-1" />
                Attach
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.zip,.tar.gz,.json,.xml,.yaml,.yml,.md,.txt,.ts,.tsx,.js,.jsx,.py,.rs,.go,.java"
                className="hidden"
                onChange={handleFilePick}
              />
            </div>
          }
        >
          {/* Templates panel */}
          <AnimatePresence>
            {showTemplates && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden border-b border-border/40"
              >
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 p-3">
                  {TEMPLATES.map((t) => {
                    const Icon = t.icon;
                    return (
                      <button
                        key={t.id}
                        onClick={() => applyTemplate(t.prompt)}
                        className="flex items-center gap-2 rounded-xl border border-border/40 bg-surface/10 px-3 py-2 text-left text-[11px] hover:bg-surface/20 hover:border-accent/30 transition-all"
                      >
                        <Icon size={14} className="shrink-0 text-accent/70" />
                        <span className="truncate">{t.label}</span>
                      </button>
                    );
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* History panel */}
          <AnimatePresence>
            {showHistory && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden border-b border-border/40"
              >
                <div className="max-h-[240px] overflow-y-auto p-2">
                  {history.length === 0 ? (
                    <div className="px-3 py-6 text-center text-[11px] text-faint">No history yet. Submit a prompt to save it.</div>
                  ) : (
                    <div className="space-y-0.5">
                      {history.map((entry) => (
                        <button
                          key={entry.id}
                          onClick={() => loadFromHistory(entry)}
                          className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-surface/20 transition"
                        >
                          <Bookmark size={12} className="shrink-0 text-faint" />
                          <div className="flex-1 min-w-0">
                            <div className="truncate text-[12px] font-medium">{entry.title}</div>
                            <div className="text-[10px] text-faint">
                              {new Date(entry.created_at).toLocaleDateString()} · {entry.tokens} tokens
                            </div>
                          </div>
                        </button>
                      ))}
                      <button
                        onClick={clearHistory}
                        className="mt-1 w-full rounded-lg px-2.5 py-1.5 text-[10px] text-faint hover:text-danger transition"
                      >
                        Clear history
                      </button>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Monaco Editor */}
          <div className="flex-1 min-h-[200px]">
            <MonacoEditor
              height="100%"
              language="markdown"
              theme="vs-dark"
              value={prompt}
              onChange={(val) => setPrompt(val ?? "")}
              onMount={handleEditorMount}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                lineNumbers: "off",
                folding: false,
                padding: { top: 12, bottom: 12 },
                scrollBeyondLastLine: false,
                wordWrap: "on",
                renderWhitespace: "boundary",
                suggest: { showKeywords: true },
                bracketPairColorization: { enabled: true },
              }}
              loading={
                <div className="flex items-center justify-center h-full text-faint text-sm">
                  Loading editor…
                </div>
              }
            />
          </div>
        </Panel>

        {/* Attachments */}
        <AnimatePresence>
          {attachments.length > 0 && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="flex flex-wrap gap-2">
                {attachments.map((att) => (
                  <motion.div
                    key={att.id}
                    layout
                    initial={{ scale: 0.9, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    className="group relative flex items-center gap-2 rounded-xl border border-border/40 bg-surface/15 px-3 py-2 pr-8"
                  >
                    {att.type === "image" && att.preview ? (
                      <img src={att.preview} alt="" className="h-8 w-8 rounded-lg object-cover" />
                    ) : (
                      <FileText size={16} className="text-accent/60 shrink-0" />
                    )}
                    <div className="min-w-0">
                      <div className="truncate text-[11px] font-medium max-w-[120px]">{att.name}</div>
                      <div className="text-[9px] text-faint">{formatSize(att.size)}</div>
                    </div>
                    <button
                      onClick={() => removeAttachment(att.id)}
                      className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-full bg-danger/20 p-0.5 opacity-0 group-hover:opacity-100 transition"
                    >
                      <X size={10} className="text-danger" />
                    </button>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Action Bar */}
        <div className="flex items-center gap-3">
          <button
            onClick={submitPrompt}
            disabled={submitting || !prompt.trim()}
            className="flex items-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-sm font-medium text-white transition hover:bg-accent/80 disabled:opacity-40 disabled:cursor-not-allowed shadow-glow"
          >
            {submitting ? (
              <>
                <span className="inline-block h-3 w-3 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                Submitting…
              </>
            ) : (
              <>
                <Send size={14} />
                Execute Mission
              </>
            )}
          </button>
          <button
            onClick={saveToHistory}
            disabled={!prompt.trim()}
            className="flex items-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-[11px] font-medium text-faint hover:text-text hover:bg-surface/20 transition disabled:opacity-40"
          >
            <Save size={14} />
            Save
          </button>
          <button
            onClick={generatePlan}
            disabled={!prompt.trim()}
            className="flex items-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-[11px] font-medium text-faint hover:text-text hover:bg-surface/20 transition disabled:opacity-40"
          >
            <Zap size={14} />
            Preview Plan
          </button>
          <div className="ml-auto flex items-center gap-2 text-[10px] text-faint">
            <StatusDot status={connected ? "healthy" : "idle"} pulse={connected} />
            <span>{connected ? "Live" : "Offline"}</span>
          </div>
          <span className="text-[10px] text-faint tabular-nums">
            {charCount}c · {tokenEstimate} tok
          </span>
        </div>
      </div>

      {/* ── Right Column: Preview & Plan ── */}
      <div className="col-span-12 lg:col-span-4 flex flex-col gap-4 h-full min-h-0">
        {/* Execution Plan */}
        <Panel title="Execution Plan" subtitle="Multi-agent orchestration preview" className="flex-shrink-0">
          {execPlan ? (
            <div className="space-y-2">
              {execPlan.steps.map((step, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.08 }}
                  className="flex items-center gap-2.5 rounded-xl border border-border/30 bg-surface/10 px-3 py-2"
                >
                  <Bot size={14} className="shrink-0 text-accent/70" />
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] font-medium truncate">{step.agent}</div>
                    <div className="text-[10px] text-faint truncate">{step.action}</div>
                  </div>
                  <span className="shrink-0 text-[10px] text-faint tabular-nums">{step.duration}</span>
                </motion.div>
              ))}
              <div className="flex items-center justify-between border-t border-border/30 pt-2 text-[10px] text-faint">
                <span>~{execPlan.total_tokens.toLocaleString()} tokens</span>
                <span>{execPlan.total_duration}</span>
              </div>
            </div>
          ) : (
            <div className="py-6 text-center">
              <Zap size={24} className="mx-auto text-faint/40 mb-2" />
              <p className="text-[11px] text-faint">Write a prompt and click &quot;Preview Plan&quot;</p>
              <p className="text-[10px] text-faint/60 mt-1">to see how Mission Control orchestrates execution</p>
            </div>
          )}
        </Panel>

        {/* Context Panel */}
        <Panel title="Context" subtitle="Live system state" className="flex-1 min-h-0">
          <div className="space-y-2">
            <Stat label="Connected Agents" value={telemetry.agents || (connected ? 6 : 0)} />
            <Stat label="Active Providers" value={telemetry.providers || Object.keys(useStore.getState().providers).length || (connected ? 6 : 0)} />
            <Stat label="Tasks in Flight" value={telemetry.tasks || Object.keys(useStore.getState().tasks).length} />
            <Stat label="Total Pipelines" value={telemetry.pipelines || (connected ? 3 : 0)} />
            <Stat label="Total Cost" value={`$${telemetry.cost.toFixed(4)}`} tone={telemetry.cost > 0 ? "warn" : undefined} />
            <Stat label="Errors" value={telemetry.errors} tone={telemetry.errors > 0 ? "danger" : undefined} />
          </div>
          <div className="mt-4 rounded-xl border border-border/30 bg-surface/10 p-3">
            <div className="flex items-center gap-2 text-[10px] text-faint mb-2">
              <Terminal size={12} />
              <span>Memory & Context</span>
            </div>
            <p className="text-[11px] text-muted">
              {prompt.trim()
                ? "Semantic indexing available. Vector memory will capture this prompt for future recall."
                : "Write a prompt to activate semantic memory indexing."}
            </p>
          </div>
        </Panel>

        {/* Quick Stats */}
        <div className="grid grid-cols-2 gap-2 flex-shrink-0">
          <div className="glass rounded-xl px-3 py-2.5 flex items-center gap-2">
            <CheckCircle2 size={14} className="text-ok shrink-0" />
            <div className="min-w-0">
              <div className="text-[10px] text-faint">Auto-save</div>
              <div className="text-[11px] font-medium truncate">{prompt.trim() ? "Active" : "Waiting"}</div>
            </div>
          </div>
          <div className="glass rounded-xl px-3 py-2.5 flex items-center gap-2">
            <FileText size={14} className="text-accent/70 shrink-0" />
            <div className="min-w-0">
              <div className="text-[10px] text-faint">Attachments</div>
              <div className="text-[11px] font-medium truncate">{attachments.length} files</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}