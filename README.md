# AgenticOS v1.0.0-rc1

A **desktop operating system for AI agents** that lets non-technical users install, run, and use local AI models, MCP tools, and plugins without ever touching a terminal.

[GitHub](https://github.com/rachidSabah/AgenticOS) | [Changelog](CHANGELOG.md) | [Architecture](ARCHITECTURE.md) | [Security](SECURITY.md) | [Roadmap](ROADMAP.md)

---

## Overview

AgenticOS is a complete desktop environment purpose-built for running AI agents locally. It replaces the need for command-line tooling, manual Python environment setup, and complex configuration with a polished native application that works out of the box.

Whether you want to run local LLMs via Ollama, connect to cloud providers like Anthropic or OpenAI, use MCP (Model Context Protocol) tools, or orchestrate multi-agent swarms, AgenticOS manages every aspect of the lifecycle — installation, configuration, runtime discovery, updates, and diagnostics — through a graphical interface.

Built on a hexagonal (clean) architecture with an event bus at its core, AgenticOS is modular, observable, and secure by construction. It runs on Windows, Linux, and macOS, and is fully containerizable for server deployments.

## Features

- **Desktop Runtime** — A native Tauri v2 application with native windows, menus, system tray, notifications, keyboard shortcuts, clipboard integration, drag-and-drop, and file associations.
- **Mission Control** — An immersive Next.js 15 dashboard with WebSocket-driven real-time views for every subsystem.
- **Runtime Discovery** — Automatic detection of Python, Node.js, Docker, Ollama, LM Studio, llama.cpp, Git, WSL, VS Code, JetBrains, and other runtimes on your system.
- **Automatic Updates** — Checks GitHub releases, downloads, verifies checksums, installs, and supports rollback for failed updates across stable, beta, and nightly channels.
- **Offline Mode** — Full functionality without internet; events are queued locally and auto-synced when connectivity returns.
- **Plugin System** — Extend AgenticOS with third-party plugins for agents, tools, providers, MCP servers, workflows, and pipeline stages.
- **MCP Support** — Full Model Context Protocol runtime with 3 transport protocols (stdio, SSE, Streamable HTTP) and 5 built-in adapters (filesystem, git, HTTP, SQLite, terminal).
- **Workspace Management** — Multiple named workspaces with tabs, panels, layouts, and persistent state.
- **Provider Management** — Multi-provider catalog with encrypted API key vault, health monitoring, cost tracking, rate limiting, and latency/cost/round-robin routing with failover.
- **Capability Engine** — Compose agents from 11 built-in capabilities; sensitive operations require human approval.
- **Memory System** — Scoped memory (working, conversation, project, shared, long-term) with lexical search, semantic recall, and knowledge graph relations.
- **Security Framework** — Role-based access control (deny-by-default), workspace isolation, approval gate, and append-only audit log.
- **Workflow Engine** — DAG-based execution with versioning, replay, approval gates, and topological sort.
- **Pipeline Engine** — Stage-based execution with scheduling, retry policies, rollback, and parallel stages.
- **Swarm Orchestration** — Multi-agent coordination with 6 patterns (sequential, parallel, fan-out, fan-in, hierarchical, voting), goal decomposition, and fault-tolerant execution.
- **Learning & Optimization** — Performance tracking, model selection, prompt optimization, routing optimization, and cost analysis.
- **Diagnostics** — System health checks, integrity verification, memory leak detection, thread monitoring, and performance metrics.
- **Portable Mode** — Run AgenticOS from a USB drive without installation.

## Architecture

AgenticOS is built on a strict **hexagonal (clean) architecture**. Business logic depends on interfaces (ports); concrete infrastructure lives behind those ports as adapters. The composition root (`kernel.py`) is the only place that knows about concrete classes.

```
User / Mission Control / CLI
      │  ports (interfaces)
      ▼
┌────────────────────────────────────────────┐
│  API (FastAPI) — REST + WebSocket           │
└───────────────┬────────────────────────────┘
                │
   ┌────────────┼──────────────────────────┐
   │  CORE       │ orchestrator, registry,   │
   │            │ scheduler, health,         │
   │            │ recovery, providers,       │
   │            │ capability, memory,        │
   │            │ security, mcp, swarm,      │
   │            │ learning                   │
   ├────────────┼──────────────────────────┤
   │  DOMAIN    │ Pydantic v2 entities:      │
   │            │ Agent, Task, Provider,     │
   │            │ Model, MCP, Orchestration  │
   ├────────────┼──────────────────────────┤
   │  PORTS     │ EventBus, ProviderAdapter, │
   │            │ Plugin, + all subsystem    │
   │            │ interfaces (Protocol)      │
   ├────────────┼──────────────────────────┤
   │  ADAPTERS  │ bus (local/redis/nats),    │
   │            │ providers, MCP, plugins,   │
   │            │ memory, security           │
   └────────────┴──────────────────────────┘
```

**Event Bus** — One abstract port, three interchangeable adapters:
- `LocalBus` — in-process asyncio (dev/CI, zero infrastructure)
- `RedisStreamsBus` — Redis Streams (production, persistent, replayable)
- `NatsJetStreamBus` — NATS JetStream (production alt, strong routing)

Every bus message is wrapped in an `EventEnvelope` (id, type, source, timestamp, topic, payload). Topics are centralized in `domain/events.py`.

**Desktop Runtime** — The desktop runtime layer (Phase 4, M6) adds native OS integration via Tauri v2: windows, workspaces, menus, notifications, system tray, keyboard shortcuts, clipboard, file drag-and-drop, terminal integration, and process management. All desktop subsystems communicate through the same EventBus.

## Quick Start

The fastest way to try AgenticOS:

1. **Download** the installer for your platform from the [GitHub Releases](https://github.com/rachidSabah/AgenticOS/releases) page.
2. **Run** the installer and launch AgenticOS.
3. **Use** the Mission Control dashboard at the automatically opened window.

That's it. No terminal, no package managers, no configuration files.

## Windows Installation

### Requirements

- Windows 10 22H2 or later (Windows 11 recommended)
- 8 GB RAM (16 GB recommended)
- WebView2 Runtime (installed automatically with the app on Windows 11; available via Windows Update on Windows 10)
- 1 GB free disk space

### Steps

1. Download the latest `AgenticOS-Setup-x64.exe` or `AgenticOS-Setup-x64.msi` from the [Releases page](https://github.com/rachidSabah/AgenticOS/releases).
2. Double-click the installer and follow the on-screen instructions.
3. AgenticOS launches automatically after installation.

A portable ZIP version (`AgenticOS-Portable-x64.zip`) is also available — extract and run `AgenticOS.exe` with no installation required.

## Linux Installation

AgenticOS is available as an AppImage (universal), DEB (Debian/Ubuntu), and RPM (Fedora/RHEL).

### Requirements

- glibc 2.28+
- WebKit2GTK 4.1+
- 8 GB RAM (16 GB recommended)

### AppImage (all distributions)

```bash
chmod +x AgenticOS-x86_64.AppImage
./AgenticOS-x86_64.AppImage
```

### DEB (Debian, Ubuntu, Mint)

```bash
sudo apt install -y ./agentic-os_1.0.0-rc1_amd64.deb
agentic-os
```

### RPM (Fedora, RHEL, Rocky Linux)

```bash
sudo dnf install -y ./agentic-os-1.0.0-rc1.x86_64.rpm
agentic-os
```

### Docker (any distribution)

```bash
docker run -d -p 8000:8000 ghcr.io/rachidsabah/agentic-os:latest
# Open http://localhost:8000
```

## macOS Installation

### Requirements

- macOS 12 (Monterey) or later
- 8 GB RAM (16 GB recommended)

### DMG

1. Download `AgenticOS-x64.dmg` or `AgenticOS-arm64.dmg` for Apple Silicon.
2. Open the DMG and drag AgenticOS to your Applications folder.
3. Launch AgenticOS from Applications.

### PKG

```bash
sudo installer -pkg agentic-os-1.0.0-rc1.pkg -target /
open /Applications/AgenticOS.app
```

## Offline Mode

AgenticOS is designed to work fully offline. When no internet connection is available:

- **Local AI models** (Ollama, LM Studio, llama.cpp) continue to work without interruption.
- **Event queuing** — API calls and actions are queued locally as `OfflineEvent` objects.
- **Auto-sync** — When connectivity is restored, queued events are automatically replayed and synced.
- **Cached auth tokens** — API keys and tokens are cached securely for offline use.
- **Configurable** — Cache size, sync interval, and auto-sync behavior are adjustable in Settings.

The offline state machine transitions through `ONLINE → OFFLINE → RECONNECTING → SYNCHRONIZING → ONLINE` with appropriate UI indicators in Mission Control.

## Mission Control

Mission Control is the primary user interface — a real-time, WebSocket-driven dashboard built with Next.js 15, React 19, TypeScript, and TailwindCSS.

### 15+ Built-in Views

| View | Description |
|------|-------------|
| **Mission Overview** | At-a-glance status of all agents, tasks, and system health |
| **AI Brain** | Live neural pulse visualization reacting to EventBus events |
| **Agent Constellation** | Interactive React Flow topology of all registered agents |
| **Execution Graph** | Real-time task execution flow with status indicators |
| **Provider Control Center** | Manage AI providers, API keys, models, health, and routing |
| **Memory Explorer** | Browse, search, and manage scoped memory across agents |
| **MCP Manager** | Register, configure, and monitor MCP servers and tools |
| **Workflow Studio** | Visual DAG editor for building and executing workflows |
| **Pipeline Builder** | Visual stage-based pipeline editor with scheduling |
| **Swarm Dashboard** | Create swarms, monitor execution, and manage coordination |
| **Plugin Marketplace** | Browse, install, and manage plugins |
| **Workspace Explorer** | Manage multiple workspaces with tabs and layouts |
| **Task Timeline** | Chronological view of all task activity |
| **System Monitor** | CPU, memory, GPU, disk, and process metrics |
| **Discovery Dashboard** | View detected runtimes, run discovery scans, configure providers |

All views are backed by real REST API responses and WebSocket event streams — no fabricated data.

## Plugin Installation

Plugins extend AgenticOS with new agents, tools, providers, MCP servers, workflows, and pipeline stages.

### From the Plugin Marketplace (Mission Control)

1. Open **Plugin Marketplace** from the sidebar in Mission Control.
2. Browse or search available plugins.
3. Click **Install** on any plugin.
4. The plugin is downloaded, validated, and activated immediately.

### Manual Installation

Drop a plugin directory or `.whl` file into the plugins directory:

```
Windows: %APPDATA%/AgenticOS/plugins/
Linux:   ~/.config/AgenticOS/plugins/
macOS:   ~/Library/Application Support/AgenticOS/plugins/
```

Plugins implement the `Plugin` port (name, load, unload) and receive a `PluginContext` with agent and provider registries.

### Plugin SDK

The Plugin SDK provides TypeScript and Python base classes for building plugins:

- Agent plugins
- Tool plugins
- Provider plugins
- MCP server plugins
- Workflow node plugins
- Pipeline stage plugins

See [`PLUGIN_SDK.md`](PLUGIN_SDK.md) for the full specification.

## Runtime Discovery

Runtime Discovery automatically finds AI runtimes and developer tools installed on your system, making them available to agents without manual configuration.

### Discoverable Runtimes

| Runtime | Detection Method |
|---------|-----------------|
| Python | PATH scanning, known install directories, Windows Registry |
| Node.js | PATH scanning |
| Docker | Docker socket check, PATH scanning |
| Ollama | PATH scanning, known install directories |
| LM Studio | Known install directories, Windows Registry |
| llama.cpp | PATH scanning |
| Git | PATH scanning |
| WSL | WSL API, Windows Registry |
| VS Code | Known install directories, Windows Registry |
| JetBrains IDEs | Known install directories, Windows Registry |
| Claude Code | PATH scanning |
| OpenCode | PATH scanning |
| MCP Servers | Config file, env vars, filesystem scanning |

### How It Works

1. **Scanning** — The Discovery Framework runs 10+ discovery providers (path, registry, WSL, Docker, filesystem, config file, env var, VS Code, JetBrains, known install dirs).
2. **Validation** — Discovered runtimes are validated (executable exists, version detected, capability match, permissions).
3. **Profiling** — Each runtime is profiled for capabilities, performance, and compatibility.
4. **Registration** — Validated runtimes are automatically registered as execution engines, available for task dispatch.
5. **Hot Reload** — The discovery framework supports hot-reloading: it watches for changes and re-scans automatically.

### Manual Discovery

Trigger a scan at any time from Mission Control's Discovery Dashboard or via the API:

```bash
curl -X POST http://localhost:8000/api/discovery/scan
```

## Automatic Updates

AgenticOS checks for updates automatically and can update itself without user intervention.

### Update Channels

| Channel | Description |
|---------|-------------|
| **Stable** | Production-ready releases (default) |
| **Beta** | Release candidates for early adopters |
| **Nightly** | Latest builds from main branch |

### Update Flow

1. **Detection** — The update manager polls GitHub Releases at configurable intervals (default: every 6 hours).
2. **Download** — Updates are downloaded in the background with checksum verification (SHA-256).
3. **Verification** — Downloaded packages are cryptographically verified before installation.
4. **Installation** — Updates are applied automatically; the app restarts after installation.
5. **Rollback** — If an update fails, AgenticOS automatically rolls back to the previous version.
6. **History** — A complete update history with versions, timestamps, and status is maintained.

### Configuration

Update behavior can be configured in Settings:
- Enable/disable automatic checks
- Select update channel (stable, beta, nightly)
- Manual check for updates

## Troubleshooting

### AgenticOS won't start

- **Windows**: Ensure WebView2 Runtime is installed. Run `AgenticOS.exe --reset` to reset the configuration.
- **Linux**: Ensure WebKit2GTK 4.1+ is installed (`sudo apt install libwebkit2gtk-4.1-dev`).
- **macOS**: Ensure the app is in the Applications folder, not quarantined (`xattr -dr com.apple.quarantine /Applications/AgenticOS.app`).

### Mission Control shows "Connecting..."

- Ensure the backend is running on port 8000.
- Check firewall rules — port 8000 must be accessible to localhost.
- Restart the desktop app.

### Runtime Discovery finds nothing

- Ensure runtimes (Python, Node.js, Ollama, etc.) are installed and on PATH.
- Run a manual scan from Discovery Dashboard.
- Check the diagnostics report for system information.

### Updates fail to install

- Check internet connectivity.
- Ensure sufficient disk space.
- Try switching to a different update channel.
- Run diagnostics and check the update history for error details.

### High memory usage

- Open System Monitor in Mission Control to identify the source.
- Reduce the number of active agents or MCP servers.
- Restart the desktop runtime from Settings.

## Diagnostics

AgenticOS includes a comprehensive diagnostics system accessible from Mission Control.

### System Information

- OS name, version, architecture
- Python, Node.js, Rust, and Tauri versions
- Display resolution and monitor count
- Locale, language, and timezone

### Performance Metrics

- CPU usage (percent and per-process)
- Memory usage (used, total, percent)
- GPU name and memory
- Disk usage (free, total, percent)
- Workspace storage usage
- Process count and thread count
- Application uptime

### Health Checks

- **Startup validation** — Verifies all subsystems initialize correctly
- **Integrity checks** — Periodic validation of application files and configuration
- **Memory leak detection** — Monitors memory growth over time
- **Thread monitoring** — Detects thread deadlocks and anomalies
- **Resource cleanup** — Ensures proper cleanup on shutdown

### Running Diagnostics

From Mission Control: Open **System Monitor** and click **Run Diagnostics**.

From the CLI:

```bash
agentic-os doctor
```

From the API:

```bash
curl http://localhost:8000/api/desktop/diagnostics
```

## Development Guide

### Prerequisites

- Python 3.14+
- Node.js 18+ (22+ recommended)
- Rust 1.77+ (for Tauri desktop builds)
- MSVC Build Tools (Windows) or GCC/Clang (Linux/macOS)

### Setup

```bash
# Clone the repository
git clone https://github.com/rachidSabah/AgenticOS.git
cd AgenticOS

# Install Python dependencies
uv sync

# Install frontend dependencies
cd apps/mission-control
npm install
cd ../..

# Start the backend
uv run python -m agentic_os serve

# In another terminal, start the frontend
cd apps/mission-control
npm run dev
```

The backend API runs at `http://localhost:8000` and the frontend at `http://localhost:3000`.

### Running Tests

```bash
# Python backend tests
uv run pytest -v --tb=short

# Frontend tests
cd apps/mission-control && npm run test

# Type checking
uv run ty

# Linting
uv run ruff check && uv run ruff format --check
```

### Building

```bash
# Build the Python package
uv build

# Build the frontend
cd apps/mission-control && npm run build

# Build the desktop app (requires Tauri CLI)
cargo tauri build
```

### Project Structure

```
src/agentic_os/       # Python backend package
  domain/             # Pydantic v2 entities and value objects
  ports/              # Abstract interfaces (Protocol)
  core/               # Business logic and orchestration
  adapters/           # Concrete infrastructure implementations
  api/                # FastAPI REST + WebSocket endpoints
  sdk/                # MCP, Swarm, and Learning SDKs
  kernel.py           # Composition root
  cli.py              # CLI entrypoint
apps/mission-control/ # Next.js 15 frontend
services/             # Standalone service modules
tests/                # Python test suite
docs/                 # Documentation and ADRs
```

## API Guide

AgenticOS exposes a comprehensive REST API and WebSocket endpoint for programmatic access.

### REST API

**Base URL:** `http://localhost:8000`

#### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/healthz` | Health check |
| GET | `/metrics` | Prometheus metrics |

#### Tasks & Agents

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks` | List all tasks |
| POST | `/api/tasks` | Create a task |
| GET | `/api/agents` | List all agents |

#### Providers

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/providers` | List providers |
| GET | `/api/provider-configs` | List provider configs |
| POST | `/api/provider-configs` | Add/update provider config |
| DELETE | `/api/provider-configs/{name}` | Delete provider |
| POST | `/api/providers/{name}/api-key` | Store API key |
| POST | `/api/providers/{name}/test` | Test provider health |
| GET | `/api/models` | List models |
| POST | `/api/models` | Register a model |
| GET | `/api/provider-health` | Provider health status |
| GET | `/api/cost` | Cost report |
| POST | `/api/routing/policy` | Set routing policy |

#### MCP

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/mcp/servers` | List MCP servers |
| POST | `/api/mcp/servers` | Register MCP server |
| GET | `/api/mcp/servers/{id}` | Get server details |
| PUT | `/api/mcp/servers/{id}` | Update server |
| DELETE | `/api/mcp/servers/{id}` | Delete server |
| POST | `/api/mcp/servers/{id}/start` | Start server |
| POST | `/api/mcp/servers/{id}/stop` | Stop server |
| POST | `/api/mcp/servers/{id}/restart` | Restart server |
| GET | `/api/mcp/servers/{id}/tools` | List server tools |

#### Swarm Orchestration

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/swarm/profiles` | Create swarm profile |
| POST | `/api/swarm/planner/analyze` | Analyze a goal |
| POST | `/api/swarm/planner/plan` | Create a plan |
| POST | `/api/swarm/scheduler/schedule` | Schedule tasks |
| POST | `/api/swarm/supervisor/monitor` | Monitor execution |
| POST | `/api/swarm/merger/merge` | Merge results |
| POST | `/api/swarm/validation/validate` | Validate output |
| POST | `/api/swarm/checkpoints` | Manage checkpoints |
| GET | `/api/swarm/metrics` | Query metrics |

#### Workflows & Pipelines

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/workflows` | List/create workflows |
| PUT/DELETE | `/api/workflows/{id}` | Update/delete workflow |
| POST | `/api/workflows/{id}/execute` | Execute workflow |
| POST | `/api/workflows/{id}/replay` | Replay workflow |
| GET/POST | `/api/pipelines` | List/create pipelines |
| POST | `/api/pipelines/{id}/execute` | Execute pipeline |
| POST | `/api/pipelines/{id}/schedule` | Schedule pipeline |

#### Full reference

See the API router in `src/agentic_os/api/app.py` for the complete list of 100+ endpoints.

### WebSocket

**Endpoint:** `ws://localhost:8000/ws`

The WebSocket streams every EventBus event in real time, including:
- Task lifecycle events (created, dispatched, completed, failed)
- Agent status changes
- Provider health updates
- Memory operations
- Security authorization decisions
- MCP server lifecycle events
- Swarm orchestration events
- Desktop runtime events

All messages are JSON-formatted `EventEnvelope` objects.

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
ws.onmessage = (event) => {
  const envelope = JSON.parse(event.data);
  console.log(envelope.topic, envelope.payload);
};
```

## SDK Guide

AgenticOS includes three Python SDKs for programmatic interaction.

### MCP SDK (`sdk/mcp/`)

Build, register, and manage MCP servers programmatically.

```python
from agentic_os.sdk.mcp.server import McpServerSdk
from agentic_os.sdk.mcp.tool import ToolSdk

# Create an MCP server
server = McpServerSdk(
    name="my-server",
    transport="stdio",
    command="python",
    args=["-m", "my_mcp_server"]
)
await server.start()

# Build a tool
tool = ToolSdk(name="search", input_schema={
    "type": "object",
    "properties": {"query": {"type": "string"}}
})
```

**Modules:** `server.py`, `tool.py`, `resource.py`, `prompt.py`, `auth.py`, `config.py`, `registration.py`, `validation.py`, `testing.py`

### Learning SDK (`sdk/learning/`)

Access the Learning & Optimization Engine for performance tracking, model selection, and routing optimization.

```python
from agentic_os.sdk.learning.client import LearningClient

client = LearningClient(base_url="http://localhost:8000")
metrics = await client.get_performance_metrics()
recommendation = await client.recommend_model(task_type="coding")
```

### Swarm SDK (`sdk/swarm/`)

Create and manage multi-agent swarms.

```python
from agentic_os.sdk.swarm.client import SwarmClient

client = SwarmClient(base_url="http://localhost:8000")

# Create a swarm
swarm = await client.create_swarm(
    name="research-team",
    topology="hierarchical",
    max_agents=3
)

# Run a goal
result = await client.run_goal(
    swarm_id=swarm.id,
    goal="Research and summarize the latest AI papers"
)
```

**Available methods:** `create_swarm`, `run_goal`, `get_plan`, `cancel_plan`, `list_swarms`, `get_swarm`, `delete_swarm`

## FAQ

**Q: Do I need an internet connection to use AgenticOS?**
A: No. AgenticOS works fully offline with local AI models. Internet is only needed for cloud provider API calls, plugin downloads, and automatic updates.

**Q: Which AI providers are supported?**
A: All OpenAI-compatible APIs, Anthropic Claude, Ollama (local), LM Studio (local), llama.cpp (local), and any custom provider via the Provider SDK.

**Q: Can I use my existing Ollama models?**
A: Yes. Runtime Discovery automatically detects Ollama installations and registered models. They appear in Mission Control without any configuration.

**Q: What is the MCP (Model Context Protocol)?**
A: MCP is an open protocol that standardizes how applications provide context and tools to LLMs. AgenticOS includes a full MCP runtime with support for stdio, SSE, and Streamable HTTP transports.

**Q: Is AgenticOS free?**
A: Yes, AgenticOS is open source under the Apache 2.0 License. It is free to use, modify, and distribute.

**Q: Can I run AgenticOS on a server without a display?**
A: Yes. AgenticOS runs as a headless server via `python -m agentic_os serve` or Docker, exposing the REST API and WebSocket endpoint on port 8000.

**Q: How do I migrate from the previous version?**
A: Automatic updates handle migration. Manual backups are available via the Settings > Backup panel. Workspace data, provider configs, and plugin settings are preserved across updates.

**Q: What data does AgenticOS collect?**
A: No data is collected by default. Telemetry is opt-in and can be enabled in Settings. Update checks query GitHub Releases API for version information.

## Support

- **Documentation** — See [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md), and the `docs/` directory.
- **GitHub Issues** — Report bugs and request features at [github.com/rachidSabah/AgenticOS/issues](https://github.com/rachidSabah/AgenticOS/issues).
- **Security Issues** — Report vulnerabilities privately to security@agenticos.dev (see [SECURITY.md](SECURITY.md)).
- **Discussions** — Join the conversation on [GitHub Discussions](https://github.com/rachidSabah/AgenticOS/discussions).

## Contributing

We welcome contributions of all sizes — bug fixes, features, documentation, and testing.

### Getting Started

1. Read [CONTRIBUTING.md](CONTRIBUTING.md) and [ARCHITECTURE.md](ARCHITECTURE.md).
2. Fork the repository and create a feature branch.
3. Follow the hexagonal architecture principles: ports before implementations.
4. Write tests for all new code (unit + integration).
5. Ensure CI quality gates pass:
   ```bash
   uv run ruff check && uv run ruff format --check
   uv run ty
   uv run pytest -v --tb=short
   ```
6. Open a pull request targeting `main`.

### Commit Conventions

We use Conventional Commits:
- `feat:` — new capability or feature
- `fix:` — bug fix
- `refactor:` — no behavior change
- `docs:` — documentation only
- `test:` — test additions or changes
- `chore:` — tooling or version bumps

### Code of Conduct

All contributors must adhere to the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

AgenticOS is released under the [Apache 2.0 License](LICENSE).

Copyright (c) 2026 AgenticOS contributors. See [LICENSE](LICENSE) for the full license text.
