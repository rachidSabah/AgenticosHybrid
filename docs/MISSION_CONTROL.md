# Mission Control — Desktop Application Guide

**Mission Control** is the immersive desktop interface for AgenticOS. Built as a Next.js 15 single-page application with React 19, it provides 15 dashboard views that give operators full visibility and control over the platform — agents, providers, runtimes, workspaces, MCP servers, swarms, learning systems, and the desktop runtime itself.

- **Frontend:** `apps/mission-control/` — Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, Framer Motion, Zustand
- **Backend:** FastAPI REST control plane + WebSocket event stream at `/ws/dashboard`
- **Desktop shell:** Tauri v2 (native window management, system tray, notifications)

---

## 1. Getting Started

### 1.1 Prerequisites

- AgenticOS backend running on port 8000 (`uv run python -m agentic_os serve`)
- Node.js 18+ and npm installed

### 1.2 Running Mission Control

```bash
# Start the backend
cd AgenticOS
uv run python -m agentic_os serve

# In another terminal, start the frontend
cd apps/mission-control
npm install --legacy-peer-deps
npm run dev
```

Open `http://localhost:3000` in your browser, or launch the Tauri desktop app via `npm run tauri dev`.

### 1.3 Architecture

Mission Control connects to the backend through:

1. **REST API** — All CRUD operations use the FastAPI REST control plane (port 8000)
2. **WebSocket** (`/ws/dashboard`) — Real-time event stream driving live dashboard updates
3. **WebSocket** (`/ws/mcp`) — Dedicated MCP event stream for server lifecycle events

Every view displays real data from EventBus envelopes or REST responses — no fabricated or cached data.

---

## 2. Desktop Overview

The Desktop Overview dashboard (`mission-overview.tsx`) provides the entry point to Mission Control. It displays:

- **System Status** — Backend health, bus type, runtime status
- **Active Workspace** — Current workspace name, tab count
- **Recent Notifications** — Latest desktop notifications with levels
- **Quick Stats** — Runtime count, task queue depth, provider health
- **Event Pulse** — Live heartbeat indicator from the EventBus WebSocket

This view serves as the landing page and includes quick-action cards for common tasks.

---

## 3. Runtime Dashboard

The **Discovery Dashboard** (`discovery-dashboard.tsx`) provides full visibility into the Runtime Discovery system.

**Tabs:**
- **Dashboard** — Provider status, cache entries, hot-reload state, discovery statistics
- **History** — Scan history with timestamps, durations, and engine counts
- **Profiles** — Discovery profiles CRUD (create, edit, activate)
- **Validation** — Engine validation results with pass/fail/skip status

**Features:**
- Real-time provider enable/disable toggles
- Start/stop hot-reload for automatic re-discovery
- Cache management (view entries, invalidate all)
- Manual scan trigger with profile selection
- Discovery statistics (total scans, engines found, duration)

**API endpoints consumed:**
- `/api/discovery/providers` — Provider status
- `/api/discovery/scan` — Trigger scans
- `/api/discovery/cache` — Cache management
- `/api/discovery/profiles` — Profile CRUD
- `/api/discovery/history` — Scan history
- `/api/discovery/stats` — Aggregated statistics
- `/api/discovery/hot-reload/status` — Hot-reload state

---

## 4. Execution Dashboard

The **Execution Graph** view (`execution-graph.tsx`) displays active and historical task execution.

**Features:**
- **Active Tasks** — Real-time task queue with status indicators (pending, running, completed, failed)
- **Execution History** — Filterable log of completed tasks with duration, status, and engine
- **Timeline View** — Chronological task execution timeline
- **Agent Assignment** — Shows which agent/engine handled each task

**API endpoints consumed:**
- `/api/tasks` — Task listing and status
- `/api/runtime/engines` — Active engines
- `/api/runtime/execute` — Task execution controls

---

## 5. Provider Dashboard

The **Provider Control Center** (`provider-control-center.tsx`) manages AI provider connections.

**Features:**
- **Provider List** — All registered providers with type and status
- **Health Status** — Real-time health indicators (healthy, degraded, down, unknown)
- **Model Registry** — List models per provider, register new models
- **API Key Management** — Store, verify, and rotate provider API keys
- **Provider Testing** — Endpoint connectivity and latency testing
- **Benchmarking** — Run provider benchmarks for performance comparison
- **Cost Tracking** — Per-provider cost summaries and rate limit status
- **Routing Configuration** — Set routing policy (latency, cost, round-robin)
- **Provider CRUD** — Add, edit, delete provider configurations

**API endpoints consumed:**
- `/api/providers` — List providers
- `/api/provider-configs` — Provider configurations CRUD
- `/api/provider-health` — Health status
- `/api/models` — Model registry
- `/api/cost` — Cost tracking
- `/api/rate-limits` — Rate limit status
- `/api/routing/policy` — Routing configuration

---

## 6. MCP Dashboard

The **MCP Manager** (`mcp-manager.tsx`) provides control over MCP (Model Context Protocol) servers.

**Features:**
- **Server List** — All registered MCP servers with transport type and status
- **Server CRUD** — Register, update, delete MCP server configurations
- **Lifecycle Management** — Start, stop, restart, reload individual servers
- **Tool Discovery** — Discover and list tools exposed by each server
- **Tool Invocation** — Call MCP tools with arguments directly from the UI
- **Resource Browser** — List and read server resources
- **Prompt Catalog** — List and retrieve server prompts
- **Health Monitoring** — Per-server health checks with aggregated summary
- **Session Management** — View active MCP sessions
- **Permission Mapping** — Configure tool→capability permission mappings

**API endpoints consumed:**
- `/api/mcp/servers` — Server CRUD
- `/api/mcp/servers/{id}/start|stop|restart|reload` — Lifecycle
- `/api/mcp/servers/{id}/tools` — Tool listing and invocation
- `/api/mcp/servers/{id}/resources` — Resource operations
- `/api/mcp/servers/{id}/prompts` — Prompt operations
- `/api/mcp/servers/{id}/health` — Health checks
- `/api/mcp/health` — Aggregated health summary

---

## 7. Swarm Dashboard

The **Swarm Dashboard** (`swarm-dashboard.tsx`) provides orchestration control for multi-agent swarms.

**Tabs:**
- **Dashboard** — Overview of active swarms, coordination patterns, agent counts
- **Swarms** — CRUD management for swarm configurations
- **Agents** — Available agents (discovered runtimes), capability matching
- **Tasks** — Task queues per swarm, status tracking
- **Execution** — Plan execution timeline, checkpoint management

**Features:**
- Swarm profile management (create, activate, delete)
- Goal analysis and plan creation
- Task dependency resolution and scheduling
- Execution monitoring with failure and deadlock detection
- Checkpoint save/restore for resilience
- Cost tracking and performance analysis
- Agent selection with capability matching

**API endpoints consumed:**
- `/api/swarm/profiles` — Swarm profiles CRUD
- `/api/swarm/swarms` — Swarm CRUD
- `/api/swarm/planner/*` — Goal analysis and planning
- `/api/swarm/scheduler/*` — Task scheduling and dispatch
- `/api/swarm/supervisor/*` — Execution monitoring and recovery
- `/api/swarm/checkpoints/*` — Checkpoint management
- `/api/swarm/cost/*` — Cost tracking
- `/api/swarm/metrics/*` — Performance metrics

---

## 8. Learning Dashboard

The Learning & Optimization dashboard provides insight into the Phase 5 Learning Engine.

**Features:**
- **Execution History** — Browse recorded executions with filtering by engine type and status
- **Performance Trends** — Latency, throughput, and error rate over time
- **Cost Analysis** — Per-provider and per-model cost metrics
- **Quality Metrics** — Success rates, quality scores by engine
- **Benchmarks** — Create, run, and compare benchmarks across engines
- **Experiments** — A/B test configurations with automatic rollback on regression
- **Recommendations** — Generated optimization recommendations (apply/dismiss)
- **Routing Analysis** — Analyze routing decisions and optimize routing policies
- **Failure Analysis** — Identify failure patterns and root causes

**API endpoints consumed:**
- `/api/learning/executions` — Execution history
- `/api/learning/metrics` — Performance metrics
- `/api/learning/cost/metrics` — Cost metrics
- `/api/learning/quality/metrics` — Quality metrics
- `/api/learning/benchmarks` — Benchmark management
- `/api/learning/experiments` — Experiment management
- `/api/learning/recommendations` — Recommendations
- `/api/learning/routing/*` — Routing analysis and optimization
- `/api/learning/failure-analysis` — Failure analysis

---

## 9. Plugin Dashboard

The **Plugin Marketplace** (`plugin-marketplace.tsx`) manages the Plugin SDK system.

**Features:**
- **Installed Plugins** — List of all loaded plugins with version and status
- **Plugin Details** — Description, author, capabilities, settings
- **Plugin Enable/Disable** — Toggle plugins on and off
- **Plugin Configuration** — Per-plugin settings editor
- **Marketplace** — Browse and install plugins (Phase 7 feature)

---

## 10. Desktop Diagnostics

The **System Monitor** (`system-monitor.tsx`) provides comprehensive diagnostic information.

**Features:**
- **System Information** — OS, platform, architecture, Python version
- **Health Checks** — Startup validation results, integrity check status
- **Service Status** — Import status of all core service modules
- **Environment** — Environment variables and paths
- **Repair Tools** — Targeted repair for workspace, config, cache, database
- **Recovery Mode** — Enter/exit recovery mode, run full recovery

**API endpoints consumed:**
- `/api/desktop/diagnostics` — Full diagnostic report
- `/api/desktop/diagnostics/health` — Quick health check

---

## 11. Desktop Updates

The Desktop Updates panel manages the Auto-Update Framework.

**Features:**
- **Current Version** — Display installed version
- **Check for Updates** — Query GitHub Releases API for new versions
- **Channel Selection** — Switch between stable, beta, and nightly channels
- **Update Details** — Release notes, asset list, version comparison
- **Download & Install** — Download and install updates with progress
- **Update History** — Log of all installed updates with timestamps
- **Rollback** — Rollback to a previous version
- **Pending Updates** — View and manage pending update manifests

**API endpoints consumed:**
- `/api/desktop/updates/check` — Check for updates
- `/api/desktop/updates/status` — Current status
- `/api/desktop/updates/version` — Installed version
- `/api/desktop/updates/history` — Update history
- `/api/desktop/updates/pending` — Pending update
- `/api/desktop/updates/download` — Download update
- `/api/desktop/updates/install` — Install update
- `/api/desktop/channels` — Channel management
- `/api/desktop/rollback` — Rollback management

---

## 12. Offline Dashboard

The Offline Dashboard monitors and controls offline mode.

**Features:**
- **Connection State** — Online, offline, or synchronizing indicator
- **Event Queue** — List of queued events with type, payload, and timestamp
- **Queue Size** — Current queue depth
- **Sync Controls** — Manual sync trigger, auto-sync toggle
- **Configuration** — Offline mode settings (auto-sync interval, queue limits)

**API endpoints consumed:**
- `/api/desktop/offline` — State information
- `/api/desktop/offline/events` — Queued events
- `/api/desktop/offline/sync` — Sync control

---

## 13. Workspace Manager

The **Workspace Explorer** (`workspace-explorer.tsx`) provides full workspace management.

**Features:**
- **Workspace List** — All workspaces with status indicators
- **Create Workspace** — Create new named workspaces
- **Switch Workspace** — One-click workspace switching
- **Edit Workspace** — Rename, reorder tabs, reorganize panels
- **Delete Workspace** — Remove workspace (with confirmation)
- **Layout Management** — View and edit workspace layouts (panel positions)
- **Tab Management** — Add, remove, activate tabs within workspaces
- **Panel Management** — Add, remove panels with position configuration

**API endpoints consumed:**
- `/api/desktop/workspaces` — Workspace CRUD
- `/api/desktop/workspaces/active` — Active workspace
- `/api/desktop/workspaces/{id}/switch` — Switch workspace
- `/api/desktop/workspaces/{id}/layout` — Layout management
- `/api/desktop/workspaces/{id}/tabs` — Tab management
- `/api/desktop/workspaces/{id}/panels` — Panel management

---

## 14. Settings

The Settings panel manages application configuration.

**Features:**
- **Theme** — Light, dark, or system-follow theme selection
- **Language** — Interface language (currently English, with i18n framework)
- **Auto-Start** — Toggle auto-start on login
- **Notifications** — Enable/disable desktop notifications
- **Font Size** — Base font size adjustment
- **Animations** — Toggle UI animations
- **Keyboard Shortcuts** — View and customize shortcut bindings
- **Configuration Reset** — Reset to default settings

**API endpoints consumed:**
- `/api/desktop/config` — Full configuration
- `/api/desktop/config/theme` — Theme settings

---

## 15. Logs

The Logs panel provides access to application logging.

**Features:**
- **Desktop Logs** — Runtime application logs with level filtering (debug, info, warning, error, critical)
- **Event Log** — Recent EventBus events with topic, source, and timestamp
- **Audit Trail** — Security audit events (RBAC decisions, approvals, tool permissions)
- **Search** — Full-text search across log entries
- **Export** — Download log files for debugging

**API endpoints consumed:**
- `/api/security/audit` — Audit log entries
- EventBus WebSocket — Live event stream

---

## 16. Performance

The Performance panel provides real-time system resource monitoring.

**Features:**
- **CPU Usage** — Current and historical CPU percentage
- **Memory Usage** — RSS memory with growth tracking and leak detection
- **Disk I/O** — Read/write throughput
- **Thread Count** — Active and total thread count with threshold alerts
- **Network Connections** — Open handles and connections
- **Resource History** — Time-series charts for all metrics
- **Diagnostic Actions** — Run cleanup, check for leaks, monitor threads

**API endpoints consumed:**
- `/api/desktop/performance` — Current metrics
- `/api/desktop/performance/history/{metric}` — Historical data
- `/api/desktop/performance/monitor/start|stop` — Monitor control

---

## 17. Health

The Health panel displays comprehensive system health information.

**Features:**
- **Service Health** — Status of all core and desktop services
- **Integrity Checks** — Module import verification, configuration checks
- **Startup Validation** — Last validation results with check details
- **Hardening Status** — Production hardening configuration and status
- **Self Diagnostics** — Full diagnostic scan with recommendations
- **Memory Reports** — Leak detection reports with baseline comparison
- **Thread Reports** — Thread enumeration with threshold warnings
- **Cleanup History** — Resource cleanup actions log

**API endpoints consumed:**
- `/api/desktop/diagnostics` — Full diagnostics
- `/api/desktop/diagnostics/health` — Quick health check

---

## 18. Event Timeline

The Event Timeline panel provides a live stream of all EventBus events.

**Features:**
- **Live Feed** — Real-time events via the `/ws/dashboard` WebSocket
- **Topic Filtering** — Filter by event topic (task.*, agent.*, discovery.*, etc.)
- **Source Filtering** — Filter by event source component
- **Severity Highlighting** — Color-coded event levels
- **Search** — Full-text search across event payloads
- **Pause/Resume** — Freeze the live feed for inspection
- **Export** — Copy or download event data

**Topics displayed:**
- `task.*` — Task lifecycle events
- `agent.*` — Agent heartbeat, status, completion
- `provider.*` — Provider registration, health, failover
- `discovery.*` — Runtime discovery scan events
- `mcp.*` — MCP server lifecycle events
- `desktop.*` — Desktop runtime events
- `swarm.*` — Swarm orchestration events
- `learning.*` — Learning engine events
- `security.*` — Authorization and approval events

---

## 19. Notifications

The Notifications panel provides a centralized notification center.

**Features:**
- **Notification List** — All notifications with level (info, success, warning, error, critical)
- **Unread Count** — Badge counter in the navigation bar
- **Dismiss** — Dismiss individual notifications
- **Click Actions** — Click notifications to navigate to relevant views
- **Clear All** — Dismiss all notifications at once
- **Auto-Dismiss** — Configure auto-dismiss timeout per level

**API endpoints consumed:**
- `/api/desktop/notifications` — List and manage notifications
- `/api/desktop/notifications/unread/count` — Unread count

---

## 20. Search

Global Search provides keyboard-driven search across all workspaces and items.

**Features:**
- **Keyboard Shortcut** — `Cmd/Ctrl + Shift + F` to open
- **Scope** — Searches workspace names, keyboard shortcuts, and registered items
- **Results** — Sorted by relevance score with category labels
- **Navigation** — Click or keyboard-Enter to navigate to the result
- **Limit** — Returns up to 20 results per query

**API endpoints consumed:**
- `/api/desktop/search?q={query}` — Global search across all scopes

---

## 21. Command Palette

The Command Palette provides keyboard-driven command execution.

**Features:**
- **Keyboard Shortcut** — `Cmd/Ctrl + Shift + P` to open
- **Categories** — Commands organized by category (workspace, view, configuration, file, help)
- **Search** — Fuzzy search across command labels and descriptions
- **Shortcut Hints** — Each command displays its keyboard shortcut
- **Execution** — Select a command to execute the associated action

**Default Commands:**

| Command                | Description                          | Shortcut            |
|------------------------|--------------------------------------|---------------------|
| New Workspace          | Create a new workspace               | `Cmd/Ctrl + N`      |
| Switch Workspace       | Switch to a different workspace      |                     |
| Command Palette        | Open the command palette             | `Cmd/Ctrl + Shift + P` |
| Global Search          | Search across workspaces             | `Cmd/Ctrl + Shift + F` |
| Toggle Dark Mode       | Switch between light and dark themes |                     |
| Open File...           | Open a file dialog                   | `Cmd/Ctrl + O`      |
| Settings               | Open desktop settings                |                     |
| About                  | About AgenticOS                      |                     |

**API endpoints consumed:**
- `/api/desktop/command-palette` — List available commands

---

## 22. Keyboard Shortcuts

All keyboard shortcuts are configurable via the Settings panel.

**Default Shortcuts:**

| Shortcut                  | Action                | Category    |
|---------------------------|-----------------------|-------------|
| `Cmd/Ctrl + Shift + P`    | Command Palette       | view        |
| `Cmd/Ctrl + Shift + F`    | Global Search         | view        |
| `Cmd/Ctrl + N`            | New Workspace         | workspace   |
| `Cmd/Ctrl + W`            | Close Window          | window      |
| `Cmd/Ctrl + M`            | Minimize              | window      |
| `Cmd/Ctrl + B`            | Toggle Sidebar        | view        |
| `Cmd/Ctrl + S`            | Save                  | file        |
| `Cmd/Ctrl + Tab`          | Next Workspace        | workspace   |

**API endpoints consumed:**
- `/api/desktop/shortcuts` — List all registered shortcuts

---

## 23. View Reference

| # | View                    | File                       | Description                          |
|---|-------------------------|----------------------------|--------------------------------------|
| 1  | Desktop Overview        | `views/mission-overview.tsx` | Entry dashboard with system status   |
| 2  | Discovery Dashboard     | `views/discovery-dashboard.tsx` | Runtime discovery controls      |
| 3  | Execution Graph         | `views/execution-graph.tsx` | Task execution visualization         |
| 4  | Provider Control Center | `views/provider-control-center.tsx` | AI provider management       |
| 5  | MCP Manager             | `views/mcp-manager.tsx` | MCP server lifecycle and tools        |
| 6  | Swarm Dashboard         | `views/swarm-dashboard.tsx` | Swarm orchestration control        |
| 7  | AI Brain                | `views/ai-brain.tsx` | Live EventBus visualization           |
| 8  | Agent Constellation     | `views/agent-constellation.tsx` | Agent topology graph              |
| 9  | Workflow Studio         | `views/workflow-studio.tsx` | DAG workflow editor                  |
| 10 | Pipeline Builder        | `views/pipeline-builder.tsx` | Stage-based pipeline editor         |
| 11 | Memory Explorer         | `views/memory-explorer.tsx` | Memory system browser                |
| 12 | Plugin Marketplace      | `views/plugin-marketplace.tsx` | Plugin management                   |
| 13 | Workspace Explorer      | `views/workspace-explorer.tsx` | Workspace CRUD and layout           |
| 14 | Task Timeline           | `views/task-timeline.tsx` | Chronological task history           |
| 15 | System Monitor          | `views/system-monitor.tsx` | Diagnostics and performance          |

---

## 24. Development

### 24.1 Project Structure

```
apps/mission-control/
├── src/
│   ├── app/              # Next.js App Router pages
│   │   ├── layout.tsx    # Root layout with sidebar and navigation
│   │   ├── page.tsx      # Main page with lazy-loaded view routing
│   │   └── globals.css   # Global styles and theme variables
│   ├── components/       # Reusable UI components
│   │   ├── ui/           # Primitive UI components (buttons, inputs, panels, etc.)
│   │   ├── shell/        # Terminal shell component
│   │   ├── error-boundary.tsx
│   │   ├── monaco-editor.tsx
│   │   ├── theme-provider.tsx
│   │   └── view-skeleton.tsx
│   ├── views/            # Dashboard views (15 files, one per view)
│   ├── lib/              # Utilities and state management
│   │   ├── api.ts        # Typed REST client
│   │   ├── types.ts      # TypeScript domain types
│   │   ├── store.ts      # Zustand state store
│   │   ├── store.test.ts # Store tests
│   │   └── active-view.tsx # Active view context
│   └── next-env.d.ts
├── package.json          # Dependencies and scripts
├── tsconfig.json         # TypeScript configuration
├── tailwind.config.ts    # Tailwind CSS configuration
├── postcss.config.mjs    # PostCSS configuration
├── vitest.config.ts      # Test configuration
└── vitest.setup.ts       # Test setup
```

### 24.2 Scripts

| Command               | Description                       |
|-----------------------|-----------------------------------|
| `npm run dev`         | Start development server (port 3000) |
| `npm run build`       | Production build to `out/`        |
| `npm run start`       | Start production server           |
| `npm run lint`        | Run ESLint checks                 |
| `npm run typecheck`   | Run TypeScript type checking      |
| `npm run test`        | Run Vitest test suite             |
| `npm run test:watch`  | Run tests in watch mode           |

### 24.3 Quality Gates

All changes must pass:
```bash
npm run typecheck && npm run lint && npm run test && npm run build
```

### 24.4 Environment Variables

| Variable                  | Default                   | Description                       |
|---------------------------|---------------------------|-----------------------------------|
| `NEXT_PUBLIC_API_BASE`   | `http://localhost:8000`   | Backend API base URL              |

### 24.5 Key Dependencies

| Package          | Version   | Purpose                          |
|------------------|-----------|----------------------------------|
| next             | 15.1.6    | React framework (App Router)     |
| react            | 19.0.0    | UI library                       |
| framer-motion    | 11.18.0   | Animations and transitions       |
| lucide-react     | 0.474.0   | Icon library                     |
| reactflow        | 11.11.4   | Node-based graph visualization   |
| zustand          | 5.0.3     | State management                 |
| tailwind-merge   | 2.6.0     | Tailwind class merging           |
| clsx             | 2.1.1     | Conditional class names          |
| @monaco-editor/react | 4.7.0 | Code editor component            |
| monaco-editor    | ^0.55.1   | Code editor engine               |
| vitest           | 2.1.8     | Test framework                   |
| jsdom            | 25.0.1    | DOM environment for tests        |
