# Mission Control — Frontend Architecture Audit Report

**Generated:** 2026-07-21  
**Scope:** All 23 views, shell infrastructure, store, API client, types, i18n  
**Files analyzed:** 47 source files (`.ts` / `.tsx`) in `src/` + `messages/en.json`  
**TypeScript check:** ✅ Clean (0 errors via `tsc --noEmit`)

---

## Executive Summary

The frontend architecture is **solid foundationally** but has significant gaps in i18n, keyboard shortcut integration at a view level, and notification integration from views. No broken imports or compilation errors were found. The WebSocket EventBus store is well-designed and powers 16 of 23 views with live data. REST endpoints are used for all write operations and initial hydration. **TypeScript compiles clean** indicating no import resolution failures.

### Key Metrics

| Dimension | Status |
|---|---|
| TypeScript Compilation | ✅ Pass (0 errors) |
| Error Boundaries | ✅ All 23 views wrapped |
| WebSocket Store Integration | ✅ 16/23 views live |
| REST API Usage | ✅ 22/23 views |
| Console Errors (static analysis) | ⚠️ 1 diagnostic warning (lint test failure) |
| i18n Coverage | ❌ 0% (system exists but unused) |
| Theme Support | ⚠️ Partial (Monaco hardcoded dark) |
| View-level Keyboard Shortcuts | ❌ 0 views register shortcuts |
| View-level Notification Integration | ❌ 0 views push notifications |
| Command Palette Integration | ⚠️ NAV only (static) |
| Test Coverage | ⚠️ 2 test files only (store, primitives) |

---

## 1. Complete View-by-View Audit

### 1.1 Mission Overview (`mission-overview.tsx`)
- **Data Source:** REST (`api.dashboard()`) + **WebSocket EventBus** (store: events, agents, tasks, providers, connected, notifications, telemetry)
- **Store Subscriptions:** `s.events`, `s.agents`, `s.tasks`, `s.providers`, `s.connected`, `s.notifications`, `s.telemetry`
- **API Calls:** `api.dashboard()` on mount (`.then()` pattern)
- **Error Handling:** Minimal granularity — single catch on dashboard fetch
- **Error Boundary:** ✅ Yes (via page.tsx wrapper)
- **Keyboard Shortcuts:** ❌ None
- **Theme:** ✅ Respects via CSS variables
- **i18n:** ❌ Hardcoded English strings only
- **Notification Integration:** ❌ None
- **Command Palette:** ❌ No view integration

### 1.2 AI Brain (`ai-brain.tsx`)
- **Data Source:** REST (`api.missions()`, `api.mission(id)`) + **WebSocket EventBus** (store: events, telemetry, agents, memory)
- **Store Subscriptions:** `s.events`, `s.telemetry`, `s.agents`, `s.memory`, `s.connected`
- **API Calls:** REST on mount + per-mission fetch; WebSocket live pulses for activity
- **Error Handling:** Simple catch on API calls
- **Error Boundary:** ✅ Yes
- **Notes:** Uses `useShallow` selector; well-structured event pulse visualization; mission details via REST
- **i18n:** ❌

### 1.3 Agent Constellation (`agent-constellation.tsx`)
- **Data Source:** REST (`api.agents()`, `api.agentGraph()`) + **EventBus** (store: events, connected)
- **Store Subscriptions:** `s.events`, `s.connected`
- **API Calls:** REST on mount + interval polling (via `api.agents()` on event count change)
- **Error Boundary:** ✅ Yes (wrapped with `ReactFlowProvider`)
- **Framework:** ReactFlow (v11)
- **i18n:** ❌

### 1.4 Execution Graph (`execution-graph.tsx`)
- **Data Source:** REST (`api.agents()`, `api.tasks()`, `api.metrics()`) + **EventBus** (store: connected, events)
- **Store Subscriptions:** `s.connected`, `s.events`
- **API Calls:** REST on mount + interval polling for task updates
- **Error Boundary:** ✅ Yes (wrapped with `ReactFlowProvider`)
- **Framework:** ReactFlow
- **i18n:** ❌

### 1.5 Swarm Dashboard (`swarm-dashboard.tsx`)
- **Data Source:** REST (`api.swarmPacks()`, `api.swarmPackConfig()`, swarm CRUD) + **EventBus** (store: events)
- **Store Subscriptions:** `s.events` (limited to pack status updates)
- **API Calls:** REST multi-fetch on mount; CRUD via dedicated API
- **Error Boundary:** ✅ Yes
- **Notes:** Inline form for pack creation; local state for canvas nodes
- **i18n:** ❌

### 1.6 Mission Orchestrator (`mission-orchestrator.tsx`)
- **Data Source:** REST (`api.missions()`, `api.missionCreate()`, etc.) + **EventBus** (store: missions, missionUpdates)
- **Store Subscriptions:** `s.missions`, `s.missionUpdates`, `s.connected`
- **API Calls:** REST fetches + re-fetch on `missionUpdates` counter change
- **Error Boundary:** ✅ Yes
- **Notes:** >1000 lines; complex state machine; uses MonacoEditor inline
- **i18n:** ❌

### 1.7 Workflow Studio (`workflow-studio.tsx`)
- **Data Source:** REST (`api.workflowList()`, `api.workflowRun()`, etc.) + **EventBus** (store: connected)
- **Store Subscriptions:** `s.connected` only
- **API Calls:** REST on mount for workflow list; CRUD via dedicated API
- **Error Boundary:** ✅ Yes (wrapped with `ReactFlowProvider`)
- **Notes:** Uses MonacoEditor for YAML; ReactFlow for graph editing
- **i18n:** ❌

### 1.8 Pipeline Builder (`pipeline-builder.tsx`)
- **Data Source:** REST (`api.pipelines()`, `api.pipelineRun()`, etc.) + **EventBus** (store: connected)
- **Store Subscriptions:** `s.connected` only
- **API Calls:** REST on mount; CRUD via dedicated API
- **Error Boundary:** ✅ Yes (wrapped with `ReactFlowProvider`)
- **Notes:** MonacoEditor for YAML; ReactFlow for node graph
- **i18n:** ❌

### 1.9 Provider Control Center (`provider-control-center.tsx`)
- **Data Source:** **WebSocket EventBus** exclusively (store: providers, connected, events)
- **Store Subscriptions:** `s.providers`, `s.connected`, `s.events`
- **API Calls:** None direct — all data derived from live EventBus stream
- **Error Boundary:** ✅ Yes
- **Notes:** Pure real-time view; no REST fallback for initial hydration
- **i18n:** ❌

### 1.10 Memory Explorer (`memory-explorer.tsx`)
- **Data Source:** Store (`s.memory`, `s.connected`) + REST (`api.searchMemory()`)
- **Store Subscriptions:** `s.memory`, `s.connected`
- **API Calls:** `api.searchMemory()` on search action
- **Error Boundary:** ✅ Yes
- **Notes:** Local state for search query and filters; store subscription for live memory updates
- **i18n:** ❌

### 1.11 Plugin Marketplace (`plugin-marketplace.tsx`)
- **Data Source:** REST (`api.plugins()`, `api.pluginDetails()`, `api.installPlugin()`, etc.) + **EventBus** (store: connected)
- **Store Subscriptions:** `s.connected`
- **API Calls:** REST on mount + action handlers
- **Error Boundary:** ✅ Yes
- **Notes:** Searchable list with install/uninstall/enable/disable actions
- **i18n:** ❌

### 1.12 MCP Manager (`mcp-manager.tsx`)
- **Data Source:** **REST exclusively** (9 sub-tabs: servers, tools, permissions, health, sessions, resources, prompts, telemetry, versions)
- **Store Subscriptions:** ❌ None
- **API Calls:** Multiple REST calls per tab (`api.mcpServers()`, `api.mcpServerTools()`, etc.)
- **Error Boundary:** ✅ Yes
- **Notes:** Pure REST view — no WebSocket live update; all data loaded on tab switch
- **i18n:** ❌

### 1.13 Workspace Explorer (`workspace-explorer.tsx`)
- **Data Source:** REST (`api.workspaceFor(agentId)`)
- **Store Subscriptions:** ❌ None
- **API Calls:** Single REST call on "Resolve" button click
- **Error Boundary:** ✅ Yes
- **Notes:** Minimal view — input + resolve button + result display; would benefit from store integration
- **i18n:** ❌

### 1.14 Task Timeline (`task-timeline.tsx`)
- **Data Source:** **WebSocket EventBus** (store: events) + raw `fetch('/api/events/recent')` for hydration
- **Store Subscriptions:** `s.events`, `s.ingest`
- **API Calls:** Raw fetch to `/api/events/recent` on mount (NOT using `api.ts` — bypasses the typed client)
- **Error Boundary:** ✅ Yes
- **⚠️ Findings:** Raw `fetch()` bypasses the typed API client (`api.ts`). This is an **architectural smell** — a class-3 finding.
- **i18n:** ❌

### 1.15 System Monitor (`system-monitor.tsx`)
- **Data Source:** REST polling (`api.performance()` every 5s) + **EventBus** (store: connected, events, performance, metrics)
- **Store Subscriptions:** `s.connected`, `s.events`, `s.performance` (via `selectMetrics` + `s.performance`)
- **API Calls:** `api.performance()` via polling hook (`usePerformancePoll`)
- **Error Boundary:** ✅ Yes
- **Notes:** Well-structured polling hook; graceful degradation with `Empty` component; performance metrics + event throughput chart
- **i18n:** ❌

### 1.16 Discovery Dashboard (`discovery-dashboard.tsx`)
- **Data Source:** REST (`api.discoveryProviders()`, `api.discoveryCache()`, `api.discoveryStats()`, etc.) + **EventBus** (store: events, connected)
- **Store Subscriptions:** `s.events`, `s.connected`
- **API Calls:** REST on mount + re-fetch on discovery-related events
- **Error Boundary:** ✅ Yes
- **Notes:** 4 sub-tabs (dashboard, history, profiles, validation); event-driven auto-reload
- **i18n:** ❌

### 1.17 Self-Healing (`self-healing.tsx`)
- **Data Source:** **EventBus** (store: events, connected, providers, agents) + REST (`api.runDiagnostics()`, `api.integrityCheck()`, `api.health()`, etc.)
- **Store Subscriptions:** `s.events`, `s.connected`, `s.providers`, `s.agents`
- **API Calls:** REST on "Run System Check" button + async repair actions
- **Error Boundary:** ✅ Yes
- **Notes:** Uses `framer-motion` for issue animations; well-structured severity classification; auto-derives health issues from event stream
- **i18n:** ❌

### 1.18 Desktop Overview (`desktop-overview.tsx`)
- **Data Source:** REST (`api.desktopState()`)
- **Store Subscriptions:** ❌ None
- **API Calls:** REST on mount + "Refresh" button
- **Error Boundary:** ✅ Yes
- **Notes:** Uses `default export` — consistent with other desktop views; all desktop views are standalone REST views
- **i18n:** ❌

### 1.19 Desktop Runtimes (`desktop-runtimes.tsx`)
- **Data Source:** REST (`api.runtimes()`, `api.runtimeEngines()`, `api.discoverRuntimes()`)
- **Store Subscriptions:** ❌ None
- **API Calls:** REST on mount + discovery action + merged runtime data
- **Error Boundary:** ✅ Yes
- **Notes:** Merges Desktop Runtimes + Runtime Engines data; shown as Phase 4/M6
- **i18n:** ❌

### 1.20 Desktop Updates (`desktop-updates.tsx`)
- **Data Source:** REST (7+ endpoints: `api.updateStatus()`, `api.channels()`, `api.updateHistory()`, etc.)
- **Store Subscriptions:** ❌ None
- **API Calls:** REST on mount (parallel independent fetches with individual try/catch) + actions (check, download, install, rollback)
- **Error Boundary:** ✅ Yes
- **Notes:** Good error isolation per REST call; inline release notes; channel switching
- **i18n:** ❌

### 1.21 Desktop Diagnostics (`desktop-diagnostics.tsx`)
- **Data Source:** REST (`api.diagnostics()`, `api.resourceUsage()`, `api.integrityCheck()`, etc.) + **EventBus** (store: connected, events, providers)
- **Store Subscriptions:** `s.connected`, `s.events`, `s.providers`
- **API Calls:** REST on mount + poll `api.resourceUsage()` every 10s when connected + manual action buttons
- **Error Boundary:** ✅ Yes
- **Notes:** Most comprehensive diagnostics view; auto-integrity-check on connect
- **i18n:** ❌

### 1.22 Desktop Offline (`desktop-offline.tsx`)
- **Data Source:** **REST exclusively** (`api.offlineState()`, `api.offlineEvents()`, `api.listBackups()`, etc.)
- **Store Subscriptions:** ❌ None
- **API Calls:** REST on mount + actions (enable, disable, sync, backup, restore)
- **Error Boundary:** ✅ Yes
- **Notes:** Queue display with sync status badges; backup creation and listing
- **i18n:** ❌

### 1.23 Desktop Settings (`desktop-settings.tsx`)
- **Data Source:** **REST exclusively** (`api.desktopConfig()`, `api.hardeningConfig()`, `api.listShortcuts()`, `api.commandPallete()`)
- **Store Subscriptions:** ❌ None
- **API Calls:** REST on mount + config updates via `api.updateDesktopConfig()` and `api.updateHardeningConfig()`
- **Error Boundary:** ✅ Yes
- **Notes:** Theme select with "light", "dark", "system" options — but ThemeProvider only supports "dark" | "light" (TypeScript type mismatch); shows keyboard shortcuts and command palette items from backend
- **i18n:** ❌

---

## 2. Cross-Cutting Concerns

### 2.1 Error Boundaries ✅
All 23 views are wrapped with `<ErrorBoundary viewName="...">` in `page.tsx`. The `withErrorBoundary` HOC exists but is unused (views use the direct wrapper approach). Every view has a named fallback skeleton.

### 2.2 i18n Coverage ❌ (CRITICAL GAP)
- **System status:** A complete i18n system exists at `lib/i18n.ts` with `t()` function and `messages/en.json` (45 lines)
- **Usage:** Zero — `t()` is **never imported or called** anywhere in the codebase
- **External dependency:** `next-intl` is in `package.json` but also unused (comment says "Replace with next-intl when full localization is needed")
- **All 23 views** use hardcoded English strings exclusively
- **Impact:** Adding localization requires changing every view

### 2.3 Theme Support ⚠️
- **✅ ThemeProvider** wraps the entire app with "dark"/"light" toggle
- **✅ TopBar** has theme toggle button (Sun/Moon icon) + keyboard shortcut (⌘T)
- **✅ DesktopSettings** shows theme selector (light/dark/system)
- **⚠️ Mismatch:** ThemeProvider type only allows "dark" | "light", but DesktopSettings offers "system" as a third option — will silently degrade
- **❌ MonacoEditor** hardcodes `theme: "vs-dark"` — ignores user's theme preference

### 2.4 Keyboard Shortcut Registration ❌
- **AppShell** registers: `⌘K` (palette toggle) + single-key navigation via NAV `hint` (e.g., "O" for overview)
- **ShortcutsModal** displays 18 documented shortcuts in a categorized UI
- **Shortcuts list defined in NAV:** All 23 views have a single-key `hint` binding
- **❌ No view** registers its own keyboard shortcuts — all shortcuts are global AppShell level
- **❌ No shortcut** is registered for view-specific actions (e.g., "Invoke" in MCP tools, "Run Check" in Self-Healing)
- View-level shortcuts could use the `useEffect` + `addEventListener("keydown")` pattern, but none do

### 2.5 Notification Integration ❌
- **NotificationsPopover** reads `s.notifications` from the store and displays them
- **Store** auto-generates notifications from ALL EventBus events in `ingest()`
- **❌ No view** explicitly pushes notifications via the store
- **❌ No view** can trigger context-specific notifications (e.g., "Workflow execution completed")
- The store's `ingest()` handles event-to-notification automatically, but views have no mechanism for action-result feedback via notifications
- Pattern like `useStore.getState().ingest(...)` or a dedicated `pushNotification()` could work but doesn't exist

### 2.6 Search/Command Palette Integration ⚠️
- **CommandPalette** works globally — filters by NAV items (view labels, IDs, hints)
- **✅ All 23 views** are discoverable via command palette (mapped in NAV)
- **❌ No view-specific commands** — palette only navigates views, doesn't expose per-view actions
- **❌ No search API integration** — palette only searches the static NAV list
- Could be extended with action registry per view

### 2.7 API Call Patterns ⚠️
- **Inconsistent patterns:** Some views use `.then()` (mission-overview, mcp-manager), some use `async/await` (all desktop views, self-healing)
- **Bypassed API client:** `task-timeline.tsx` uses raw `fetch('/api/events/recent')` instead of the typed `api` client — **architectural smell**
- **Error handling:** Inconsistent — some views catch errors granularly (desktop-updates), others have a single catch block
- **Polling:** Two views do their own polling (system-monitor: 5s, desktop-diagnostics: 10s) — no centralized polling utility

### 2.8 Store Architecture
- **WebSocket** to `ws://.../ws/dashboard` — well-designed with exponential backoff, jitter, Tauri compatibility
- **Event ingestion** translates raw events into typed store state (agents, tasks, providers, telemetry, memory, etc.)
- **Auto-notifications** from events via `ingest()`
- **Metrics selector** `selectMetrics()` available for consistent metric consumption
- **15 store fields** — well-factored for current needs
- **No REST write-through cache** — REST writes don't auto-update store

---

## 3. Prioritized Fix List

### 🔴 P0 — Critical

| # | Finding | Component | Fix |
|---|---|---|---|
| 1 | **Task Timeline bypasses typed API client** using raw `fetch()` | `task-timeline.tsx` line 27 | Replace `fetch('/api/events/recent')` with `api.eventsRecent()` (add method to api.ts if missing) |
| 2 | **DesktopSettings offers "system" theme** that ThemeProvider doesn't support | `desktop-settings.tsx` line 99 / `theme-provider.tsx` | Either add "system" to ThemeProvider type + logic, or remove from UI options |
| 3 | **MonacoEditor hardcodes vs-dark** regardless of user theme | `monaco-editor.tsx` line 40 | Read theme from ThemeProvider context and switch Monaco theme dynamically |

### 🟠 P1 — High

| # | Finding | Component | Fix |
|---|---|---|---|
| 4 | **i18n system exists but completely unused** — 0% coverage across all views | All 23 views + `lib/i18n.ts` | Either adopt `t()` across all views or remove dead i18n code; write for at least critical UX strings |
| 5 | **No view-level keyboard shortcuts** — all shortcuts are global-only | All 23 views | Add view-specific keyboard bindings (e.g., Ctrl+Enter to invoke in MCP Tools, Ctrl+S in Workflow Studio) |
| 6 | **No view-level notification integration** — views can't push feedback notifications | All 23 views | Add `pushNotification()` helper to store; integrate in views for action results (e.g., "Backup completed") |
| 7 | **Provider Control Center has no REST fallback** — pure store subscription with no hydration | `provider-control-center.tsx` | Add initial REST fetch as fallback for store hydration |

### 🟡 P2 — Medium

| # | Finding | Component | Fix |
|---|---|---|---|
| 8 | **MCP Manager no WebSocket subscription** — all 9 sub-tabs are REST-only with no live updates | `mcp-manager.tsx` | Subscribe to relevant EventBus topics (mcp.*) for auto-refresh |
| 9 | **Inconsistent API patterns** — mix of `.then()` and `async/await` across views | Multiple views | Standardize on `async/await` across all views |
| 10 | **No centralized polling hook** — 2 views implement custom polling | `system-monitor.tsx`, `desktop-diagnostics.tsx` | Extract `usePoll(fn, intervalMs)` into `lib/hooks.ts` |
| 11 | **Command palette is static** — no view-specific commands or search results | `command-palette.tsx` | Add action registry so views can register commands; add API search integration |
| 12 | **Standalone desktop views have no WebSocket integration** — 5 desktop views are REST-only | `desktop-overview`, `desktop-runtimes`, `desktop-updates`, `desktop-offline`, `desktop-settings` | Subscribe to relevant store slices for live updates (at minimum `s.connected`) |

### 🟢 P3 — Low

| # | Finding | Component | Fix |
|---|---|---|---|
| 13 | **View naming inconsistency** — desktop views use `export default function` while core views use `export function X` | All desktop views vs core views | Align export style (choose `named export` to match lazy-load imports in `page.tsx`) |
| 14 | **Store `ingest()` has no error boundary** for malformed events | `store.ts` | Add typed validation before processing events in `ingest()` |
| 15 | **Hardcoded English strings in every view** — i18n would require touching 23+ files | All 23 views | Extract strings alongside adopting i18n (P1 item #4) |
| 16 | **No hook for `useStore` selectors** — many views duplicate selector logic | Multiple views | Create `useStoreAgent()`, `useStoreEvents()`, etc. custom hooks |
| 17 | **Error boundary `withErrorBoundary` HOC unused** | `error-boundary.tsx` line 54 | Either use it or remove it |
| 18 | **Messages file is minimal (45 lines)** — doesn't cover all UI strings | `messages/en.json` | Expand to full coverage or remove |

---

## 4. Architecture Assessment Summary

### Strengths
- **WebSocket EventBus** is well-implemented with auto-reconnect, exponential backoff, and jitter
- **All 23 views have error boundaries** with named fallback skeletons
- **TypeScript strict mode** passes with zero errors — no broken imports
- **Lazy loading** for all views via React.lazy + Suspense
- **Clean separation** between typed REST client (`api.ts`) and Zustand store (`store.ts`)
- **Desktop views** have good accessibility (ARIA roles, labels)

### Weaknesses
- **i18n is a facade** — complete infrastructure exists but zero adoption
- **No centralized patterns** for polling, hooks, or store selectors
- **No view-specific keyboard shortcuts** — all shortcuts are shell-level
- **No notification integration from views** — the notification system is entirely store-driven
- **MonacoEditor ignores theme** — always renders dark regardless of user preference
- **Task Timeline bypasses the typed API client** — architectural inconsistency
