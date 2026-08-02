"use client";

import { useCallback, useEffect, useState, useRef, useMemo } from "react";
import { safeFixed, safeNum } from "@/lib/safe";
import { Panel, Stat, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { List, type RowComponentProps } from "react-window";
import { AutoSizer } from "react-virtualized-auto-sizer";
import { api } from "@/lib/api";
import type {
  MCPHealthSummary,
  MCPPermissionMapping,
  MCPPrompt,
  MCPServerDetail,
  MCPSessionMap,
  MCPTool,
  MCPToolResult,
} from "@/lib/types";

type McpTab = "servers" | "tools" | "permissions" | "health" | "sessions" | "resources" | "prompts" | "telemetry" | "versions";

export function McpManager() {
  const [tab, setTab] = useState<McpTab>("servers");

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 overflow-auto p-4">
      <div className="col-span-12 flex items-center gap-1 border-b border-border/60 px-0 pt-0">
        {(["servers", "tools", "permissions", "health", "sessions", "resources", "prompts", "telemetry", "versions"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-t-lg px-4 py-2 text-xs font-medium transition ${
              tab === t
                ? "bg-surface/40 text-text"
                : "text-faint hover:text-muted hover:bg-surface/20"
            }`}
          >
            {t === "servers"
              ? "Servers"
              : t === "tools"
                ? "Tools"
                : t === "permissions"
                  ? "Permissions"
                  : t === "health"
                    ? "Health"
                    : t === "sessions"
                      ? "Sessions"
                      : t === "resources"
                        ? "Resources"
                        : t === "prompts"
                          ? "Prompts"
                          : t === "versions"
          ? "Versions"
          : "Telemetry"}
          </button>
        ))}
      </div>
      <div className="col-span-12 min-h-0 flex-1 overflow-auto">
        {tab === "servers" && <McpServersTab />}
        {tab === "tools" && <McpToolsTab />}
        {tab === "permissions" && <McpPermissionsTab />}
        {tab === "health" && <McpHealthTab />}
        {tab === "sessions" && <McpSessionsTab />}
        {tab === "resources" && <McpResourcesTab />}
        {tab === "prompts" && <McpPromptsTab />}
        {tab === "telemetry" && <McpTelemetryTab />}
        {tab === "versions" && <McpVersionsTab />}
      </div>
    </div>
  );
}

// ── Sub-tab: Servers ──

function McpServersTab() {
  const [servers, setServers] = useState<MCPServerDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  // Create form state
  const [newName, setNewName] = useState("");
  const [newTransport, setNewTransport] = useState("stdio");
  const [newCommand, setNewCommand] = useState("");
  const [newArgs, setNewArgs] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    api.mcpServers().then(setServers).catch((err) => { console.error("API error:", err); setError(String(err)); }).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAction = async (action: Promise<unknown>, msg: string) => {
    try {
      await action;
      setActionMsg(msg);
      load();
    } catch (err) {
      setActionMsg(`Action failed: ${err}`);
    }
    setTimeout(() => setActionMsg(null), 4000);
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    const body: Record<string, unknown> = { name: newName.trim(), transport: newTransport };
    if (newTransport === "stdio") {
      body.command = newCommand || "node";
      body.args = newArgs ? newArgs.split(" ").filter(Boolean) : [];
    } else {
      body.url = newUrl || "http://localhost:3000";
    }
    if (newDesc) body.description = newDesc;
    try {
      await api.registerMcpServer(body);
      setShowCreate(false);
      setNewName("");
      setNewCommand("");
      setNewArgs("");
      setNewUrl("");
      setNewDesc("");
      load();
    } catch (err) {
      setActionMsg(`Create failed: ${err}`);
      setTimeout(() => setActionMsg(null), 4000);
    }
  };

  const totalTools = servers.reduce((s, sv) => s + sv.tools.length, 0);
  const running = servers.filter((s) => s.status === "running").length;
  const failed = servers.filter((s) => s.status === "failed").length;

  return (
    <div className="col-span-1 md:col-span-12 grid h-full grid-cols-1 md:grid-cols-12 gap-4">
      <div className="col-span-12 flex flex-wrap gap-3">
        <Stat label="Total Servers" value={servers.length} />
        <Stat label="Running" value={running} tone={running ? "ok" : "default"} />
        <Stat label="Failed" value={failed} tone={failed ? "danger" : "default"} />
        <Stat label="Discovered Tools" value={totalTools} tone="accent" />
        <div className="ml-auto flex items-start gap-2">
          {actionMsg && <span className="rounded-md bg-surface/40 px-3 py-1.5 text-xs text-muted">{actionMsg}</span>}
          <button
            onClick={() => load()}
            className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20"
          >
            Refresh
          </button>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80"
          >
            {showCreate ? "Cancel" : "Add Server"}
          </button>
        </div>
      </div>

      {showCreate && (
        <div className="col-span-12 rounded-xl border border-border/60 bg-surface/20 p-4">
          <h3 className="mb-3 text-sm font-semibold">Register New MCP Server</h3>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Server name *"
              className="rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs placeholder:text-faint"
            />
            <select
              value={newTransport}
              onChange={(e) => setNewTransport(e.target.value)}
              className="rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs"
            >
              <option value="stdio">STDIO</option>
              <option value="sse">SSE</option>
              <option value="streamable_http">Streamable HTTP</option>
            </select>
            {newTransport === "stdio" ? (
              <>
                <input
                  value={newCommand}
                  onChange={(e) => setNewCommand(e.target.value)}
                  placeholder="Command (default: node)"
                  className="rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs placeholder:text-faint"
                />
                <input
                  value={newArgs}
                  onChange={(e) => setNewArgs(e.target.value)}
                  placeholder="Args (space-separated)"
                  className="rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs placeholder:text-faint"
                />
              </>
            ) : (
              <input
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                placeholder="URL (e.g. http://localhost:3000)"
                className="rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs placeholder:text-faint"
              />
            )}
            <input
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="Description (optional)"
              className="col-span-2 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs placeholder:text-faint"
            />
          </div>
          <div className="mt-3 flex gap-2">
            <button
              onClick={handleCreate}
              disabled={!newName.trim()}
              className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
            >
              Create Server
            </button>
          </div>
        </div>
      )}

      <div className="col-span-12">
        <Panel title="MCP Servers" subtitle={`${servers.length} registered`}>
          {loading ? (
            <div className="flex items-center justify-center py-12 text-xs text-faint">Loading…</div>
          ) : servers.length === 0 ? (
            <Empty title="No MCP servers" hint="Register an MCP server to get started." />
          ) : (
            <div className="space-y-2">
              {servers.map((sv) => {
                const healthMap: Record<string, string> = {
                  healthy: "healthy",
                  degraded: "degraded",
                  unhealthy: "down",
                  unknown: "unknown",
                };
                const statusStr = sv.status === "running" ? "healthy" : sv.status === "failed" ? "down" : sv.status;
                return (
                  <div key={sv.config.id} className="flex items-center gap-3 rounded-xl border border-border/60 px-3 py-2.5">
                    <StatusDot status={statusStr} pulse={sv.status === "running"} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{sv.config.name}</span>
                        <Badge tone={sv.status === "running" ? "ok" : sv.status === "failed" ? "danger" : "default"}>
                          {sv.status}
                        </Badge>
                        <Badge tone="info">{sv.config.transport}</Badge>
                      </div>
                      <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-faint">
                        <span>Health: {sv.health}</span>
                        <span>Tools: {sv.tools.length}</span>
                        <span>Restarts: {sv.restart_count}</span>
                        {sv.config.description && <span className="truncate">{sv.config.description}</span>}
                        {sv.error && <span className="text-danger">{sv.error}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {sv.status === "running" ? (
                        <button
                          onClick={() => handleAction(api.mcpStopServer(sv.config.id), "Server stopped")}
                          className="rounded-md bg-warn/12 px-2.5 py-1 text-[11px] font-medium text-warn transition hover:bg-warn/20"
                        >
                          Stop
                        </button>
                      ) : (
                        <button
                          onClick={() => handleAction(api.mcpStartServer(sv.config.id), "Server started")}
                          className="rounded-md bg-ok/12 px-2.5 py-1 text-[11px] font-medium text-ok transition hover:bg-ok/20"
                        >
                          Start
                        </button>
                      )}
                      <button
                        onClick={() => handleAction(api.mcpRestartServer(sv.config.id), "Server restarted")}
                        className="rounded-md bg-accent/12 px-2.5 py-1 text-[11px] font-medium text-accent transition hover:bg-accent/20"
                      >
                        Restart
                      </button>
                      <button
                        onClick={() => handleAction(api.mcpReloadServer(sv.config.id), "Server reloaded")}
                        className="rounded-md bg-surface/40 px-2.5 py-1 text-[11px] text-faint transition hover:bg-surface/60"
                      >
                        Reload
                      </button>
                      <button
                        onClick={() => {
                          if (window.confirm(`Delete MCP server "${sv.config.name}"?`)) {
                            handleAction(api.deleteMcpServer(sv.config.id), "Server deleted");
                          }
                        }}
                        className="rounded-md bg-danger/12 px-2.5 py-1 text-[11px] font-medium text-danger transition hover:bg-danger/20"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

// ── Virtualized MCP Tool Row ──

function McpToolRow({ index, style, tools }: { index: number; style: React.CSSProperties; tools: MCPTool[] }) {
  const t = tools[index];
  return (
    <div style={style} className="px-1 py-1">
      <div className="rounded-xl border border-border/60 px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{t.name}</span>
        </div>
        {t.description && (
          <div className="mt-0.5 text-[11px] text-faint">{t.description}</div>
        )}
        {t.input_schema && (
          <details className="mt-1">
            <summary className="cursor-pointer text-[11px] text-faint hover:text-muted">Input schema</summary>
            <pre className="mt-1 overflow-auto rounded bg-surface/20 p-2 text-[10px] text-faint">
              {JSON.stringify(t.input_schema, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}

// ── Sub-tab: Tools ──

function McpToolsTab() {
  const [servers, setServers] = useState<MCPServerDetail[]>([]);
  const [selectedServer, setSelectedServer] = useState<string>("");
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [callToolName, setCallToolName] = useState("");
  const [callArgs, setCallArgs] = useState("{}");
  const [callResult, setCallResult] = useState<MCPToolResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadServers = useCallback(() => {
    api.mcpServers().then(setServers).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  useEffect(() => { loadServers(); }, [loadServers]);

  useEffect(() => {
    if (!selectedServer) return;
    api.mcpServerTools(selectedServer).then(setTools).catch(() => setTools([]));
  }, [selectedServer]);

  const handleDiscover = async () => {
    if (!selectedServer) return;
    setLoading(true);
    try {
      const discovered = await api.mcpDiscoverTools(selectedServer);
      setTools(discovered);
    } catch (err) {
      setCallResult({ content: `Discovery failed: ${err}`, is_error: true });
    } finally {
      setLoading(false);
    }
  };

  const handleCall = async () => {
    if (!selectedServer || !callToolName) return;
    setLoading(true);
    setCallResult(null);
    try {
      let parsedArgs: Record<string, unknown> = {};
      try {
        parsedArgs = JSON.parse(callArgs || "{}");
      } catch {
        setCallResult({ content: "Invalid JSON in arguments", is_error: true });
        setLoading(false);
        return;
      }
      const result = await api.mcpCallTool(selectedServer, callToolName, parsedArgs);
      setCallResult(result);
    } catch (err) {
      setCallResult({ content: `Call failed: ${err}`, is_error: true });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="col-span-1 md:col-span-12 grid h-full grid-cols-1 md:grid-cols-12 gap-4">
      <div className="col-span-12 flex items-center gap-3">
        <select
          value={selectedServer}
          onChange={(e) => { setSelectedServer(e.target.value); setCallResult(null); }}
          className="flex-1 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs"
        >
          <option value="">Select a server…</option>
          {servers.map((sv) => (
            <option key={sv.config.id} value={sv.config.id}>
              {sv.config.name} ({sv.status})
            </option>
          ))}
        </select>
        <button
          onClick={handleDiscover}
          disabled={!selectedServer || loading}
          className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
        >
          {loading ? "Working…" : "Discover Tools"}
        </button>
      </div>

      {selectedServer && (
        <>
          <Panel title="Discovered Tools" subtitle={`${tools.length} tools`} className="col-span-12 lg:col-span-6 min-h-0 flex-1" contentClassName="p-0">
            {tools.length === 0 ? (
              <div className="p-4">
                <Empty title="No tools discovered" hint='Click "Discover Tools" to list available tools.' />
              </div>
            ) : (
              <div className="h-full w-full">
                <AutoSizer
                  renderProp={({ height, width }) => (
                    <List<{ tools: MCPTool[] }>
                      style={{ height: height ?? 0, width: width ?? 0 }}
                      rowCount={tools.length}
                      rowHeight={80}
                      rowProps={{ tools }}
                      rowComponent={McpToolRow}
                      overscanCount={10}
                    />
                  )}
                />
              </div>
            )}
          </Panel>

          <Panel title="Invoke Tool" subtitle="Execute a tool on the selected server" className="col-span-12 lg:col-span-6 min-h-0 flex-1">
            <div className="space-y-3">
              <select
                value={callToolName}
                onChange={(e) => setCallToolName(e.target.value)}
                className="w-full rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs"
              >
                <option value="">Select tool…</option>
                {tools.map((t) => (
                  <option key={t.name} value={t.name}>{t.name}</option>
                ))}
              </select>
              <div>
                <label className="block text-[11px] font-medium text-faint">Arguments (JSON)</label>
                <textarea
                  value={callArgs}
                  onChange={(e) => setCallArgs(e.target.value)}
                  rows={4}
                  className="mt-1 w-full rounded-lg border border-border/60 bg-surface/20 px-3 py-2 font-mono text-xs placeholder:text-faint"
                />
              </div>
              <button
                onClick={handleCall}
                disabled={!callToolName || loading}
                className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
              >
                {loading ? "Invoking…" : "Invoke Tool"}
              </button>
              {callResult && (
                <div className={`rounded-xl border px-3 py-2.5 ${callResult.is_error ? "border-danger/40 bg-danger/8" : "border-ok/40 bg-ok/8"}`}>
                  <div className="mb-1 flex items-center gap-2">
                    <Badge tone={callResult.is_error ? "danger" : "ok"}>
                      {callResult.is_error ? "Error" : "Success"}
                    </Badge>
                  </div>
                  <pre className="max-h-48 overflow-auto text-xs text-muted">{callResult.content}</pre>
                </div>
              )}
            </div>
          </Panel>
        </>
      )}

      {!selectedServer && (
        <div className="col-span-12">
          <Empty title="Select a server" hint="Choose an MCP server from the dropdown to view its tools." />
        </div>
      )}
    </div>
  );
}

// ── Sub-tab: Permissions ──

function McpPermissionsTab() {
  const [servers, setServers] = useState<MCPServerDetail[]>([]);
  const [selectedServer, setSelectedServer] = useState<string>("");
  const [mappings, setMappings] = useState<MCPPermissionMapping[]>([]);
  const [newTool, setNewTool] = useState("");
  const [newCapability, setNewCapability] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadServers = useCallback(() => {
    api.mcpServers().then(setServers).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  useEffect(() => { loadServers(); }, [loadServers]);

  useEffect(() => {
    if (!selectedServer) return;
    api.mcpPermissions(selectedServer).then(setMappings).catch(() => setMappings([]));
  }, [selectedServer]);

  const handleAdd = () => {
    if (!newTool.trim() || !newCapability.trim()) return;
    setMappings((prev) => [
      ...prev,
      { tool_name: newTool.trim(), capability: newCapability.trim(), description: newDesc.trim() || undefined },
    ]);
    setNewTool("");
    setNewCapability("");
    setNewDesc("");
  };

  const handleRemove = (idx: number) => {
    setMappings((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    if (!selectedServer) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const result = await api.mcpSetPermissions(selectedServer, mappings);
      setSaveMsg(`Saved ${result.mappings_count} mappings`);
    } catch (err) {
      setSaveMsg(`Save failed: ${err}`);
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(null), 4000);
    }
  };

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <select
          value={selectedServer}
          onChange={(e) => { setSelectedServer(e.target.value); setSaveMsg(null); }}
          className="flex-1 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs"
        >
          <option value="">Select a server…</option>
          {servers.map((sv) => (
            <option key={sv.config.id} value={sv.config.id}>{sv.config.name}</option>
          ))}
        </select>
        {saveMsg && <span className="text-xs text-muted">{saveMsg}</span>}
      </div>

      {selectedServer && (
        <>
          <Panel title="Permission Mappings" subtitle={`${mappings.length} mappings`} className="col-span-6">
            {mappings.length === 0 ? (
              <Empty title="No mappings" hint="Add tool-to-capability mappings below." />
            ) : (
              <div className="space-y-1.5">
                {mappings.map((m, i) => (
                  <div key={i} className="flex items-center gap-2 rounded-lg border border-border/40 px-3 py-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 text-xs">
                        <span className="font-mono font-medium">{m.tool_name}</span>
                        <Badge tone="accent">{m.capability}</Badge>
                      </div>
                      {m.description && (
                        <div className="mt-0.5 text-[11px] text-faint">{m.description}</div>
                      )}
                    </div>
                    <button
                      onClick={() => handleRemove(i)}
                      className="rounded-md bg-danger/12 px-2 py-1 text-[11px] text-danger hover:bg-danger/20"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Add Mapping" subtitle="Link a tool to a permission capability" className="col-span-6">
            <div className="space-y-3">
              <input
                value={newTool}
                onChange={(e) => setNewTool(e.target.value)}
                placeholder="Tool name *"
                className="w-full rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs placeholder:text-faint"
              />
              <input
                value={newCapability}
                onChange={(e) => setNewCapability(e.target.value)}
                placeholder="Capability (e.g. mcp.tool.invoke) *"
                className="w-full rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs placeholder:text-faint"
              />
              <input
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Description (optional)"
                className="w-full rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs placeholder:text-faint"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleAdd}
                  disabled={!newTool.trim() || !newCapability.trim()}
                  className="rounded-lg bg-surface/40 px-4 py-2 text-xs font-medium transition hover:bg-surface/60 disabled:opacity-50"
                >
                  Add to List
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save All Mappings"}
                </button>
              </div>
            </div>
          </Panel>
        </>
      )}

      {!selectedServer && (
        <div className="col-span-12">
          <Empty title="Select a server" hint="Choose an MCP server to manage its permission mappings." />
        </div>
      )}
    </div>
  );
}

// ── Sub-tab: Health ──

function McpHealthTab() {
  const [servers, setServers] = useState<MCPServerDetail[]>([]);
  const [summary, setSummary] = useState<MCPHealthSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.mcpServers().then(setServers).catch((err) => { console.error("API error:", err); setError(String(err)); });
    api.mcpHealthSummary().then(setSummary).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  useEffect(() => { load(); }, [load]);

  const healthyCount = servers.filter((s) => s.health === "healthy").length;
  const degradedCount = servers.filter((s) => s.health === "degraded").length;
  const unhealthyCount = servers.filter((s) => s.health === "unhealthy").length;
  const unknownCount = servers.filter((s) => s.health === "unknown").length;

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex flex-wrap gap-3">
        <Stat label="Total" value={servers.length} />
        <Stat label="Healthy" value={healthyCount} tone="ok" />
        <Stat label="Degraded" value={degradedCount} tone={degradedCount ? "warn" : "default"} />
        <Stat label="Unhealthy" value={unhealthyCount} tone={unhealthyCount ? "danger" : "default"} />
        <Stat label="Unknown" value={unknownCount} tone="default" />
        <div className="ml-auto flex items-start gap-2">
          <button
            onClick={() => load()}
            className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20"
          >
            Refresh
          </button>
        </div>
      </div>

      {summary && (
        <div className="col-span-12">
          <div className="flex flex-wrap gap-3">
            <Stat label="Running" value={summary.running} tone="ok" />
          </div>
        </div>
      )}

      <Panel title="Server Health" subtitle="Health status per MCP server" className="col-span-12">
        {servers.length === 0 ? (
          <Empty title="No servers" hint="Register MCP servers to see their health status." />
        ) : (
          <div className="space-y-2">
            {servers.map((sv) => {
              const healthDot = sv.health === "healthy" ? "healthy" : sv.health === "degraded" ? "degraded" : sv.health === "unhealthy" ? "down" : "unknown";
              return (
                <div key={sv.config.id} className="flex items-center gap-3 rounded-xl border border-border/60 px-3 py-2.5">
                  <StatusDot status={healthDot} pulse={sv.health === "healthy"} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{sv.config.name}</span>
                      <Badge tone={sv.health === "healthy" ? "ok" : sv.health === "degraded" ? "warn" : sv.health === "unhealthy" ? "danger" : "default"}>
                        {sv.health}
                      </Badge>
                      <Badge tone="info">{sv.status}</Badge>
                    </div>
                    <div className="mt-0.5 flex gap-3 text-[11px] text-faint">
                      <span>Tools: {sv.tools.length}</span>
                      <span>Transport: {sv.config.transport}</span>
                      {sv.last_health_check && (
                        <span>Last check: {new Date(sv.last_health_check).toLocaleTimeString()}</span>
                      )}
                      {sv.error && <span className="text-danger">{sv.error}</span>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Sub-tab: Sessions ──

function McpSessionsTab() {
  const [sessions, setSessions] = useState<MCPSessionMap | null>(null);
  const [servers, setServers] = useState<MCPServerDetail[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.mcpSessions().then(setSessions).catch((err) => { console.error("API error:", err); setError(String(err)); });
    api.mcpServers().then(setServers).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  useEffect(() => { load(); }, [load]);

  const serverName = (serverId: string) => {
    const sv = servers.find((s) => s.config.id === serverId);
    return sv ? sv.config.name : serverId;
  };

  const entries = sessions ? Object.entries(sessions.sessions) : [];

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Active Sessions" value={sessions?.total ?? 0} tone={sessions?.total ? "accent" : "default"} />
        <div className="ml-auto flex items-start gap-2">
          <button
            onClick={() => load()}
            className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20"
          >
            Refresh
          </button>
        </div>
      </div>

      <Panel title="Session Details" subtitle="server_id → session_id mappings" className="col-span-12">
        {entries.length === 0 ? (
          <Empty title="No active sessions" hint="Sessions are created when MCP servers establish connections." />
        ) : (
          <div className="space-y-1.5">
            {entries.map(([serverId, sessionId]) => (
              <div key={serverId} className="flex items-center gap-3 rounded-xl border border-border/60 px-3 py-2.5">
                <StatusDot status="running" pulse />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{serverName(serverId)}</span>
                    <Badge tone="info">{serverId.slice(0, 12)}…</Badge>
                  </div>
                  <div className="mt-0.5 font-mono text-[11px] text-faint">Session: {sessionId}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Sub-tab: Resources ──

function McpResourcesTab() {
  const [servers, setServers] = useState<MCPServerDetail[]>([]);
  const [selectedServer, setSelectedServer] = useState<string>("");
  const [resources, setResources] = useState<Array<{ uri: string; name: string; description?: string }>>([]);
  const [error, setError] = useState<string | null>(null);

  const loadServers = useCallback(() => {
    api.mcpServers().then(setServers).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  useEffect(() => { loadServers(); }, [loadServers]);

  const loadResources = useCallback(() => {
    if (!selectedServer) return;
    api.mcpServerResources(selectedServer).then(setResources).catch(() => setResources([]));
  }, [selectedServer]);

  useEffect(() => { loadResources(); }, [loadResources]);

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <select
          value={selectedServer}
          onChange={(e) => setSelectedServer(e.target.value)}
          className="flex-1 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs"
        >
          <option value="">Select a server…</option>
          {servers.map((s) => (
            <option key={s.config.id} value={s.config.id}>{s.config.name}</option>
          ))}
        </select>
        <button
          onClick={() => loadResources()}
          className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20"
        >
          Refresh
        </button>
      </div>

      <Panel title="Resources" subtitle={`${resources.length} resources`} className="col-span-12">
        {!selectedServer ? (
          <Empty title="Select a server" hint="Choose an MCP server to view its resources." />
        ) : resources.length === 0 ? (
          <Empty title="No resources" hint="This server does not expose any resources." />
        ) : (
          <div className="space-y-2">
            {resources.map((r) => (
              <div key={r.uri} className="rounded-xl border border-border/60 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <Badge tone="accent">Resource</Badge>
                  <span className="text-sm font-medium">{r.name}</span>
                </div>
                <div className="mt-1 font-mono text-[11px] text-faint">{r.uri}</div>
                {r.description && <div className="mt-0.5 text-[11px] text-faint">{r.description}</div>}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Sub-tab: Prompts ──

function McpPromptsTab() {
  const [servers, setServers] = useState<MCPServerDetail[]>([]);
  const [selectedServer, setSelectedServer] = useState<string>("");
  const [prompts, setPrompts] = useState<MCPPrompt[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadServers = useCallback(() => {
    api.mcpServers().then(setServers).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  useEffect(() => { loadServers(); }, [loadServers]);

  const loadPrompts = useCallback(() => {
    if (!selectedServer) return;
    api.mcpServerPrompts(selectedServer).then(setPrompts).catch(() => setPrompts([]));
  }, [selectedServer]);

  useEffect(() => { loadPrompts(); }, [loadPrompts]);

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <select
          value={selectedServer}
          onChange={(e) => setSelectedServer(e.target.value)}
          className="flex-1 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs"
        >
          <option value="">Select a server…</option>
          {servers.map((s) => (
            <option key={s.config.id} value={s.config.id}>{s.config.name}</option>
          ))}
        </select>
        <button
          onClick={() => loadPrompts()}
          className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20"
        >
          Refresh
        </button>
      </div>

      <Panel title="Prompts" subtitle={`${prompts.length} prompt templates`} className="col-span-12">
        {!selectedServer ? (
          <Empty title="Select a server" hint="Choose an MCP server to view its prompt templates." />
        ) : prompts.length === 0 ? (
          <Empty title="No prompts" hint="This server does not expose any prompt templates." />
        ) : (
          <div className="space-y-2">
            {prompts.map((p) => (
              <div key={p.name} className="rounded-xl border border-border/60 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <Badge tone="info">Prompt</Badge>
                  <span className="text-sm font-medium">{p.name}</span>
                </div>
                {p.description && <div className="mt-0.5 text-[11px] text-faint">{p.description}</div>}
                {p.arguments && Array.isArray(p.arguments) && p.arguments.length > 0 && (
                  <div className="mt-1 text-[11px] text-faint">
                    Arguments: {p.arguments.map((a: unknown) => (a as { name?: string }).name).join(", ")}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Sub-tab: Telemetry ──

function McpTelemetryTab() {
  const [summary, setSummary] = useState<{ total_requests: number; successful_requests: number; failed_requests: number; error_rate: number; avg_latency_ms: number; active_servers: number } | null>(null);
  const [latency, setLatency] = useState<{ p50: number; p90: number; p95: number; p99: number; min: number; max: number } | null>(null);
  const [errors, setErrors] = useState<Array<{ timestamp: string; server_id: string; method: string; error: string }>>([]);

  const load = useCallback(async () => {
    try {
      const [sum, lat, errs] = await Promise.all([
        api.mcpTelemetrySummary(),
        api.mcpLatencyDistribution(),
        api.mcpRecentErrors(20),
      ]);
      setSummary(sum);
      setLatency(lat);
      setErrors(errs.errors);
    } catch (e) {
      // Telemetry may not be available
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Total Requests" value={summary?.total_requests ?? 0} />
        <Stat label="Successful" value={summary?.successful_requests ?? 0} tone="ok" />
        <Stat label="Failed" value={summary?.failed_requests ?? 0} tone={summary?.failed_requests ? "danger" : "default"} />
        <Stat label="Error Rate" value={summary ? `${safeFixed((safeNum(summary?.error_rate) * 100), 1)}%` : "N/A"} tone={summary && summary.error_rate > 0.1 ? "warn" : "default"} />
        <div className="ml-auto">
          <button
            onClick={() => load()}
            className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20"
          >
            Refresh
          </button>
        </div>
      </div>

      <Panel title="Latency Distribution" subtitle="Request latency percentiles (ms)" className="col-span-6">
        {latency ? (
          <div className="space-y-2">
            {[
              { label: "p50", value: latency.p50 },
              { label: "p90", value: latency.p90 },
              { label: "p95", value: latency.p95 },
              { label: "p99", value: latency.p99 },
              { label: "Min", value: latency.min },
              { label: "Max", value: latency.max },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between">
                <span className="text-xs text-faint">{label}</span>
                <span className="font-mono text-xs">{value.toFixed(2)}ms</span>
              </div>
            ))}
          </div>
        ) : (
          <Empty title="No latency data" hint="Latency data will appear as requests are made." />
        )}
      </Panel>

      <Panel title="Recent Errors" subtitle="Last 20 errors" className="col-span-6">
        {errors.length === 0 ? (
          <Empty title="No errors" hint="No errors have been recorded." />
        ) : (
          <div className="space-y-1.5">
            {errors.slice(0, 10).map((err, i) => (
              <div key={i} className="rounded-lg border border-danger/20 bg-danger/5 px-2 py-1.5">
                <div className="flex items-center gap-2 text-[11px]">
                  <Badge tone="danger">Error</Badge>
                  <span className="font-mono text-faint">{err.method}</span>
                </div>
                <div className="mt-0.5 truncate text-[10px] text-danger">{err.error}</div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Sub-tab: Versions ──

function McpVersionsTab() {
  const [versions, setVersions] = useState<Record<string, { server_id: string; protocol_version: string | null; server_version: string | null }>>({});
  const [matrix, setMatrix] = useState<{ supported_versions: string[]; recommended_version: string; servers: Record<string, { protocol_version: string | null; compatible: boolean }> } | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [vers, mat] = await Promise.all([
        api.mcpVersions(),
        api.mcpVersionMatrix(),
      ]);
      setVersions(vers);
      setMatrix(mat);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return <div className="flex items-center justify-center p-8 text-xs text-faint">Loading version info…</div>;
  }

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <button
          onClick={() => load()}
          className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20"
        >
          Refresh
        </button>
      </div>

      <Panel title="Protocol Versions" subtitle="Supported protocol versions" className="col-span-6">
        <div className="space-y-2">
          {matrix && (
            <>
              <div className="flex items-center justify-between">
                <span className="text-xs text-faint">Recommended</span>
                <span className="font-mono text-xs text-ok">{matrix.recommended_version}</span>
              </div>
              <div className="border-t border-border/40 pt-2">
                <div className="mb-1 text-[11px] font-medium text-faint">Supported</div>
                {matrix.supported_versions.map((v) => (
                  <div key={v} className="flex items-center gap-2 py-0.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-ok" />
                    <span className="text-xs text-muted">{v}</span>
                  </div>
                ))}
              </div>
            </>
          )}
          {!matrix && <Empty title="No version info" hint="No protocol version data available." />}
        </div>
      </Panel>

      <Panel title="Server Versions" subtitle="Version info per server" className="col-span-6">
        {Object.keys(versions).length === 0 ? (
          <Empty title="No servers" hint="No MCP servers have version information." />
        ) : (
          <div className="space-y-2">
            {Object.entries(versions).map(([sid, info]) => (
              <div key={sid} className="rounded-xl border border-border/60 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium">{sid}</span>
                  <Badge tone={matrix?.servers[sid]?.compatible ? "ok" : "warn"}>
                    {matrix?.servers[sid]?.compatible ? "Compatible" : "Incompatible"}
                  </Badge>
                </div>
                <div className="mt-1 grid grid-cols-1 md:grid-cols-2 gap-1 text-[11px] text-faint">
                  <span>Protocol: {info.protocol_version || "—"}</span>
                  <span>Server: {info.server_version || "—"}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
