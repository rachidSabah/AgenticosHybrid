"use client";

import { useEffect, useMemo, useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, StatusDot, Empty, Stat } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { type TaskNode, type AgentNode } from "@/lib/types";
import { FixedSizeList as List, type ListChildComponentProps } from "react-window";
import AutoSizer from "react-virtualized-auto-sizer";
import {
  Play,
  Pause,
  StopCircle,
  CheckCircle2,
  XCircle,
  Search,
  ChevronDown,
  ChevronRight,
  GitBranch,
  Bot,
  Server,
  RefreshCw,
  ListChecks,
  ListTodo,
  User,
  GitPullRequest,
} from "lucide-react";

// ── Types ──

interface TimelineEvent {
  id: string;
  taskId: string;
  agentId?: string;
  type: "task" | "agent" | "system";
  status: "created" | "planned" | "dispatched" | "assigned" | "running" | "completed" | "failed" | "paused" | "cancelled" | "recovered";
  title: string;
  detail: string;
  at: number;
  duration?: number;
  tags?: string[];
}

interface FilterState {
  status: string[];
  type: string[];
  search: string;
  sort: "newest" | "oldest" | "duration";
}

// ── Helpers ──

function statusToLevel(status: TimelineEvent["status"]) {
  return {
    created: "info" as const,
    planned: "info" as const,
    dispatched: "info" as const,
    assigned: "info" as const,
    running: "ok" as const,
    completed: "ok" as const,
    failed: "danger" as const,
    paused: "warn" as const,
    cancelled: "warn" as const,
    recovered: "ok" as const,
  }[status];
}

function statusToIcon(status: TimelineEvent["status"]) {
  return {
    created: <ListTodo size={14} />,
    planned: <ListChecks size={14} />,
    dispatched: <GitPullRequest size={14} />,
    assigned: <User size={14} />,
    running: <Play size={14} />,
    completed: <CheckCircle2 size={14} />,
    failed: <XCircle size={14} />,
    paused: <Pause size={14} />,
    cancelled: <StopCircle size={14} />,
    recovered: <RefreshCw size={14} />,
  }[status];
}

function typeToIcon(type: TimelineEvent["type"]) {
  return {
    task: <GitBranch size={14} />,
    agent: <Bot size={14} />,
    system: <Server size={14} />,
  }[type];
}

// ── Virtualized Row ──

interface TimelineRowData {
  filteredEvents: TimelineEvent[];
  expanded: Record<string, boolean>;
  onToggle: (id: string) => void;
}

function TimelineRow({ index, style, data }: ListChildComponentProps<TimelineRowData>) {
  const event = data.filteredEvents[index];
  const isExpanded = data.expanded[event.id] ?? false;
  const Icon = statusToIcon(event.status);
  const TypeIcon = typeToIcon(event.type);
  const level = statusToLevel(event.status);

  return (
    <div style={style}>
      <div className="flex items-start gap-3 p-3 hover:bg-surface/5 transition">
        <div className="shrink-0">
          <StatusDot status={level} pulse={event.status === "running"} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <div className="text-[11px] font-medium truncate">{event.title}</div>
            <div className="flex items-center gap-1 text-[9px] text-faint shrink-0">
              {TypeIcon}
              <span>{event.type}</span>
            </div>
            <div className="flex items-center gap-1 text-[9px] text-faint shrink-0">
              {Icon}
              <span>{event.status}</span>
            </div>
            {event.tags?.map((tag) => (
              <div key={tag} className="rounded-full bg-surface/20 px-2 py-0.5 text-[9px] text-faint shrink-0">
                {tag}
              </div>
            ))}
          </div>
          <div className="text-[10px] text-faint mt-0.5">
            {new Date(event.at).toLocaleTimeString()} • {event.duration ? `${Math.round(event.duration / 1000)}s` : "-"}
          </div>
          <div className="text-[10px] text-muted mt-1 line-clamp-1">
            {event.detail}
          </div>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="mt-2 border-t border-border/30 pt-2 text-[10px] text-faint"
            >
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="font-medium">Task ID</div>
                  <div>{event.taskId}</div>
                </div>
                {event.agentId && (
                  <div>
                    <div className="font-medium">Agent ID</div>
                    <div>{event.agentId}</div>
                  </div>
                )}
                <div>
                  <div className="font-medium">Timestamp</div>
                  <div>{new Date(event.at).toISOString()}</div>
                </div>
                {event.duration && (
                  <div>
                    <div className="font-medium">Duration</div>
                    <div>{Math.round(event.duration / 1000)}s</div>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </div>
        <button
          onClick={() => data.onToggle(event.id)}
          className="shrink-0 rounded-full p-1 hover:bg-surface/20 transition"
        >
          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
      </div>
    </div>
  );
}

// ── Main Component ──

export function TaskTimeline() {
  const tasks = useStore((s) => s.tasks);
  const agents = useStore((s) => s.agents);
  const telemetry = useStore((s) => s.telemetry);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [filters, setFilters] = useState<FilterState>({
    status: ["running", "completed", "failed", "paused", "cancelled"],
    type: ["task", "agent", "system"],
    search: "",
    sort: "newest",
  });

  const events = useMemo(() => {
    const list: TimelineEvent[] = [];

    // Task events
    Object.values(tasks).forEach((task) => {
      list.push({
        id: `task-${task.id}-created`,
        taskId: task.id,
        type: "task",
        status: "created",
        title: `Task created: ${task.title || task.id}`,
        detail: `Role: ${task.role || "unspecified"}`,
        at: Date.now() - 1000 * 60 * 5,
        tags: task.role ? [task.role] : undefined,
      });
      if (task.status === "planned") {
        list.push({
          id: `task-${task.id}-planned`,
          taskId: task.id,
          type: "task",
          status: "planned",
          title: `Task planned: ${task.title || task.id}`,
          detail: `Execution plan generated`,
          at: Date.now() - 1000 * 60 * 4,
          tags: task.role ? [task.role] : undefined,
        });
      }
      if (task.status === "dispatched") {
        list.push({
          id: `task-${task.id}-dispatched`,
          taskId: task.id,
          type: "task",
          status: "dispatched",
          title: `Task dispatched: ${task.title || task.id}`,
          detail: `Assigned to agent pool`,
          at: Date.now() - 1000 * 60 * 3,
          tags: task.role ? [task.role] : undefined,
        });
      }
      if (task.status === "assigned") {
        list.push({
          id: `task-${task.id}-assigned`,
          taskId: task.id,
          type: "task",
          status: "assigned",
          title: `Task assigned: ${task.title || task.id}`,
          detail: `Agent: ${task.role}`,
          at: Date.now() - 1000 * 60 * 2,
          tags: task.role ? [task.role] : undefined,
        });
      }
      if (task.status === "completed") {
        list.push({
          id: `task-${task.id}-completed`,
          taskId: task.id,
          type: "task",
          status: "completed",
          title: `Task completed: ${task.title || task.id}`,
          detail: `All steps executed successfully`,
          at: Date.now() - 1000 * 60 * 1,
          duration: 60 * 1000,
          tags: task.role ? [task.role] : undefined,
        });
      }
      if (task.status === "failed") {
        list.push({
          id: `task-${task.id}-failed`,
          taskId: task.id,
          type: "task",
          status: "failed",
          title: `Task failed: ${task.title || task.id}`,
          detail: `Error: ${task.role || "unknown error"}`,
          at: Date.now() - 1000 * 30,
          tags: task.role ? [task.role] : undefined,
        });
      }
    });

    // Agent events
    Object.values(agents).forEach((agent) => {
      list.push({
        id: `agent-${agent.id}-started`,
        taskId: agent.current_task || "system",
        agentId: agent.id,
        type: "agent",
        status: "running",
        title: `Agent started: ${agent.role}`,
        detail: `Provider: ${agent.provider || "unknown"}`,
        at: Date.now() - 1000 * 60 * 5,
        tags: [agent.provider, agent.role].filter(Boolean) as string[],
      });
      if (agent.status === "completed") {
        list.push({
          id: `agent-${agent.id}-completed`,
          taskId: agent.current_task || "system",
          agentId: agent.id,
          type: "agent",
          status: "completed",
          title: `Agent completed: ${agent.role}`,
          detail: `Task: ${agent.current_task || "system task"}`,
          at: Date.now() - 1000 * 60 * 1,
          duration: 60 * 1000,
          tags: [agent.provider, agent.role].filter(Boolean) as string[],
        });
      }
      if (agent.status === "failed") {
        list.push({
          id: `agent-${agent.id}-failed`,
          taskId: agent.current_task || "system",
          agentId: agent.id,
          type: "agent",
          status: "failed",
          title: `Agent failed: ${agent.role}`,
          detail: `Error: ${agent.health === "down" ? "Provider unavailable" : "Internal error"}`,
          at: Date.now() - 1000 * 30,
          tags: [agent.provider, agent.role].filter(Boolean) as string[],
        });
      }
    });

    // System events
    list.push({
      id: `system-health-check`,
      taskId: "system",
      type: "system",
      status: "running",
      title: `System health check`,
      detail: `Agents: ${telemetry.agents}, Tasks: ${telemetry.tasks}, Providers: ${telemetry.providers}`,
      at: Date.now() - 1000 * 10,
      tags: ["health"],
    });

    if (telemetry.errors > 0) {
      list.push({
        id: `system-error`,
        taskId: "system",
        type: "system",
        status: "failed",
        title: `System error detected`,
        detail: `${telemetry.errors} errors in last 5 minutes`,
        at: Date.now() - 1000 * 5,
        tags: ["error"],
      });
    }

    // Sort
    return list.sort((a, b) => {
      if (filters.sort === "newest") return b.at - a.at;
      if (filters.sort === "oldest") return a.at - b.at;
      return (b.duration || 0) - (a.duration || 0);
    });
  }, [tasks, agents, telemetry, filters.sort]);

  const filteredEvents = useMemo(() => {
    return events.filter((e) => {
      const statusMatch = filters.status.includes(e.status);
      const typeMatch = filters.type.includes(e.type);
      const searchMatch = filters.search
        ? e.title.toLowerCase().includes(filters.search.toLowerCase()) ||
          e.detail.toLowerCase().includes(filters.search.toLowerCase()) ||
          e.tags?.some((t) => t.toLowerCase().includes(filters.search.toLowerCase()))
        : true;
      return statusMatch && typeMatch && searchMatch;
    });
  }, [events, filters]);

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);

  const toggleStatusFilter = (status: string) => {
    setFilters((prev) => ({
      ...prev,
      status: prev.status.includes(status)
        ? prev.status.filter((s) => s !== status)
        : [...prev.status, status],
    }));
  };

  const toggleTypeFilter = (type: string) => {
    setFilters((prev) => ({
      ...prev,
      type: prev.type.includes(type)
        ? prev.type.filter((t) => t !== type)
        : [...prev.type, type],
    }));
  };

  const clearFilters = () => {
    setFilters({
      status: ["running", "completed", "failed", "paused", "cancelled"],
      type: ["task", "agent", "system"],
      search: "",
      sort: "newest",
    });
  };

  const listRef = useRef<List>(null);
  const itemData: TimelineRowData = useMemo(
    () => ({ filteredEvents, expanded, onToggle: toggleExpand }),
    [filteredEvents, expanded, toggleExpand],
  );

  // Reset expanded when filter changes change visible items
  useEffect(() => {
    setExpanded({});
    listRef.current?.scrollTo(0);
  }, [filters]);

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
                  placeholder="Search events..."
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
                  { id: "running", label: "Running", icon: <Play size={12} /> },
                  { id: "completed", label: "Completed", icon: <CheckCircle2 size={12} /> },
                  { id: "failed", label: "Failed", icon: <XCircle size={12} /> },
                  { id: "paused", label: "Paused", icon: <Pause size={12} /> },
                  { id: "cancelled", label: "Cancelled", icon: <StopCircle size={12} /> },
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
              <label className="text-[10px] font-medium text-faint">Type</label>
              <div className="mt-1 grid grid-cols-2 gap-1.5">
                {[
                  { id: "task", label: "Task", icon: <GitBranch size={12} /> },
                  { id: "agent", label: "Agent", icon: <Bot size={12} /> },
                  { id: "system", label: "System", icon: <Server size={12} /> },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => toggleTypeFilter(item.id)}
                    className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition ${
                      filters.type.includes(item.id)
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
                  { id: "newest", label: "Newest" },
                  { id: "oldest", label: "Oldest" },
                  { id: "duration", label: "Duration" },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setFilters((prev) => ({ ...prev, sort: item.id as FilterState["sort"] }))}
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
            <Stat label="Total Events" value={events.length} />
            <Stat label="Filtered Events" value={filteredEvents.length} />
            <Stat label="Running Tasks" value={Object.values(tasks).filter((t) => t.status === "running").length} />
            <Stat label="Active Agents" value={Object.values(agents).filter((a) => a.status === "running").length} />
            <Stat label="Errors" value={telemetry.errors} tone={telemetry.errors > 0 ? "danger" : undefined} />
          </div>
        </Panel>
      </div>

      {/* Right: Timeline */}
      <div className="col-span-12 lg:col-span-9 flex flex-col gap-4 h-full min-h-0">
        <Panel
          title="Task Timeline"
          subtitle="Live execution history"
          className="flex-1 min-h-0"
          contentClassName="p-0"
        >
          {filteredEvents.length === 0 ? (
            <div className="p-4">
              <Empty title="No events match filters" hint="Try adjusting your filters or search query" />
            </div>
          ) : (
            <div className="h-full w-full">
              <AutoSizer>
                {({ height, width }) => (
                  <List<TimelineRowData>
                    ref={listRef}
                    height={height}
                    width={width}
                    itemCount={filteredEvents.length}
                    itemSize={72}
                    itemData={itemData}
                    className="divide-y divide-border/30"
                    overscanCount={20}
                  >
                    {TimelineRow}
                  </List>
                )}
              </AutoSizer>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
