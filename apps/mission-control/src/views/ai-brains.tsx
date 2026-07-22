"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, Stat, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { type AgentNode } from "@/lib/types";
import { Brain, Zap, Cpu, MemoryStick, HardDrive, Thermometer, Activity, GitBranch, Network, Wifi, Shield, Settings, RefreshCw, Search, Filter, ChevronDown, ChevronRight } from "lucide-react";

interface BrainNode {
  id: string;
  agentId: string;
  agentRole: string;
  status: "idle" | "thinking" | "coding" | "failed" | "completed";
  energy: number;
  neurons: number;
  synapses: number;
  cpu: number;
  memory: number;
  temperature: number;
  lastPulse: number;
  pulses: { topic: string; at: number }[];
}

interface FilterState {
  status: string[];
  search: string;
  sort: "energy" | "neurons" | "synapses" | "cpu" | "memory" | "temperature" | "newest";
}

export function AIBrains() {
  const agents = useStore((s) => s.agents);
  const telemetry = useStore((s) => s.telemetry);
  const [selected, setSelected] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [filters, setFilters] = useState<FilterState>({
    status: ["thinking", "coding", "idle"],
    search: "",
    sort: "energy",
  });

  const brainNodes = useMemo(() => {
    return Object.values(agents).map((agent) => {
      const statusMap: Record<string, BrainNode["status"]> = {
        running: "thinking",
        completed: "completed",
        failed: "failed",
        idle: "idle",
        healthy: "idle",
        degraded: "idle",
        down: "failed",
        thinking: "thinking",
        coding: "coding",
      };

      const status = statusMap[agent.status] || "idle";
      const energy = status === "thinking" ? 80 + Math.random() * 20 : status === "coding" ? 60 + Math.random() * 30 : 20 + Math.random() * 30;
      const neurons = status === "thinking" ? 1000 + Math.random() * 500 : status === "coding" ? 800 + Math.random() * 400 : 500 + Math.random() * 300;
      const synapses = status === "thinking" ? 5000 + Math.random() * 2000 : status === "coding" ? 3000 + Math.random() * 1500 : 1000 + Math.random() * 1000;
      const cpu = status === "thinking" ? 70 + Math.random() * 20 : status === "coding" ? 50 + Math.random() * 30 : 20 + Math.random() * 20;
      const memory = status === "thinking" ? 1000 + Math.random() * 500 : status === "coding" ? 800 + Math.random() * 400 : 500 + Math.random() * 300;
      const temperature = status === "thinking" ? 70 + Math.random() * 15 : status === "coding" ? 60 + Math.random() * 20 : 40 + Math.random() * 20;

      return {
        id: `brain-${agent.id}`,
        agentId: agent.id,
        agentRole: agent.role,
        status,
        energy,
        neurons,
        synapses,
        cpu,
        memory,
        temperature,
        lastPulse: Date.now() - Math.random() * 60000,
        pulses: telemetry.pulses.filter((p) => p.topic.includes(agent.id)).slice(0, 5),
      };
    });
  }, [agents, telemetry.pulses]);

  const filteredBrains = useMemo(() => {
    return brainNodes.filter((brain) => {
      const statusMatch = filters.status.includes(brain.status);
      const searchMatch = filters.search
        ? brain.agentId.toLowerCase().includes(filters.search.toLowerCase()) ||
          brain.agentRole.toLowerCase().includes(filters.search.toLowerCase())
        : true;
      return statusMatch && searchMatch;
    }).sort((a, b) => {
      if (filters.sort === "energy") return b.energy - a.energy;
      if (filters.sort === "neurons") return b.neurons - a.neurons;
      if (filters.sort === "synapses") return b.synapses - a.synapses;
      if (filters.sort === "cpu") return b.cpu - a.cpu;
      if (filters.sort === "memory") return b.memory - a.memory;
      if (filters.sort === "temperature") return b.temperature - a.temperature;
      return b.lastPulse - a.lastPulse;
    });
  }, [brainNodes, filters]);

  const toggleExpand = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleStatusFilter = (status: string) => {
    setFilters((prev) => ({
      ...prev,
      status: prev.status.includes(status)
        ? prev.status.filter((s) => s !== status)
        : [...prev.status, status],
    }));
  };

  const clearFilters = () => {
    setFilters({
      status: ["thinking", "coding", "idle"],
      search: "",
      sort: "energy",
    });
  };

  return (
    <div className="grid h-full grid-cols-12 gap-4 overflow-auto p-4">
      {/* Left: Filters */}
      <div className="col-span-12 lg:col-span-3 flex flex-col gap-4">
        <Panel title="Filters" className="flex-shrink-0">
          <div className="space-y-3">
            <div>
              <label className="text-[10px] font-medium text-faint">Search</label>
              <div className="mt-1 relative">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
                <input
                  type="text"
                  placeholder="Search brains..."
                  value={filters.search}
                  onChange={(e) => setFilters((prev) => ({ ...prev, search: e.target.value }))}
                  className="w-full rounded-lg border border-border/40 bg-surface/10 pl-8 pr-2.5 py-1.5 text-[11px] focus:border-accent/50 focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="text-[10px] font-medium text-faint">Status</label>
              <div className="mt-1 grid grid-cols-2 gap-1.5">
                {[
                  { id: "thinking", label: "Thinking", icon: <Brain size={12} /> },
                  { id: "coding", label: "Coding", icon: <GitBranch size={12} /> },
                  { id: "idle", label: "Idle", icon: <Activity size={12} /> },
                  { id: "failed", label: "Failed", icon: <Zap size={12} /> },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => toggleStatusFilter(item.id)}
                    className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition ${
                      filters.status.includes(item.id)
                        ? "bg-accent/20 text-accent"
                        : "text-faint hover:text-text hover:bg-surface/20"
                    }`}
                  >
                    {item.icon}
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-[10px] font-medium text-faint">Sort</label>
              <div className="mt-1 grid grid-cols-2 gap-1.5">
                {[
                  { id: "energy", label: "Energy" },
                  { id: "neurons", label: "Neurons" },
                  { id: "synapses", label: "Synapses" },
                  { id: "cpu", label: "CPU" },
                  { id: "memory", label: "Memory" },
                  { id: "temperature", label: "Temperature" },
                  { id: "newest", label: "Newest" },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setFilters((prev) => ({ ...prev, sort: item.id as any }))}
                    className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition ${
                      filters.sort === item.id
                        ? "bg-accent/20 text-accent"
                        : "text-faint hover:text-text hover:bg-surface/20"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <button
              onClick={clearFilters}
              className="mt-1 w-full rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-faint hover:text-text hover:bg-surface/20 transition"
            >
              Clear filters
            </button>
          </div>
        </Panel>
        <Panel title="Stats" className="flex-shrink-0">
          <div className="space-y-2">
            <Stat label="Total Brains" value={brainNodes.length} />
            <Stat label="Filtered Brains" value={filteredBrains.length} />
            <Stat label="Thinking" value={brainNodes.filter((b) => b.status === "thinking").length} />
            <Stat label="Coding" value={brainNodes.filter((b) => b.status === "coding").length} />
            <Stat label="Errors" value={telemetry.errors} tone={telemetry.errors > 0 ? "danger" : undefined} />
          </div>
        </Panel>
        {selected && (
          <Panel title="Details" className="flex-shrink-0">
            <BrainDetails brain={filteredBrains.find((b) => b.id === selected)} />
          </Panel>
        )}
      </div>

      {/* Right: Brain Grid */}
      <div className="col-span-12 lg:col-span-9 flex flex-col gap-4 h-full min-h-0">
        <Panel
          title="AI Brains"
          subtitle="Live neural activity"
          className="flex-1 min-h-0"
        >
          {filteredBrains.length === 0 ? (
            <div className="p-4">
              <Empty title="No brains match filters" hint="Try adjusting your filters or search query" />
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 overflow-y-auto h-full p-2">
              {filteredBrains.map((brain) => {
                const isExpanded = expanded[brain.id];
                const statusColor = {
                  thinking: "#8b5cf6",
                  coding: "#06b6d4",
                  idle: "#64748b",
                  failed: "#ef4444",
                  completed: "#10b981",
                }[brain.status];

                return (
                  <motion.div
                    key={brain.id}
                    layout
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="relative rounded-2xl border border-border/30 bg-surface/20 p-4 backdrop-blur-sm hover:bg-surface/30 transition"
                    style={{ borderColor: statusColor + "33" }}
                    onClick={() => setSelected(brain.id)}
                  >
                    {/* Glow effect */}
                    <motion.div
                      className="absolute inset-0 rounded-2xl opacity-30"
                      animate={{ boxShadow: `0 0 20px ${statusColor}33` }}
                      transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                    />

                    {/* Status indicator */}
                    <div className="absolute top-3 right-3">
                      <div className="flex items-center gap-1.5 text-[9px] font-medium">
                        <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: statusColor }} />
                        <span>{brain.status}</span>
                      </div>
                    </div>

                    {/* Energy pulse */}
                    <AnimatePresence>
                      {brain.status === "thinking" && (
                        <motion.div
                          className="absolute inset-0 rounded-2xl"
                          initial={{ opacity: 0, scale: 1 }}
                          animate={{ opacity: 0.1, scale: 1.2 }}
                          exit={{ opacity: 0, scale: 1.5 }}
                          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                          style={{ backgroundColor: statusColor }}
                        />
                      )}
                    </AnimatePresence>

                    <div className="relative z-10">
                      <div className="flex items-center gap-3">
                        <Brain size={20} className="text-accent" />
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-semibold truncate">{brain.agentRole}</div>
                          <div className="text-[10px] text-faint truncate">ID: {brain.agentId}</div>
                        </div>
                      </div>

                      <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] text-faint">
                        <div className="flex items-center gap-1.5">
                          <Zap size={12} />
                          <span>{brain.energy.toFixed(0)}%</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Cpu size={12} />
                          <span>{brain.cpu.toFixed(0)}%</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <MemoryStick size={12} />
                          <span>{(brain.memory / 1000).toFixed(1)}GB</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Thermometer size={12} />
                          <span>{brain.temperature.toFixed(0)}°C</span>
                        </div>
                      </div>

                      <div className="mt-3 flex items-center gap-2">
                        <div className="h-1 flex-1 rounded-full bg-surface/50">
                          <div
                            className="h-full rounded-full"
                            style={{ width: `${brain.energy}%`, backgroundColor: statusColor }}
                          />
                        </div>
                        <span className="text-[9px] font-medium">{brain.energy.toFixed(0)}%</span>
                      </div>

                      {isExpanded && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="mt-3 border-t border-border/30 pt-3"
                        >
                          <div className="grid grid-cols-2 gap-2 text-[9px] text-faint">
                            <div>
                              <div className="font-medium">Neurons</div>
                              <div>{brain.neurons.toLocaleString()}</div>
                            </div>
                            <div>
                              <div className="font-medium">Synapses</div>
                              <div>{brain.synapses.toLocaleString()}</div>
                            </div>
                            <div>
                              <div className="font-medium">Last Pulse</div>
                              <div>{new Date(brain.lastPulse).toLocaleTimeString()}</div>
                            </div>
                            <div>
                              <div className="font-medium">Pulses</div>
                              <div>{brain.pulses.length}</div>
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </div>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleExpand(brain.id);
                      }}
                      className="absolute bottom-3 right-3 rounded-full p-1 hover:bg-surface/30 transition"
                    >
                      {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                  </motion.div>
                );
              })}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function BrainDetails({ brain }: { brain?: BrainNode }) {
  if (!brain) return null;

  return (
    <div className="space-y-3 text-[10px] text-faint">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <div className="font-medium">Agent ID</div>
          <div>{brain.agentId}</div>
        </div>
        <div>
          <div className="font-medium">Role</div>
          <div>{brain.agentRole}</div>
        </div>
        <div>
          <div className="font-medium">Status</div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: {
              thinking: "#8b5cf6",
              coding: "#06b6d4",
              idle: "#64748b",
              failed: "#ef4444",
              completed: "#10b981",
            }[brain.status] }} />
            <span>{brain.status}</span>
          </div>
        </div>
        <div>
          <div className="font-medium">Energy</div>
          <div>{brain.energy.toFixed(0)}%</div>
        </div>
        <div>
          <div className="font-medium">Neurons</div>
          <div>{brain.neurons.toLocaleString()}</div>
        </div>
        <div>
          <div className="font-medium">Synapses</div>
          <div>{brain.synapses.toLocaleString()}</div>
        </div>
        <div>
          <div className="font-medium">CPU</div>
          <div>{brain.cpu.toFixed(0)}%</div>
        </div>
        <div>
          <div className="font-medium">Memory</div>
          <div>{(brain.memory / 1000).toFixed(1)}GB</div>
        </div>
        <div>
          <div className="font-medium">Temperature</div>
          <div>{brain.temperature.toFixed(0)}°C</div>
        </div>
        <div>
          <div className="font-medium">Last Pulse</div>
          <div>{new Date(brain.lastPulse).toLocaleString()}</div>
        </div>
      </div>

      <div>
        <div className="font-medium">Recent Pulses</div>
        <div className="mt-1 space-y-1">
          {brain.pulses.map((pulse, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent/50" />
              <span className="truncate flex-1">{pulse.topic}</span>
              <span className="text-[9px] text-faint/70">{new Date(pulse.at).toLocaleTimeString()}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}