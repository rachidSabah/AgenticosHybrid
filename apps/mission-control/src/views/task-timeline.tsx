"use client";

import { useEffect, useMemo, useState, useRef } from "react";
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
  Clock,
  Search,
  Filter,
  ChevronDown,
  ChevronRight,
  GitBranch,
  GitCommit,
  GitPullRequest,
  AlertCircle,
  Zap,
  Bot,
  FileText,
  FileCode,
  File,
  Folder,
  Database,
  Server,
  Network,
  Wifi,
  Shield,
  Settings,
  RefreshCw,
  ListFilter,
  ListChecks,
  ListTodo,
  ListEnd,
  ListStart,
  List,
  Calendar,
  History,
  Tag,
  User,
  Users,
  Cpu,
  MemoryStick,
  HardDrive,
  Thermometer,
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
  icon?: React.ReactNode;
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
    created: "info",
    planned: "info",
    dispatched: "info",
    assigned: "info",
    running: "ok",
    completed: "ok",
    failed: "danger",
    paused: "warn",
    cancelled: "warn",
    recovered: "ok",
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
        at: Date.now() - 1000 * 60 * 5, // Mock time
        tags: [task.role],
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
          tags: [task.role],
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
          tags: [task.role],
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
          tags: [task.role],
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
          tags: [task.role],
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
          tags: [task.role],
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
        tags: [agent.provider, agent.role],
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
          tags: [agent.provider, agent.role],
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
          tags: [agent.provider, agent.role],
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
              {filteredEvents.length === 0 ? (
                <div className="p-4">
                  <Empty title="No events match filters" hint="Try adjusting your filters or search query" />
                </div>
              ) : (
                <div className="h-full w-full">
                  <AutoSizer>
                    {({ height, width }) => (
                      <List
                        height={height}
                        width={width}
                        itemCount={filteredEvents.length}
                        itemSize={isExpanded ? 160 : 80} // Adjust based on expanded state
                        itemData={{ filteredEvents, expanded, toggleExpand }}
                        className="divide-y divide-border/30"
                      >
                        {TimelineRow}
                      </List>
                    )}
                  </AutoSizer>
                </div>
              )}
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
                        onClick={() => toggleExpand(event.id)}
                        className="shrink-0 rounded-full p-1 hover:bg-surface/20 transition"
                      </motion.div>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          }
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}