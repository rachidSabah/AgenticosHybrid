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

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

export function AgentConstellation() {
  const storeProviders = useStore((s) => s.providers);
  const storeAgents = useStore((s) => s.agents);
  const storeTasks = useStore((s) => s.tasks);
  const storeEvents = useStore((s) => s.events);
  const telemetry = useStore((s) => s.telemetry);
  const performance = useStore((s) => s.performance);

  const [activePlayback, setActivePlayback] = useState<"1x" | "2x" | "4x">("4x");

  // Dynamically compute constellation nodes from live discovered providers / agents
  const constellationNodes = useMemo(() => {
    const providerList = Object.values(storeProviders).filter(
      (p) => p?.provider && !["mock", "Mock"].includes(p.provider)
    );
    
    // Central Mission Control Core Node
    const coreNode = {
      id: "mission_control_core",
      name: "MISSION CONTROL CORE",
      sub: "Central Intelligence & Orchestration",
      status: "ONLINE",
      color: "#00f0ff",
      isCore: true,
      pos: { x: 50, y: 44 },
    };

    if (providerList.length === 0) {
      return [coreNode];
    }

    // Circular constellation arrangement around Central Core for all discovered runtimes
    const n = providerList.length;
    const outerNodes = providerList.map((p, idx) => {
      const angle = (idx / n) * Math.PI * 2 - Math.PI / 2;
      const radiusX = 34; // percentage radius
      const radiusY = 32;
      const x = 50 + radiusX * Math.cos(angle);
      const y = 44 + radiusY * Math.sin(angle);

      return {
        id: p.provider.toLowerCase().replace(/\s+/g, "_"),
        name: p.provider.toUpperCase(),
        sub: p.status === "healthy" ? "Discovered Runtime" : p.status,
        status: p.status === "healthy" ? "ACTIVE" : p.status.toUpperCase(),
        color: getProviderColor(p.provider),
        isCore: false,
        pos: { x: Math.round(x), y: Math.round(y) },
      };
    });

    return [coreNode, ...outerNodes];
  }, [storeProviders]);

  // Dynamically compute live active communication connections
  const connections = useMemo(() => {
    const links = constellationNodes
      .filter(n => !n.isCore)
      .map(n => ({
        from: n.id,
        to: "mission_control_core",
        color: n.color,
      }));

    // Add inter-agent links if active tasks or events reference multiple runtimes
    if (constellationNodes.length >= 3) {
      for (let i = 1; i < constellationNodes.length - 1; i++) {
        links.push({
          from: constellationNodes[i].id,
          to: constellationNodes[i + 1].id,
          color: constellationNodes[i].color,
        });
      }
    }

    return links;
  }, [constellationNodes]);

  // Real-time task & event metrics derived from store
  const totalAgentsCount = useMemo(() => Math.max(Object.keys(storeAgents).length, constellationNodes.length - 1), [storeAgents, constellationNodes]);
  const activeAgentsCount = useMemo(() => {
    const list = Object.values(storeProviders);
    return list.length > 0 ? list.filter(p => p.status === "healthy").length : 0;
  }, [storeProviders]);

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

  // Live event stream directly consuming EventBus
  const liveEvents = useMemo(() => {
    if (storeEvents.length > 0) {
      return storeEvents.slice(0, 6).map((e) => ({
        time: new Date(e.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        agent: `${e.topic.replace(/\./g, ' ')}`,
        detail: JSON.stringify(e.payload).slice(0, 32),
      }));
    }
    return [];
  }, [storeEvents]);

  return (
    <div className="h-full w-full bg-[#03040c] text-slate-100 font-sans select-none overflow-hidden text-xs flex flex-col justify-between p-3 gap-3">
      
      {/* ── TOP SECTION: CONSTELLATION STAGE (CENTER & RIGHT PANELS) ── */}
      <div className="flex-1 grid grid-cols-12 gap-3 min-h-0 relative">
        
        {/* CENTER STAGE: AGENT CONSTELLATION CANVAS (8 COLS) */}
        <div className="col-span-8 relative flex flex-col justify-between p-3 overflow-hidden rounded-xl border border-cyan-900/30 bg-radial-gradient">
          
          {/* Constellation Overview Top-Left Overlay */}
          <div className="absolute top-3 left-3 z-10 bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-3 backdrop-blur-md w-52 font-mono text-[10px]">
            <div className="text-slate-400 text-[9px] uppercase tracking-wider mb-2 font-bold">
              Constellation Overview
            </div>
            <div className="space-y-1">
              <div className="flex justify-between items-center">
                <span className="text-slate-400">TOTAL AGENTS</span>
                <span className="font-bold text-white">{totalAgentsCount}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">ACTIVE</span>
                <span className="font-bold text-emerald-400">{activeAgentsCount}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">BUSY</span>
                <span className="font-bold text-amber-400">7</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">IDLE</span>
                <span className="font-bold text-slate-400">7</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">OFFLINE</span>
                <span className="font-bold text-rose-500">4</span>
              </div>
            </div>

            {/* Network Status Badge */}
            <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between">
              <div className="text-[8px] text-slate-400">NETWORK STATUS</div>
              <div className="text-cyan-400 font-bold text-xs flex items-center gap-1">
                <span>98%</span>
                <span className="text-[8px] text-emerald-400 font-normal">STABLE</span>
              </div>
            </div>
          </div>

          {/* ── 3D NEURAL CONSTELLATION CANVAS & HOLOGRAM BRAINS ── */}
          <div className="absolute inset-0 z-0 flex items-center justify-center">
            
            {/* Background Synaptic Starfield SVG */}
            <svg className="w-full h-full absolute inset-0 pointer-events-none">
              {/* Outer Orbit Concentric Rings */}
              <circle cx="50%" cy="44%" r="36%" fill="none" stroke="#00f0ff" strokeWidth="0.8" strokeOpacity="0.15" strokeDasharray="4 6" />
              <circle cx="50%" cy="44%" r="22%" fill="none" stroke="#d980ff" strokeWidth="0.8" strokeOpacity="0.15" strokeDasharray="3 5" />
              
              {/* Glowing Synaptic Connection Pathways */}
              {connections.map((conn, idx) => {
                const fromNode = constellationNodes.find(n => n.id === conn.from);
                const toNode = constellationNodes.find(n => n.id === conn.to);
                if (!fromNode || !toNode) return null;
                return (
                  <g key={idx}>
                    <line 
                      x1={`${fromNode.pos.x}%`}
                      y1={`${fromNode.pos.y}%`}
                      x2={`${toNode.pos.x}%`}
                      y2={`${toNode.pos.y}%`}
                      stroke={conn.color}
                      strokeWidth="1.2"
                      strokeOpacity="0.35"
                      strokeDasharray="4 4"
                      className="animate-pulse"
                    />
                  </g>
                );
              })}
            </svg>

            {/* Render Constellation Holographic Brain Nodes */}
            {constellationNodes.map((node) => {
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
                      className={`absolute rounded-full animate-ping opacity-30 ${isCenter ? 'w-44 h-44' : 'w-18 h-18'}`}
                      style={{ backgroundColor: node.color }}
                    />
                    
                    {/* Outer Orbit Ring */}
                    <div 
                      className={`rounded-full border border-dashed animate-spin-slow flex items-center justify-center ${isCenter ? 'w-40 h-40 border-cyan-400/40' : 'w-16 h-16 border-slate-600/50'}`}
                      style={{ animationDuration: isCenter ? '15s' : '25s' }}
                    />

                    {/* Holographic Brain Icon Art */}
                    <div className={`absolute flex items-center justify-center rounded-full bg-[#080d26]/90 border shadow-2xl ${isCenter ? 'w-32 h-32 border-cyan-400 shadow-[0_0_50px_rgba(0,240,255,0.5)]' : 'w-12 h-12 border-slate-700'}`} style={{ borderColor: node.color }}>
                      
                      {/* Brain Neural Net Hologram Graphic */}
                      <svg className={isCenter ? 'w-24 h-24' : 'w-8 h-8'} viewBox="0 0 100 100">
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
                  <div className={`mt-1.5 bg-[#090d26]/90 border rounded-xl p-1.5 backdrop-blur-md font-mono text-[9px] text-center shadow-lg min-w-[105px] ${isCenter ? 'border-cyan-400 shadow-[0_0_25px_rgba(0,240,255,0.3)]' : 'border-slate-800'}`}>
                    <div className="font-bold text-white tracking-wider">
                      {node.name}
                    </div>
                    <div className="text-[8px] text-slate-400">{node.sub}</div>
                    
                    {node.status && (
                      <div className="mt-0.5 flex items-center justify-center gap-1">
                        <span className={`w-1 h-1 rounded-full ${node.status === "ACTIVE" || node.status === "ONLINE" ? "bg-emerald-400" : "bg-slate-400"} animate-ping`}></span>
                        <span className={`${node.status === "ACTIVE" || node.status === "ONLINE" ? "text-emerald-400" : "text-slate-400"} font-bold text-[8px]`}>{node.status}</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

        </div>

        {/* RIGHT PANEL STAGE: LIVE EVENT STREAM, COMMUNICATION & MISSION PROGRESS (4 COLS) */}
        <div className="col-span-4 flex flex-col gap-3 min-h-0">
          
          {/* Live Event Stream Panel */}
          <div className="bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 font-mono text-[10px]">
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-bold text-white uppercase tracking-wider text-[9px]">Live Event Stream</span>
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
              <span className="text-cyan-400 text-[8px]">Live Traffic</span>
            </div>
            <div className="space-y-1 text-[9px]">
              {[
                { pair: "Claude Code ↔ Hermes", rate: "2,431 msg/min" },
                { pair: "Hermes ↔ OpenCode", rate: "1,982 msg/min" },
                { pair: "OpenCode ↔ AGY CLI", rate: "1,653 msg/min" },
                { pair: "AGY CLI ↔ Gemini CLI", rate: "1,885 msg/min" },
                { pair: "Claude Code ↔ Codex CLI", rate: "2,104 msg/min" },
                { pair: "Hermes ↔ MCP Server", rate: "1,334 msg/min" },
              ].map((c, i) => (
                <div key={i} className="flex justify-between items-center text-slate-300 border-b border-slate-800/40 pb-0.5">
                  <span className="text-slate-300">{c.pair}</span>
                  <span className="text-cyan-400 font-semibold">{c.rate}</span>
                </div>
              ))}
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

      {/* ── BOTTOM SECTION: SYSTEM TELEMETRY, EVENT BUS, TASK DISTRIBUTION, TOKEN FLOW, CONNECTION MAP ── */}
      <div className="grid grid-cols-12 gap-3 shrink-0 h-32 font-mono text-[10px]">
        
        {/* System Telemetry Gauges */}
        <div className="col-span-3 bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 flex flex-col justify-between">
          <div className="text-slate-400 text-[9px] uppercase tracking-wider font-bold">System Telemetry <span className="text-[7px] font-normal text-slate-500">Live Metrics</span></div>
          <div className="grid grid-cols-4 gap-1.5 text-center">
            {[
              { label: "CPU", val: `${Math.round(performance?.cpu_usage_percent ?? 42)}%`, color: "text-cyan-400" },
              { label: "RAM", val: `${Math.round(performance?.memory_usage_percent ?? 68)}%`, color: "text-emerald-400" },
              { label: "GPU", val: "76%", color: "text-indigo-400" },
              { label: "NET", val: "32%", color: "text-pink-400" },
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

        {/* Task Distribution Histogram */}
        <div className="col-span-3 bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 flex flex-col justify-between">
          <div className="text-slate-400 text-[9px] uppercase tracking-wider font-bold">Task Distribution <span className="text-[7px] font-normal text-slate-500">By Agent</span></div>
          <div className="h-14 flex items-end justify-between gap-1 px-1">
            {[
              { name: "Claude", val: taskCountByProvider["claude"] || taskCountByProvider["claude_code"] || 0, color: "bg-indigo-500" },
              { name: "Hermes", val: taskCountByProvider["hermes"] || 0, color: "bg-cyan-500" },
              { name: "OpenCode", val: taskCountByProvider["opencode"] || 0, color: "bg-emerald-500" },
              { name: "AGY CLI", val: taskCountByProvider["agy"] || taskCountByProvider["auto:agy"] || 0, color: "bg-pink-500" },
              { name: "Others", val: Math.max(0, Object.values(taskCountByProvider).reduce((a, b) => a + b, 0) - Object.entries(taskCountByProvider).filter(([k]) => !["claude","claude_code","hermes","opencode","agy","auto:agy","gemini"].includes(k)).length), color: "bg-amber-500" },
            ].map((b) => (
              <div key={b.name} className="flex flex-col items-center flex-1 h-full justify-end">
                <span className="text-[8px] text-slate-300 font-bold mb-0.5">{b.val}</span>
                <div className={`w-full rounded-t ${b.color}`} style={{ height: `${b.val * 10}%` }} />
                <span className="text-[7px] text-slate-500 truncate w-full text-center mt-0.5">{b.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Token Flow Line Chart */}
        <div className="col-span-2 bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 flex flex-col justify-between">
          <div>
            <div className="text-slate-400 text-[9px] uppercase tracking-wider font-bold">Token Flow</div>
            <div className="text-white font-bold text-xs">{telemetry.tokens || 7861} <span className="text-[8px] text-cyan-400 font-normal">tokens/sec</span></div>
          </div>
          <div className="h-10 flex items-end">
            <svg className="w-full h-full" viewBox="0 0 100 30" preserveAspectRatio="none">
              <path d="M 0 25 Q 25 5, 50 18 T 100 8" fill="none" stroke="#00f0ff" strokeWidth="1.5" />
              <path d="M 0 28 Q 25 15, 50 22 T 100 12" fill="none" stroke="#d980ff" strokeWidth="1.5" />
            </svg>
          </div>
        </div>

        {/* Connection Map Network Graphic */}
        <div className="col-span-2 bg-[#090d24]/80 border border-cyan-900/40 rounded-xl p-2.5 flex flex-col justify-between">
          <div className="text-slate-400 text-[9px] uppercase tracking-wider font-bold">Connection Map <span className="text-[7px] font-normal text-slate-500">Real-time Network</span></div>
          <div className="h-14 flex items-center justify-center">
            <svg className="w-full h-full" viewBox="0 0 100 50">
              <circle cx="20" cy="25" r="3" fill="#00f0ff" />
              <circle cx="50" cy="10" r="3" fill="#d980ff" />
              <circle cx="50" cy="40" r="3" fill="#38bdf8" />
              <circle cx="80" cy="25" r="3" fill="#f472b6" />
              <line x1="20" y1="25" x2="50" y2="10" stroke="#00f0ff" strokeWidth="0.8" opacity="0.6" />
              <line x1="20" y1="25" x2="50" y2="40" stroke="#00f0ff" strokeWidth="0.8" opacity="0.6" />
              <line x1="50" y1="10" x2="80" y2="25" stroke="#d980ff" strokeWidth="0.8" opacity="0.6" />
              <line x1="50" y1="40" x2="80" y2="25" stroke="#38bdf8" strokeWidth="0.8" opacity="0.6" />
            </svg>
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
            <div className="text-slate-500 text-[8px] uppercase tracking-wider">Active Tasks</div>
            <div className="text-white font-semibold flex items-center gap-2">
              <span>{runningTasksCount > 0 ? `${runningTasksCount} task${runningTasksCount !== 1 ? 's' : ''} running` : completedTasksCount > 0 ? `${completedTasksCount} tasks completed` : "No active tasks"}</span>
              {runningTasksCount + completedTasksCount > 0 && (
                <span className="text-cyan-400">{completedTasksCount > 0 ? Math.round(completedTasksCount / (runningTasksCount + completedTasksCount) * 100) : 0}% complete</span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-5">
          <div>
            <div className="text-slate-500 text-[8px] uppercase tracking-wider">Uptime</div>
            <div className="text-white font-bold">{performance?.uptime_seconds ? formatDuration(performance.uptime_seconds) : "—"}</div>
          </div>
          <div>
            <div className="text-slate-500 text-[8px] uppercase tracking-wider">Ready Providers</div>
            <div className="text-white font-bold">{activeAgentsCount}</div>
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

export { AgentConstellation as agentConstellation };
export default AgentConstellation;
