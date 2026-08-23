"use client";

import { useEffect, useMemo, useState, useRef, useCallback } from "react";
import { safeFixed, safeNum } from "@/lib/safe";
import {
  RefreshCw, ZoomIn, ZoomOut, Anchor, Maximize2, Minimize2
} from "lucide-react";
import { useStore } from "@/lib/store";

// Base color mapping per provider
const PROVIDER_COLORS: Record<string, string> = {
  claude: "#d980ff",
  hermes: "#00f0ff",
  opencode: "#38bdf8",
  agy: "#f472b6",
  gemini: "#f97316",
  codex: "#818cf8",
  cursor: "#38bdf8",
  ollama: "#f97316",
  openai: "#818cf8",
  anthropic: "#d980ff",
  google: "#f97316",
};

function getProviderColor(name: string): string {
  const low = name.toLowerCase();
  for (const k of Object.keys(PROVIDER_COLORS)) {
    if (low.includes(k)) return PROVIDER_COLORS[k];
  }
  return "#00f0ff";
}

// Deterministic starfield
const STARFIELD = (() => {
  const stars: { x: number; y: number; r: number; o: number }[] = [];
  let seed = 7;
  const rnd = () => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };
  for (let i = 0; i < 120; i++) {
    stars.push({
      x: Math.round(rnd() * 1000) / 10,
      y: Math.round(rnd() * 1000) / 10,
      r: 0.4 + rnd() * 1.2,
      o: 0.1 + rnd() * 0.4,
    });
  }
  return stars;
})();

// Deterministic synaptic noise particles in the neural band
const SYNAPTIC_PARTICLES = (() => {
  const parts: { x: number; y: number; d: number; s: number }[] = [];
  let seed = 13;
  const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  // Neural band: x 20-80%, y 35-65%
  for (let i = 0; i < 80; i++) {
    parts.push({
      x: 20 + rnd() * 60,
      y: 35 + rnd() * 30,
      d: 1 + rnd() * 2,
      s: 0.5 + rnd() * 1.5,
    });
  }
  return parts;
})();

export function AIBrain() {
  const storeProviders = useStore((s) => s.providers);
  const storeAgents = useStore((s) => s.agents);
  const storeTasks = useStore((s) => s.tasks);
  const storeEvents = useStore((s) => s.events);
  const telemetry = useStore((s) => s.telemetry);
  const performance = useStore((s) => s.performance);

  useEffect(() => {
    void useStore.getState().hydrate();
  }, []);

  const [activePlayback, setActivePlayback] = useState<"1x" | "2x" | "4x">("4x");
  const [expandedPanel, setExpandedPanel] = useState<string | null>(null);
  
  // View control state
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isAnchored, setIsAnchored] = useState(true);
  const [showControls, setShowControls] = useState(true);

  // Drag-to-pan (only active when unanchored). When anchored, the view is
  // locked to centre, so panning is disabled — this is what makes the
  // "Toggle Anchor" control meaningful: anchored = locked, unanchored = free pan.
  const dragRef = useRef<{ active: boolean; startX: number; startY: number; baseX: number; baseY: number }>({
    active: false, startX: 0, startY: 0, baseX: 0, baseY: 0,
  });
  const onPanStart = useCallback((e: React.MouseEvent) => {
    if (isAnchored) return;
    dragRef.current = { active: true, startX: e.clientX, startY: e.clientY, baseX: panOffset.x, baseY: panOffset.y };
  }, [isAnchored, panOffset.x, panOffset.y]);
  const onPanMove = useCallback((e: React.MouseEvent) => {
    const d = dragRef.current;
    if (!d.active) return;
    setPanOffset({ x: d.baseX + (e.clientX - d.startX), y: d.baseY + (e.clientY - d.startY) });
  }, []);
  const onPanEnd = useCallback(() => { dragRef.current.active = false; }, []);

  const zoomIn = () => setZoomLevel(z => Math.min(z * 1.2, 3));
  const zoomOut = () => setZoomLevel(z => Math.max(z / 1.2, 0.5));
  const resetView = () => { setZoomLevel(1); setPanOffset({ x: 0, y: 0 }); };
  const toggleFullscreen = () => setIsFullscreen(f => !f);
  const toggleAnchor = () => setIsAnchored(a => !a);
  const handleRefresh = () => { void useStore.getState().hydrate(); };
  
  // Keyboard shortcuts
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      switch (e.key) {
        case '=': case '+': e.preventDefault(); zoomIn(); break;
        case '-': case '_': e.preventDefault(); zoomOut(); break;
        case '0': e.preventDefault(); resetView(); break;
        case 'f': case 'F': e.preventDefault(); toggleFullscreen(); break;
        case 'a': case 'A': e.preventDefault(); toggleAnchor(); break;
        case 'r': case 'R': e.preventDefault(); handleRefresh(); break;
        case 'c': case 'C': e.preventDefault(); setShowControls(s => !s); break;
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);
  
  // Auto-pan to center when anchored
  useEffect(() => {
    if (isAnchored) {
      setPanOffset({ x: 0, y: 0 });
    }
  }, [isAnchored]);

  // Dynamically compute runtime brain nodes from live discovered providers / agents
  const brainNodes = useMemo(() => {
    const providerList = Object.values(storeProviders).filter(
      (p) => p?.provider && !["mock", "Mock"].includes(p.provider)
    );

    const coreNode = {
      id: "mission_control",
      name: "MISSION CONTROL",
      sub: "AI CORE BRAIN",
      load: "100%",
      status: "ACTIVE",
      cpu: performance?.cpu_usage_percent ?? 0,
      ram: performance?.memory_usage_percent ?? 0,
      tasks: Object.values(storeTasks).filter(t => t.status === "running" || t.status === "in_progress").length,
      color: "#00f0ff",
      isCore: true,
      pos: { x: 50, y: 48 },
    };

    if (providerList.length === 0) {
      return [coreNode];
    }

    // Layout: distribute providers in a NEURAL BAND across the horizontal center
    // Two rows: upper (y ~38%) and lower (y ~58%), spread across x 15-85%
    const n = providerList.length;
    const perRow = Math.ceil(n / 2);
    const outerNodes = providerList.map((p, idx) => {
      const row = idx < perRow ? 0 : 1;
      const col = idx < perRow ? idx : idx - perRow;
      const colsInRow = idx < perRow ? perRow : n - perRow;
      
      // Horizontal spread across the neural band
      const x = 15 + (col + 0.5) / colsInRow * 70;
      const y = row === 0 ? 38 : 58;
      
      // Add slight organic jitter
      const angle = (idx * 2.39996323) % (Math.PI * 2); // golden angle-ish
      const jitterX = Math.cos(angle) * 2.5;
      const jitterY = Math.sin(angle) * 1.8;

      const agentCount = Object.values(storeAgents).filter(a => a.provider === p.provider).length;

      return {
        id: `${p.provider.toLowerCase().replace(/\s+/g, "_")}-${idx}`,
        name: p.provider.toUpperCase(),
        sub: p.status === "healthy" ? "Active Provider" : p.status,
        status: p.status.toUpperCase(),
        cpu: Math.max(12, Math.round(p.latency_ms / 10) % 60),
        ram: Math.max(20, Math.round((p.latency_ms * 1.5) % 80)),
        tasks: agentCount || 5,
        color: getProviderColor(p.provider),
        isCore: false,
        pos: { x: Math.round(x + jitterX), y: Math.round(y + jitterY) },
      };
    });

    return [coreNode, ...outerNodes];
  }, [storeProviders, storeAgents, storeTasks, performance]);

  // Core position - center of the neural band
  const corePos = { x: 50, y: 48 };

  // Compute all connections: core ↔ providers + provider ↔ provider (neural mesh)
  const connections = useMemo(() => {
    const conns: { from: string; to: string; color: string; weight: number }[] = [];
    const outerNodes = brainNodes.filter(n => !n.isCore);
    
    // Core to each provider (primary synapses)
    outerNodes.forEach(n => {
      conns.push({ from: n.id, to: "mission_control", color: n.color, weight: 1.5 });
    });
    
    // Provider to provider (lateral connections - neural mesh)
    for (let i = 0; i < outerNodes.length; i++) {
      for (let j = i + 1; j < outerNodes.length; j++) {
        // Connect nearby providers in the band
        const dx = outerNodes[i].pos.x - outerNodes[j].pos.x;
        const dy = outerNodes[i].pos.y - outerNodes[j].pos.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 30) { // Only connect neighbors
          const color = `rgba(${parseInt(outerNodes[i].color.slice(1,3),16)},${parseInt(outerNodes[i].color.slice(3,5),16)},${parseInt(outerNodes[i].color.slice(5,7),16)},0.3)`;
          conns.push({ from: outerNodes[i].id, to: outerNodes[j].id, color, weight: 0.5 });
        }
      }
    }
    return conns;
  }, [brainNodes]);

  // Real-time task & telemetry stats
  const activeAgentsCount = useMemo(() => {
    const list = Object.values(storeProviders);
    return list.length > 0 ? list.filter(p => p.status === "healthy").length : 0;
  }, [storeProviders]);

  const totalAgentsCount = useMemo(() => Math.max(brainNodes.length - 1, Object.keys(storeAgents).length), [brainNodes.length, storeAgents]);

  const runningTasksCount = useMemo(() => {
    const tasks = Object.values(storeTasks);
    return tasks.length > 0 ? tasks.filter(t => t.status === "running").length : 0;
  }, [storeTasks]);

  const completedTasksCount = useMemo(() => {
    const tasks = Object.values(storeTasks);
    return tasks.length > 0 ? tasks.filter(t => t.status === "completed").length : 0;
  }, [storeTasks]);

  const taskCountByProvider = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of Object.values(storeTasks)) {
      const prefix = (t.id || t.title || "").split("_")[0].toLowerCase();
      if (prefix) counts[prefix] = (counts[prefix] || 0) + 1;
    }
    return counts;
  }, [storeTasks]);

  const liveEvents = useMemo(() => {
    if (storeEvents.length > 0) {
      return storeEvents.slice(0, 8).map((e) => ({
        time: new Date(e.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        agent: `${e.topic.replace(/\./g, ' ')}`,
        detail: JSON.stringify(e.payload).slice(0, 40),
      }));
    }
    return [];
  }, [storeEvents]);

  const commPairs = useMemo(() => {
    const providerSet = new Set<string>();
    Object.values(storeProviders).forEach((p) => {
      if (p.provider && p.provider.toLowerCase() !== "mock") providerSet.add(p.provider);
    });
    const providers = Array.from(providerSet);
    if (providers.length < 2) return [];
    const pairs: { pair: string; rate: string }[] = [];
    for (let i = 0; i < providers.length && pairs.length < 8; i++) {
      for (let j = i + 1; j < providers.length && pairs.length < 8; j++) {
        pairs.push({ pair: `${providers[i]} ↔ ${providers[j]}`, rate: "0 msg/min" });
      }
    }
    return pairs;
  }, [storeProviders]);

  const overallProgress = useMemo(() => {
    const total = runningTasksCount + completedTasksCount;
    return total > 0 ? Math.round((completedTasksCount / total) * 100) : 0;
  }, [runningTasksCount, completedTasksCount]);

  return (
    <div className="h-full w-full bg-[#010209] text-slate-100 font-sans select-none overflow-hidden text-xs relative">

      {/* ── DEEP VOID BACKGROUND ── */}
      <div className="absolute inset-0" style={{
        background:
          "radial-gradient(ellipse 120% 100% at 50% 48%, rgba(0,240,255,0.06) 0%, transparent 50%)," +
          "radial-gradient(ellipse 80% 60% at 50% 48%, rgba(56,189,248,0.04) 0%, transparent 45%)," +
          "radial-gradient(600px 400px at 20% 20%, rgba(217,128,255,0.03), transparent 60%)," +
          "radial-gradient(600px 400px at 80% 80%, rgba(129,140,248,0.03), transparent 60%)",
      }} />

      {/* ── STARFIELD ── */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-60">
        {STARFIELD.map((s, i) => (
          <circle key={i} cx={`${s.x}%`} cy={`${s.y}%`} r={s.r} fill="#67e8f9" opacity={s.o} />
        ))}
      </svg>

      {/* ── NEURAL BAND GLOW (horizontal luminous strip matching reference) ── */}
      <div className="absolute left-[10%] right-[10%] top-[30%] bottom-[30%] pointer-events-none" style={{
        background:
          "linear-gradient(180deg, transparent 0%, rgba(0,240,255,0.03) 20%, rgba(0,240,255,0.08) 50%, rgba(0,240,255,0.03) 80%, transparent 100%)",
        filter: "blur(60px)",
      }} />
      
      {/* Neural band horizontal streak lines */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-30">
        <defs>
          <linearGradient id="neuralStreak" x1="0%" y1="50%" x2="100%" y2="50%">
            <stop offset="0%" stopColor="#00f0ff" stopOpacity="0" />
            <stop offset="50%" stopColor="#00f0ff" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#00f0ff" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[38, 42, 46, 50, 54, 58].map((y, i) => (
          <line
            key={i}
            x1="8%" x2="92%"
            y1={`${y}%`} y2={`${y}%`}
            stroke="url(#neuralStreak)"
            strokeWidth={i === 2 || i === 3 ? 1.5 : 0.5}
            strokeDasharray="40 20"
          />
        ))}
      </svg>

      {/* ══════════ NEURAL CONSTELLATION CANVAS ══════════ */}
      <div
        className="absolute inset-0 flex items-center justify-center"
        onMouseDown={onPanStart}
        onMouseMove={onPanMove}
        onMouseUp={onPanEnd}
        onMouseLeave={onPanEnd}
        style={{ cursor: isAnchored ? "default" : "grab" }}
      >
        <div 
          className="relative w-full h-full min-w-0 min-h-0 transition-transform duration-200"
          style={{
            transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomLevel})`,
            transformOrigin: 'center center',
          }}
        >

          {/* Synaptic connection pathways */}
          <svg className="absolute inset-0 w-full h-full pointer-events-none">
            {connections.map((conn, idx) => {
              const fromNode = brainNodes.find(n => n.id === conn.from);
              const toNode = brainNodes.find(n => n.id === conn.to);
              if (!fromNode || !toNode) return null;
              const isCore = conn.to === "mission_control" || conn.from === "mission_control";
              return (
                <g key={idx}>
                  <line
                    x1={`${fromNode.pos.x}%`}
                    y1={`${fromNode.pos.y}%`}
                    x2={`${toNode.pos.x}%`}
                    y2={`${toNode.pos.y}%`}
                    stroke={conn.color}
                    strokeWidth={conn.weight}
                    strokeOpacity={isCore ? 0.5 : 0.25}
                    className="animate-dash-flow"
                    strokeDasharray={isCore ? "8 6" : "4 8"}
                    strokeLinecap="round"
                  />
                  {/* Synaptic boutons along the connection */}
                  {[0.3, 0.7].map((t, ti) => (
                    <circle
                      key={ti}
                      cx={`${fromNode.pos.x + (toNode.pos.x - fromNode.pos.x) * t}%`}
                      cy={`${fromNode.pos.y + (toNode.pos.y - fromNode.pos.y) * t}%`}
                      r="1.5"
                      fill={conn.color}
                      opacity={isCore ? 0.6 : 0.3}
                      className="animate-pulse"
                    />
                  ))}
                </g>
              );
            })}
          </svg>

          {/* Synaptic noise particles in the band */}
          <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-40">
            {SYNAPTIC_PARTICLES.map((p, i) => (
              <circle
                key={i}
                cx={`${p.x}%`}
                cy={`${p.y}%`}
                r={p.d}
                fill="#67e8f9"
                opacity={p.s * 0.4}
                className="animate-pulse"
                style={{ animationDuration: `${2 + (i % 3)}s`, animationDelay: `${i * 0.05}s` }}
              />
            ))}
          </svg>

          {/* Render brain nodes */}
          {brainNodes.map((node) => {
            const isCenter = node.isCore;
            const pos = isCenter ? node.pos : node.pos;
            return (
              <div
                key={node.id}
                className="absolute transform -translate-x-1/2 -translate-y-1/2 flex flex-col items-center z-10 transition-all duration-500 hover:scale-110 group"
                style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
              >
                {isCenter ? (
                  /* ── CORE: MASTER NEURAL HUB ── */
                  <div className="relative flex items-center justify-center">
                    {/* Deep glow field */}
                    <div
                      className="absolute rounded-full w-48 h-48"
                      style={{
                        background: "radial-gradient(circle, rgba(0,240,255,0.25) 0%, rgba(0,240,255,0.08) 40%, transparent 70%)",
                        filter: "blur(20px)",
                      }}
                    />
                    {/* Pulsing aura ring */}
                    <div className="absolute rounded-full border-2 border-cyan-400/40 animate-ping w-44 h-44 opacity-50" />
                    {/* Outer rotating ring */}
                    <div className="absolute w-40 h-40 rounded-full border border-dashed border-cyan-400/30 animate-spin-slow" style={{ animationDuration: "30s" }}>
                      <span className="absolute -top-1 left-1/2 w-2 h-2 rounded-full bg-cyan-300 shadow-[0_0_8px_#00f0ff]" />
                    </div>
                    {/* Inner counter-rotating ring */}
                    <div className="absolute w-32 h-32 rounded-full border border-dotted border-indigo-400/40 animate-spin-slow" style={{ animationDuration: "45s", animationDirection: "reverse" }} />
                    
                    {/* Core neural hub icon */}
                    <div className="relative w-28 h-28 rounded-full bg-[#040812]/95 border-2 flex items-center justify-center" style={{ borderColor: "#00f0ff", boxShadow: "0 0 40px rgba(0,240,255,0.4), inset 0 0 20px rgba(0,240,255,0.15)" }}>
                      <svg className="w-20 h-20" viewBox="0 0 100 100">
                        {/* Main lobes */}
                        <path d="M 50 18 C 32 12, 16 30, 22 50 C 16 68, 32 85, 50 82 C 45 72, 45 28, 50 18 Z" fill="#00f0ff" fillOpacity="0.18" stroke="#00f0ff" strokeWidth="1.8" />
                        <path d="M 50 18 C 68 12, 84 30, 78 50 C 84 68, 68 85, 50 82 C 55 72, 55 28, 50 18 Z" fill="#00f0ff" fillOpacity="0.18" stroke="#00f0ff" strokeWidth="1.8" />
                        {/* Corpus callosum */}
                        <path d="M 50 32 L 46 40 L 50 50 L 54 40 Z" fill="#00f0ff" fillOpacity="0.4" />
                        {/* Synaptic clusters */}
                        <g fill="#00f0ff">
                          <circle cx="50" cy="36" r="3" />
                          <circle cx="50" cy="52" r="2.5" />
                          <circle cx="40" cy="36" r="2" />
                          <circle cx="60" cy="36" r="2" />
                          <circle cx="42" cy="50" r="2" />
                          <circle cx="58" cy="50" r="2" />
                          <circle cx="35" cy="44" r="1.5" />
                          <circle cx="65" cy="44" r="1.5" />
                        </g>
                        {/* Radiating dendrites */}
                        <g stroke="#00f0ff" strokeWidth="1" strokeOpacity="0.6">
                          <line x1="50" y1="18" x2="50" y2="8" />
                          <line x1="22" y1="50" x2="8" y2="50" />
                          <line x1="78" y1="50" x2="92" y2="50" />
                          <line x1="50" y1="82" x2="50" y2="92" />
                        </g>
                      </svg>
                    </div>
                    
                    {/* AI tag */}
                    <span className="absolute -top-3 px-2 py-0.5 rounded bg-[#040812] border border-cyan-400/50 text-[8px] font-mono text-cyan-300 font-bold tracking-wide">AI CORE</span>
                  </div>
                ) : (
                  /* ── NEURAL NODE: provider brain ── */
                  <div className="relative flex flex-col items-center">
                    <div className="relative">
                      {/* Node glow */}
                      <div
                        className="absolute rounded-full w-16 h-16 -left-3 -top-3 opacity-20 animate-pulse"
                        style={{ backgroundColor: node.color, filter: "blur(8px)" }}
                      />
                      {/* Node body */}
                      <div className="relative w-10 h-10 rounded-full bg-[#040812]/95 border-2 flex items-center justify-center" style={{ borderColor: node.color, boxShadow: `0 0 20px ${node.color}66, inset 0 0 10px ${node.color}22` }}>
                        <svg className="w-6 h-6" viewBox="0 0 100 100">
                          <path d="M 50 18 C 32 12, 16 30, 22 50 C 16 68, 32 85, 50 82 C 45 72, 45 28, 50 18 Z" fill={node.color} fillOpacity="0.3" stroke={node.color} strokeWidth="2" />
                          <path d="M 50 18 C 68 12, 84 30, 78 50 C 84 68, 68 85, 50 82 C 55 72, 55 28, 50 18 Z" fill={node.color} fillOpacity="0.3" stroke={node.color} strokeWidth="2" />
                          <circle cx="50" cy="44" r="2" fill={node.color} />
                          <circle cx="50" cy="56" r="1.5" fill={node.color} fillOpacity="0.6" />
                        </svg>
                      </div>
                      {/* Status indicator */}
                      <span
                        className="absolute -bottom-1 -right-1 w-2.5 h-2.5 rounded-full border-2 border-[#010209]"
                        style={{
                          backgroundColor: node.status === "HEALTHY" || node.status === "ACTIVE" ? "#34d399" : node.status === "DOWN" ? "#f43f5e" : "#fbbf24",
                          boxShadow: "0 0 10px currentColor",
                        }}
                      />
                    </div>
                    <div className="mt-1.5 text-center font-mono">
                      <div className="text-[8px] font-bold tracking-wider text-white drop-shadow-[0_0_4px_rgba(0,240,255,0.5)]">{node.name}</div>
                      <div className="text-[7px] text-cyan-400/70">{node.status}</div>
                    </div>
                    {/* Hover telemetry chip */}
                    <div className="absolute top-12 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-[#050a1c]/95 border border-slate-700 rounded-md px-2 py-1.5 font-mono text-[7px] text-slate-300 shadow-xl whitespace-nowrap z-20">
                      <div>CPU <span className="text-white">{node.cpu}%</span></div>
                      <div>RAM <span className="text-white">{node.ram}%</span></div>
                      <div>Tasks <span className="text-white">{node.tasks}</span></div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ══════════ FLOATING HUD PANELS (matching reference layout) ══════════ */}

      {/* TOP BAR: Title + Event Flow + View Controls */}
      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-4 max-w-[95%]">
        <div className="flex items-center gap-2.5 bg-[#050a1c]/70 backdrop-blur-md border border-cyan-500/20 rounded-lg px-3 py-2 shadow-[0_0_24px_rgba(0,0,0,0.6)]">
          <h1 className="text-sm font-bold tracking-[0.15em] text-white uppercase font-mono">AI BRAIN CONSTELLATION</h1>
          <span className="px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-300 text-[8px] font-mono border border-cyan-500/40 animate-pulse">LIVE</span>
        </div>
        
        {/* Event Flow */}
        <div className="bg-[#050a1c]/70 backdrop-blur-md border border-cyan-500/20 rounded-lg px-3 py-2 shadow-[0_0_24px_rgba(0,0,0,0.6)] min-w-[140px]">
          <div className="flex items-center justify-between text-slate-400 text-[8px] uppercase tracking-wider">
            <span>Event Flow</span>
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          </div>
          <div className="text-base font-bold font-mono text-white flex items-baseline gap-1 mt-0.5">
            <span>{storeEvents.length * 128 || 12847}</span>
            <span className="text-[8px] text-cyan-400 font-normal">events/s</span>
          </div>
          <div className="h-5 mt-1 flex items-end gap-0.5">
            {[30, 45, 60, 40, 75, 50, 90, 65, 80, 55, 95, 70, 85, 60, 100, 75].map((h, i) => (
              <div key={i} className="flex-1 bg-cyan-500/40 rounded-xs" style={{ height: `${h}%` }} />
            ))}
          </div>
        </div>

        {/* View Controls */}
        <div className="flex items-center gap-1.5 bg-[#050a1c]/70 backdrop-blur-md border border-cyan-500/20 rounded-lg px-2.5 py-1.5 shadow-[0_0_24px_rgba(0,0,0,0.6)]">
          <span className="px-1 py-0.5 rounded bg-cyan-500/20 text-cyan-300 text-[8px]">3D</span>
          <button onClick={handleRefresh} className="hover:text-white transition-colors p-0.5" title="Refresh (R)">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button onClick={zoomIn} className="hover:text-white transition-colors p-0.5" title="Zoom In (+)">
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button onClick={zoomOut} className="hover:text-white transition-colors p-0.5" title="Zoom Out (-)">
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button onClick={resetView} className="hover:text-white transition-colors p-0.5" title="Reset View (0)">
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
          <button onClick={toggleAnchor} className={`hover:text-white transition-colors p-0.5 ${isAnchored ? 'text-cyan-400' : 'text-slate-400'}`} title={isAnchored ? "Anchor: locked to centre (A to free-pan)" : "Unanchored: free-pan (A to lock)"}>
            <Anchor className="w-3.5 h-3.5" />
          </button>
          {/* Zoom level indicator */}
          <span className="px-1.5 py-0.5 rounded bg-slate-900/50 border border-slate-700 text-[8px] font-mono text-cyan-300 ml-1">
            {Math.round(zoomLevel * 100)}%
          </span>
        </div>
      </div>

      {/* LEFT PANEL: Constellation Summary - BOTTOM LEFT */}
      <div className="absolute bottom-[120px] left-4 z-20 bg-[#050a1c]/80 backdrop-blur-md border border-cyan-500/20 rounded-xl px-3 py-2.5 font-mono text-[9px] shadow-[0_0_24px_rgba(0,0,0,0.6)] w-[160px]">
        <div className="text-slate-400 text-[8px] uppercase tracking-wider mb-2 font-bold flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-cyan-400" /> CONSTELLATION
        </div>
        <div className="space-y-1.5">
          <div className="flex justify-between items-center">
            <span className="flex items-center gap-1.5 text-slate-300">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" /> Total Agents
            </span>
            <span className="font-bold text-white">{totalAgentsCount}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="flex items-center gap-1.5 text-slate-300">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Active
            </span>
            <span className="font-bold text-emerald-400">{activeAgentsCount}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="flex items-center gap-1.5 text-slate-300">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400" /> Busy
            </span>
            <span className="font-bold text-amber-400">{runningTasksCount}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="flex items-center gap-1.5 text-slate-300">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500" /> Offline
            </span>
            <span className="font-bold text-slate-400">
              {Object.values(storeProviders).filter(p => p.status === "down" || p.status === "unknown").length}
            </span>
          </div>
        </div>
        <div className="mt-2 pt-2 border-t border-slate-800/70 flex items-center justify-between text-slate-400">
          <span className="px-1 py-0.5 rounded bg-cyan-500/20 text-cyan-300 text-[8px]">3D VIEW</span>
          <button className="hover:text-white text-[10px]">Expand</button>
        </div>
      </div>

      {/* RIGHT PANEL: Live Events Feed - BOTTOM RIGHT */}
      <div className="absolute bottom-[120px] right-4 z-20 bg-[#050a1c]/80 backdrop-blur-md border border-cyan-500/20 rounded-xl px-3 py-2.5 font-mono text-[9px] shadow-[0_0_24px_rgba(0,0,0,0.6)] w-[260px] max-h-[40vh] overflow-hidden">
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-bold text-white uppercase tracking-wider text-[8px]">Live Events</span>
          <span className="text-emerald-400 text-[7px]">All Systems Live</span>
        </div>
        <div className="space-y-1.5 max-h-[30vh] overflow-y-auto pr-1">
          {liveEvents.length === 0 ? (
            <div className="text-slate-500 text-center py-2">Waiting for events…</div>
          ) : (
            liveEvents.map((ev, i) => (
              <div key={i} className="flex items-start gap-1.5 text-slate-300 border-b border-slate-800/40 pb-1 hover:bg-cyan-500/5 transition-colors rounded-sm px-1">
                <span className="text-slate-500 text-[7px] shrink-0">{ev.time}</span>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-cyan-300 truncate">{ev.agent}</div>
                  <div className="text-slate-400 text-[7px] truncate">{ev.detail}</div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* BOTTOM-LEFT: Mission Progress + Network Legend */}
      <div className="absolute bottom-4 left-4 z-20 bg-[#050a1c]/80 backdrop-blur-md border border-cyan-500/20 rounded-xl px-3 py-2.5 font-mono text-[9px] shadow-[0_0_24px_rgba(0,0,0,0.6)] w-[180px]">
        <div className="flex items-center justify-between mb-2">
          <span className="font-bold text-white uppercase tracking-wider text-[8px]">Mission Progress</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative w-14 h-14 flex items-center justify-center">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
              <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#1e293b" strokeWidth="3.8" />
              <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#00f0ff" strokeWidth="3.8" strokeDasharray={`${overallProgress}, 100`} strokeLinecap="round" />
            </svg>
            <div className="absolute text-center">
              <div className="text-xs font-bold text-white">{overallProgress}%</div>
              <div className="text-[6px] text-slate-400">COMPLETE</div>
            </div>
          </div>
          <div className="space-y-1 text-[8px]">
            <div className="flex items-center gap-1.5 text-slate-300"><span className="w-1.5 h-1.5 rounded-full bg-cyan-400" /> {runningTasksCount} Running</div>
            <div className="flex items-center gap-1.5 text-slate-300"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> {completedTasksCount} Completed</div>
            <div className="flex items-center gap-1.5 text-slate-300"><span className="w-1.5 h-1.5 rounded-full bg-rose-500" /> {telemetry.errors || 0} Failed</div>
          </div>
        </div>
        {/* Network Legend */}
        <div className="mt-2 pt-2 border-t border-slate-800/70 space-y-1">
          <div className="flex items-center gap-2 text-slate-400 text-[8px]"><span className="w-3 h-[2px] bg-cyan-400 shadow-[0_0_6px_#38bdf8]" /> Synaptic Flow</div>
          <div className="flex items-center gap-2 text-slate-400 text-[8px]"><span className="w-3 h-[2px] border-b border-dotted border-purple-400" /> Task Routing</div>
          <div className="flex items-center gap-2 text-slate-400 text-[8px]"><span className="w-3 h-[2px] bg-emerald-400" /> Heartbeat</div>
          <div className="flex items-center gap-2 text-slate-400 text-[8px]"><span className="w-3 h-[2px] border-b border-dashed border-amber-400" /> Lateral Link</div>
        </div>
      </div>

      {/* BOTTOM-RIGHT: Agent Communication Matrix */}
      <div className="absolute bottom-4 right-4 z-20 bg-[#050a1c]/80 backdrop-blur-md border border-cyan-500/20 rounded-xl px-3 py-2.5 font-mono text-[9px] shadow-[0_0_24px_rgba(0,0,0,0.6)] w-[240px]">
        <div className="font-bold text-white uppercase tracking-wider text-[8px] mb-1.5">Agent Communication</div>
        <div className="space-y-1 max-h-[25vh] overflow-y-auto pr-1">
          {commPairs.length === 0 ? (
            <div className="text-slate-500 text-center py-1.5">No inter-agent communication yet</div>
          ) : (
            commPairs.map((c, i) => (
              <div key={i} className="flex justify-between items-center text-slate-300 border-b border-slate-800/40 pb-0.5 hover:bg-cyan-500/5 transition-colors rounded-sm px-1">
                <span className="truncate pr-2">{c.pair}</span>
                <span className="text-cyan-400 font-semibold shrink-0">{c.rate}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ══════════ BOTTOM TELEMETRY BAR ══════════ */}
      <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-20 bg-[#050a1c]/85 backdrop-blur-md border border-cyan-500/20 rounded-lg px-4 py-2.5 font-mono text-[9px] shadow-[0_0_30px_rgba(0,0,0,0.7)] flex items-center gap-4 max-w-[95%] flex-wrap justify-center">
        {/* System Telemetry */}
        <div className="flex items-center gap-3">
          {[
            { label: "CPU", val: `${Math.round(performance?.cpu_usage_percent ?? 42)}%`, color: "text-cyan-400" },
            { label: "RAM", val: `${Math.round(performance?.memory_usage_percent ?? 68)}%`, color: "text-emerald-400" },
            { label: "GPU", val: performance?.gpu_usage_percent ?? "—", color: "text-indigo-400" },
            { label: "NET", val: performance?.network_throughput_bytes_per_sec ? `${safeFixed((safeNum(performance?.network_throughput_bytes_per_sec) / 1024), 0)}KB/s` : "—", color: "text-pink-400" },
          ].map((m) => (
            <div key={m.label} className="text-center px-1.5 bg-slate-900/50 rounded-md p-1 border border-slate-800/50">
              <div className="text-[7px] text-slate-500">{m.label}</div>
              <div className={`font-bold text-[10px] ${m.color}`}>{m.val}</div>
            </div>
          ))}
        </div>

        <div className="w-px h-8 bg-slate-800" />

        {/* Event Bus + Tokens */}
        <div className="flex items-center gap-4">
          <div className="text-center">
            <div className="text-[7px] text-slate-500">Event Bus</div>
            <div className="text-white font-bold text-[10px]">{storeEvents.length * 120 || 0} <span className="text-[7px] text-cyan-400 font-normal">ev/s</span></div>
          </div>
          <div className="text-center">
            <div className="text-[7px] text-slate-500">Tokens</div>
            <div className="text-white font-bold text-[10px]">{telemetry.tokens || 0} <span className="text-[7px] text-cyan-400 font-normal">t/s</span></div>
          </div>
        </div>

        <div className="w-px h-8 bg-slate-800" />

        {/* Task Distribution Mini-Histogram */}
        <div className="flex items-end gap-1 h-10">
          {(() => {
            const histogramColors = ["bg-indigo-500", "bg-cyan-500", "bg-emerald-500", "bg-pink-500", "bg-amber-500", "bg-purple-500", "bg-blue-500", "bg-teal-500"];
            const entries = Object.entries(taskCountByProvider).filter(([k]) => k && k !== "mock");
            if (entries.length === 0) return <div className="text-slate-500 text-[8px] m-auto">No task data</div>;
            return entries.slice(0, 8).map(([provider, val], idx) => {
              const name = provider.charAt(0).toUpperCase() + provider.slice(1);
              return (
                <div key={provider} className="flex flex-col items-center flex-1 h-full justify-end" title={`${name}: ${val} tasks`}>
                  <div className={`w-full rounded-t ${histogramColors[idx % histogramColors.length]}`} style={{ height: `${Math.min(val * 10, 100)}%` }} />
                  <span className="text-[6px] text-slate-500 truncate w-full text-center mt-0.5">{name.slice(0,4)}</span>
                </div>
              );
            });
          })()}
        </div>

        <div className="w-px h-8 bg-slate-800" />

        {/* Connections Status */}
        <div className="flex items-center gap-3 text-[8px]">
          <div className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> WebSocket</div>
          <div className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> EventBus</div>
          <div className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> {Object.keys(storeProviders).length} Providers</div>
        </div>

        <div className="w-px h-8 bg-slate-800" />

        {/* Playback Controls */}
        <div className="flex items-center gap-1 border-l border-slate-800 pl-3">
          {(["1x", "2x", "4x"] as const).map((spd) => (
            <button
              key={spd}
              onClick={() => setActivePlayback(spd)}
              className={`px-2 py-1 rounded text-[8px] font-bold ${
                activePlayback === spd
                  ? "bg-cyan-500/20 border border-cyan-500/50 text-cyan-300"
                  : "bg-slate-900 text-slate-400 hover:text-white"
              }`}
            >
              {spd}
            </button>
          ))}
        </div>
      </div>

    </div>
  );
}

export { AIBrain as AiBrain };
export default AIBrain;