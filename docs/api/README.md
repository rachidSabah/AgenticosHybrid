# API Documentation

AgenticOS exposes a REST + WebSocket control plane at `http://localhost:8000` (configurable via `--port`). All API endpoints are defined in `src/agentic_os/api/app.py` and served by FastAPI.

Interactive documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Authentication

### API Keys
Provider management endpoints can use API key authentication. API keys are stored in the encrypted vault:

```http
POST /api/providers/{name}/api-key
Content-Type: application/json

{"api_key": "sk-..."}
```

### Bearer Tokens
All API requests (except health/public endpoints) must include a bearer token:

```http
Authorization: Bearer <token>
```

Tokens are validated against the configured authentication provider. Token scopes are mapped to RBAC roles.

### CORS
The API allows cross-origin requests from:
- `http://localhost:3000` (Mission Control dev server)
- `http://127.0.0.1:3000`
- `tauri://localhost`
- `https://tauri.localhost`

## Base URL

All endpoints are prefixed with `/api/` unless otherwise noted:

```
http://localhost:8000/api/...
```

---

## Desktop Runtime (`/api/desktop/*`)

The Desktop Runtime API controls the Tauri-based native desktop shell.

### Runtime State
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/state` | Full desktop state (windows, workspaces, config, performance, diagnostics) |
| GET | `/api/desktop/status` | Desktop runtime status (stopped/starting/running/stopping/error) |
| POST | `/api/desktop/restart` | Restart the desktop runtime |

### Windows (`/api/desktop/windows/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/windows` | List all windows |
| GET | `/api/desktop/windows/{window_id}` | Get window details |
| POST | `/api/desktop/windows` | Create a new window (body: `WindowConfig`) |
| DELETE | `/api/desktop/windows/{window_id}` | Close a window |
| POST | `/api/desktop/windows/{window_id}/focus` | Focus a window |
| POST | `/api/desktop/windows/{window_id}/minimize` | Minimize a window |
| POST | `/api/desktop/windows/{window_id}/maximize` | Maximize a window |
| POST | `/api/desktop/windows/{window_id}/restore` | Restore a window |
| POST | `/api/desktop/windows/{window_id}/fullscreen` | Enter fullscreen |

### Workspaces (`/api/desktop/workspaces/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/workspaces` | List all workspaces |
| POST | `/api/desktop/workspaces` | Create a workspace |
| GET | `/api/desktop/workspaces/{workspace_id}` | Get workspace details |
| PUT | `/api/desktop/workspaces/{workspace_id}` | Update workspace properties |
| DELETE | `/api/desktop/workspaces/{workspace_id}` | Delete a workspace |
| POST | `/api/desktop/workspaces/{workspace_id}/switch` | Switch to a workspace |
| GET | `/api/desktop/workspaces/active` | Get the active workspace |
| GET | `/api/desktop/workspaces/{workspace_id}/layout` | Get workspace layout |
| PUT | `/api/desktop/workspaces/{workspace_id}/layout` | Update workspace layout |
| POST | `/api/desktop/workspaces/{workspace_id}/tabs` | Add a tab to a workspace |
| DELETE | `/api/desktop/workspaces/{workspace_id}/tabs/{tab_id}` | Remove a tab |
| POST | `/api/desktop/workspaces/{workspace_id}/tabs/{tab_id}/activate` | Activate a tab |
| POST | `/api/desktop/workspaces/{workspace_id}/panels` | Add a panel |
| DELETE | `/api/desktop/workspaces/{workspace_id}/panels/{panel_id}` | Remove a panel |

### Notifications (`/api/desktop/notifications/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/notifications` | List all notifications |
| POST | `/api/desktop/notifications` | Send a notification (body: `DesktopNotification`) |
| DELETE | `/api/desktop/notifications/{notification_id}` | Dismiss a notification |
| POST | `/api/desktop/notifications/{notification_id}/click` | Mark notification as clicked |
| GET | `/api/desktop/notifications/unread/count` | Get unread notification count |

### File Integration (`/api/desktop/files/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/desktop/file/open` | Open a file dialog (body: `DialogConfig`) |
| POST | `/api/desktop/file/save` | Open a save file dialog (body: `DialogConfig`) |

### Clipboard (`/api/desktop/clipboard`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/clipboard` | Get clipboard content |
| PUT | `/api/desktop/clipboard` | Set clipboard content (body: `ClipboardContent`) |

### Terminal (`/api/desktop/terminal/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/terminals` | List open terminals |
| POST | `/api/desktop/terminals` | Open a new terminal (body: `TerminalConfig`) |
| DELETE | `/api/desktop/terminals/{terminal_id}` | Close a terminal |

### Process (`/api/desktop/processes/*`)
Process management is handled through the Runtime Execution Engine under `/api/runtime/`. Desktop-specific process information is available via desktop diagnostics.

### Configuration (`/api/desktop/config`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/config` | Get desktop configuration |
| PUT | `/api/desktop/config` | Update desktop configuration |
| GET | `/api/desktop/config/theme` | Get current theme |
| PUT | `/api/desktop/config/theme` | Set theme (light/dark/system) |

### Diagnostics (`/api/desktop/diagnostics`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/diagnostics` | Full system diagnostics (OS, Python, Tauri, Node versions, display info) |
| GET | `/api/desktop/diagnostics/health` | Health check for all desktop subsystems |

### Performance (`/api/desktop/performance`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/performance` | Current performance metrics (CPU, memory, GPU, disk, uptime) |
| GET | `/api/desktop/performance/history/{metric}` | Historical values for a specific metric |
| POST | `/api/desktop/performance/monitor/start` | Start performance monitoring |
| POST | `/api/desktop/performance/monitor/stop` | Stop performance monitoring |

### Menus (`/api/desktop/menus/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/menus` | List all menus |
| POST | `/api/desktop/menus` | Create a custom menu (body: `MenuConfig`) |
| GET | `/api/desktop/menus/default` | Get default menu definitions |

### Keyboard Shortcuts (`/api/desktop/shortcuts/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/shortcuts` | List all registered keyboard shortcuts |

### Command Palette (`/api/desktop/command-palette`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/command-palette` | Get command palette items |

### Global Search (`/api/desktop/search`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/search?q={query}` | Global search across workspaces, files, and settings |

### Runtime Discovery (`/api/desktop/runtimes/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/runtimes` | List discovered runtimes |
| POST | `/api/desktop/runtimes/discover` | Trigger runtime discovery scan |
| GET | `/api/desktop/runtimes/{runtime_type}` | Get runtime details by type |
| POST | `/api/desktop/runtimes/{runtime_type}/verify` | Verify a specific runtime |

### Updates (`/api/desktop/updates/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/updates/check?channel=stable` | Check for available updates |
| GET | `/api/desktop/updates/status` | Current update status |
| GET | `/api/desktop/updates/history` | Update history |
| GET | `/api/desktop/updates/pending` | Get pending update manifest |
| GET | `/api/desktop/updates/version` | Current installed version |
| POST | `/api/desktop/updates/download` | Download an update (body: `UpdateManifest`) |
| POST | `/api/desktop/updates/install` | Install a downloaded update (body: `UpdateManifest`) |

### Channels (`/api/desktop/channels/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/channels` | List available update channels |
| GET | `/api/desktop/channels/current` | Get current update channel |
| PUT | `/api/desktop/channels` | Set update channel (body: `{"channel": "beta"}`) |

### Rollback (`/api/desktop/rollback`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/desktop/rollback` | Rollback to specified version |
| GET | `/api/desktop/rollback/available` | List available rollback versions |

### Installer (`/api/desktop/installer/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/desktop/installer/generate` | Generate an installer (body: `InstallerConfig`) |
| POST | `/api/desktop/installer/generate-all` | Generate all platform installers |
| GET | `/api/desktop/installer/supported-types` | List supported installer types |
| POST | `/api/desktop/installer/validate` | Validate an installer at a given path |

### First Run (`/api/desktop/first-run/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/first-run` | Get first run wizard state |
| POST | `/api/desktop/first-run/step` | Execute a first-run step (welcome/workspace/config/runtime_discovery/provider/plugin/database/health) |
| POST | `/api/desktop/first-run/complete` | Mark first run as complete |

### Offline (`/api/desktop/offline/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/offline` | Get offline mode state |
| POST | `/api/desktop/offline/enable` | Enable offline mode |
| POST | `/api/desktop/offline/disable` | Disable offline mode |
| GET | `/api/desktop/offline/events` | List queued offline events |
| POST | `/api/desktop/offline/sync` | Sync queued offline events |

### Backup/Restore (`/api/desktop/backup/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/desktop/backup` | Create a backup (body: `BackupConfig`) |
| GET | `/api/desktop/backups` | List available backups |
| POST | `/api/desktop/restore` | Restore from a backup (body: `RestoreConfig`) |
| GET | `/api/desktop/restore/points` | List available restore points |

### Hardening (`/api/desktop/hardening/*`)
Hardening endpoints control production hardening features (integrity checks, memory leak detection, thread monitoring, startup validation, graceful shutdown). See `/api/desktop/diagnostics` for related endpoints.

---

## Providers (`/api/providers/*`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/providers` | List all registered providers |
| GET | `/api/provider-configs` | List provider configurations |
| POST | `/api/provider-configs` | Create or update a provider config (body: `ProviderConfig`) |
| DELETE | `/api/provider-configs/{name}` | Delete a provider config |
| POST | `/api/providers/{name}/api-key` | Store an API key for a provider |
| GET | `/api/providers/{name}/api-key/status` | Check if an API key exists for a provider |
| POST | `/api/providers/{name}/test` | Test provider connectivity |
| POST | `/api/providers/{name}/benchmark` | Benchmark a provider |
| GET | `/api/models` | List registered models (optional `?provider=` filter) |
| POST | `/api/models` | Register a custom model |
| GET | `/api/provider-health` | Health status of all providers |
| GET | `/api/cost` | Cost report (optional `?provider=` filter) |
| GET | `/api/rate-limits` | Rate limit status for each provider |
| POST | `/api/routing/policy` | Set routing policy (`latency`/`cost`/`round_robin`) |

---

## Runtime (`/api/runtime/*`)

The Universal Execution Engine API for managing runtime engines and executing tasks.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/runtime/engines` | List engines (optional `?engine_type=`, `?capability=`, `?status=` filters) |
| GET | `/api/runtime/engines/{engine_id}` | Get engine details |
| POST | `/api/runtime/engines` | Register a new engine (body: `EngineRegistration`) |
| DELETE | `/api/runtime/engines/{engine_id}` | Unregister an engine |
| POST | `/api/runtime/engines/{engine_id}/execute` | Execute on a specific engine |
| POST | `/api/runtime/execute` | Execute on the best matching engine |
| POST | `/api/runtime/discover` | Trigger engine discovery |
| GET | `/api/runtime/capabilities` | List capabilities for all engines |
| GET | `/api/runtime/engines/{engine_id}/health` | Engine health check |
| POST | `/api/runtime/engines/{engine_id}/benchmark` | Benchmark an engine |
| GET | `/api/runtime/engines/{engine_id}/sessions` | List engine sessions |

### Discovery (`/api/discovery/*`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/discovery/providers` | List discovery providers |
| PUT | `/api/discovery/providers/{name}` | Enable/disable a discovery provider |
| POST | `/api/discovery/scan` | Run discovery scan (optional `?profile=` name) |
| GET | `/api/discovery/cache` | List cached discovery results |
| DELETE | `/api/discovery/cache` | Clear discovery cache |
| GET | `/api/discovery/history` | Discovery scan history |
| GET | `/api/discovery/stats` | Aggregated discovery statistics |
| GET | `/api/discovery/profiles` | List discovery profiles |
| POST | `/api/discovery/profiles` | Create a discovery profile |
| GET | `/api/discovery/profiles/{name}` | Get a profile |
| DELETE | `/api/discovery/profiles/{name}` | Delete a profile |
| POST | `/api/discovery/profiles/{name}/activate` | Activate a profile for scheduled scanning |
| POST | `/api/discovery/engines/{engine_id}/validate` | Validate a discovered engine |
| POST | `/api/discovery/engines/{engine_id}/profile` | Profile a discovered engine |
| POST | `/api/discovery/hot-reload/start` | Start hot-reload monitoring |
| POST | `/api/discovery/hot-reload/stop` | Stop hot-reload monitoring |
| GET | `/api/discovery/hot-reload/status` | Hot-reload status |

---

## MCP (`/api/mcp/*`)

The Model Context Protocol (MCP) API manages MCP server lifecycles, tools, resources, and prompts.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/mcp/servers` | List MCP servers (optional `?status=`, `?enabled_only=` filters) |
| GET | `/api/mcp/servers/{server_id}` | Get server detail |
| POST | `/api/mcp/servers` | Register an MCP server (body: `MCPServerCreate`) |
| PUT | `/api/mcp/servers/{server_id}` | Update an MCP server (body: `MCPServerUpdate`) |
| DELETE | `/api/mcp/servers/{server_id}` | Delete an MCP server |
| POST | `/api/mcp/servers/{server_id}/start` | Start a server |
| POST | `/api/mcp/servers/{server_id}/stop` | Stop a server |
| POST | `/api/mcp/servers/{server_id}/restart` | Restart a server |
| POST | `/api/mcp/servers/{server_id}/reload` | Reload server configuration |
| GET | `/api/mcp/servers/{server_id}/tools` | List server tools |
| POST | `/api/mcp/servers/{server_id}/tools/discover` | Discover tools from server |
| POST | `/api/mcp/servers/{server_id}/tools/call` | Invoke a tool (body: `{"tool": "...", "arguments": {...}}`) |
| GET | `/api/mcp/servers/{server_id}/resources` | List server resources |
| GET | `/api/mcp/servers/{server_id}/resources/read` | Read a resource (`?uri=`) |
| POST | `/api/mcp/servers/{server_id}/resources/subscribe` | Subscribe to resource updates |
| DELETE | `/api/mcp/servers/{server_id}/resources/subscribe` | Unsubscribe from resource updates |
| GET | `/api/mcp/servers/{server_id}/prompts` | List server prompts |
| GET | `/api/mcp/servers/{server_id}/prompts/get` | Get a prompt by name |
| GET | `/api/mcp/servers/{server_id}/health` | Server health check |
| GET | `/api/mcp/health` | Health summary for all MCP servers |
| GET | `/api/mcp/sessions` | List active MCP sessions |
| POST | `/api/mcp/servers/{server_id}/permissions` | Set tool→capability permission mappings |
| GET | `/api/mcp/servers/{server_id}/permissions` | Get permission mappings |

---

## Orchestration (`/api/orchestration/*`)

The Orchestration API coordinates multi-agent swarms, goals, and tasks.

### Swarm Profiles & Swarms
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/swarm/profiles` | List swarm profiles |
| GET | `/api/swarm/profiles/{name}` | Get a profile |
| POST | `/api/swarm/profiles` | Create a profile |
| DELETE | `/api/swarm/profiles/{name}` | Delete a profile |
| GET | `/api/swarm/swarms` | List swarms |
| GET | `/api/swarm/swarms/{swarm_id}` | Get a swarm |
| POST | `/api/swarm/swarms` | Create a swarm |
| DELETE | `/api/swarm/swarms/{swarm_id}` | Delete a swarm |

### Planner
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/swarm/planner/analyze` | Analyze a goal for complexity |
| POST | `/api/swarm/planner/plan` | Create a full execution plan |
| POST | `/api/swarm/planner/resolve-dependencies` | Resolve task dependencies |
| POST | `/api/swarm/planner/parallelize` | Identify parallelizable tasks |

### Scheduler
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/swarm/scheduler/schedule` | Schedule plan tasks (topological sort) |
| POST | `/api/swarm/scheduler/dispatch` | Dispatch a task to an agent |
| GET | `/api/swarm/scheduler/schedule/{plan_id}` | Get scheduled order |

### Supervisor
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/swarm/supervisor/monitor` | Monitor plan execution |
| POST | `/api/swarm/supervisor/detect-failures` | Detect failed/hung tasks |
| POST | `/api/swarm/supervisor/detect-deadlocks` | Detect deadlocked dependency chains |
| POST | `/api/swarm/supervisor/restart` | Restart a failed task |
| POST | `/api/swarm/supervisor/reassign` | Reassign task to a different agent |

### Result Merger, Validation, Checkpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/swarm/merge` | Merge task results with a strategy |
| POST | `/api/swarm/merge/resolve` | Resolve merge conflicts |
| POST | `/api/swarm/validate/output` | Validate task output |
| POST | `/api/swarm/validate/plan` | Validate plan structure |
| POST | `/api/swarm/validate/security` | Validate security constraints |
| POST | `/api/swarm/validate/policy` | Validate against policies |
| POST | `/api/swarm/checkpoints` | Save execution checkpoint |
| GET | `/api/swarm/checkpoints/{checkpoint_id}` | Restore a checkpoint |
| GET | `/api/swarm/checkpoints` | List checkpoints for a plan |
| DELETE | `/api/swarm/checkpoints/{checkpoint_id}` | Delete a checkpoint |

### Agent Selection, Metrics, Cost, Recovery
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/swarm/agent-select` | Select best agent for a task |
| POST | `/api/swarm/capability-match` | Find agents matching capabilities |
| POST | `/api/swarm/metrics/collect` | Collect execution metrics |
| POST | `/api/swarm/metrics/timeline` | Record timeline entry |
| GET | `/api/swarm/metrics/timeline/{plan_id}` | Get execution timeline |
| POST | `/api/swarm/cost/estimate` | Estimate plan cost |
| POST | `/api/swarm/cost/track` | Track actual cost |
| GET | `/api/swarm/cost/{plan_id}` | Get accumulated costs |
| GET | `/api/swarm/performance/{plan_id}` | Performance analysis |
| POST | `/api/swarm/recovery/task` | Recover a failed task |
| POST | `/api/swarm/recovery/plan` | Recover an execution plan |
| POST | `/api/swarm/recovery/rollback` | Rollback to a checkpoint |
| POST | `/api/swarm/retry/should` | Check if task should retry |
| POST | `/api/swarm/retry/reset` | Reset retry count |

### Goals & Tasks
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/swarm/goals` | List orchestration goals |
| GET | `/api/swarm/goals/{goal_id}` | Get a goal |
| POST | `/api/swarm/goals` | Create a goal |
| DELETE | `/api/swarm/goals/{goal_id}` | Cancel a goal |
| GET | `/api/swarm/plans/{plan_id}` | Get an orchestration plan |
| GET | `/api/swarm/tasks` | List orchestration tasks |
| GET | `/api/swarm/tasks/{task_id}` | Get a task |

---

## Learning (`/api/learning/*`)

The Learning & Optimization Engine API collects execution data, generates recommendations, and optimizes system behavior.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/learning/profiles` | List learning profiles |
| POST | `/api/learning/profiles` | Create a learning profile |
| GET | `/api/learning/profiles/{profile_id}` | Get a profile |
| DELETE | `/api/learning/profiles/{profile_id}` | Delete a profile |
| POST | `/api/learning/executions` | Record an execution |
| GET | `/api/learning/executions` | List executions |
| GET | `/api/learning/executions/{execution_id}` | Get execution details |
| POST | `/api/learning/analyze` | Analyze executions |
| GET | `/api/learning/metrics` | Get learning metrics |
| GET | `/api/learning/recommendations` | List recommendations |
| POST | `/api/learning/recommendations/generate` | Generate a recommendation |
| POST | `/api/learning/recommendations/{id}/apply` | Apply a recommendation |
| POST | `/api/learning/recommendations/{id}/dismiss` | Dismiss a recommendation |
| POST | `/api/learning/optimization` | Run optimization |
| GET | `/api/learning/optimization/results` | List optimization results |
| POST | `/api/learning/optimization/{id}/rollback` | Rollback an optimization |
| POST | `/api/learning/routing/analyze` | Analyze routing patterns |
| POST | `/api/learning/routing/optimize` | Optimize routing |
| GET | `/api/learning/routing/stats` | Routing statistics |
| POST | `/api/learning/benchmarks` | Create a benchmark |
| POST | `/api/learning/benchmarks/{id}/run` | Run a benchmark |
| GET | `/api/learning/benchmarks` | List benchmarks |
| GET | `/api/learning/benchmarks/{id}` | Get benchmark details |
| DELETE | `/api/learning/benchmarks/{id}` | Delete a benchmark |
| POST | `/api/learning/experiments` | Create an experiment |
| GET | `/api/learning/experiments` | List experiments |
| GET | `/api/learning/experiments/{id}` | Get experiment details |
| POST | `/api/learning/experiments/{id}/start` | Start an experiment |
| POST | `/api/learning/experiments/{id}/complete` | Complete an experiment |
| POST | `/api/learning/evaluate` | Evaluate a target |
| GET | `/api/learning/evaluations/{target_id}` | List evaluations |
| POST | `/api/learning/performance/profile` | Profile performance |
| GET | `/api/learning/performance/trends` | Performance trends |
| GET | `/api/learning/cost/metrics` | Cost metrics |
| GET | `/api/learning/quality/metrics` | Quality metrics |
| GET | `/api/learning/failure-analysis` | Failure analysis |
| GET | `/api/learning/policies` | List optimization policies |
| POST | `/api/learning/policies` | Create a policy |
| PUT | `/api/learning/policies/{policy_id}` | Update a policy |
| DELETE | `/api/learning/policies/{policy_id}` | Delete a policy |
| GET | `/api/learning/latency/metrics` | Latency metrics |

---

## Plugins (`/api/plugins/*`)

Plugin management handles the plugin lifecycle: registration, configuration, and discovery.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/plugins` | List installed plugins |
| POST | `/api/plugins` | Install a plugin |
| DELETE | `/api/plugins/{plugin_id}` | Uninstall a plugin |
| GET | `/api/plugins/{plugin_id}` | Get plugin details |
| PUT | `/api/plugins/{plugin_id}/config` | Update plugin configuration |
| POST | `/api/plugins/{plugin_id}/enable` | Enable a plugin |
| POST | `/api/plugins/{plugin_id}/disable` | Disable a plugin |

---

## Event Bus (`/api/events/*`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/events` | List recent events |
| GET | `/api/events/topics` | List available event topics |

---

## Dashboard (`/api/dashboard`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard` | Aggregated dashboard summary |

---

## Health (`/api/health`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/healthz` | Simple health check (`{"status": "ok"}`) |
| GET | `/metrics` | Prometheus-formatted metrics |

---

## WebSocket API (`/ws`)

AgenticOS provides two WebSocket endpoints for real-time event streaming:

### Dashboard WebSocket (`/ws/dashboard`)
Streams all EventBus events to connected Mission Control dashboards. Each message is an `EventEnvelope` with `id`, `type`, `source`, `timestamp`, `topic`, and `payload`.

### MCP WebSocket (`/ws/mcp`)
Streams MCP-specific events (20 topics covering registration, lifecycle, health, tools, permissions, sessions, resources, transport, and capabilities).

**Connection:**
```javascript
const ws = new WebSocket("ws://localhost:8000/ws/dashboard");
ws.onmessage = (event) => {
  const envelope = JSON.parse(event.data);
  console.log(envelope.topic, envelope.payload);
};
```

---

## SDK Client Usage

The Python SDK provides programmatic access to the API. See `docs/SDK.md` for full documentation.

```python
from agentic_os.sdk.mcp import McpServerSdk
from agentic_os.sdk.swarm import SwarmClient
from agentic_os.sdk.learning import LearningClient

# MCP Server SDK
sdk = McpServerSdk.create_stdio(name="my-server", command="node", args=["server.js"])
await sdk.initialize()
await sdk.register(registry)
await sdk.start()

# Swarm SDK
swarm = SwarmClient()
await swarm.initialize()
spec = await swarm.create_swarm(name="my-swarm", topology="mesh")

# Learning SDK
learning = LearningClient(manager)
await learning.record_execution(
    execution_id="exec-1",
    engine_type="generic",
    engine_name="engine-1",
    duration_ms=1500.0,
    status="completed",
)
```

---

## Error Handling

All API errors return structured JSON responses:

```json
{
  "detail": "Engine not found"
}
```

Standard HTTP status codes:
| Status | Meaning |
|--------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad request (invalid input) |
| 404 | Resource not found |
| 409 | Conflict (duplicate) |
| 422 | Validation error |
| 500 | Internal server error |
| 501 | Not implemented |
| 503 | Service unavailable (subsystem not initialized) |

---

## Rate Limiting

Provider rate limits are configurable per provider and tracked via `GET /api/rate-limits`:

```json
{
  "openai": 45,
  "anthropic": 58
}
```

Rate limits are enforced at the provider adapter level. When a provider's rate limit is exceeded, the routing engine automatically falls back to the next available provider if configured.

---

## Pagination

List endpoints support standard pagination via `limit` and `offset` query parameters:

```http
GET /api/workflows?limit=20&offset=40
GET /api/learning/executions?limit=50&offset=0
GET /api/swarm/tasks?limit=100&offset=0
```

Default `limit` is 50 unless otherwise specified. Maximum `limit` is 1000.

---

## Versioning

The API is versioned through the URL path prefix (`/api/`). The current API version is **v1**.

Component versions can be queried:
- `GET /api/desktop/updates/version` — installed AgenticOS version
- `GET /healthz` — backend status
- `GET /api/desktop/diagnostics` — detailed component versions (Python, Node, Rust, Tauri, etc.)

The OpenAPI schema is available at `/openapi.json` and reflects the exact version of the running application.
