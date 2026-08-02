"use client";

import React, { useState, useEffect } from "react";
import { Html } from "@react-three/drei";

export interface BrainHUDProps {
  name: string;
  version?: string;
  status: string;
  health?: string;
  latency?: number;
  model?: string;
  tasks?: number;
  cpu?: number;
  memory?: number;
  gpu?: number;
  activity?: string;
  color?: string;
  position: [number, number, number];
  compact?: boolean;
}

const ProgressRing = ({ value = 0, color = "#00f0ff", label = "" }: { value?: number, color?: string, label?: string }) => {
  const radius = 12;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (value / 100) * circumference;

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-8 h-8 flex items-center justify-center">
        <svg className="w-full h-full transform -rotate-90">
          <circle
            cx="16"
            cy="16"
            r={radius}
            stroke="currentColor"
            strokeWidth="3"
            fill="transparent"
            className="text-gray-700"
          />
          <circle
            cx="16"
            cy="16"
            r={radius}
            stroke={color}
            strokeWidth="3"
            fill="transparent"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            className="transition-all duration-500 ease-out"
          />
        </svg>
        <span className="absolute text-[9px] font-mono text-white">
          {Math.round(value)}
        </span>
      </div>
      <span className="text-[9px] font-mono text-gray-400 uppercase tracking-wider">{label}</span>
    </div>
  );
};

export function BrainHUD({
  name,
  version,
  status,
  health,
  latency,
  model,
  tasks,
  cpu = 0,
  memory = 0,
  gpu = 0,
  activity,
  color = "#00f0ff",
  position,
  compact = false,
}: BrainHUDProps) {
  const [mounted, setMounted] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const getStatusColor = (s: string) => {
    switch (s?.toLowerCase()) {
      case "active":
      case "healthy":
        return "bg-green-500 shadow-[0_0_8px_#22c55e]";
      case "idle":
        return "bg-gray-400 shadow-[0_0_8px_#9ca3af]";
      case "error":
      case "unhealthy":
        return "bg-red-500 shadow-[0_0_8px_#ef4444]";
      case "busy":
      case "thinking":
      case "coding":
      case "planning":
        return "bg-cyan-500 shadow-[0_0_8px_#00f0ff]";
      default:
        return "bg-cyan-500 shadow-[0_0_8px_#00f0ff]";
    }
  };

  const isExpanded = isHovered || !compact;

  return (
    <Html
      position={position}
      center
      distanceFactor={15}
      zIndexRange={[100, 0]}
    >
      <div
        className={`transition-all duration-500 ease-out transform pointer-events-auto
          ${mounted ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0"}
        `}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <div
          className="relative bg-[#060810]/80 backdrop-blur-md rounded-lg overflow-hidden border border-white/10"
          style={{ borderColor: `${color}40`, boxShadow: `0 4px 20px -2px ${color}20` }}
        >
          {/* Top highlight bar */}
          <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ backgroundColor: color }} />

          <div className="p-3 min-w-[140px]">
            {/* Header */}
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${getStatusColor(health || status)} animate-pulse`} />
                <h3 className="text-white font-bold text-sm whitespace-nowrap">{name}</h3>
              </div>
              {version && <span className="text-xs text-gray-400 font-mono">{version}</span>}
            </div>

            {/* Expanded Content */}
            <div 
              className={`grid transition-all duration-300 ease-in-out ${
                isExpanded ? "grid-rows-[1fr] opacity-100 mt-3" : "grid-rows-[0fr] opacity-0 mt-0"
              }`}
            >
              <div className="overflow-hidden flex flex-col gap-3">
                
                {/* Meta info */}
                <div className="flex justify-between items-center text-xs font-mono text-gray-300 bg-white/5 rounded p-1.5">
                  <div className="flex items-center gap-1.5 truncate max-w-[100px]" title={model}>
                    <svg className="w-3 h-3 text-violet-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                    </svg>
                    <span className="truncate">{model || "N/A"}</span>
                  </div>
                  {latency !== undefined && (
                    <div className={`flex items-center gap-1 shrink-0 ${latency > 1000 ? 'text-red-400' : latency > 500 ? 'text-orange-400' : 'text-green-400'}`}>
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      {latency < 1000 ? `${Math.round(latency)}ms` : `${(latency / 1000).toFixed(1)}s`}
                    </div>
                  )}
                </div>

                {/* Activity & Tasks */}
                <div className="flex justify-between items-center px-1">
                  <div className="flex flex-col">
                    <span className="text-[10px] text-gray-500 uppercase tracking-wider">Activity</span>
                    <span className="text-xs text-white font-medium capitalize">{activity || status}</span>
                  </div>
                  {tasks !== undefined && (
                    <div className="flex flex-col items-end">
                      <span className="text-[10px] text-gray-500 uppercase tracking-wider">Tasks</span>
                      <span className="text-xs text-white font-medium">{tasks}</span>
                    </div>
                  )}
                </div>

                {/* Hardware Metrics */}
                <div className="flex justify-between items-center pt-2 border-t border-white/5">
                  <ProgressRing value={cpu} color="#3b82f6" label="CPU" />
                  <ProgressRing value={memory} color="#a855f7" label="MEM" />
                  <ProgressRing value={gpu} color="#22c55e" label="GPU" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Html>
  );
}
