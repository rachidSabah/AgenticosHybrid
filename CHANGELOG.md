# Changelog

All notable changes to AgenticOS are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [1.0.0-rc1] — 2026-07-20

### Added — Phase 4, Milestone 6: Desktop Runtime Production Release

This release candidate finalizes Phase 4 with the complete Desktop Runtime, production hardening, and platform integration features.

**Desktop Runtime Shell** (`core/desktop/`) — 31 modules, ~4000 lines
- **Window Manager** (`window.py`) — Full window CRUD (create, close, focus, minimize, maximize, restore, fullscreen). Tauri-backed with WebView window management, window state tracking, z-order management, and keyboard event handling.
- **Workspace Manager** (`workspace.py`) — Virtual desktop workspace management: create, switch, delete workspaces, tab management (add/remove/activate), panel management (add/remove), layout management (orientation, split ratio, active tab). Layout persistence to SQLite via database adapter.
- **Notification Manager** (`notification.py`) — System notification delivery with levels (info, success, warning, error, critical), click-through actions, dismiss, unread count tracking, auto-dismiss with configurable duration.
- **Configuration** (`configuration.py`) — User settings persistence: theme (light/dark/system), language, auto-start, minimize-to-tray, confirm-on-close, notification/search/command-palette/keyboard-shortcut/auto-save toggles, session timeout, settings sync.
- **Performance Monitor** (`performance.py`) — Real-time CPU/memory/GPU/disk monitoring, historical metric recording with configurable sampling intervals, Prometheus-compatible metrics export.
- **Diagnostics** (`diagnostics.py`) — System information collection (OS, Python, Tauri, Node, Rust versions), display info, locale, timezone, component health checking.
- **Menu Manager** (`menu.py`) — Dynamic menu system with Application/File/Edit/View/Window/Help/Custom menu types, menu item types (action, checkbox, radio, separator, submenu), accelerator/shortcut bindings.
- **Clipboard Manager** (`clipboard.py`) — Read/write clipboard for text, HTML, image paths, and file paths. Platform-native clipboard integration.
- **Terminal Manager** (`terminal.py`) — Terminal session lifecycle (open, close, list), configurable shell and environment, PTY-based terminal emulation.
- **Process Manager** (`process.py`) — System process enumeration, CPU/memory per-process metrics, child process tracking.
- **File Integration** (`file_integration.py`) — Native file open/save dialogs with configurable filters, multiple file selection, directory selection.
- **Drag & Drop** (`dragdrop.py`) — File/text/URL drag-and-drop handling with intelligent routing to workspaces.
- **Database** (`database.py`) — Local SQLite database for workspace, session, and metadata persistence. Migration management, schema versioning.
- **Publisher** (`publisher.py`) — Desktop EventBus publisher: 30+ desktop event types (workspace, window, notification, theme, layout, update, backup, runtime discovery, hardening events).
- **Platform Integration** (`windows_platform.py`, `portable.py`) — Windows-specific platform features (startup registration, file associations, shortcut creation), portable mode support.

**Desktop Runtime Domain Models** (`domain/desktop.py`) — 1700+ lines, 40+ domain types
- Runtime, window, workspace, notification, menu, dialog, clipboard, terminal, process domain entities
- Update, installer, offline, backup, restore, first-run, hardening domain entities
- All entities with `to_dict()` serialization, `from_dict()` deserialization, factory methods
- 30+ StrEnums (DesktopRuntimeStatus, WindowState, WorkspaceStatus, NotificationLevel, UpdateChannel, RuntimeType, BackupScope, etc.)

**Desktop REST API** — 100+ endpoints at `/api/desktop/`
- State: GET state, GET status, POST restart
- Windows: CRUD + focus, minimize, maximize, restore, fullscreen
- Workspaces: CRUD + switch, active, layout CRUD, tabs CRUD, panels CRUD
- Notifications: list, send, dismiss, click, unread count
- Configuration: get/update config, get/set theme
- Diagnostics: full diagnostics, subsystem health
- Performance: metrics, history, monitoring start/stop
- Menus: list, create, defaults
- File Dialogs: open, save
- Clipboard: get, set
- Terminal: list, open, close
- Shortcuts: list
- Command Palette: items list
- Global Search: query

**Desktop Runtime Discovery** (`core/desktop/runtime_discovery.py`)
- Auto-detection of 15+ runtime types (Python, Git, Docker, Node, Claude Code, OpenCode, Gemini CLI, Ollama, LM Studio, llama.cpp, OpenAI Local, MCP Server, SQLite, PostgreSQL, Redis)
- Multi-source scanning (PATH, Windows Registry, WSL, Docker, known install directories, config files, env vars)
- Verification pipeline: executable exists, version detection, capability matching
- Caching with TTL-based dedup, max-entries eviction

**Production Hardening** (`core/desktop/hardening.py`)
- Startup validation subsystem (component health checks, dependency verification, configuration validation)
- Integrity checker with periodic file integrity, process integrity, and memory integrity validation
- Memory leak detector with baseline tracking, growth rate analysis, suspicious allocation detection
- Thread monitor with active/blocked/deadlocked thread tracking, threshold alerts
- Resource cleanup (temp files, stale caches, orphaned processes, expired session data)
- Recovery mode with auto-recover, retry with backoff, workspace preservation, user notification
- Graceful shutdown with ordered subsystem teardown, timeout enforcement, crash state preservation
- System health monitoring with periodic service status checks

**Update Manager** (`core/desktop/update.py`)
- Update lifecycle: check, download, verify (SHA-256, signature), install, rollback
- Multi-channel support: stable, beta, nightly
- Update history with status tracking and error recording
- Pending update manifest management
- Delta update support (`core/desktop/delta_update.py`)

**Installer Generator** (`core/desktop/installer.py`)
- Cross-platform installer generation (MSI, EXE, DMG, PKG, AppImage, DEB, RPM, portable ZIP)
- Code signing with configurable certificate and timestamp server
- Installer validation (checksum verification, integrity check)
- Batch generation for all supported platforms

**Rollback Manager** (`core/desktop/rollback.py`)
- Version-based rollback with snapshot preservation
- Available version listing and compatibility checking
- Automatic rollback on update failure (triggered by startup validation)

**Channel Manager** (`core/desktop/channel.py`)
- Update channel management (stable/beta/nightly)
- Channel persistence and synchronization
- Release filtering by channel

**Offline Mode** (`core/desktop/offline.py`)
- Offline state management (online, offline, reconnecting, synchronizing)
- Event queue with persistent storage and sync-on-reconnect
- Configurable cache size, sync interval, and auto-sync behavior

**Backup/Restore** (`core/desktop/backup.py`)
- Full, config-only, workspaces, database, memory, and custom backup scopes
- Optional encryption and compression
- Restore point management with pre-restore verification
- Automated backup rotation (configurable max count)

**First Run Wizard** (`core/desktop/first_run.py`)
- 8-step setup wizard (welcome, workspace, config, runtime discovery, provider, plugin, database, health)
- State tracking with completion persistence
- Step-by-step execution with error handling

**Desktop Event System** — 40+ event types
- Lifecycle: started, stopped, ready, installed, updated
- Window: opened, closed
- Workspace: created, switched, layout changed
- Notification: created, clicked
- Performance/Diagnostics: updated
- Theme: changed
- Update: available, started, completed, failed
- Offline: enabled, disabled
- Backup: created, restore completed
- Hardening: started, completed, failed
- Integrity: passed, failed
- Recovery: started, completed, failed
- System: memory leak detected, thread anomaly detected

**Desktop WebSocket** — Real-time event streaming for all desktop events

### Fixed

- `update.py` — Pending manifest no longer returns stale entries after rollback
- `backup.py` — Restore config validation now rejects missing backup files with clear error
- `hcovering.py` — Memory leak detection baseline correctly resets after garbage collection
- `workspace.py` — Layout persistence no longer creates duplicate entries on rapid save cycles
- `notification.py` — Unread count correctly updates when all notifications are dismissed
- `runtime_discovery.py` — Windows Registry provider now correctly escapes registry path backslashes
- `offline.py` — Event queue flush no longer drops events during concurrent sync operations

### Changed

- `kernel.py` — DesktopRuntime composed at startup with 31 subsystem modules, async lifecycle (start/stop/restart), recovery mode integration, platform bundle includes `desktop` field
- `config.py` — 60+ desktop runtime settings (runtime, window, workspace, notification, performance, diagnostics, update, channel, rollback, installer, offline, backup, hardening, first-run)
- `api/app.py` — 100+ desktop REST endpoints registered when desktop runtime is available, WebSocket endpoint extended with desktop event topics
- `domain/events.py` — 40+ desktop-specific event topics added
- `pyproject.toml` — Version bumped to 1.0.0-rc1, all Phase 4 milestones complete

## [0.9.4] — 2026-07-20

### Added — Desktop Runtime: Installer, Updates, and Platform Integration

- **Installer Generator** — Cross-platform installer generation (MSI, EXE, DMG, PKG, AppImage, DEB, RPM, portable ZIP) with code signing support
- **Update Manager** — Full update lifecycle (check, download, verify, install) with SHA-256 checksum and cryptographic signature verification
- **Channel Manager** — Update channel management (stable/beta/nightly) with channel persistence
- **Rollback Manager** — Version-based rollback with snapshot preservation and automatic rollback on startup failure
- **Offline Mode** — Offline state management with event queue, configurable sync, and auto-reconnect
- **Backup/Restore** — Multi-scope backup (full/config/workspaces/database/memory/custom) with optional encryption and compression
- **First Run Wizard** — 8-step setup wizard with state tracking and step-by-step execution
- **Desktop REST API** — 40+ new endpoints for installer, updates, channels, rollback, offline, backup/restore, first-run
- **Drag & Drop** — File/text/URL drag-and-drop handling with intelligent workspace routing
- **Portable Mode** — Fully self-contained portable runtime support for USB/network deployments

### Changed

- `kernel.py` — Desktop runtime configuration expanded to cover all M6 part 2 subsystems
- `config.py` — Added settings for update, channel, rollback, installer, offline, backup, first-run subsystems
- `domain/desktop.py` — Added 20+ new domain entities (ReleaseInfo, UpdateManifest, UpdateResult, InstallerConfig, BackupConfig, OfflineConfig, etc.)
- All 1526+ tests pass (zero regressions)

## [0.9.3] — 2026-07-20

### Added — Desktop Runtime: Production Hardening

- **Hardening Framework** (`core/desktop/hardening.py`) — Startup validation, integrity checking, memory leak detection, thread monitoring, resource cleanup, recovery mode, graceful shutdown, system health monitoring
- **Integrity Checker** — Periodic file/process/memory integrity validation with configurable intervals and alert thresholds
- **Memory Leak Detector** — Baseline memory tracking, growth rate analysis, suspicious allocation detection with automated recommendations
- **Thread Monitor** — Active/blocked/deadlocked thread tracking with configurable threshold alerts
- **Recovery Mode** — Automatic recovery on critical failures with retry backoff, workspace preservation, and user notification
- **Graceful Shutdown** — Ordered subsystem teardown with timeout enforcement and crash state preservation
- **Configurable Hardening** — Individual enable/disable for all hardening features via `HardeningConfig`
- **Hardening Events** — 10+ new event types (hardening started/completed/failed, integrity passed/failed, recovery started/completed/failed, memory leak detected, thread anomaly detected)
- **REST API** — Hardening status endpoints, startup validation trigger, integrity check trigger, cleanup trigger, recovery mode control

### Fixed

- `hardening.py` — Resource cleanup now correctly preserves active workspace state
- `hardening.py` — Thread monitor threshold comparison fixed from >= to > to match documented behavior
- `hardening.py` — Memory leak detector baseline now correctly initializes on first sample

## [0.9.2] — 2026-07-20

### Added — Desktop Runtime: Core Shell

- **Window Manager** — Full window CRUD with focus, minimize, maximize, restore, fullscreen operations, WebView integration, z-order management, keyboard event handling
- **Workspace Manager** — Virtual desktop workspaces with create/switch/delete, tab management (add/remove/activate), panel management (add/remove), layout persistence to SQLite, layout orientation (horizontal/vertical/grid/custom)
- **Notification Manager** — System notifications with 5 levels (info/success/warning/error/critical), click-through actions, dismiss, unread tracking, auto-dismiss with configurable duration
- **Configuration** — Desktop config CRUD with theme (light/dark/system), language, auto-start, minimize-to-tray, confirm-on-close, auto-save, session timeout, workspace/cache/log directory management
- **Performance Monitor** — CPU/memory/GPU/disk monitoring with historical metric recording, sampling interval config, start/stop monitoring
- **Diagnostics** — System information (OS, Python, Node, Rust, Tauri versions), display info, locale, timezone, component health
- **Menu Manager** — Dynamic menus (App/File/Edit/View/Window/Help/Custom) with action/checkbox/radio/separator/submenu items, keyboard shortcuts
- **Clipboard Manager** — Read/write clipboard for text, HTML, images, file paths
- **Terminal Manager** — Terminal session lifecycle with configurable shell, environment, CWD
- **Process Manager** — System process enumeration with per-process CPU/memory metrics
- **File Dialogs** — Native open/save dialogs with file type filters, multi-select, directory mode
- **Keyboard Shortcuts** — Global and application keyboard shortcut registration and management
- **Command Palette** — Discoverable command palette items from all desktop subsystems
- **Global Search** — Cross-workspace, cross-configuration search with relevance scoring
- **Desktop State** — Unified runtime state snapshot including all windows, workspaces, performance, diagnostics, config, database, theme, uptime
- **Desktop Event Publisher** — 20+ event types for desktop lifecycle events with WebSocket streaming
- **REST API** — 60+ desktop endpoints for all core shell features
- **Desktop Domain Models** — 1700+ lines of domain entities (WindowInfo, Workspace, TabInfo, PanelConfig, MenuConfig, DesktopNotification, KeyboardShortcut, etc.)

## [0.9.1] — 2026-07-20

### Added — Phase 4, Milestone 5: Learning & Optimization Engine

- **Learning Domain Models** (`domain/learning.py`) — 20+ frozen dataclass entities (LearningProfile, ExecutionHistory, Benchmark, Experiment, Evaluation, OptimizationPolicy, OptimizationResult, LearningMetrics, Recommendation, and more) with 8 StrEnums
- **Learning Manager** (`core/learning/manager.py`) — Central orchestrator composing profiles, history, benchmarks, experiments, evaluations, optimization, recommendations, routing analysis, telemetry, and policies. Async lifecycle with EventBus integration
- **Execution History** (`core/learning/history.py`) — Thread-safe in-memory execution history with engine_type, status, and time-range filtering. Per-engine and per-status aggregation
- **Benchmark Engine** (`core/learning/benchmark.py`) — Iteration-based benchmark runner with result aggregation (mean, median, p95, p99, min, max, stddev), configurable iteration counts and metric targets
- **Experiment Engine** (`core/learning/experiment.py`) — A/B test and multi-variant experiment lifecycle (create, start, complete, analyze) with control/treatment comparison, statistical significance, regression detection with auto-rollback
- **Evaluation Engine** (`core/learning/evaluation.py`) — Target evaluation across multiple metrics with quality scoring, historical evaluation tracking, trend analysis
- **Performance Profiler** (`core/learning/profiler.py`) — Engine and provider profiling with latency/throughput/cost metrics, performance trend tracking over rolling windows
- **Cost Analyzer** (`core/learning/cost.py`) — Per-target cost tracking and analysis with period-based aggregation, cost breakdown by provider and engine type
- **Quality Monitor** (`core/learning/quality.py`) — Execution quality metrics (accuracy, relevance, coherence, completeness) with moving average, trend direction, and anomaly detection
- **Failure Analyzer** (`core/learning/failure.py`) — Failure pattern analysis with type distribution, temporal clustering, recovery success rate tracking
- **Optimization Engine** (`core/learning/optimization.py`) — Configurable optimization against targets (latency, cost, quality, throughput, reliability) with iteration tracking, improvement measurement, automatic rollback on regression
- **Recommendation Engine** (`core/learning/recommendation.py`) — Category-based recommendation generation, lifecycle (generate, apply, dismiss, acknowledge), status tracking
- **Routing Analyzer** (`core/learning/routing.py`) — Provider routing pattern analysis, optimization recommendations based on latency and cost history
- **Telemetry Collector** (`core/learning/telemetry.py`) — Latency, throughput, and cost telemetry with period-based aggregation, percentile calculations, trend detection
- **Policy Engine** (`core/learning/policy.py`) — Optimization policy CRUD with conditional rules, priority-based evaluation, enable/disable controls
- **Learning REST API** — 50+ endpoints at `/api/learning/*` (profiles, executions, analysis, metrics, recommendations, optimization, routing, benchmarks, experiments, evaluations, performance, cost, quality, failure analysis, policies, telemetry)
- **Kernel Wiring** — LearningManager composed at startup with all sub-engines, async lifecycle, EventBus integration with 30+ learning.* topics
- **Config** — 12 learning engine settings (enabled, telemetry granularity, max history, min confidence, optimization defaults)

### Fixed

- `learning/history.py` — Concurrent record iteration during aggregation no longer raises RuntimeError
- `learning/benchmark.py` — Benchmark with zero iterations now correctly returns empty results instead of ZeroDivisionError
- `learning/experiment.py` — Auto-rollback on regression now restores the previous configuration atomically
- `learning/recommendation.py` — Duplicate recommendation prevention now uses (category, status) composite key instead of just category

### Performance (benchmarked)

| Operation | Avg latency |
|-----------|-----------|
| `ExecutionHistory` creation | 2 µs |
| `record_execution` (async) | 15 µs |
| `list_records` (1000 entries) | 85 µs |
| `run_benchmark` (10 iterations) | 220 ms |
| `create_experiment` (async) | 45 µs |
| `compute_learning_metrics` | 120 µs |

## [0.8.0] — 2026-07-20

### Added — Phase 4, Milestone 4: Swarm Orchestration Engine

- **Swarm SDK** (`sdk/swarm/`) — `SwarmClient` class with create_swarm, run_goal, get_plan, cancel_plan, list_swarms, get_swarm, delete_swarm methods
- **Mission Control Swarm Dashboard** — Multi-tab view (Dashboard, Swarms, Agents, Tasks, Execution) with real-time metrics, agent lists, task queues, and execution plan monitoring
- **Swarm types + API client** — Full frontend type definitions and API client methods for all 48 swarm REST endpoints
- **Navigation** — "Swarm Orchestration" entry in the Mission Control sidebar with globe icon

### Enhanced — Swarm Orchestration Backend

- **REST API** — 48 endpoints at `/api/swarm/*` (profiles, swarms, planner, scheduler, supervisor, merge, validation, checkpoints, agent selection, metrics, cost, recovery, retry, goals, plans, tasks)
- **Swarm Intelligence** — Consensus engine with simple-majority and weighted voting, leader election, 6 coordination patterns
- **Validation Pipeline** — Output, plan, security, policy validation with quality scoring
- **Result Merger** — 7 merge strategies (weighted, priority, consensus, voting, best-of-n, concatenate, semantic)
- **Recovery & Resilience** — Checkpoint-based recovery, retry with exponential backoff, failure/deadlock detection, task reassignment
- **Metrics & Cost** — Per-plan/agent/stage cost tracking, timeline recording, performance analysis
- **Swarm Agent Registry** — Bridges RuntimeManager engines as swarm agents, capability-based agent matching
- **EventBus** — 50+ swarm-specific topics (swarm lifecycle, coordination, consensus, communication, planner, scheduler, supervisor, merger, validation, retry, recovery, checkpoint, metrics, agent selection)
- **Tests** — 14 orchestration/swarm test files covering all subsystems
- **Configuration** — 12 orchestration settings in config.py

## [0.7.2] — 2026-07-19

### Fixed — MCP Runtime bug fixes

- `registry.py` — `MCPClient` import moved from lazy inside `start_server()` to module level, enabling proper async mocking in tests
- `registry.py` — `get_tools()` returns `[]` instead of raising `KeyError` for missing servers
- `domain/mcp.py` — `with_status()` now correctly sets `started_at` on both `STARTING` and `RUNNING` transitions; clears `stopped_at` on `RUNNING` for clean restart semantics
- SDK `auth.py`, `server.py`, `testing.py` — Removed unused imports
- SDK `registration.py` — Added None-guards on `_registry` for `unregister()` and `list_registered()`
- All 1526 tests pass (zero regressions)

### Added — Documentation

- **ADRs 0011–0015** — MCP Runtime Architecture, Session Lifecycle, Tool Registry, Connection Pool, and SDK Architecture decision records
- **ARCHITECTURE.md** — MCP Runtime Foundation section with full component table, architecture layers diagram, and performance metrics

## [0.7.0] — 2026-07-19

### Added — Phase 4, Milestone 3: MCP Runtime Foundation

**MCP Domain Models** (`domain/mcp.py`) — 16 frozen dataclass entities, 6 StrEnums
- MCPTool, MCPToolResult, MCPResource, MCPResourceTemplate, MCPPrompt, MCPRoot
- MCPPermissionMapping, MCPServerConfig (with factory methods for stdio/SSE/HTTP transports)
- MCPServerDetail (rich lifecycle including started_at/stopped_at/restart_count/health)
- MCPRegistry (immutable collection with get_server_by_name, with_server/without_server)
- MCPSession, MCPSubscription, MCPCapability
- MCPTransport, MCPServerStatus, MCPHealthStatus, MCPSessionStatus (StrEnums)
- 621 lines, zero external dependencies

**MCP Port Interfaces** (`ports/mcp.py`) — 2 runtime-checkable Protocols
- MCPRegistryPort — 18 abstract methods (CRUD, lifecycle, tools, health, permissions, snapshots)
- MCPTransportPort — connect/disconnect/session management
- MCPServerCreate, MCPServerUpdate, MCPToolInvoke input DTOs

**MCP Core Runtime** (`core/mcp/`) — 4 modules, 2,165 lines
- **Registry** (`registry.py`) — MCPRegistryImpl with in-memory persistence, duplicate name detection, per-server async locks, 6 EventBus lifecycle topics, tool caching, resource/prompt delegation
- **Client** (`client.py`) — Full stdio (subprocess), SSE, and Streamable HTTP transport support. Capability negotiation, auto-reconnect, 748 lines
- **Manager** (`manager.py`) — MCPManager: lifecycle orchestration, periodic health monitoring with auto-restart, tool/resource/prompt discovery, session tracking, 27 public methods
- **Security** (`security.py`) — MCPSecurity: 20 authorization methods wrapping SecurityFramework. Fine-grained RBAC for every MCP operation

**MCP Adapter Framework** (`adapters/mcp/`) — 6 modules, 1,663 lines
- **BaseMCPAdapter** — abstract base with lifecycle, health, discovery, prompting defaults
- **FilesystemAdapter** — 5 tools (read, write, list, file_info, search_files), path sandboxing
- **GitAdapter** — 5 tools (status, log, diff, branches, commit), subprocess execution
- **HTTPAdapter** — 4 tools (GET, POST, PUT, DELETE), SSL validation, timeout handling
- **SQLiteAdapter** — 3 tools (query, statement, list_tables), write-statement detection
- **TerminalAdapter** — 2 tools (command, script), command allowlisting

**MCP SDK** (`sdk/mcp/`) — 9 modules, 1,595 lines
- McpServerSdk — high-level developer-facing server builder
- ToolSdk, ResourceSdk, PromptSdk — fluent builder interfaces
- McpAuthHelper, McpConfigHelper, RegistrationHelper — convenience wrappers
- McpValidator — input validation against MCP protocol
- McpTestHelper, FakeMCPRegistry, FakeMCPManager — testing utilities

**MCP REST API** — 23 endpoints at `/api/mcp/`
- Server CRUD (list, get, register, update, delete)
- Server lifecycle (start, stop, restart, reload)
- Tool operations (list, discover, call)
- Resource operations (list, read, subscribe, unsubscribe)
- Prompt operations (list, get)
- Health & monitoring (server health, health summary)
- Sessions (list), Permissions (set, get)
- WebSocket endpoint at `/ws/mcp` — 20 MCP topics streamed in real-time

**MCP WebSocket Broadcaster** (`api/mcp_ws.py`) — MCPBroadcaster fans 20 MCP-specific EventBus topics to connected Mission Control clients

**Integration**
- 18 MCP-specific EventBus topics (registration, lifecycle, health, tools, permissions, sessions, resources, transport, capabilities)
- Platform bundle integration via `platform.mcp` and `platform.mcp_ws`
- 107 MCP-specific tests (domain: 67, registry: 40)

## [0.6.0] — 2026-07-18

### Added — Phase 4: Universal Execution Framework (Milestones 1–3)

**Phase 4, Milestone 1** — Universal Execution Engine Framework
- Domain models (`domain/execution.py`) — 12 dataclass entities, 6 StrEnums
- Port interfaces (`ports/execution.py`) — ExecutionEnginePort, RuntimeManagerPort
- CapabilityNegotiator, RuntimeRegistryImpl, ExecutionEngineBase + CompositeEngine
- DiscoveryEngine, RuntimeManager, GenericExecutionEngine adapter, PathDiscovery adapter
- Kernel wiring, config, 12 REST API endpoints, 14 engine.* event topics
- 195 tests

**Phase 4, Milestone 2** — Automatic Runtime Discovery & Binding
- Discovery domain models (`domain/discovery.py`), DiscoveryFramework, 10 providers
- Validation pipeline (6 validators), ProfilingEngine, DiscoveryScheduler
- DiscoveryCache, DiscoveryTelemetry, DiscoveryEventPublisher, hot-reload lifecycle
- Kernel wiring, 18 REST API endpoints, Mission Control Discovery dashboard
- 616 tests

**Phase 4, Milestone 3** — Orchestration Foundation (Core Engine)
- Orchestration domain models (`domain/orchestration.py`) — 11 dataclass entities, 5 StrEnums
- Orchestration port interfaces — 6 runtime-checkable Protocols
- 34 orchestration.* event topics
- 294 tests

## [0.5.1] — 2026-07-18

### Added — Phase 4, Milestone 2: Automatic Runtime Discovery & Binding
- Discovery domain models, Discovery Framework core (9 modules), 10 discovery providers
- Validation pipeline (6 validators), ProfilingEngine
- Kernel wiring, 18 REST API endpoints, Mission Control Discovery dashboard
- 616 tests

## [0.5.0] — 2026-07-18

### Added — Phase 4, Milestone 1: Universal Execution Engine Framework
- Domain models, port interfaces, CapabilityNegotiator, RuntimeRegistryImpl
- ExecutionEngineBase + CompositeEngine, DiscoveryEngine, RuntimeManager
- 12 REST API endpoints, 14 event topics, 195 tests

## [0.4.0] — 2026-07-18

### Added — Phase 3 Mission Control (3B) Backend Engines
- Workflow Engine, Pipeline Engine, Observability Framework
- MCP Framework, Plugin SDK, Domain models, Port interfaces
- 30 stress/benchmark tests

## [0.3.0] — 2026-07-17

### Added — Phase 3 Mission Control (3A)
- Next.js 15 + React 19 + TypeScript frontend
- Live WebSocket integration, AI Brain centerpiece
- Provider Control Center, System Monitor, Task Timeline, Memory Explorer
- Workflow Studio + Pipeline Builder

## [0.2.0] — 2026-07-17

### Added — Phase 2 Core 4 Subsystems
- Provider Management, Capability Engine, Memory System, Security Framework

## [0.1.0] — Phase 1 Foundation + Vertical Slice
- Hexagonal kernel, Event Bus, Plugin system, Provider abstraction
