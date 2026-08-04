"use client";

import { useEffect, useRef, useState } from "react";
import { Terminal as XTerminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { Terminal as TerminalIcon, X, Plus, ChevronDown, ChevronUp } from "lucide-react";

interface TerminalSession {
  id: string;
  worktreePath: string;
  term: XTerminal;
  fitAddon: FitAddon;
  ws: WebSocket | null;
}

export function TerminalPanel({
  worktreePath,
  onClose,
}: {
  worktreePath: string;
  onClose: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [session, setSession] = useState<TerminalSession | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(false);

  useEffect(() => {
    if (!containerRef.current || !worktreePath) return;

    const term = new XTerminal({
      theme: { background: "#0a0b10", foreground: "#e2e8f0", cursor: "#f59e0b" },
      fontSize: 12,
      fontFamily: "monospace",
      cursorBlink: true,
      scrollback: 1000,
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(containerRef.current);
    fitAddon.fit();

    const sessionId = `term-${Date.now()}`;
    const wsUrl = `ws://localhost:8000/ws/terminal?path=${encodeURIComponent(worktreePath)}`;

    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        term.writeln("\x1b[32m✓ Connected to terminal\x1b[0m");
        term.writeln(`\x1b[36mWorktree: ${worktreePath}\x1b[0m\r\n`);
      };
      ws.onmessage = (ev) => {
        term.write(ev.data);
      };
      ws.onclose = () => {
        term.writeln("\r\n\x1b[31m✗ Terminal session ended\x1b[0m");
      };
      ws.onerror = () => {
        term.writeln("\r\n\x1b[31m✗ Terminal connection failed\x1b[0m");
      };
    } catch {
      term.writeln("\x1b[31m✗ Failed to connect\x1b[0m");
    }

    term.onData((data) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    const s: TerminalSession = {
      id: sessionId, worktreePath, term, fitAddon, ws,
    };
    setSession(s);

    const resizeObserver = new ResizeObserver(() => fitAddon.fit());
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      if (ws) ws.close();
      term.dispose();
    };
  }, [worktreePath]);

  return (
    <div className="border-t border-white/10 bg-[#0a0b10]">
      <div className="flex items-center justify-between px-3 py-1.5">
        <div className="flex items-center gap-2">
          <TerminalIcon size={12} className="text-emerald-400" />
          <span className="text-[10px] font-semibold text-white/60">Terminal</span>
          <span className="font-mono text-[9px] text-white/30 truncate max-w-[200px]">{worktreePath}</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setIsCollapsed(!isCollapsed)} className="rounded p-0.5 text-white/40 hover:bg-white/10 hover:text-white">
            {isCollapsed ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
          <button onClick={onClose} className="rounded p-0.5 text-white/40 hover:bg-white/10 hover:text-white">
            <X size={12} />
          </button>
        </div>
      </div>
      {!isCollapsed && (
        <div ref={containerRef} className="h-48 px-2 pb-2" />
      )}
    </div>
  );
}
