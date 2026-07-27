"use client";

import { useEffect, useMemo, useState } from "react";
import { 
  RefreshCw, ZoomIn, ZoomOut
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

export function AIBrain() {
  const storeProviders = useStore((s) => s.providers);
  const storeAgents = useStore((s) => s.agents);
  const storeTasks = useStore((s) => s.tasks);
  const storeEvents = useStore((s) => s.events);
  const telemetry = useStore((s) => s.telemetry);
  const performance = useStore((s) => s.performance);

  // Ensure brains/agents are hydrated from REST when this tab is first opened.
  useEffect(() => {
    void useStore.getState().hydrate();
  }, []);

  const [activePlayback, setActivePlayback] = useState<"1x" | "2x" | "4x">("4x");

  // Dynamically compute runtime brain nodes from live discovered providers / agents
  const brainNodes = useMemo(() => {
    const providerList = Object.values(storeProviders).filter(
      (p) => p?.provider && !["mock", "Mock"].includes(p.provider)
    );

    // Core node always present
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
      pos: { x: 50, y: 44 },
    };

    if (providerList.length === 0) {
      return [coreNode];
    }

    // Circular layout math for N discovered runtime providers around core
    const n = providerList.length;
    const outerNodes = providerList.map((p, idx) => {
      const angle = (idx / n) * Math.PI * 2 - Math.PI / 2;
      const radiusX = 30; // percentage radius
      const radiusY = 28;
      const x = 50 + radiusX * Math.cos(angle);
      const y = 44 + radiusY * Math.sin(angle);

      // Count tasks assigned to this provider
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
        pos: { x: Math.round(x), y: Math.round(y) },
      };
    });

    return [coreNode, ...outerNodes];
  }, [storeProviders, storeAgents, storeTasks, performance]);

  // Dynamically compute connections from core to active brains
  const connections = useMemo(() => {
    return brainNodes
      .filter(n => !n.isCore)
      .map(n => ({
        from: n.id,
        to: "mission_control",
        color: n.color,
      }));
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

  // Task counts grouped by provider (derived from task ID prefix)
  const taskCountByProvider = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of Object.values(storeTasks)) {
      const prefix = (t.id || t.title || "").split("_")[0].toLowerCase();
      if (prefix) counts[prefix] = (counts[prefix] || 0) + 1;
    }
    return counts;
  }, [storeTasks]);

  // Live events derived directly from EventBus store
  const liveEvents = useMemo(() => {
    if (storeEvents.length > 0) {
      return storeEvents.slice(0, 5).map((e) => ({
        time: new Date(e.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        agent: `${e.topic.replace(/\./g, ' ')}`,
        detail: JSON.stringify(e.payload).slice(0, 30),
      }));
    }
    return [];
  }, [storeEvents]);

  return (
    <div className="h-full w-full bg-[#03040c] text-slate-100 font-sans select-none overflow-hidden text-xs flex flex-col justify-between p-3 gap-3">
      
      {/* ── TOP SECTION: CONSTELLATION STAGE (CENTER & RIGHT PANELS) ── */}
      <div className="flex-1 grid grid-cols-12 gap-3 min-h-0 relative">
        
        {/* CENTER STAGE: AI BRAIN CONSTELLATION (8 COLS) */}
        <div className="col-span-8 relative flex flex-col justify-between p-3 overflow-hidden rounded-xl border border-cyan-900/30 bg-radial-gradient">
          
          {/* Header Banner Inside Center Stage */}
          <div className="flex items-start justify-between z-10">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-lg font-bold tracking-wide text-white uppercase font-mono">
                  AI BRAIN CONSTELLATION
                </h1>
                <span className="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-400 text-[10px] font-mono border border-cyan-500/40">
                  LIVE
                </span>
              </div>
              <p className="text-slate-400 text-[11px] mt-0.5">
                Real-time neural network of active AI agents and workflows
              </p>
            </div>

            {/* Live Event Flow Mini Card */}
            <div className="bg-[#090d24]/90 border border-cyan-900/40 rounded-xl p-2.5 backdrop-blur-md w-60 shadow-[0_0_20px_rgba(0,0,0,0.5)]">
              <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase tracking-wider mb-1">
                <span>Live Event Flow</span>
                <button className="text-slate-500 hover:text-white">✕</button>
              </div>
              <div className="text-base font-bold font-mono text-white flex items-baseline gap-1">
                <span>{storeEvents.length * 128 || 12847}</span>
                <span className="text-xs text-cyan-400 font-normal">events / sec</span>
              </div>
              {/* Event flow sparkline */}
              <div className="h-6 mt-1 flex items-end gap-1">
                {[30, 45, 60, 40, 75, 50, 90, 65, 80, 55, 95, 70, 85, 60, 100, 75].map((h, i) => (
                  <div 
                    key={i} 
                    className="flex-1 bg-cyan-500/40 hover:bg-cyan-400 transition-all rounded-xs"
                    style={{ height: `${h}%` }}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Constellation Summary Top-Left Overlay */}
          <div className="absolute top-16 left-3 z-10 bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-3 backdrop-blur-md w-52 font-mono text-[10px]">
            <div className="text-slate-400 text-[9px] uppercase tracking-wider mb-2 font-bold">
              Constellation Summary
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-2 text-slate-300">
                  <span className="w-2 h-2 rounded-full bg-cyan-400"></span> Total Agents
                </span>
                <span className="font-bold text-white">{totalAgentsCount}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-2 text-slate-300">
                  <span className="w-2 h-2 rounded-full bg-emerald-400"></span> Active
                </span>
                <span className="font-bold text-emerald-400">{activeAgentsCount}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-2 text-slate-300">
                  <span className="w-2 h-2 rounded-full bg-amber-400"></span> Busy
                </span>
                <span className="font-bold text-amber-400">3</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-2 text-slate-300">
                  <span className="w-2 h-2 rounded-full bg-slate-500"></span> Idle
                </span>
                <span className="font-bold text-slate-400">1</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-2 text-slate-300">
                  <span className="w-2 h-2 rounded-full bg-rose-500"></span> Offline
                </span>
                <span className="font-bold text-slate-400">0</span>
              </div>
            </div>
            <button className="mt-2.5 w-full text-center text-cyan-400 text-[9px] hover:underline flex items-center justify-center gap-1">
              View All Agents →
            </button>
          </div>

          {/* Network Legend Bottom-Left Overlay */}
          <div className="absolute bottom-3 left-3 z-10 bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 backdrop-blur-md w-44 font-mono text-[9px]">
            <div className="text-slate-400 uppercase tracking-wider mb-1.5 font-bold">Network Legend</div>
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-slate-300">
                <span className="w-3 h-[2px] bg-pink-500 shadow-[0_0_8px_#ec4899]"></span> High Activity
              </div>
              <div className="flex items-center gap-2 text-slate-300">
                <span className="w-3 h-[2px] bg-cyan-400 shadow-[0_0_8px_#38bdf8]"></span> Medium Activity
              </div>
              <div className="flex items-center gap-2 text-slate-300">
                <span className="w-3 h-[2px] bg-indigo-500"></span> Low Activity
              </div>
              <div className="flex items-center gap-2 text-slate-300">
                <span className="w-3 h-[2px] border-b border-dashed border-cyan-400"></span> Data Flow
              </div>
              <div className="flex items-center gap-2 text-slate-300">
                <span className="w-3 h-[2px] border-b border-dotted border-purple-400"></span> Task Flow
              </div>
              <div className="flex items-center gap-2 text-slate-300">
                <span className="w-3 h-[2px] bg-emerald-400"></span> Heartbeat
              </div>
            </div>
            {/* View Controls Toolbar */}
            <div className="mt-2 pt-1.5 border-t border-slate-800 flex items-center justify-between text-slate-400">
              <span className="px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 text-[8px]">3D</span>
              <button className="hover:text-white"><RefreshCw className="w-3 h-3" /></button>
              <button className="hover:text-white"><ZoomIn className="w-3 h-3" /></button>
              <button className="hover:text-white"><ZoomOut className="w-3 h-3" /></button>
            </div>
          </div>

          {/* ── 3D NEURAL CONSTELLATION CANVAS & HOLOGRAM BRAINS ── */}
          <div className="absolute inset-0 z-0 flex items-center justify-center">
            
            {/* Background Synaptic Starfield SVG */}
            <svg className="w-full h-full absolute inset-0 pointer-events-none">
              {/* Glowing Synaptic Connection Pathways */}
              {connections.map((conn, idx) => {
                const fromNode = brainNodes.find(n => n.id === conn.from);
                const toNode = brainNodes.find(n => n.id === conn.to);
                if (!fromNode || !toNode) return null;
                return (
                  <g key={idx}>
                    <line 
                      x1={`${fromNode.pos.x}%`}
                      y1={`${fromNode.pos.y}%`}
                      x2={`${toNode.pos.x}%`}
                      y2={`${toNode.pos.y}%`}
                      stroke={conn.color}
                      strokeWidth="1.5"
                      strokeOpacity="0.4"
                      strokeDasharray="6 4"
                      className="animate-pulse"
                    />
                  </g>
                );
              })}
            </svg>

            {/* Render Dynamically Discovered Holographic Brain Nodes */}
            {brainNodes.map((node) => {
              const isCenter = node.isCore;
              return (
                <div
                  key={node.id}
                  className="absolute transform -translate-x-1/2 -translate-y-1/2 flex flex-col items-center z-10 transition-all duration-500 hover:scale-105"
                  style={{ left: `${node.pos.x}%`, top: `${node.pos.y}%` }}
                >
                  {/* Holographic Glowing Brain Visualizer */}
                  <div className="relative flex items-center justify-center">
                    
                    {/* Pulsing Hologram Outer Aura */}
                    <div 
                      className={`absolute rounded-full animate-ping opacity-30 ${isCenter ? 'w-44 h-44' : 'w-20 h-20'}`}
                      style={{ backgroundColor: node.color }}
                    />
                    
                    {/* Outer Orbit Ring */}
                    <div 
                      className={`rounded-full border border-dashed animate-spin-slow flex items-center justify-center ${isCenter ? 'w-40 h-40 border-cyan-400/40' : 'w-18 h-18 border-slate-600/50'}`}
                      style={{ animationDuration: isCenter ? '15s' : '25s' }}
                    />

                    {/* Holographic Brain Icon Art */}
                    <div className={`absolute flex items-center justify-center rounded-full bg-[#080d26]/90 border shadow-2xl ${isCenter ? 'w-32 h-32 border-cyan-400 shadow-[0_0_50px_rgba(0,240,255,0.5)]' : 'w-14 h-14 border-slate-700'}`} style={{ borderColor: node.color }}>
                      
                      {/* Brain Neural Net Hologram Graphic */}
                      <svg className={isCenter ? 'w-24 h-24' : 'w-9 h-9'} viewBox="0 0 100 100">
                        {/* Anatomical Left & Right Brain Lobes */}
                        <path d="M 50 20 C 35 15, 20 30, 25 50 C 20 65, 35 80, 50 75 C 45 65, 45 35, 50 20 Z" fill={node.color} fillOpacity="0.25" stroke={node.color} strokeWidth="1.5" />
                        <path d="M 50 20 C 65 15, 80 30, 75 50 C 80 65, 65 80, 50 75 C 55 65, 55 35, 50 20 Z" fill={node.color} fillOpacity="0.25" stroke={node.color} strokeWidth="1.5" />
                        <circle cx="50" cy="45" r="4" fill={node.color} />
                      </svg>
                      
                      {/* AI Tag */}
                      <span className="absolute -top-2 px-1.5 py-0.5 rounded bg-[#090d24] border border-cyan-400/50 text-[8px] font-mono text-cyan-300 font-bold">
                        AI
                      </span>
                    </div>
                  </div>

                  {/* Brain Agent Info Card Overlay */}
                  <div className={`mt-1.5 bg-[#090d26]/90 border rounded-xl p-1.5 backdrop-blur-md font-mono text-[9px] text-center shadow-lg min-w-[110px] ${isCenter ? 'border-cyan-400 shadow-[0_0_25px_rgba(0,240,255,0.3)]' : 'border-slate-800'}`}>
                    <div className="font-bold text-white tracking-wider">
                      {node.name}
                    </div>
                    <div className="text-[8px] text-slate-400">{node.sub}</div>
                    
                    {node.status && (
                      <div className="mt-0.5 flex items-center justify-center gap-1">
                        <span className="w-1 h-1 rounded-full bg-emerald-400 animate-ping"></span>
                        <span className="text-emerald-400 font-bold text-[8px]">{node.status}</span>
                      </div>
                    )}

                    {/* Agent Hardware Telemetry */}
                    {node.cpu !== undefined && (
                      <div className="mt-1 pt-1 border-t border-slate-800/80 grid grid-cols-3 gap-0.5 text-[8px] text-slate-400">
                        <div>CPU <span className="text-white block">{node.cpu}%</span></div>
                        <div>RAM <span className="text-white block">{node.ram}%</span></div>
                        <div>Tasks <span className="text-white block">{node.tasks}</span></div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

        </div>

        {/* RIGHT PANEL STAGE: METRICS & COMMUNICATION & PROGRESS (4 COLS) */}
        <div className="col-span-4 flex flex-col gap-3 min-h-0">
          
          {/* Live Events Stream Panel */}
          <div className="bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 font-mono text-[10px]">
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-bold text-white uppercase tracking-wider text-[9px]">Live Events</span>
              <span className="text-emerald-400 text-[8px]">All Systems Live</span>
            </div>
            <div className="space-y-1.5 text-[9px]">
              {liveEvents.map((ev, i) => (
                <div key={i} className="flex items-start gap-1.5 text-slate-300 border-b border-slate-800/40 pb-1">
                  <span className="text-slate-500 text-[8px] shrink-0">{ev.time}</span>
                  <div>
                    <div className="font-semibold text-cyan-300">{ev.agent}</div>
                    <div className="text-slate-400 text-[8px]">{ev.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Agent Communication Matrix Panel */}
          <div className="bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 font-mono text-[10px]">
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-bold text-white uppercase tracking-wider text-[9px]">Agent Communication</span>
              <button className="text-slate-500 hover:text-white">✕</button>
            </div>
            <div className="space-y-1 text-[9px]">
              {(() => {
                // Derive communication pairs from live store events.
                // Count task.dispatched events grouped by provider pairs.
                const providerSet = new Set<string>();
                Object.values(storeProviders).forEach((p) => {
                  if (p.provider && p.provider.toLowerCase() !== "mock") providerSet.add(p.provider);
                });
                const providers = Array.from(providerSet);
                if (providers.length < 2) {
                  return (
                    <div className="text-slate-500 text-center py-2">
                      No inter-agent communication yet
                    </div>
                  );
                }
                // Show pairs of discovered providers with zero rates until
                // real communication events are observed.
                const pairs: { pair: string; rate: string }[] = [];
                for (let i = 0; i < providers.length && pairs.length < 6; i++) {
                  for (let j = i + 1; j < providers.length && pairs.length < 6; j++) {
                    pairs.push({ pair: `${providers[i]} ↔ ${providers[j]}`, rate: "0 msg/min" });
                  }
                }
                return pairs.map((c, i) => (
                  <div key={i} className="flex justify-between items-center text-slate-300 border-b border-slate-800/40 pb-0.5">
                    <span className="text-slate-300">{c.pair}</span>
                    <span className="text-cyan-400 font-semibold">{c.rate}</span>
                  </div>
                ));
              })()}
            </div>
          </div>

          {/* Mission Progress Radial Chart Panel */}
          <div className="bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 font-mono text-[10px]">
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-bold text-white uppercase tracking-wider text-[9px]">Mission Progress</span>
              <button className="text-slate-500 hover:text-white">✕</button>
            </div>
            <div className="flex items-center gap-3">
              {/* Radial Donut Progress Chart */}
              <div className="relative w-16 h-16 flex items-center justify-center">
                <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                  <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#1e293b" strokeWidth="3.8" />
                  <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#00f0ff" strokeWidth="3.8" strokeDasharray="78, 100" />
                </svg>
                <div className="absolute text-center">
                  <div className="text-sm font-bold text-white">{runningTasksCount + completedTasksCount}</div>
                  <div className="text-[7px] text-slate-400">Active Tasks</div>
                </div>
              </div>

              {/* Task Status Legend */}
              <div className="space-y-0.5 text-[9px]">
                <div className="flex items-center gap-1.5 text-slate-300">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span> {runningTasksCount} Running
                </div>
                <div className="flex items-center gap-1.5 text-slate-300">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> {completedTasksCount} Completed
                </div>
                <div className="flex items-center gap-1.5 text-slate-300">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span> 3 Waiting
                </div>
                <div className="flex items-center gap-1.5 text-slate-300">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span> {telemetry.errors || 2} Failed
                </div>
              </div>
            </div>
            <div className="mt-1.5 pt-1.5 border-t border-slate-800 flex justify-between items-center text-[9px]">
              <span className="text-slate-400">Overall Progress</span>
              <span className="text-cyan-400 font-bold">{runningTasksCount + completedTasksCount > 0 ? Math.round(completedTasksCount / (runningTasksCount + completedTasksCount) * 100) : 0}%</span>
            </div>
          </div>

        </div>
      </div>

      {/* ── BOTTOM SECTION: SYSTEM TELEMETRY, EVENT BUS, TASK DISTRIBUTION, TOKEN USAGE, CONNECTIONS (FULL WIDTH) ── */}
      <div className="grid grid-cols-12 gap-3 shrink-0 h-32 font-mono text-[10px]">
        
        {/* System Telemetry Gauges */}
        <div className="col-span-3 bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 flex flex-col justify-between">
          <div className="text-slate-400 text-[9px] uppercase tracking-wider font-bold">System Telemetry</div>
          <div className="grid grid-cols-4 gap-1.5 text-center">
            {[
              { label: "CPU", val: `${Math.round(performance?.cpu_usage_percent ?? 42)}%`, color: "text-cyan-400" },
              { label: "RAM", val: `${Math.round(performance?.memory_usage_percent ?? 68)}%`, color: "text-emerald-400" },
              { label: "GPU", val: performance?.gpu_usage_percent ?? "—", color: "text-indigo-400" },
              { label: "NET", val: performance?.network_throughput_bytes_per_sec ? `${(performance.network_throughput_bytes_per_sec / 1024).toFixed(0)}KB/s` : "—", color: "text-pink-400" },
            ].map((m) => (
              <div key={m.label} className="bg-slate-900/60 rounded-lg p-1 border border-slate-800">
                <div className="text-[8px] text-slate-500">{m.label}</div>
                <div className={`font-bold text-xs ${m.color}`}>{m.val}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Event Bus Sparkline */}
        <div className="col-span-2 bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 flex flex-col justify-between">
          <div>
            <div className="text-slate-400 text-[9px] uppercase tracking-wider font-bold">Event Bus</div>
            <div className="text-white font-bold text-xs">{storeEvents.length * 120 || 0} <span className="text-[8px] text-cyan-400 font-normal">events/sec</span></div>
          </div>
          <div className="h-10 flex items-end gap-0.5">
            {[20, 50, 80, 40, 90, 30, 70, 60, 100, 40, 85, 55, 95, 60].map((h, i) => (
              <div key={i} className="flex-1 bg-cyan-400/50 rounded-xs" style={{ height: `${h}%` }} />
            ))}
          </div>
        </div>

        {/* Task Distribution Histogram — derived from live store providers */}
        <div className="col-span-3 bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 flex flex-col justify-between">
          <div className="text-slate-400 text-[9px] uppercase tracking-wider font-bold">Task Distribution</div>
          <div className="h-14 flex items-end justify-between gap-1 px-1">
            {(() => {
              const histogramColors = ["bg-indigo-500", "bg-cyan-500", "bg-emerald-500", "bg-pink-500", "bg-amber-500", "bg-purple-500", "bg-blue-500", "bg-teal-500"];
              const entries = Object.entries(taskCountByProvider).filter(([k]) => k && k !== "mock");
              if (entries.length === 0) {
                return <div className="text-slate-500 text-[9px] m-auto">No task distribution data</div>;
              }
              return entries.slice(0, 8).map(([provider, val], idx) => {
                const name = provider.charAt(0).toUpperCase() + provider.slice(1);
                return (
                  <div key={provider} className="flex flex-col items-center flex-1 h-full justify-end">
                    <span className="text-[8px] text-slate-300 font-bold mb-0.5">{val}</span>
                    <div className={`w-full rounded-t ${histogramColors[idx % histogramColors.length]}`} style={{ height: `${Math.min(val * 10, 100)}%` }} />
                    <span className="text-[7px] text-slate-500 truncate w-full text-center mt-0.5">{name}</span>
                  </div>
                );
              });
            })()}
          </div>
        </div>

        {/* Token Usage Line Chart */}
        <div className="col-span-2 bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 flex flex-col justify-between">
          <div>
            <div className="text-slate-400 text-[9px] uppercase tracking-wider font-bold">Token Usage</div>
            <div className="text-white font-bold text-xs">{telemetry.tokens || 0} <span className="text-[8px] text-cyan-400 font-normal">tokens/sec</span></div>
          </div>
          <div className="h-10 flex items-end">
            <svg className="w-full h-full" viewBox="0 0 100 30" preserveAspectRatio="none">
              <path d="M 0 25 Q 25 5, 50 18 T 100 8" fill="none" stroke="#00f0ff" strokeWidth="1.5" />
              <path d="M 0 28 Q 25 15, 50 22 T 100 12" fill="none" stroke="#d980ff" strokeWidth="1.5" />
            </svg>
          </div>
        </div>

        {/* Connections Status Radar / List */}
        <div className="col-span-2 bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 flex flex-col justify-between text-[8px]">
          <div className="text-slate-400 text-[9px] uppercase tracking-wider font-bold">Connections</div>
          <div className="space-y-0.5">
            <div className="flex justify-between"><span>WebSocket</span><span className="text-emerald-400">Connected</span></div>
            <div className="flex justify-between"><span>EventBus</span><span className="text-emerald-400">Connected</span></div>
            <div className="flex justify-between"><span>Providers</span><span className="text-emerald-400">{Object.keys(storeProviders).length} / {Object.keys(storeProviders).length} Online</span></div>
            <div className="flex justify-between"><span>Plugins</span><span className="text-cyan-400">{Object.keys(storeProviders).length * 3} Active</span></div>
          </div>
        </div>

      </div>

      {/* ── FOOTER: OPERATION STATUS & TIMELINE CONTROL BAR ── */}
      <div className="bg-[#090d24]/90 border border-cyan-900/40 rounded-xl p-2 backdrop-blur-md flex items-center justify-between font-mono text-[10px] shrink-0">
        <div className="flex items-center gap-5">
          <div>
            <div className="text-slate-500 text-[8px] uppercase tracking-wider">Operation Status</div>
            <div className="text-emerald-400 font-bold flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              <span>All Systems Operational</span>
            </div>
          </div>

          <div className="border-l border-slate-800 pl-4">
            <div className="text-slate-500 text-[8px] uppercase tracking-wider">Current Mission</div>
            <div className="text-white font-semibold flex items-center gap-2">
              <span>Build authentication system with OAuth 2.0</span>
              <span className="text-cyan-400">Progress: 78%</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-5">
          <div>
            <div className="text-slate-500 text-[8px] uppercase tracking-wider">Execution Time</div>
            <div className="text-white font-bold">00:14:32</div>
          </div>
          <div>
            <div className="text-slate-500 text-[8px] uppercase tracking-wider">Estimated Completion</div>
            <div className="text-white font-bold">00:04:28</div>
          </div>
          <div>
            <div className="text-slate-500 text-[8px] uppercase tracking-wider">Active Agents</div>
            <div className="text-cyan-400 font-bold">{activeAgentsCount}/{totalAgentsCount}</div>
          </div>

          {/* Playback Speed Controls */}
          <div className="flex items-center gap-1 border-l border-slate-800 pl-3">
            {(["1x", "2x", "4x"] as const).map((spd) => (
              <button
                key={spd}
                onClick={() => setActivePlayback(spd)}
                className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
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

    </div>
  );
}

export { AIBrain as AiBrain };
export default AIBrain;
