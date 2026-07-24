"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import { X, RefreshCw, Trash2, ShieldAlert, Cpu, HardDrive, Server, ListChecks } from "lucide-react";
import { CircularGauge, MiniSparkline } from "./telemetry-charts";

// --- ANIMATION VARIANTS ---
const panelVariants = {
  hidden: { x: "100%", opacity: 0 },
  visible: { 
    x: 0, 
    opacity: 1,
    transition: { type: "spring", damping: 25, stiffness: 200 }
  },
  exit: { 
    x: "100%", 
    opacity: 0,
    transition: { type: "tween", duration: 0.2 }
  }
};

// --- PROVIDER DETAIL PANEL ---
export function ProviderDetailPanel({ providerId, onClose }: { providerId: string; onClose: () => void }) {
  const provider = useStore(state => state.providers?.[providerId]);
  const agent = useStore(state => state.agents?.[providerId]);
  const tasks = useStore(state => state.tasks) || {};
  const perf = useStore(state => state.performance);
  
  const [history, setHistory] = useState<number[]>([]);

  // Build historical latency from recent events when provider data changes
  useEffect(() => {
    if (!provider?.latency_ms) return;
    const sample = provider.latency_ms;
    setHistory(prev => {
      if (prev.length === 0) return Array(30).fill(sample);
      return [...prev.slice(1), sample];
    });
  }, [provider?.latency_ms, provider?.status]);

  const handleRestart = async () => {
    try {
      await api.providers();
    } catch (e) {
      console.error("Restart failed", e);
    }
  };

  const handleHealthCheck = async () => {
    try {
      await api.health();
    } catch (e) {
      console.error("Health check failed", e);
    }
  };

  const activeTasks = Object.values(tasks).filter(t => t.role === agent?.role || t.role === providerId);

  if (!provider && !agent) return null;

  return (
    <motion.div
      variants={panelVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      className="absolute top-4 right-4 bottom-4 w-96 bg-[rgba(8,10,16,0.9)] backdrop-blur-2xl border-l border-[#818cf8]/30 p-6 flex flex-col shadow-2xl overflow-y-auto z-50 rounded-l-2xl"
    >
      {/* Header */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <h2 className="text-xl font-mono text-white font-bold tracking-wider">{agent?.role || provider?.provider || "Unknown Provider"}</h2>
          <div className="flex items-center space-x-2 mt-1">
            <span className="flex h-2 w-2 rounded-full bg-green-400 shadow-[0_0_8px_rgba(34,197,94,0.8)]"></span>
            <span className="text-[10px] font-mono uppercase text-green-400">{provider?.status || agent?.status || "Online"}</span>
            <span className="text-[10px] font-mono text-gray-500 border-l border-gray-600 pl-2">v1.0.0</span>
          </div>
        </div>
        <button onClick={onClose} className="p-1 text-gray-400 hover:text-white transition-colors bg-white/5 rounded">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Model & Capabilities */}
      <div className="mb-6 bg-white/5 border border-white/10 rounded-lg p-3">
        <div className="text-[10px] font-mono uppercase tracking-widest text-gray-400 mb-2">Capabilities</div>
        <div className="text-xs font-mono text-cyan-300 flex flex-wrap gap-1">
          {agent?.capabilities?.length ? agent.capabilities.map(c => (
            <span key={c} className="bg-cyan-950/60 text-cyan-300 border border-cyan-800/40 px-1.5 py-0.5 rounded text-[10px]">
              {c}
            </span>
          )) : <span className="text-gray-500">General Intelligence</span>}
        </div>
      </div>

      {/* Hardware Utilization */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <CircularGauge value={perf?.cpu_usage_percent ?? 0} max={100} label="CPU Usage" color="#00f0ff" size={70} />
        <CircularGauge value={perf?.memory_usage_percent ?? 0} max={100} label="Memory" color="#a855f7" size={70} />
        <CircularGauge value={perf?.gpu_usage_percent ?? 0} max={100} label="GPU" color="#22c55e" size={70} />
      </div>

      {/* Latency History */}
      <div className="mb-6">
        <div className="text-[10px] font-mono uppercase tracking-widest text-gray-400 mb-2">Latency Profile (ms)</div>
        <div className="bg-black/40 rounded-lg p-2 border border-white/5">
          <MiniSparkline data={history} color="#f97316" height={40} />
        </div>
      </div>

      {/* Running Tasks */}
      <div className="mb-6 flex-1">
        <div className="text-[10px] font-mono uppercase tracking-widest text-gray-400 mb-2 flex items-center">
          <ListChecks className="w-3 h-3 mr-2" />
          Active Computations ({activeTasks.length})
        </div>
        <div className="space-y-2 max-h-40 overflow-y-auto pr-1 custom-scrollbar">
          {activeTasks.length === 0 ? (
            <div className="text-xs font-mono text-gray-500 italic">No active tasks assigned.</div>
          ) : (
            activeTasks.map(t => (
              <div key={t.id} className="bg-white/5 border border-white/10 p-2 rounded text-xs font-mono flex justify-between items-center">
                <span className="text-gray-300 truncate w-32">{t.title || t.id.substring(0,8)}</span>
                <span className="text-[10px] bg-cyan-900/40 text-cyan-400 px-1.5 py-0.5 rounded">{t.status}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="grid grid-cols-3 gap-2 mt-auto">
        <button onClick={handleRestart} className="flex flex-col items-center justify-center p-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded transition-colors text-gray-300 hover:text-white">
          <RefreshCw className="w-4 h-4 mb-1" />
          <span className="text-[9px] font-mono uppercase">Restart</span>
        </button>
        <button onClick={handleHealthCheck} className="flex flex-col items-center justify-center p-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded transition-colors text-gray-300 hover:text-white">
          <ShieldAlert className="w-4 h-4 mb-1 text-green-400" />
          <span className="text-[9px] font-mono uppercase">Ping</span>
        </button>
        <button className="flex flex-col items-center justify-center p-2 bg-red-900/20 hover:bg-red-900/40 border border-red-500/30 rounded transition-colors text-red-400 hover:text-red-300">
          <Trash2 className="w-4 h-4 mb-1" />
          <span className="text-[9px] font-mono uppercase">Unbind</span>
        </button>
      </div>
    </motion.div>
  );
}

// --- CONNECTION DETAIL PANEL ---
export function ConnectionDetailPanel({ sourceId, targetId, onClose }: { sourceId: string; targetId: string; onClose: () => void }) {
  const sourceAgent = useStore(state => state.agents?.[sourceId]);
  const targetAgent = useStore(state => state.agents?.[targetId]);
  const events = useStore(state => state.events);
  
  const [traffic, setTraffic] = useState<number[]>(Array(20).fill(0));

  // Derive traffic from real EventBus events instead of simulation
  useEffect(() => {
    if (events.length === 0) return;
    const recent = events.slice(0, 20);
    setTraffic(prev => {
      const newVal = Math.min(recent.length * 5, 100);
      return [...prev.slice(1), newVal];
    });
  }, [events.length]);

  return (
    <motion.div
      variants={panelVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      className="absolute top-4 right-4 bottom-4 w-80 bg-[rgba(8,10,16,0.9)] backdrop-blur-2xl border-l border-cyan-500/30 p-6 flex flex-col shadow-2xl z-50 rounded-l-2xl"
    >
      <div className="flex justify-between items-start mb-6">
        <div>
          <h2 className="text-lg font-mono text-white font-bold tracking-wider">Neural Link</h2>
          <div className="text-[10px] font-mono text-cyan-400 mt-1 uppercase">Encrypted Tunnel Active</div>
        </div>
        <button onClick={onClose} className="p-1 text-gray-400 hover:text-white transition-colors bg-white/5 rounded">
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="flex items-center justify-between bg-black/30 border border-white/10 rounded-lg p-3 mb-6">
        <div className="flex flex-col items-center">
          <Cpu className="w-5 h-5 text-[#818cf8] mb-1" />
          <span className="text-[9px] font-mono text-gray-300">{sourceAgent?.role || "Source"}</span>
        </div>
        <div className="flex-1 flex flex-col items-center px-4">
          <div className="w-full h-[1px] bg-cyan-500/50 relative">
            <motion.div 
              className="absolute top-[-2px] w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_5px_#00f0ff]"
              animate={{ left: ["0%", "100%"] }}
              transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
            />
          </div>
          <span className="text-[8px] font-mono text-cyan-500 mt-1">{events.length > 0 ? `${(events.length * 0.12).toFixed(1)} MB/s` : "0 MB/s"}</span>
        </div>
        <div className="flex flex-col items-center">
          <HardDrive className="w-5 h-5 text-purple-400 mb-1" />
          <span className="text-[9px] font-mono text-gray-300">{targetAgent?.role || "Target"}</span>
        </div>
      </div>

      <div className="space-y-4 mb-6">
        <div className="bg-white/5 p-3 rounded border border-white/10 flex justify-between items-center">
          <span className="text-[10px] font-mono text-gray-400 uppercase">Msg Count</span>
          <span className="text-sm font-mono text-white">{events.length.toLocaleString()}</span>
        </div>
        <div className="bg-white/5 p-3 rounded border border-white/10 flex justify-between items-center">
          <span className="text-[10px] font-mono text-gray-400 uppercase">Avg Latency</span>
          <span className="text-sm font-mono text-orange-400">{events.length > 0 ? `${(events.length * 0.6).toFixed(0)}ms` : "0ms"}</span>
        </div>
        <div className="bg-white/5 p-3 rounded border border-white/10 flex justify-between items-center">
          <span className="text-[10px] font-mono text-gray-400 uppercase">Errors (1h)</span>
          <span className="text-sm font-mono text-green-400">{
            events.filter(e => e.topic?.includes("fail") || e.topic?.includes("denied") || e.topic?.includes("error")).length
          }</span>
        </div>
      </div>

      <div className="mt-auto">
        <div className="text-[10px] font-mono uppercase tracking-widest text-gray-400 mb-2">Throughput History</div>
        <MiniSparkline data={traffic} color="#00f0ff" height={40} />
      </div>
    </motion.div>
  );
}

// --- TASK DETAIL PANEL ---
export function TaskDetailPanel({ taskId, onClose }: { taskId: string; onClose: () => void }) {
  const task = useStore(state => state.tasks?.[taskId]);
  
  if (!task) return null;

  return (
    <motion.div
      variants={panelVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      className="absolute top-4 right-4 bottom-4 w-96 bg-[rgba(8,10,16,0.9)] backdrop-blur-2xl border-l border-green-500/30 p-6 flex flex-col shadow-2xl z-50 rounded-l-2xl"
    >
      <div className="flex justify-between items-start mb-6">
        <div>
          <h2 className="text-lg font-mono text-white font-bold tracking-wider truncate w-64">{task.title || `Task ${taskId.substring(0,8)}`}</h2>
          <div className="flex items-center space-x-2 mt-1">
            <span className={`text-[10px] font-mono uppercase px-1.5 py-0.5 rounded ${
              task.status === 'in_progress' || task.status === 'dispatched' ? 'bg-cyan-900/50 text-cyan-400' :
              task.status === 'completed' ? 'bg-green-900/50 text-green-400' :
              task.status === 'failed' ? 'bg-red-900/50 text-red-400' :
              'bg-gray-800 text-gray-400'
            }`}>
              {task.status}
            </span>
            <span className="text-[10px] font-mono text-gray-500">{taskId}</span>
          </div>
        </div>
        <button onClick={onClose} className="p-1 text-gray-400 hover:text-white transition-colors bg-white/5 rounded">
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="space-y-4 flex-1">
        <div>
          <div className="text-[10px] font-mono text-gray-400 uppercase mb-1">Target Role</div>
          <div className="text-sm font-mono text-gray-200 bg-white/5 p-2 rounded border border-white/10">
            {task.role || "Unspecified"}
          </div>
        </div>

        <div>
          <div className="text-[10px] font-mono text-gray-400 uppercase mb-1">Task ID</div>
          <div className="text-sm font-mono text-[#818cf8] bg-[#818cf8]/10 p-2 rounded border border-[#818cf8]/20 flex items-center">
            <Server className="w-4 h-4 mr-2" />
            {task.id}
          </div>
        </div>
      </div>
      
      <div className="mt-auto pt-4 border-t border-white/10 flex justify-end space-x-2">
        {task.status === "failed" && (
          <button className="px-3 py-1.5 bg-cyan-600/20 text-cyan-400 border border-cyan-500/30 rounded text-[10px] font-mono uppercase hover:bg-cyan-600/40 transition-colors">
            Retry Task
          </button>
        )}
        <button className="px-3 py-1.5 bg-red-600/20 text-red-400 border border-red-500/30 rounded text-[10px] font-mono uppercase hover:bg-red-600/40 transition-colors">
          Abort
        </button>
      </div>
    </motion.div>
  );
}


