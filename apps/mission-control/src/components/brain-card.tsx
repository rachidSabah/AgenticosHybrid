"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Brain, Cpu, MemoryStick, Activity, Zap, Clock,
  Globe, Server, ChevronDown, ChevronRight,
  RefreshCw,
} from "lucide-react";
import { Badge } from "@/components/ui/primitives";
import type { BrainRecord, BrainVendor } from "@/lib/use-brains";
import { brainStatusToColor, VENDOR_ICON_MAP } from "@/lib/use-brains";
import { type ReactNode } from "react";

// ── Vendor icon ─────────────────────────────────────────────────────────────

export function VendorIcon({ vendor, size = 16 }: { vendor: BrainVendor; size?: number }) {
  const color = VENDOR_ICON_MAP[vendor] ?? "#94a3b8";
  const initial = vendor.charAt(0).toUpperCase();

  return (
    <span
      className="inline-flex items-center justify-center rounded-full font-bold text-white"
      style={{
        backgroundColor: color + "33",
        color,
        width: size + 4,
        height: size + 4,
        fontSize: Math.max(8, size * 0.5),
      }}
      title={vendor}
    >
      {initial}
    </span>
  );
}

// ── Status indicator ────────────────────────────────────────────────────────

export function BrainStatusDot({ status, pulse }: { status: string; pulse?: boolean }) {
  const color = brainStatusToColor(status as any);
  return (
    <span className="relative inline-flex h-2.5 w-2.5">
      {pulse && (
        <span
          className="absolute inline-flex h-full w-full rounded-full animate-ping opacity-60"
          style={{ backgroundColor: color }}
        />
      )}
      <span
        className="relative inline-flex h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
      />
    </span>
  );
}

// ── Health bar ──────────────────────────────────────────────────────────────

export function HealthBar({ value, max = 100, label, color }: {
  value: number;
  max?: number;
  label?: string;
  color?: string;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const barColor = color ?? (
    pct > 80 ? "#10b981" : pct > 50 ? "#f59e0b" : pct > 20 ? "#f97316" : "#ef4444"
  );

  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-[10px] text-faint w-8 shrink-0">{label}</span>}
      <div className="h-1.5 flex-1 rounded-full bg-surface/40 overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          style={{ backgroundColor: barColor }}
        />
      </div>
      <span className="text-[10px] tabular-nums text-faint w-8 text-right shrink-0">
        {value.toFixed(0)}{max === 100 ? "%" : ""}
      </span>
    </div>
  );
}

// ── Brain Card ──────────────────────────────────────────────────────────────

interface BrainCardProps {
  brain: BrainRecord;
  expanded?: boolean;
  onToggle?: () => void;
  onSelect?: () => void;
  onRefresh?: () => void;
  onRemove?: () => void;
}

export function BrainCard({
  brain,
  expanded = false,
  onToggle,
  onSelect,
  onRefresh,
  onRemove,
}: BrainCardProps) {
  const statusColor = brainStatusToColor(brain.status);
  const statusPulse = ["connected", "executing", "busy", "healthy"].includes(brain.status);

  // Format uptime
  const uptimeStr = formatDuration(brain.uptime);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="relative rounded-2xl border border-border/30 bg-surface/20 p-4 backdrop-blur-sm hover:bg-surface/30 transition cursor-pointer group"
      style={{ borderColor: statusColor + "33" }}
      onClick={onSelect}
    >
      {/* Glow on active status */}
      {statusPulse && (
        <motion.div
          className="absolute inset-0 rounded-2xl opacity-20 pointer-events-none"
          animate={{ boxShadow: `0 0 15px ${statusColor}44` }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
        />
      )}

      {/* Status indicator top-right */}
      <div className="absolute top-3 right-3 flex items-center gap-1.5">
        <BrainStatusDot status={brain.status} pulse={statusPulse} />
        <span className="text-[9px] font-medium text-faint">{brain.status}</span>
      </div>

      {/* Header */}
      <div className="relative z-10">
        <div className="flex items-center gap-3">
          <VendorIcon vendor={brain.vendor} size={20} />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold truncate text-text">
              {brain.display_name}
            </div>
            <div className="text-[10px] text-faint truncate flex items-center gap-1">
              <span>{brain.brain_type}</span>
              <span className="mx-1">·</span>
              <span>{brain.vendor}</span>
              <span className="mx-1">·</span>
              <span>{brain.runtime}</span>
            </div>
          </div>
        </div>

        {/* Quick stats */}
        <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] text-faint">
          <div className="flex items-center gap-1.5">
            <Cpu size={12} />
            <span>{brain.cpu_usage.toFixed(0)}%</span>
          </div>
          <div className="flex items-center gap-1.5">
            <MemoryStick size={12} />
            <span>{(brain.memory_usage / 1024).toFixed(1)}GB</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Activity size={12} />
            <span>{brain.latency.toFixed(0)}ms</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Zap size={12} />
            <span>{brain.current_tasks} tasks</span>
          </div>
        </div>

        {/* Health bar for CPU */}
        <div className="mt-2">
          <HealthBar value={brain.cpu_usage} label="CPU" />
        </div>
        <div className="mt-1">
          <HealthBar value={brain.memory_usage} max={65536} label="RAM" />
        </div>

        {/* Version & uptime */}
        <div className="mt-2 flex items-center gap-2 text-[9px] text-faint">
          <span className="flex items-center gap-1">
            <Server size={10} />
            v{brain.version}
          </span>
          <span className="flex items-center gap-1">
            <Clock size={10} />
            {uptimeStr}
          </span>
          {brain.connection_state === "connected" ? (
            <Globe size={10} className="text-ok" />
          ) : (
            <Globe size={10} className="text-danger" />
          )}
        </div>

        {/* Tags */}
        {brain.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {brain.tags.slice(0, 3).map((tag) => (
              <Badge key={tag} tone="default">{tag}</Badge>
            ))}
            {brain.tags.length > 3 && (
              <Badge tone="default">+{brain.tags.length - 3}</Badge>
            )}
          </div>
        )}

        {/* Collapsible details */}
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="mt-3 border-t border-border/30 pt-3 space-y-2 text-[10px] text-faint"
            >
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="font-medium text-[9px] uppercase text-faint/70">Health</div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <BrainStatusDot status={brain.health} />
                    <span>{brain.health}</span>
                  </div>
                </div>
                <div>
                  <div className="font-medium text-[9px] uppercase text-faint/70">Queue</div>
                  <div className="mt-0.5">{brain.queue_depth} queued</div>
                </div>
                <div>
                  <div className="font-medium text-[9px] uppercase text-faint/70">Throughput</div>
                  <div className="mt-0.5">{brain.throughput.toFixed(1)}/s</div>
                </div>
                <div>
                  <div className="font-medium text-[9px] uppercase text-faint/70">Models</div>
                  <div className="mt-0.5">{brain.active_models} active</div>
                </div>
                <div>
                  <div className="font-medium text-[9px] uppercase text-faint/70">Sessions</div>
                  <div className="mt-0.5">{brain.session_count}</div>
                </div>
                <div>
                  <div className="font-medium text-[9px] uppercase text-faint/70">Errors</div>
                  <div className="mt-0.5 text-danger">{brain.error_count}</div>
                </div>
              </div>

              {brain.last_error && (
                <div className="rounded-lg bg-danger/10 border border-danger/20 p-2 text-[9px] text-danger">
                  {brain.last_error}
                </div>
              )}

              <div className="flex items-center gap-2 pt-1">
                <span className="text-[8px] text-faint/50">
                  Discovered {new Date(brain.discovered_at).toLocaleDateString()}
                </span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Action buttons */}
      <div className="absolute bottom-3 right-3 flex items-center gap-1 z-20">
        {onRefresh && (
          <button
            onClick={(e) => { e.stopPropagation(); onRefresh(); }}
            className="rounded-full p-1 hover:bg-surface/30 transition text-faint hover:text-text"
            title="Refresh"
          >
            <RefreshCw size={12} />
          </button>
        )}
        {onToggle && (
          <button
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            className="rounded-full p-1 hover:bg-surface/30 transition text-faint hover:text-text"
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        )}
      </div>
    </motion.div>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}
