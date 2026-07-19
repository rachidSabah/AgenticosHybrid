"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type {
  MCPHealthSummary,
  MCPPermissionMapping,
  MCPServerDetail,
  MCPSessionMap,
  MCPTool,
  MCPToolResult,
} from "@/lib/types";

type McpTab = "servers" | "tools" | "permissions" | "health" | "sessions";

export function McpManager() {
  const [tab, setTab] = useState<McpTab>("servers");

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-border/60 px-4 pt-2">
        {(["servers", "tools", "permissions", "health", "sessions"] as const).map((t) => (
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
                    : "Sessions"}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {tab === "servers" && <McpServersTab />}
        {tab === "tools" && <McpToolsTab />}
        {tab === "permissions" && <McpPermissionsTab />}
        {tab === "health" && <McpHealthTab />}
        {tab === "sessions" && <McpSessionsTab />}
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

  const load = useCallback(() => {
    setLoading(true);
    api.mcpServers().then(setServers).catch(() => {}).finally(() => setLoading(false));
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
    <div className="grid h-full grid-cols-12 gap-4 p-4">
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

// ── Sub-tab: Tools ──

function McpToolsTab() {
  const [servers, setServers] = useState<MCPServerDetail[]>([]);
  const [selectedServer, setSelectedServer] = useState<string>("");
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [callToolName, setCallToolName] = useState("");
  const [callArgs, setCallArgs] = useState("{}");
  const [callResult, setCallResult] = useState<MCPToolResult | null>(null);
  const [loading, setLoading] = useState(false);

  const loadServers = useCallback(() => {
    api.mcpServers().then(setServers).catch(() => {});
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
    <div className="grid h-full grid-cols-12 gap-4 p-4">
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
          <Panel title="Discovered Tools" subtitle={`${tools.length} tools`} className="col-span-6 row-span-2">
            {tools.length === 0 ? (
              <Empty title="No tools discovered" hint='Click "Discover Tools" to list available tools.' />
            ) : (
              <div className="space-y-2">
                {tools.map((t) => (
                  <div key={t.name} className="rounded-xl border border-border/60 px-3 py-2.5">
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
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Invoke Tool" subtitle="Execute a tool on the selected server" className="col-span-6 row-span-2">
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

  const loadServers = useCallback(() => {
    api.mcpServers().then(setServers).catch(() => {});
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
    <div className="grid h-full grid-cols-12 gap-4 p-4">
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

  const load = useCallback(() => {
    api.mcpServers().then(setServers).catch(() => {});
    api.mcpHealthSummary().then(setSummary).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const healthyCount = servers.filter((s) => s.health === "healthy").length;
  const degradedCount = servers.filter((s) => s.health === "degraded").length;
  const unhealthyCount = servers.filter((s) => s.health === "unhealthy").length;
  const unknownCount = servers.filter((s) => s.health === "unknown").length;

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
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

  const load = useCallback(() => {
    api.mcpSessions().then(setSessions).catch(() => {});
    api.mcpServers().then(setServers).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const serverName = (serverId: string) => {
    const sv = servers.find((s) => s.config.id === serverId);
    return sv ? sv.config.name : serverId;
  };

  const entries = sessions ? Object.entries(sessions.sessions) : [];

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
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
