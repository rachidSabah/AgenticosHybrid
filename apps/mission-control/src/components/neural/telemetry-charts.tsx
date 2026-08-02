"use client";

import React, { useMemo, useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "@/lib/store";
import { Activity, Server, Database, Globe, Cpu, CheckCircle2, AlertCircle } from "lucide-react";

// --- MINI SPARKLINE ---
export function MiniSparkline({ data, color = "#818cf8", height = 30 }: { data: number[], color?: string, height?: number }) {
  const width = 120;
  
  const pathData = useMemo(() => {
    if (!data || data.length === 0) return `M 0 ${height} L ${width} ${height}`;
    const maxVal = Math.max(...data, 1);
    const minVal = Math.min(...data, 0);
    const range = maxVal - minVal;
    
    const stepX = width / (data.length > 1 ? data.length - 1 : 1);
    
    return data.reduce((acc, val, i) => {
      const x = i * stepX;
      const y = height - ((val - minVal) / (range || 1)) * height * 0.8 - height * 0.1; // 10% padding
      return `${acc} ${i === 0 ? "M" : "L"} ${x} ${y}`;
    }, "");
  }, [data, height, width]);

  const fillPath = `${pathData} L ${width} ${height} L 0 ${height} Z`;

  return (
    <div className="relative flex flex-col justify-center" style={{ width, height }}>
      <svg width={width} height={height} className="overflow-visible">
        <defs>
          <linearGradient id={`gradient-${color}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.4} />
            <stop offset="100%" stopColor={color} stopOpacity={0.0} />
          </linearGradient>
        </defs>
        <motion.path
          d={fillPath}
          fill={`url(#gradient-${color})`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5 }}
        />
        <motion.path
          d={pathData}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1, ease: "easeOut" }}
        />
      </svg>
    </div>
  );
}

// --- CIRCULAR GAUGE ---
export function CircularGauge({ value, max, label, color = "#818cf8", size = 64 }: { value: number, max: number, label: string, color?: string, size?: number }) {
  const strokeWidth = 4;
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const safeValue = Math.min(Math.max(value, 0), max);
  const percentage = max > 0 ? safeValue / max : 0;
  const strokeDashoffset = circumference - percentage * circumference;

  return (
    <div className="flex flex-col items-center justify-center space-y-1">
      <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="transform -rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.1)"
            strokeWidth={strokeWidth}
          />
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset }}
            transition={{ type: "spring", stiffness: 60, damping: 15 }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-[10px] font-mono text-gray-200">
            {Math.round(percentage * 100)}%
          </span>
        </div>
      </div>
      <span className="text-[9px] font-mono uppercase tracking-wider text-gray-400">{label}</span>
    </div>
  );
}

// --- EVENT FREQUENCY METER ---
export function EventFrequencyMeter({ pulses }: { pulses: { topic: string; at: number }[] }) {
  const [bins, setBins] = useState<number[]>(Array(10).fill(0));

  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      const newBins = Array(10).fill(0);
      pulses.forEach(p => {
        const diffSec = Math.floor((now - p.at) / 1000);
        if (diffSec >= 0 && diffSec < 10) {
          newBins[9 - diffSec]++; // 9 is newest, 0 is oldest
        }
      });
      setBins(newBins);
    }, 1000);
    return () => clearInterval(interval);
  }, [pulses]);

  const maxVal = Math.max(...bins, 5);

  return (
    <div className="flex flex-col space-y-2 w-full">
      <div className="flex justify-between items-center text-[10px] font-mono uppercase tracking-wider text-gray-400">
        <span>Events/sec</span>
        <span className="text-[#818cf8]">{bins[9]} /s</span>
      </div>
      <div className="flex items-end space-x-1 h-12 w-full">
        {bins.map((val, i) => (
          <motion.div
            key={i}
            className="flex-1 bg-[#818cf8] rounded-t-[2px] opacity-80"
            initial={{ height: 0 }}
            animate={{ height: `${(val / maxVal) * 100}%` }}
            transition={{ type: "spring", stiffness: 200, damping: 20 }}
            style={{
              background: "linear-gradient(180deg, #818cf8 0%, #4f6cff 100%)",
            }}
          />
        ))}
      </div>
      <div className="flex justify-between text-[8px] font-mono text-gray-500">
        <span>-10s</span>
        <span>now</span>
      </div>
    </div>
  );
}

// --- CONNECTION STATUS PANEL ---
export function ConnectionStatusPanel() {
  const connected = useStore((state) => state.connected);
  const providers = useStore((state) => state.providers) || {};
  
  const providerCount = Object.keys(providers).length;
  const activeProviders = Object.values(providers).filter(p => p.status === "healthy").length;

  const statuses = [
    { label: "WebSocket", status: connected, icon: Globe },
    { label: "EventBus", status: true, icon: Activity },
    { label: "Database", status: true, icon: Database },
    { label: "Providers", status: activeProviders > 0, icon: Server, detail: `${activeProviders}/${providerCount}` }
  ];

  return (
    <div className="flex flex-col space-y-3">
      <span className="text-[10px] font-mono uppercase tracking-wider text-gray-400">Systems Core</span>
      <div className="grid grid-cols-2 gap-2">
        {statuses.map((sys) => (
          <div key={sys.label} className="flex items-center space-x-2 bg-white/5 border border-white/10 rounded px-2 py-1.5">
            <sys.icon className={`w-3 h-3 ${sys.status ? "text-green-400" : "text-red-400"}`} />
            <div className="flex flex-col">
              <span className="text-[9px] font-mono text-gray-300">{sys.label}</span>
              {sys.detail && <span className="text-[8px] font-mono text-gray-500">{sys.detail}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- MISSION PROGRESS PANEL ---
export function MissionProgressPanel() {
  const tasks = useStore((state) => state.tasks) || {};
  const taskList = Object.values(tasks);
  
  const total = taskList.length;
  const completed = taskList.filter(t => t.status === "completed").length;
  const running = taskList.filter(t => t.status === "in_progress" || t.status === "dispatched").length;
  const failed = taskList.filter(t => t.status === "failed").length;
  const waiting = total - completed - running - failed;

  return (
    <div className="flex flex-col space-y-3">
      <span className="text-[10px] font-mono uppercase tracking-wider text-gray-400">Mission Ops</span>
      <div className="flex items-center space-x-4">
        <CircularGauge value={completed} max={total || 1} label="Completion" color="#22c55e" size={54} />
        
        <div className="flex flex-col space-y-1 w-full text-[9px] font-mono">
          <div className="flex justify-between items-center">
            <span className="text-gray-400">Active</span>
            <span className="text-cyan-400">{running}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-gray-400">Waiting</span>
            <span className="text-gray-200">{waiting}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-gray-400">Completed</span>
            <span className="text-green-400">{completed}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-gray-400">Failed</span>
            <span className="text-red-400">{failed}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- MAIN TELEMETRY PANEL ---
export function TelemetryPanel({ className = "" }: { className?: string }) {
  const telemetry = useStore((state) => state.telemetry);
  const perf = useStore((state) => state.performance);
  const pulses = telemetry?.pulses || [];
  
  // Build historical data from real performance metrics
  const history = useRef<{ cpu: number[], mem: number[], net: number[] }>({
    cpu: Array(30).fill(0), mem: Array(30).fill(0), net: Array(30).fill(0)
  });

  useEffect(() => {
    if (!perf) return;
    history.current = {
      cpu: [...history.current.cpu.slice(1), perf.cpu_usage_percent],
      mem: [...history.current.mem.slice(1), perf.memory_usage_percent],
      net: [...history.current.net.slice(1), Math.min(perf.process_count * 10, 100)],
    };
  }, [perf]);

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={`bg-[rgba(8,10,16,0.85)] backdrop-blur-xl border border-[#818cf8]/20 rounded-xl p-4 w-72 flex flex-col space-y-6 ${className}`}
    >
      <div className="flex items-center space-x-2 border-b border-white/10 pb-3">
        <Cpu className="w-4 h-4 text-[#818cf8]" />
        <h2 className="text-[12px] font-mono text-gray-200 uppercase tracking-widest font-bold">Nexus Telemetry</h2>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <CircularGauge value={history.current.cpu[29] || 0} max={100} label="CPU" color="#00f0ff" size={50} />
        <CircularGauge value={history.current.mem[29] || 0} max={100} label="MEM" color="#a855f7" size={50} />
        <CircularGauge value={telemetry?.latency || 0} max={1000} label="LATENCY" color="#f97316" size={50} />
      </div>

      <div className="flex flex-col space-y-1">
        <span className="text-[10px] font-mono uppercase tracking-wider text-gray-400">Network Traffic</span>
        <MiniSparkline data={history.current.net} color="#818cf8" height={36} />
      </div>

      <EventFrequencyMeter pulses={pulses} />
      
      <div className="border-t border-white/5 pt-4">
        <ConnectionStatusPanel />
      </div>

      <div className="border-t border-white/5 pt-4">
        <MissionProgressPanel />
      </div>
    </motion.div>
  );
}
