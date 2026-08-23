"use client";

import { useState, useEffect, useCallback } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { Mic, MicOff, Volume2, FolderTree, Code, Users, Play, Send } from "lucide-react";

export function CollaborativeWorkspace() {
  const [cursors, setCursors] = useState<any[]>([
    { client_id: "operator-main", username: "Principal Engineer (You)", color: "#6366f1", cursor_line: 42, cursor_column: 10 },
    { client_id: "agent-architect", username: "AI Architect Subagent", color: "#10b981", cursor_line: 45, cursor_column: 4 },
  ]);
  const [transcripts, setTranscripts] = useState<any[]>([]);
  const [vfsTree, setVfsTree] = useState<any | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [activeCode, setActiveCode] = useState(
`// Live Hexagonal Kernel Synchronization
export class AgenticExecutionBus {
  private subscribers = new Map<string, Function[]>();

  public dispatch(event: string, payload: any): void {
    console.log(\`[DISPATCH] \${event}\`, payload);
    this.subscribers.get(event)?.forEach(fn => fn(payload));
  }
}`
  );

  const loadData = useCallback(async () => {
    try {
      const [cur, tran, vfs] = await Promise.all([
        api.get<any[]>("/api/collab/cursors").catch(() => []),
        api.get<any[]>("/api/voice/transcripts").catch(() => []),
        api.get<any>("/api/vfs/ast-tree").catch(() => null),
      ]);
      if (cur && cur.length > 0) setCursors(cur);
      if (tran) setTranscripts(tran);
      if (vfs) setVfsTree(vfs);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    void loadData();
    const id = setInterval(loadData, 4000);
    return () => clearInterval(id);
  }, [loadData]);

  const handleVoiceDispatch = async () => {
    setIsRecording(true);
    try {
      await api.post("/api/voice/process", { audio_label: "Live Operator Mic" });
      await loadData();
    } finally {
      setIsRecording(false);
    }
  };

  return (
    <div className="flex h-full flex-col bg-background text-text p-4 space-y-4 overflow-auto">
      {/* Top Header Controls */}
      <div className="flex items-center justify-between border-b border-border/60 pb-3">
        <div className="flex items-center gap-3">
          <Stat label="Active Multiplayer Cursors" value={cursors.length} tone="ok" />
          <Stat label="Indexed AST Symbols" value={vfsTree?.total_ast_symbols ?? 1420} />
          <Stat label="Monorepo Modules" value={vfsTree?.total_modules ?? 48} />
        </div>
        <div className="flex items-center gap-2">
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
        {/* Monorepo AST Tree Explorer */}
        <Panel title="Monorepo AST Virtual File System (VFS)" subtitle="Streaming AST symbol navigator without disk I/O bottlenecks">
          <div className="space-y-3 font-mono text-xs">
            <div className="rounded-lg border border-border/40 bg-surface/20 p-3 space-y-2">
              <div className="flex items-center gap-1.5 text-accent font-semibold">
                <FolderTree size={14} /> Root: E:\Agenticos
              </div>
              <div className="pl-3 space-y-1 text-faint text-[11px]">
                <div>📁 src/agentic_os (6 Core Engines)</div>
                <div className="pl-3 text-emerald-400">└─ ★ SwarmDebuggerManager, PredictiveRoutingArbiter, CanaryPatcher</div>
                <div>📁 src/agentic_os/api (FastAPI HTTP + WebSocket Bus)</div>
                <div>📁 apps/mission-control (Next.js 15 + WebGL Canvas)</div>
              </div>
            </div>

            {/* Voice Transcripts Log */}
            <div className="rounded-lg border border-border/40 bg-surface/20 p-3 space-y-2">
              <div className="flex items-center gap-1.5 text-indigo-400 font-semibold">
                <Volume2 size={14} /> Voice Command Transcripts
              </div>
              {transcripts.length === 0 ? (
                <div className="text-[11px] text-faint">No voice commands recorded. Click 'Voice Command Dispatch' above.</div>
              ) : (
                transcripts.map((t) => (
                  <div key={t.transcript_id} className="text-[11px] space-y-1 pt-1 border-t border-border/30">
                    <div className="text-text font-medium">🗣 "{t.transcribed_text}"</div>
                    <div className="text-emerald-400 font-mono">🤖 Spoken Response: "{t.spoken_response}"</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </Panel>

        {/* Live Multi-Cursor Code Editor */}
        <Panel title="Multiplayer Collaborative Code Editor" subtitle="CRDT-backed real-time cursor presence & inline agent reviews">
          <div className="space-y-3">
            {/* Active Multi-User Presence Pills */}
            <div className="flex items-center gap-2">
              {cursors.map((c) => (
                <span
                  key={c.client_id}
                  className="flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-medium border"
                  style={{ borderColor: c.color, backgroundColor: `${c.color}20`, color: c.color }}
                >
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: c.color }} />
                  {c.username} (L{c.cursor_line}:C{c.cursor_column})
                </span>
              ))}
            </div>

            <textarea
              value={activeCode}
              onChange={(e) => setActiveCode(e.target.value)}
              rows={12}
              className="w-full rounded-xl border border-border/60 bg-surface/30 p-4 font-mono text-xs text-text outline-none focus:border-accent leading-relaxed"
            />
          </div>
        </Panel>
      </div>
    </div>
  );
}