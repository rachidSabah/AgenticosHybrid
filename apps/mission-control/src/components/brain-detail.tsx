"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity, AlertTriangle, BarChart3, BookOpen, Box,
  Heart, ListTodo, Logs,
  Network, Settings, Sliders, Zap,
  Clock, Globe, Wifi, Server,
} from "lucide-react";
import { Badge, Stat } from "@/components/ui/primitives";
import { BrainStatusDot, VendorIcon } from "@/components/brain-card";
import type { BrainRecord, BrainRelationship } from "@/lib/use-brains";
import { brainStatusToColor } from "@/lib/use-brains";

// ── Tab definitions ─────────────────────────────────────────────────────────

interface TabDef {
  id: string;
  label: string;
  icon: React.ReactNode;
}

const TABS: TabDef[] = [
  { id: "overview", label: "Overview", icon: <Activity size={14} /> },
  { id: "capabilities", label: "Capabilities", icon: <Zap size={14} /> },
  { id: "health", label: "Health", icon: <Heart size={14} /> },
  { id: "metrics", label: "Metrics", icon: <BarChart3 size={14} /> },
  { id: "logs", label: "Logs", icon: <Logs size={14} /> },
  { id: "events", label: "Events", icon: <Activity size={14} /> },
  { id: "relationships", label: "Relationships", icon: <Network size={14} /> },
  { id: "configuration", label: "Configuration", icon: <Settings size={14} /> },
  { id: "models", label: "Models", icon: <Box size={14} /> },
  { id: "history", label: "History", icon: <Clock size={14} /> },
  { id: "tasks", label: "Tasks", icon: <ListTodo size={14} /> },
  { id: "performance", label: "Performance", icon: <Sliders size={14} /> },
];

// ── Props ───────────────────────────────────────────────────────────────────

interface BrainDetailProps {
  brain: BrainRecord;
  relationships?: BrainRelationship[];
  onClose?: () => void;
  onRefresh?: () => void;
}

// ── Main Component ──────────────────────────────────────────────────────────

export function BrainDetail({ brain, relationships = [], onClose, onRefresh }: BrainDetailProps) {
  const [activeTab, setActiveTab] = useState("overview");

  const statusColor = brainStatusToColor(brain.status);
  const uptimeStr = formatDuration(brain.uptime);

  const relatedBrains = useMemo(() => {
    const ids = new Set<string>();
    for (const r of relationships) {
      if (r.source_id === brain.id) ids.add(r.target_id);
      if (r.target_id === brain.id) ids.add(r.source_id);
    }
    return Array.from(ids);
  }, [relationships, brain.id]);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-start gap-4 border-b border-border/40 px-6 py-4">
        <VendorIcon vendor={brain.vendor} size={32} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold truncate">{brain.display_name}</h2>
            <span
              className="px-2 py-0.5 rounded text-[10px] font-medium"
              style={{
                backgroundColor: statusColor + "22",
                color: statusColor,
                borderColor: statusColor + "44",
              }}
            >
              {brain.status}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-xs text-faint">
            <span>{brain.brain_type}</span>
            <span>·</span>
            <span>{brain.vendor}</span>
            <span>·</span>
            <span>v{brain.version}</span>
            <span>·</span>
            <span>{brain.runtime}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="rounded-lg px-3 py-1.5 text-xs font-medium bg-surface/20 hover:bg-surface/40 transition"
            >
              Refresh
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="rounded-lg px-3 py-1.5 text-xs font-medium bg-surface/20 hover:bg-surface/40 transition"
            >
              Close
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex overflow-x-auto border-b border-border/40 px-4 gap-1 shrink-0">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-2.5 text-[11px] font-medium whitespace-nowrap border-b-2 transition ${
                isActive
                  ? "border-accent text-accent"
                  : "border-transparent text-faint hover:text-text"
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
          >
            {activeTab === "overview" && <OverviewTab brain={brain} uptimeStr={uptimeStr} />}
            {activeTab === "capabilities" && <CapabilitiesTab brain={brain} />}
            {activeTab === "health" && <HealthTab brain={brain} />}
            {activeTab === "metrics" && <MetricsTab brain={brain} />}
            {activeTab === "logs" && <LogsTab brain={brain} />}
            {activeTab === "events" && <EventsTab brain={brain} />}
            {activeTab === "relationships" && <RelationshipsTab brain={brain} relationships={relationships} relatedBrains={relatedBrains} />}
            {activeTab === "configuration" && <ConfigurationTab brain={brain} />}
            {activeTab === "models" && <ModelsTab brain={brain} />}
            {activeTab === "history" && <HistoryTab brain={brain} />}
            {activeTab === "tasks" && <TasksTab brain={brain} />}
            {activeTab === "performance" && <PerformanceTab brain={brain} />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

// ── Overview Tab ────────────────────────────────────────────────────────────

function OverviewTab({ brain, uptimeStr }: { brain: BrainRecord; uptimeStr: string }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Status" value={
          <div className="flex items-center gap-2">
            <BrainStatusDot status={brain.status} pulse />
            <span className="text-sm">{brain.status}</span>
          </div>
        } />
        <Stat label="Health" value={
          <div className="flex items-center gap-2">
            <BrainStatusDot status={brain.health} />
            <span className="text-sm capitalize">{brain.health}</span>
          </div>
        } />
        <Stat label="Uptime" value={<span className="text-sm">{uptimeStr}</span>} />
        <Stat label="Connection" value={
          <div className="flex items-center gap-2">
            <Globe size={16} className={brain.connection_state === "connected" ? "text-ok" : "text-danger"} />
            <span className="text-sm">{brain.connection_state}</span>
          </div>
        } />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="CPU Usage" value={`${brain.cpu_usage.toFixed(0)}%`} tone={brain.cpu_usage > 80 ? "danger" : brain.cpu_usage > 50 ? "warn" : "default"} />
        <Stat label="Memory" value={`${(brain.memory_usage / 1024).toFixed(1)}GB`} tone={brain.memory_usage > 32768 ? "danger" : "default"} />
        <Stat label="Latency" value={`${brain.latency.toFixed(0)}ms`} />
        <Stat label="Throughput" value={`${brain.throughput.toFixed(1)}/s`} />
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-3">Details</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2 text-xs text-faint">
          <DetailItem label="ID" value={brain.id} />
          <DetailItem label="Type" value={brain.brain_type} />
          <DetailItem label="Vendor" value={brain.vendor} />
          <DetailItem label="Runtime" value={brain.runtime} />
          <DetailItem label="Version" value={brain.version} />
          <DetailItem label="Workspace" value={brain.workspace} />
          <DetailItem label="Priority" value={String(brain.priority)} />
          <DetailItem label="Active Models" value={String(brain.active_models)} />
          <DetailItem label="Queue Depth" value={String(brain.queue_depth)} />
          <DetailItem label="Current Tasks" value={String(brain.current_tasks)} />
          <DetailItem label="Session Count" value={String(brain.session_count)} />
          <DetailItem label="Error Count" value={String(brain.error_count)} />
          <DetailItem label="Available Context" value={`${(brain.available_context / 1024).toFixed(0)}K tokens`} />
          <DetailItem label="Last Heartbeat" value={new Date(brain.heartbeat).toLocaleString()} />
          <DetailItem label="Discovered" value={new Date(brain.discovered_at).toLocaleString()} />
          <DetailItem label="Last Seen" value={new Date(brain.last_seen).toLocaleString()} />
        </div>
      </div>

      {brain.tags.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-2">Tags</h3>
          <div className="flex flex-wrap gap-1.5">
            {brain.tags.map((tag) => (
              <Badge key={tag}>{tag}</Badge>
            ))}
          </div>
        </div>
      )}

      {brain.last_error && (
        <div className="rounded-xl border border-danger/30 bg-danger/10 p-4">
          <div className="flex items-start gap-2 text-sm text-danger">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <div>
              <div className="font-medium">Last Error</div>
              <div className="text-xs mt-1 text-danger/80">{brain.last_error}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Capabilities Tab ────────────────────────────────────────────────────────

function CapabilitiesTab({ brain }: { brain: BrainRecord }) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Zap size={16} className="text-accent" />
          Capabilities ({brain.capabilities.length})
        </h3>
        {brain.capabilities.length === 0 ? (
          <p className="text-xs text-faint">No capabilities registered.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
            {brain.capabilities.map((cap) => (
              <div
                key={cap}
                className="rounded-lg border border-border/30 bg-surface/10 px-3 py-2 text-xs"
              >
                {cap}
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Server size={16} className="text-accent" />
          Supported Tools ({brain.supported_tools.length})
        </h3>
        {brain.supported_tools.length === 0 ? (
          <p className="text-xs text-faint">No tools registered.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {brain.supported_tools.map((tool) => (
              <Badge key={tool} tone="info">{tool}</Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Health Tab ──────────────────────────────────────────────────────────────

function HealthTab({ brain }: { brain: BrainRecord }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Status" value={brain.status} />
        <Stat label="Health" value={brain.health} tone={
          brain.health === "healthy" ? "ok" : brain.health === "degraded" ? "warn" : brain.health === "unhealthy" ? "danger" : "default"
        } />
        <Stat label="Uptime" value={formatDuration(brain.uptime)} />
        <Stat label="Heartbeat" value={new Date(brain.heartbeat).toLocaleTimeString()} />
      </div>

      <div className="space-y-4">
        <HealthBarSection label="CPU Usage" value={brain.cpu_usage} max={100} unit="%" />
        <HealthBarSection label="Memory Usage" value={brain.memory_usage} max={65536} unit="MB" />
      </div>

      <div className="rounded-xl border border-border/30 bg-surface/10 p-4">
        <h4 className="text-xs font-semibold mb-2 flex items-center gap-2">
          <AlertTriangle size={14} />
          Connection State
        </h4>
        <div className="flex items-center gap-2 text-sm">
          <Wifi size={16} className={brain.connection_state === "connected" ? "text-ok" : "text-danger"} />
          <span className="capitalize">{brain.connection_state}</span>
        </div>
      </div>

      {brain.error_count > 0 && (
        <div className="rounded-xl border border-danger/30 bg-danger/10 p-4">
          <h4 className="text-xs font-semibold mb-2 flex items-center gap-2 text-danger">
            <AlertTriangle size={14} />
            Error Count: {brain.error_count}
          </h4>
          {brain.last_error && (
            <p className="text-[11px] text-danger/80 mt-1">{brain.last_error}</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Metrics Tab ─────────────────────────────────────────────────────────────

function MetricsTab({ brain }: { brain: BrainRecord }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <Stat label="CPU" value={`${brain.cpu_usage.toFixed(0)}%`} />
        <Stat label="Memory" value={`${(brain.memory_usage / 1024).toFixed(1)}GB`} />
        <Stat label="Latency" value={`${brain.latency.toFixed(0)}ms`} />
        <Stat label="Throughput" value={`${brain.throughput.toFixed(1)}/s`} />
        <Stat label="Available Context" value={`${(brain.available_context / 1024).toFixed(0)}K`} />
        <Stat label="Uptime" value={formatDuration(brain.uptime)} />
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Resource Usage</h3>
        <HealthBarSection label="CPU" value={brain.cpu_usage} max={100} unit="%" />
        <HealthBarSection label="RAM" value={brain.memory_usage} max={65536} unit="MB" />
        <HealthBarSection label="Context" value={brain.available_context} max={128000} unit="tokens" />
      </div>
    </div>
  );
}

// ── Logs Tab ────────────────────────────────────────────────────────────────

function LogsTab({ brain }: { brain: BrainRecord }) {
  // Placeholder — real logs would come from an API endpoint
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Logs size={16} className="text-accent" />
          Recent Logs
        </h3>
        <span className="text-[10px] text-faint">Live stream not connected</span>
      </div>
      <div className="rounded-xl border border-border/30 bg-surface/5 p-6 text-center">
        <Logs size={32} className="mx-auto text-faint/40 mb-2" />
        <p className="text-xs text-faint">Connect to the log stream to view real-time logs</p>
        <button className="mt-3 rounded-lg px-4 py-2 text-xs font-medium bg-accent/20 text-accent hover:bg-accent/30 transition">
          Connect Log Stream
        </button>
      </div>
    </div>
  );
}

// ── Events Tab ──────────────────────────────────────────────────────────────

function EventsTab({ brain }: { brain: BrainRecord }) {
  // Placeholder — real events would come from the EventBus
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Activity size={16} className="text-accent" />
          Brain Events
        </h3>
      </div>
      <div className="rounded-xl border border-border/30 bg-surface/5 p-6 text-center">
        <Activity size={32} className="mx-auto text-faint/40 mb-2" />
        <p className="text-xs text-faint">Live event stream for this brain</p>
        <p className="text-[10px] text-faint/60 mt-1">Events appear here as they are emitted by the backend</p>
      </div>
    </div>
  );
}

// ── Relationships Tab ────────────────────────────────────────────────────────

function RelationshipsTab({ brain, relationships, relatedBrains }: {
  brain: BrainRecord;
  relationships: BrainRelationship[];
  relatedBrains: string[];
}) {
  const brainRels = relationships.filter(
    (r) => r.source_id === brain.id || r.target_id === brain.id
  );

  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold flex items-center gap-2">
        <Network size={16} className="text-accent" />
        Relationships ({brainRels.length})
      </h3>

      {brainRels.length === 0 ? (
        <div className="rounded-xl border border-border/30 bg-surface/5 p-6 text-center">
          <Network size={32} className="mx-auto text-faint/40 mb-2" />
          <p className="text-xs text-faint">No relationships established</p>
        </div>
      ) : (
        <div className="space-y-2">
          {brainRels.map((rel) => {
            const otherId = rel.source_id === brain.id ? rel.target_id : rel.source_id;
            const direction = rel.source_id === brain.id ? "→" : "←";
            return (
              <div
                key={rel.id}
                className="flex items-center justify-between rounded-lg border border-border/30 bg-surface/10 px-4 py-2.5"
              >
                <div className="flex items-center gap-3">
                  <Badge tone={
                    rel.relationship_type === "parent" || rel.relationship_type === "executor"
                      ? "accent" : "default"
                  }>
                    {rel.relationship_type}
                  </Badge>
                  <span className="text-xs text-faint">{direction}</span>
                  <span className="text-xs font-medium">{otherId}</span>
                </div>
                <div className="flex items-center gap-3 text-[10px] text-faint">
                  <span>Weight: {(rel.weight * 100).toFixed(0)}%</span>
                  <span className={rel.active ? "text-ok" : "text-danger"}>
                    {rel.active ? "Active" : "Inactive"}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {relatedBrains.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold mb-2">Connected Brains ({relatedBrains.length})</h4>
          <div className="flex flex-wrap gap-1.5">
            {relatedBrains.map((id) => (
              <Badge key={id} tone="info">{id}</Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Configuration Tab ───────────────────────────────────────────────────────

function ConfigurationTab({ brain }: { brain: BrainRecord }) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Settings size={16} className="text-accent" />
          Brain Configuration
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2 text-xs text-faint">
          <DetailItem label="Type" value={brain.brain_type} />
          <DetailItem label="Vendor" value={brain.vendor} />
          <DetailItem label="Runtime" value={brain.runtime} />
          <DetailItem label="Version" value={brain.version} />
          <DetailItem label="Workspace" value={brain.workspace} />
          <DetailItem label="Priority" value={String(brain.priority)} />
          <DetailItem label="Connection" value={brain.connection_state} />
          <DetailItem label="Max Context" value={`${(brain.available_context / 1024).toFixed(0)}K tokens`} />
        </div>
      </div>

      {Object.keys(brain.metadata).length > 0 && (
        <div>
          <h4 className="text-xs font-semibold mb-2">Metadata</h4>
          <div className="rounded-xl border border-border/30 bg-surface/10 p-4">
            <div className="grid grid-cols-2 gap-2 text-xs text-faint">
              {Object.entries(brain.metadata).map(([key, value]) => (
                <div key={key}>
                  <span className="font-medium">{key}:</span>{" "}
                  <span>{String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Models Tab ──────────────────────────────────────────────────────────────

function ModelsTab({ brain }: { brain: BrainRecord }) {
  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold flex items-center gap-2">
        <Box size={16} className="text-accent" />
        Supported Models ({brain.supported_models.length})
      </h3>

      {brain.supported_models.length === 0 ? (
        <div className="rounded-xl border border-border/30 bg-surface/5 p-6 text-center">
          <Box size={32} className="mx-auto text-faint/40 mb-2" />
          <p className="text-xs text-faint">No models registered</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
          {brain.supported_models.map((model) => (
            <div
              key={model}
              className="rounded-lg border border-border/30 bg-surface/10 px-3 py-2 text-xs"
            >
              {model}
            </div>
          ))}
        </div>
      )}

      <div className="text-xs text-faint">
        <span className="font-medium">Active Models:</span> {brain.active_models}
      </div>
    </div>
  );
}

// ── History Tab ─────────────────────────────────────────────────────────────

function HistoryTab({ brain }: { brain: BrainRecord }) {
  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold flex items-center gap-2">
        <Clock size={16} className="text-accent" />
        History & Activity
      </h3>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Session Count" value={brain.session_count} />
        <Stat label="Error Count" value={brain.error_count} tone={brain.error_count > 0 ? "danger" : "default"} />
        <Stat label="Discovered" value={new Date(brain.discovered_at).toLocaleDateString()} />
        <Stat label="Last Seen" value={new Date(brain.last_seen).toLocaleTimeString()} />
      </div>

      <div className="rounded-xl border border-border/30 bg-surface/5 p-6 text-center">
        <BookOpen size={32} className="mx-auto text-faint/40 mb-2" />
        <p className="text-xs text-faint">Activity timeline coming soon</p>
      </div>
    </div>
  );
}

// ── Tasks Tab ───────────────────────────────────────────────────────────────

function TasksTab({ brain }: { brain: BrainRecord }) {
  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold flex items-center gap-2">
        <ListTodo size={16} className="text-accent" />
        Task Overview
      </h3>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Current Tasks" value={brain.current_tasks} />
        <Stat label="Queue Depth" value={brain.queue_depth} />
        <Stat label="Throughput" value={`${brain.throughput.toFixed(1)}/s`} />
        <Stat label="Latency" value={`${brain.latency.toFixed(0)}ms`} />
      </div>

      <div className="rounded-xl border border-border/30 bg-surface/5 p-6 text-center">
        <ListTodo size={32} className="mx-auto text-faint/40 mb-2" />
        <p className="text-xs text-faint">Detailed task list coming soon</p>
        <p className="text-[10px] text-faint/60 mt-1">Task data will be fetched from the task scheduler</p>
      </div>
    </div>
  );
}

// ── Performance Tab ─────────────────────────────────────────────────────────

function PerformanceTab({ brain }: { brain: BrainRecord }) {
  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold flex items-center gap-2">
        <Sliders size={16} className="text-accent" />
        Performance Metrics
      </h3>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <Stat label="CPU Usage" value={`${brain.cpu_usage.toFixed(0)}%`} tone={
          brain.cpu_usage > 80 ? "danger" : brain.cpu_usage > 50 ? "warn" : "default"
        } />
        <Stat label="Memory Usage" value={`${(brain.memory_usage / 1024).toFixed(1)}GB`} tone={
          brain.memory_usage > 32768 ? "danger" : "default"
        } />
        <Stat label="Latency (avg)" value={`${brain.latency.toFixed(0)}ms`} tone={
          brain.latency > 1000 ? "danger" : brain.latency > 500 ? "warn" : "default"
        } />
        <Stat label="Throughput" value={`${brain.throughput.toFixed(1)}/s`} />
        <Stat label="Available Context" value={`${(brain.available_context / 1024).toFixed(0)}K tokens`} />
        <Stat label="Uptime" value={formatDuration(brain.uptime)} />
      </div>

      <div className="space-y-3">
        <h4 className="text-xs font-semibold">Resource Bars</h4>
        <HealthBarSection label="CPU" value={brain.cpu_usage} max={100} unit="%" />
        <HealthBarSection label="RAM" value={brain.memory_usage} max={65536} unit="MB" />
        <HealthBarSection label="Context Usage" value={brain.available_context} max={128000} unit="tokens" />
      </div>
    </div>
  );
}

// ── Shared sub-components ───────────────────────────────────────────────────

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="font-medium text-[10px] uppercase tracking-wider text-faint/70">{label}</span>
      <div className="mt-0.5 text-xs">{value}</div>
    </div>
  );
}

function HealthBarSection({ label, value, max, unit }: {
  label: string;
  value: number;
  max: number;
  unit: string;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div>
      <div className="flex justify-between text-xs text-faint mb-1">
        <span>{label}</span>
        <span className="tabular-nums">{value.toFixed(0)}{unit}</span>
      </div>
      <div className="h-2 rounded-full bg-surface/30 overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          style={{
            backgroundColor: pct > 80 ? "#ef4444" : pct > 50 ? "#f59e0b" : "#10b981",
          }}
        />
      </div>
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}
