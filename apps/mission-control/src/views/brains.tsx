"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain, LayoutGrid, GitBranch,
  Search, RefreshCw, Filter, X,
  Table,
  Activity,
} from "lucide-react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { BrainCard, VendorIcon, BrainStatusDot } from "@/components/brain-card";
import { BrainDetail } from "@/components/brain-detail";
import { BrainConstellation } from "@/views/brain-constellation";
import { useBrainsStore, selectFilteredBrains, selectBrainsByGroup, brainStatusToColor, BRAIN_STATUSES, BRAIN_TYPES, BRAIN_VENDORS } from "@/lib/use-brains";
import type { BrainRecord } from "@/lib/use-brains";

// ── Component ───────────────────────────────────────────────────────────────

export function Brains() {
  const store = useBrainsStore();

  const brains = useBrainsStore((s) => s.brains);
  const relationships = useBrainsStore((s) => s.relationships);
  const filter = useBrainsStore((s) => s.filter);
  const viewMode = useBrainsStore((s) => s.viewMode);
  const selectedBrainId = useBrainsStore((s) => s.selectedBrainId);
  const connected = useBrainsStore((s) => s.connected);
  const loading = useBrainsStore((s) => s.loading);

  const setViewMode = useBrainsStore((s) => s.setViewMode);
  const setSelectedBrain = useBrainsStore((s) => s.setSelectedBrain);
  const setFilter = useBrainsStore((s) => s.setFilter);
  const resetFilter = useBrainsStore((s) => s.resetFilter);
  const toggleExpand = useBrainsStore((s) => s.toggleExpand);
  const expandedBrains = useBrainsStore((s) => s.expandedBrains);
  const fetchBrains = useBrainsStore((s) => s.fetchBrains);
  const fetchRelationships = useBrainsStore((s) => s.fetchRelationships);
  const refreshBrain = useBrainsStore((s) => s.refreshBrain);
  const rescan = useBrainsStore((s) => s.rescan);
  const connectSSE = useBrainsStore((s) => s.connectSSE);
  const disconnectSSE = useBrainsStore((s) => s.disconnectSSE);

  const [showFilters, setShowFilters] = useState(false);
  const [rescanning, setRescanning] = useState(false);

  // Connect SSE on mount
  useEffect(() => {
    fetchBrains();
    fetchRelationships();
    connectSSE();
    return () => {
      disconnectSSE();
    };
  }, [fetchBrains, fetchRelationships, connectSSE, disconnectSSE]);

  // Filtered data
  const brainList = useMemo(() => Object.values(brains), [brains]);
  const filteredBrains = useMemo(
    () => selectFilteredBrains(brains, filter),
    [brains, filter],
  );
  const groupedBrains = useMemo(
    () => selectBrainsByGroup(brains, filter),
    [brains, filter],
  );

  const selectedBrain = selectedBrainId ? brains[selectedBrainId] : null;

  const handleRescan = async () => {
    setRescanning(true);
    await rescan();
    setRescanning(false);
  };

  // Stats
  const totalBrains = brainList.length;
  const healthyCount = brainList.filter((b) => b.health === "healthy").length;
  const degradedCount = brainList.filter((b) => b.health === "degraded").length;
  const unhealthyCount = brainList.filter((b) => b.health === "unhealthy").length;
  const activeCount = brainList.filter(
    (b) => ["connected", "executing", "busy"].includes(b.status),
  ).length;

  // Active filter count
  const activeFilterCount =
    (filter.status.length > 0 ? 1 : 0) +
    (filter.health.length > 0 ? 1 : 0) +
    (filter.type.length > 0 ? 1 : 0) +
    (filter.vendor.length > 0 ? 1 : 0) +
    (filter.runtime.length > 0 ? 1 : 0) +
    (filter.search ? 1 : 0);

  return (
    <div className="grid h-full grid-cols-12 gap-4 overflow-auto p-4">
      {/* ── Left sidebar ── */}
      <div className="col-span-12 lg:col-span-3 flex flex-col gap-4">
        {/* Stats */}
        <Panel title="Brain Registry" className="flex-shrink-0">
          <div className="space-y-2">
            <Stat label="Total Brains" value={totalBrains} />
            <Stat label="Active" value={activeCount} tone="ok" />
            <Stat
              label="Healthy / Degraded / Unhealthy"
              value={
                <div className="flex items-center gap-2">
                  <span className="text-ok">{healthyCount}</span>
                  <span className="text-faint">/</span>
                  <span className="text-warn">{degradedCount}</span>
                  <span className="text-faint">/</span>
                  <span className="text-danger">{unhealthyCount}</span>
                </div>
              }
            />
            <Stat label="Filtered" value={filteredBrains.length} />
          </div>
        </Panel>

        {/* View mode & Actions */}
        <Panel title="View" className="flex-shrink-0">
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-1.5">
              {([
                { id: "card" as const, icon: <LayoutGrid size={14} />, label: "Cards" },
                { id: "table" as const, icon: <Table size={14} />, label: "Table" },
                { id: "graph" as const, icon: <GitBranch size={14} />, label: "Graph" },
              ]).map((item) => (
                <button
                  key={item.id}
                  onClick={() => setViewMode(item.id)}
                  className={`flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-2 text-[10px] font-medium transition ${
                    viewMode === item.id
                      ? "bg-accent/20 text-accent border border-accent/30"
                      : "text-faint hover:text-text hover:bg-surface/20 border border-transparent"
                  }`}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </button>
              ))}
            </div>

            <button
              onClick={handleRescan}
              disabled={rescanning}
              className="w-full flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[11px] font-medium bg-surface/20 hover:bg-surface/40 transition disabled:opacity-50"
            >
              <RefreshCw size={14} className={rescanning ? "animate-spin" : ""} />
              {rescanning ? "Scanning..." : "Rescan Brains"}
            </button>
          </div>
        </Panel>

        {/* Filters */}
        <div className="flex-shrink-0">
          <div className="flex items-center justify-between mb-2 px-0.5">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className="flex items-center gap-2 text-sm font-semibold"
            >
              <Filter size={14} />
              Filters
              {activeFilterCount > 0 && (
                <Badge tone="accent">{activeFilterCount}</Badge>
              )}
            </button>
          </div>
          <section className="panel flex min-h-0 flex-col">
            <div className="min-h-0 flex-1 overflow-auto p-3 space-y-3">
            {/* Search */}
            <div>
              <label className="text-[10px] font-medium text-faint">Search</label>
              <div className="mt-1 relative">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
                <input
                  type="text"
                  placeholder="Search brains..."
                  value={filter.search}
                  onChange={(e) => setFilter({ search: e.target.value })}
                  className="w-full rounded-lg border border-border/40 bg-surface/10 pl-8 pr-2.5 py-1.5 text-[11px] focus:border-accent/50 focus:outline-none"
                />
                {filter.search && (
                  <button
                    onClick={() => setFilter({ search: "" })}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-faint hover:text-text"
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            </div>

            {/* Sort */}
            <div>
              <label className="text-[10px] font-medium text-faint">Sort By</label>
              <div className="mt-1 grid grid-cols-2 gap-1">
                {([
                  { id: "display_name", label: "Name" },
                  { id: "status", label: "Status" },
                  { id: "health", label: "Health" },
                  { id: "cpu_usage", label: "CPU" },
                  { id: "memory_usage", label: "Memory" },
                  { id: "latency", label: "Latency" },
                ] as const).map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setFilter({ sort: item.id })}
                    className={`rounded-lg px-2 py-1 text-[10px] font-medium transition ${
                      filter.sort === item.id
                        ? "bg-accent/20 text-accent"
                        : "text-faint hover:text-text hover:bg-surface/20"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <div className="mt-1.5 flex gap-1">
                <button
                  onClick={() => setFilter({ sortDir: "asc" })}
                  className={`flex-1 rounded-lg px-2 py-1 text-[10px] font-medium transition ${
                    filter.sortDir === "asc"
                      ? "bg-accent/20 text-accent"
                      : "text-faint hover:text-text hover:bg-surface/20"
                  }`}
                >
                  Asc
                </button>
                <button
                  onClick={() => setFilter({ sortDir: "desc" })}
                  className={`flex-1 rounded-lg px-2 py-1 text-[10px] font-medium transition ${
                    filter.sortDir === "desc"
                      ? "bg-accent/20 text-accent"
                      : "text-faint hover:text-text hover:bg-surface/20"
                  }`}
                >
                  Desc
                </button>
              </div>
            </div>

            {/* Group By */}
            <div>
              <label className="text-[10px] font-medium text-faint">Group By</label>
              <div className="mt-1 grid grid-cols-2 gap-1">
                {([
                  { id: "none", label: "None" },
                  { id: "type", label: "Type" },
                  { id: "vendor", label: "Vendor" },
                  { id: "status", label: "Status" },
                  { id: "health", label: "Health" },
                  { id: "runtime", label: "Runtime" },
                ] as const).map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setFilter({ groupBy: item.id })}
                    className={`rounded-lg px-2 py-1 text-[10px] font-medium transition ${
                      filter.groupBy === item.id
                        ? "bg-accent/20 text-accent"
                        : "text-faint hover:text-text hover:bg-surface/20"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Collapsible advanced filters */}
            {showFilters && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="space-y-3"
              >
                {/* Status filter */}
                <div>
                  <label className="text-[10px] font-medium text-faint">Status</label>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {BRAIN_STATUSES.slice(0, 10).map((s) => (
                      <button
                        key={s}
                        onClick={() => useBrainsStore.getState().toggleStatusFilter(s)}
                        className={`rounded-lg px-2 py-0.5 text-[9px] font-medium transition ${
                          filter.status.includes(s)
                            ? "bg-accent/20 text-accent border border-accent/30"
                            : "text-faint hover:text-text border border-transparent"
                        }`}
                      >
                        {s}
                      </button>
                    ))}
                    {filter.status.length > 0 && (
                      <button
                        onClick={() => setFilter({ status: [] })}
                        className="rounded-lg px-2 py-0.5 text-[9px] text-danger hover:bg-danger/10"
                      >
                        Clear
                      </button>
                    )}
                  </div>
                </div>

                {/* Type filter */}
                <div>
                  <label className="text-[10px] font-medium text-faint">Type</label>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {BRAIN_TYPES.map((t) => (
                      <button
                        key={t}
                        onClick={() => {
                          const current = filter.type;
                          const next = current.includes(t)
                            ? current.filter((x) => x !== t)
                            : [...current, t];
                          setFilter({ type: next });
                        }}
                        className={`rounded-lg px-2 py-0.5 text-[9px] font-medium transition ${
                          filter.type.includes(t)
                            ? "bg-accent/20 text-accent border border-accent/30"
                            : "text-faint hover:text-text border border-transparent"
                        }`}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Vendor filter */}
                <div>
                  <label className="text-[10px] font-medium text-faint">Vendor</label>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {BRAIN_VENDORS.slice(0, 15).map((v) => (
                      <button
                        key={v}
                        onClick={() => {
                          const current = filter.vendor;
                          const next = current.includes(v)
                            ? current.filter((x) => x !== v)
                            : [...current, v];
                          setFilter({ vendor: next });
                        }}
                        className={`rounded-lg px-2 py-0.5 text-[9px] font-medium transition ${
                          filter.vendor.includes(v)
                            ? "bg-accent/20 text-accent border border-accent/30"
                            : "text-faint hover:text-text border border-transparent"
                        }`}
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                </div>
              </motion.div>
            )}

            {/* Reset */}
            {activeFilterCount > 0 && (
              <button
                onClick={resetFilter}
                className="w-full rounded-lg px-3 py-1.5 text-[10px] font-medium text-faint hover:text-text hover:bg-surface/20 transition"
              >
                Reset all filters
              </button>
            )}
          </div>
          </section>
        </div>
      </div>

      {/* ── Main content ── */}
      <div className="col-span-12 lg:col-span-9 flex flex-col gap-4 h-full min-h-0">
        {/* Connection status bar */}
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[10px] font-medium ${
          connected ? "bg-ok/10 text-ok" : "bg-danger/10 text-danger"
        }`}>
          <span className={`inline-block h-2 w-2 rounded-full ${connected ? "bg-ok animate-pulse" : "bg-danger"}`} />
          <span>{connected ? "SSE connected — live updates active" : "SSE disconnected"}</span>
          <span className="ml-auto text-faint">{brainList.length} brains discovered</span>
        </div>

        {/* Table mode */}
        {viewMode === "table" && (
          <Panel title="Brains" subtitle="Table view" className="flex-1 min-h-0">
            {filteredBrains.length === 0 ? (
              <Empty title="No brains match filters" hint="Try adjusting your filters or search query" />
            ) : (
              <div className="overflow-auto h-full">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border/30 text-[10px] text-faint uppercase tracking-wider">
                      <th className="text-left py-2 px-2 font-medium">Name</th>
                      <th className="text-left py-2 px-2 font-medium">Type</th>
                      <th className="text-left py-2 px-2 font-medium">Vendor</th>
                      <th className="text-left py-2 px-2 font-medium">Status</th>
                      <th className="text-left py-2 px-2 font-medium">Health</th>
                      <th className="text-right py-2 px-2 font-medium">CPU</th>
                      <th className="text-right py-2 px-2 font-medium">Memory</th>
                      <th className="text-right py-2 px-2 font-medium">Latency</th>
                      <th className="text-right py-2 px-2 font-medium">Tasks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredBrains.map((brain) => (
                      <TableRow
                        key={brain.id}
                        brain={brain}
                        onClick={() => setSelectedBrain(brain.id)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        )}

        {/* Graph mode */}
        {viewMode === "graph" && (
          <Panel title="Constellation" subtitle="Graph view" className="flex-1 min-h-0" contentClassName="p-2">
            {brainList.length === 0 ? (
              <Empty title="No brains to display" hint="Run a discovery scan to find brains" />
            ) : (
              <BrainConstellation
                brains={brainList}
                relationships={relationships}
                onSelectBrain={(id) => setSelectedBrain(id)}
              />
            )}
          </Panel>
        )}

        {/* Card mode */}
        {viewMode === "card" && (
          <Panel title="Brains" subtitle="Card view" className="flex-1 min-h-0">
            {filteredBrains.length === 0 ? (
              <div className="p-4">
                <Empty title="No brains match filters" hint="Try adjusting your filters or search query" />
              </div>
            ) : (
              <div className="overflow-y-auto h-full p-2">
                {Object.entries(groupedBrains).map(([group, groupList]) => (
                  <div key={group} className="mb-6">
                    {filter.groupBy !== "none" && (
                      <div className="flex items-center gap-2 mb-3 px-1">
                        <h3 className="text-xs font-semibold capitalize text-faint">{group}</h3>
                        <span className="text-[10px] text-faint/50">({groupList.length})</span>
                      </div>
                    )}
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                      {groupList.map((brain) => (
                        <BrainCard
                          key={brain.id}
                          brain={brain}
                          expanded={expandedBrains[brain.id] ?? false}
                          onToggle={() => toggleExpand(brain.id)}
                          onSelect={() => setSelectedBrain(brain.id)}
                          onRefresh={() => refreshBrain(brain.id)}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        )}
      </div>

      {/* ── Detail panel (slide-over) ── */}
      <AnimatePresence>
        {selectedBrain && (
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 25, stiffness: 200 }}
            className="fixed inset-y-0 right-0 z-50 w-full max-w-2xl border-l border-border/40 bg-surface shadow-2xl"
          >
            <BrainDetail
              brain={selectedBrain}
              relationships={relationships.filter(
                (r) => r.source_id === selectedBrain.id || r.target_id === selectedBrain.id,
              )}
              onClose={() => setSelectedBrain(null)}
              onRefresh={() => refreshBrain(selectedBrain.id)}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Table Row ───────────────────────────────────────────────────────────────

function TableRow({ brain, onClick }: { brain: BrainRecord; onClick: () => void }) {
  const statusColor = brainStatusToColor(brain.status);

  return (
    <tr
      className="border-b border-border/20 hover:bg-surface/20 transition cursor-pointer"
      onClick={onClick}
    >
      <td className="py-2.5 px-2">
        <div className="flex items-center gap-2">
          <VendorIcon vendor={brain.vendor} size={16} />
          <span className="font-medium">{brain.display_name}</span>
        </div>
      </td>
      <td className="py-2.5 px-2 text-faint">{brain.brain_type}</td>
      <td className="py-2.5 px-2 text-faint">{brain.vendor}</td>
      <td className="py-2.5 px-2">
        <div className="flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: statusColor }}
          />
          <span>{brain.status}</span>
        </div>
      </td>
      <td className="py-2.5 px-2">
        <BrainStatusDot status={brain.health} />
        <span className="ml-1.5 capitalize text-[11px]">{brain.health}</span>
      </td>
      <td className="py-2.5 px-2 text-right tabular-nums">
        <span className={brain.cpu_usage > 80 ? "text-danger" : brain.cpu_usage > 50 ? "text-warn" : ""}>
          {brain.cpu_usage.toFixed(0)}%
        </span>
      </td>
      <td className="py-2.5 px-2 text-right tabular-nums text-faint">
        {(brain.memory_usage / 1024).toFixed(1)}GB
      </td>
      <td className="py-2.5 px-2 text-right tabular-nums text-faint">
        {brain.latency.toFixed(0)}ms
      </td>
      <td className="py-2.5 px-2 text-right tabular-nums">
        {brain.current_tasks}
      </td>
    </tr>
  );
}
