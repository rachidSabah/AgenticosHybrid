"use client";

import { useState, useEffect, useCallback } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { Mic, MicOff, Volume2, FolderTree, Play, CheckCircle2 } from "lucide-react";

export function CollaborativeWorkspace() {
  // Presence is rendered ONLY from real backend cursor data.
  const [cursors, setCursors] = useState<any[]>([]);
  const [transcripts, setTranscripts] = useState<any[]>([]);
  const [vfsTree, setVfsTree] = useState<any | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceInput, setVoiceInput] = useState("AgenticOS, run full regression check on all subsystems and report readiness score.");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [executionResult, setExecutionResult] = useState<string | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [activeCode, setActiveCode] = useState("");

  const loadData = useCallback(async () => {
    try {
      const [cur, tran, vfs] = await Promise.all([
        api.get<any[]>("/api/collab/cursors").catch(() => []),
        api.get<any[]>("/api/voice/transcripts").catch(() => []),
        api.get<any>("/api/vfs/ast-tree").catch(() => null),
      ]);
      // Render exactly what the backend returns — no optimistic local entries.
      setCursors(Array.isArray(cur) ? cur : []);
      setTranscripts(Array.isArray(tran) ? tran : []);
      setVfsTree(vfs ?? null);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    void loadData();
    const id = setInterval(loadData, 4000);
    return () => clearInterval(id);
  }, [loadData]);

  const handleVoiceDispatch = async () => {
    setIsRecording(true);
    setVoiceError(null);
    try {
      const res = await api.post<any>("/api/voice/process", { audio_label: voiceInput });
      // Only real API responses are kept — no optimistic fabricated replies.
      if (res && res.transcript_id) {
        setTranscripts((prev) => [res, ...prev]);
      }
      await loadData();
    } catch {
      setVoiceError("Voice dispatch failed: backend request error");
    } finally {
      setIsRecording(false);
    }
  };

  const handleExecuteCode = async () => {
    setIsExecuting(true);
    setExecutionResult(null);
    try {
      const res = await api.post<any>("/api/collab/execute", { code: activeCode });
      if (res && res.stdout) {
        setExecutionResult(res.stdout);
      }
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="flex h-full flex-col bg-background text-text p-4 space-y-4 overflow-auto">
      {/* Top Header Controls */}
      <div className="flex items-center justify-between border-b border-border/60 pb-3">
        <div className="flex items-center gap-3">
          <Stat label="Active Multiplayer Cursors" value={cursors.length} tone="ok" />
          <Stat label="Indexed AST Symbols" value={vfsTree?.total_ast_symbols ?? "—"} />
          <Stat label="Monorepo Modules" value={vfsTree?.total_modules ?? "—"} />
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={voiceInput}
            onChange={(e) => setVoiceInput(e.target.value)}
            className="w-80 rounded-lg border border-border/60 bg-surface/30 px-3 py-1.5 text-xs text-text outline-none focus:border-accent"
            placeholder="Voice command prompt..."
          />
          <button
            onClick={handleVoiceDispatch}
            disabled={isRecording}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
              isRecording ? "bg-rose-600 text-white animate-pulse" : "bg-accent text-white hover:bg-accent/80"
            }`}
          >
            {isRecording ? <><MicOff size={14} /> Processing Voice…</> : <><Mic size={14} /> Voice Command Dispatch</>}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-4">
        {/* Monorepo AST Tree Explorer — rendered only from real backend data */}
        <Panel title="Monorepo AST Virtual File System (VFS)" subtitle="Streaming AST symbol navigator without disk I/O bottlenecks">
          <div className="space-y-3 font-mono text-xs">
            <div className="rounded-lg border border-border/40 bg-surface/20 p-3 space-y-2">
              <div className="flex items-center gap-1.5 text-accent font-semibold">
                <FolderTree size={14} /> Root: {vfsTree?.root ?? "—"}
              </div>
              {Array.isArray(vfsTree?.tree) && vfsTree.tree.length > 0 ? (
                <div className="pl-3 space-y-1.5 text-faint text-[11px]">
                  {vfsTree.tree.map((node: any, i: number) => (
                    <div key={node.path || i} className="block">
                      {node.is_dir ? "📁" : "📄"} {node.path || node.name}
                      {Array.isArray(node.symbols) && node.symbols.length > 0 && (
                        <span className="text-faint/70"> ({node.symbols.slice(0, 3).join(", ")})</span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="pl-3 text-[11px] text-faint">No files shared in this session</div>
              )}
            </div>

            {/* Voice Transcripts Log */}
            <div className="rounded-lg border border-border/40 bg-surface/20 p-3 space-y-2">
              <div className="flex items-center gap-1.5 text-indigo-400 font-semibold">
                <Volume2 size={14} /> Voice Command Transcripts
              </div>
              {voiceError && (
                <div className="text-[11px] text-rose-400">{voiceError}</div>
              )}
              {transcripts.length === 0 ? (
                <div className="text-[11px] text-faint">No voice commands recorded. Click &apos;Voice Command Dispatch&apos; above.</div>
              ) : (
                transcripts.map((t) => (
                  <div key={t.transcript_id} className="text-[11px] space-y-1 pt-1 border-t border-border/30">
                    <div className="text-text font-medium">🗣 &ldquo;{t.transcribed_text}&rdquo;</div>
                    <div className="text-emerald-400 font-mono">🤖 Spoken Response: &ldquo;{t.spoken_response}&rdquo;</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </Panel>

        {/* Live Multi-Cursor Code Editor */}
        <Panel title="Multiplayer Collaborative Code Editor" subtitle="CRDT-backed real-time cursor presence & inline agent reviews">
          <div className="space-y-3">
            {/* Active Multi-User Presence Pills & Run Button */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {cursors.length === 0 ? (
                  <span className="text-[11px] text-faint">No collaborators connected</span>
                ) : (
                  cursors.map((c) => (
                    <span
                      key={c.client_id}
                      className="flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-medium border"
                      style={{ borderColor: c.color, backgroundColor: `${c.color}20`, color: c.color }}
                    >
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: c.color }} />
                      {c.username} (L{c.cursor_line}:C{c.cursor_column})
                    </span>
                  ))
                )}
              </div>
              <button
                onClick={handleExecuteCode}
                disabled={isExecuting}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-1 text-xs font-semibold text-white hover:bg-emerald-500 transition disabled:opacity-50"
              >
                <Play size={12} className={isExecuting ? "animate-spin" : ""} />
                {isExecuting ? "Executing…" : "Execute Code"}
              </button>
            </div>

            <textarea
              value={activeCode}
              onChange={(e) => setActiveCode(e.target.value)}
              rows={10}
              placeholder="Paste or select code to execute…"
              className="w-full rounded-xl border border-border/60 bg-surface/30 p-4 font-mono text-xs text-text outline-none focus:border-accent leading-relaxed"
            />

            {executionResult && (
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs font-mono text-emerald-400 flex items-center gap-2">
                <CheckCircle2 size={14} className="shrink-0" />
                <span>{executionResult}</span>
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}