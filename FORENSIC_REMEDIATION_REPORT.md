# AgenticOS — Forensic Swarm Execution & Discovery Remediation Report

**Scope:** Deep forensic investigation and production remediation of Swarm Orchestration,
Mission Orchestrator, Execution Graph, AI Agent Binding, AI Brain, Agent Constellation,
dynamic CLI discovery, agent execution adapters, artifact generation, telemetry/health
reporting, task/result verification, and Windows subprocess security.

**Guiding rule enforced throughout:** *Do not make the UI look correct — make the
underlying system correct.* If the real system has 0 agents / 0 tasks / 0 events /
0 artifacts, the UI now shows exactly that.

---

## A. Root causes — where each fabricated state originated

| # | Fabrication observed | Root cause (file) | Classification |
|---|----------------------|-------------------|----------------|
| A1 | `Python` / `Git` / `Node` displayed as active AI agents | `windows_detector.py` instantiated every `KNOWN_RUNTIMES` entry (incl. python/node/bun/git) as `BrainType.LOCAL_CLI` brains; `_detect_python_agent_processes()` / `_detect_node_agent_processes()` registered **every running python/node process** as `ORCHESTRATOR` brains with fabricated `health=95.0`; `runtime_bridge.py` Python/Node/Bun/Git connectors produced `LOCAL_CLI` brain records with `health=100.0 if installed`; `services/runtime_discovery/manager.py` force-injected PYTHON/NODEJS/GIT/DOCKER and bound them ACTIVE; `/api/local-agents` served git/python/node/docker/vscode-cli unfiltered as "Local Agents" | FABRICATED DATA |
| A2 | `Gemini_cli` active despite retirement | Gemini defined at ~25 sites across the whole pipeline (adapters, enums, provider catalogs, discovery maps, strategy registry, brain catalog, vendor maps, frontend color/vendor lists). No `agy → Gemini` alias existed; the stale provider was simply never removed from the source of truth | STALE PROVIDER DEFINITION |
| A3 | Failed retry/fallback recorded as COMPLETED | `orchestrator._run_provider` applied the `_is_error_output`/`_is_unusable_output` guard **only on attempt 1**; attempts 2 and 3 set `TaskStatus.COMPLETED` directly from whatever string the provider returned | FABRICATED COMPLETION |
| A4 | Silent agent run recorded as completed | `generic_cli.py` returned `f"[{bin}] completed '{title}'"` when stdout was empty (exit 0) — a fabricated result string that the report writer persisted | FABRICATED COMPLETION |
| A5 | Mission "COMPLETE" from a Markdown plan only | No independent artifact verification existed anywhere. Any non-error prose result → `COMPLETED`. The historical `[DELIVERABLE_VERIFIED]` bug was already fixed and regression-tested (`test_autonomous_fallback.py`), but report-only missions were still indistinguishable from verified builds | MISSING VERIFICATION |
| A6 | Mock adapter "executions" | `services/execution_engine/adapters/*` returned `{"mock": True}` when the CLI binary was absent, and `manager._execute_on_engine` marked any returned dict `COMPLETED`. The adapters' stdin JSON-RPC protocol is not implemented by real CLIs | FABRICATED COMPLETION |
| A7 | Omniroute simulated provider calls | `core/omniroute/executor.py::_simulate_invoke` returned `COMPLETED` with random latency (0.1–2.0 s), random tokens, and `"[openai] Simulated response…"` output; stream adapters yielded fabricated `chunk-i` content | FABRICATED DATA |
| A8 | `35ms avg latency`, fake swarm plan, pseudo-swarm members | `app.py` `/api/swarm/metrics` hardcoded `avg_latency_ms: 35.0`; `/api/swarm/plans` returned a hardcoded always-`running` plan; `swarm_coordinator.record_mission` synthesized members from the mission's preferred-agent name list; `/api/swarm/agents` labelled every probed provider `"active"` with fabricated capability defaults; `/omniroute/routes` invented `12.5 ms` latency | FABRICATED DATA |
| A9 | Fake health/heartbeat | `brains/health.py` auto-heartbeated every `local_cli`/`custom` brain every 30 s ("so active system brains remain healthy"), making liveness un-falsifiable; `windows_detector` used invented baselines (95/100/60/50) | FABRICATED HEALTH |
| A10 | Fabricated consensus | `orchestration/intelligence.py::_collect_vote` synthesized votes from a capability/latency heuristic; `strategies/consensus.py` voted YES/NO from latency thresholds; `swarm/debugger.py::conduct_debate` hardcoded `vote="approve"`, conf 0.92–0.99, always `consensus_reached=True` | FABRICATED CONSENSUS |
| A11 | Demo telemetry modules | `chaos_engine` (42.0 ms / 0.99 / fake logs), `canary_patcher` (48/48 tests, fake worktree), `gpu_hub` (RTX 4090, 48 °C, fake downloaded models), `hud_daemon` ("162 passed", 18.5 ms), `voice/dispatch` (confidence 0.99 transcripts), `predictive_arbiter` (seeded latencies 177/774/55/156/45/95 ms, $2.45 spend), `learning/benchmark` (`random.uniform` "metrics"), `server/status.py` (42.5 MB / 50 % psutil fallback), `desktop/process.py` (random PID, no process), `/omniroute/compress` (42 % savings), `/api/collab/execute` (24.5 ms, "0 errors"), adapter estimates (`based_on_samples=100` with 0 samples) | FABRICATED DATA |
| A12 | Frontend-invented state | `swarm-studio` (demo DAG agents + invented tokens/memory, debate fallback 0.96, "10 Captured", 600 ms step-status timer), `mission-orchestrator` (client-created `msn-*` missions + localStorage resurrection), `mission-overview` (fake log rows, "100 % uptime"), `execution-graph` (invented progress 60/65/25/50/5 %, synthetic "System Health" node), `ai-brain`/`ai-brains` (CPU/RAM/energy/neurons derived from nothing, `×120 ev/s`, `?? 42/68`), `galaxy-constellation` (98.4/100, 120 bpm, 1.4 GB/s, 142 tok/s), `anatomical-ai-brain` (99 % scores), `gpu-acceleration` (RTX 4090 fallback catalog), `disaster-recovery` (seeded backups + `setTimeout` fake "Verified" row), `collaborative-workspace` (fake presence/AST/AI reply), `detail-panel` (`×0.12 MB/s`, `×0.6 ms`), `telemetry-charts` (always-green EventBus/Database, `process_count × 10` network) | UI FALLBACK / FABRICATED DATA |

**Pre-existing fixes verified intact (no regression):** `_execute_autonomous_fallback` already
records an honest failure; `DELIVERABLE_VERIFIED` / "Verified Complete" strings no longer exist
in source; `DEFAULT_TASKS`/`INITIAL_*`/`MOCK_*` registries already removed; Windows security
(CREATE_NO_WINDOW, directory/extension guards, read-only `winreg`) preserved and unchanged.

---

## B. Files changed

**Backend — execution integrity**
- `src/agentic_os/core/orchestrator.py` — new `_finalize_attempt()` shared terminal-state
  handler: the SAME error-output guard now applies to attempts 1/2/3; independent artifact
  verification before `COMPLETED`; new `PLAN_GENERATED` outcome + `task.plan_generated` event.
- `src/agentic_os/core/artifact_verification.py` — **NEW** module: `WorkspaceSnapshot`
  (before/after diff), `verify_files()` (exists / is_file / size>0), `verify_task_execution()`
  (coding roles require real non-report files; prose roles may satisfy verification with their
  honest task report).
- `src/agentic_os/adapters/providers/generic_cli.py` — empty stdout propagates unchanged;
  the fabricated `[bin] completed '…'` string was removed.
- `src/agentic_os/domain/agent.py` — `TaskStatus.PLAN_GENERATED`, `Task.verification` field.
- `src/agentic_os/domain/mission.py` — `MissionStatus.PARTIAL`.
- `src/agentic_os/domain/events.py` — `Topic.MISSION_PARTIAL`.
- `src/agentic_os/api/app.py` — mission watcher: `plan_generated` is terminal; mission
  outcome FAILED > PARTIAL > COMPLETED.

**Backend — Gemini removal (source of truth)**
Deleted: `services/execution_engine/adapters/gemini_cli_adapter.py`.
Edited: `core/contracts/execution_engine.py`, `src/agentic_os/domain/execution.py`,
`src/agentic_os/domain/brains.py`, `src/agentic_os/domain/desktop.py`,
`src/agentic_os/core/runtime/runtime.py`, `services/runtime_discovery/models.py`
(enum members); `services/execution_engine/{__init__,manager,discovery,routing}.py`;
`src/agentic_os/adapters/providers/{strategies,auto_bind,factory}.py`;
`src/agentic_os/adapters/discovery/{path,shell_profile}.py`;
`services/installer/provider_catalog.py`; `src/agentic_os/core/brains/{catalog,bridge,
capabilities,runtime_bridge,windows_detector,windows_discovery,unix_discovery}.py`;
`src/agentic_os/core/discovery/local/{scanner,path_scanner,filesystem_scanner,
process_scanner,version_detector,capability_detector}.py`;
`src/agentic_os/domain/discovery.py`; `src/agentic_os/discovery/service.py`;
`services/runtime_discovery/{manager,cli_discovery,validation,profiling,binding}.py`
and `providers/{path,env_var,wsl}.py`; `src/agentic_os/core/{mission,orchestrator}.py`
(role maps / kind lists); `src/agentic_os/core/runtime/runtime_bridge.py`.
Cloud LLM **model** catalogs (omniroute model names, `GEMINI_API_KEY` cloud provider) are
intentionally retained — they are API credentials/models, not the retired CLI agent.

**Backend — runtimes ≠ agents**
- `src/agentic_os/core/brains/windows_detector.py` — python/node/bun/git removed from
  `KNOWN_RUNTIMES`; python/node "agent process" fabrication deleted; health derives only from
  real probe evidence; invented latency/task numbers zeroed.
- `src/agentic_os/core/brains/runtime_bridge.py` — `is_ai_agent=False` on
  Python/Node/Bun/Git connectors; `to_brain_records()` excludes them.
- `src/agentic_os/core/brains/bridge.py` — `_NON_AGENT_TOOL_TYPES` gate: git/python/node/
  docker/vscode-cli/… never become BrainRecords.
- `src/agentic_os/core/brains/health.py` — synthetic 30 s auto-heartbeat removed.
- `src/agentic_os/api/app.py` — `/api/local-agents` returns AI agents by default (tools only
  via `?include_tools=true`, each tagged `kind: "tool" | "ai_agent"`); SSE stream filtered;
  `/api/swarm/agents` reports `ready`/`detected`/`not_detected` (never `active`), no invented
  capability defaults; `/api/swarm/tasks` real registry rows only; `/api/swarm/plans` derived
  from real mission plans; `avg_latency_ms` → `null`; `/omniroute/routes` no invented latency,
  status `ready`.
- `services/runtime_discovery/manager.py` — forced PYTHON/NODEJS/GIT/DOCKER injection removed.
- `src/agentic_os/core/orchestration/swarm_coordinator.py` — `record_mission` no longer
  synthesizes swarm members.

**Backend — no fake telemetry/consensus**
`core/healing/{chaos_engine,canary_patcher}.py`, `core/desktop/{gpu_hub,hud_daemon}.py`,
`core/voice/dispatch.py`, `core/routing/predictive_arbiter.py`,
`core/learning/benchmark.py`, `server/status.py`, `core/desktop/process.py`,
`core/omniroute/executor.py`, `services/execution_engine/manager.py` (mock results → FAILED),
`services/execution_engine/adapters/*` (honest zero estimates),
`core/orchestration/{intelligence.py, strategies/consensus.py}`, `core/swarm/debugger.py`,
`/omniroute/compress`, `/api/collab/execute`.

**Frontend (17 files)** — all fabrications listed in A12 replaced with honest values,
"—", or explicit empty states; gemini color/vendor entries removed from
`use-brains.ts`, `ai-brain.tsx`, `agent-constellation.tsx`, `runtime-dashboard.tsx`.

**Tests** — `tests/test_forensic_remediation.py` (**NEW**, 23 tests); updated:
`test_provider_strategies.py`, `test_brains/{test_bridge,test_catalog,test_runtime_bridge}.py`,
`test_runtime/test_runtime_bridge.py`, `test_runtime_domain.py`, `test_sd_domain.py`,
`test_desktop_security.py`, `test_desktop_engine.py`, `test_discovery/test_capability_detector.py`,
`test_omniroute/test_executor.py`, `test_orchestrator.py`,
`test_orchestration_{intelligence,strategies}.py`, `test_orchestrator_output_guard.py`,
`apps/mission-control/tests/e2e/{swarm-studio,collab-workspace}.spec.ts`.

---

## C. Architecture

**Before**

```
OS discovery → fake registry (KNOWN_AGENTS/runtimes-as-brains/synthetic members)
            → heuristic votes (latency/capability)
            → unguarded retry paths → COMPLETED on any non-exception string
            → fabricated telemetry (35ms/42ms/99.x/seeds)
            → frontend fallbacks (demo agents, invented %, localStorage resurrection)
```

**After**

```
OS discovery → candidate generation → binary validation → version probe
            → evidence-based classification (ai_agent | runtime | developer_tool | unknown)
            → canonical registry (agents only; runtimes exposed separately)
            → adapter (per-CLI execution strategy) → REAL subprocess launch
            → stdout/stderr capture (pid, exit code, timeout, tree-kill)
            → independent artifact verification (workspace diff + file checks)
            → honest terminal state (COMPLETED | PLAN_GENERATED | FAILED)
            → mission outcome (COMPLETED | PARTIAL | FAILED)
            → telemetry derived only from real events
            → frontend renders backend state verbatim (empty stays empty)
```

---

## D. Agent inventory

The canonical inventory is produced at runtime by the discovery engine
(`GET /api/discovery/agents`) from **actual machine state** — it is never static.
On this Linux CI machine no Windows CLIs are installed, so a live scan reports zero
AI agents (`agents: [], runtimes: [...]`), and the UI shows `0` / `NOT DETECTED` accordingly.
The discovery→registry contract is proven by `tests/test_discovery_engine.py`
(agy fixture) and `tests/test_forensic_remediation.py` (negative guarantees).

Agent statuses have precise meanings everywhere:
`NOT_DETECTED / DETECTED / READY / STARTING / RUNNING / COMPLETED / FAILED / TIMEOUT / DISCONNECTED`.
`READY` = installed + version probe passed + adapter compatible. `RUNNING` is produced
**only** by a real process execution (real PID, real exit code — `run_cli.py` captures both
and performs process-tree termination on timeout).

## E. Removed agents/tools (with reasons derived from discovery semantics)

```
Gemini CLI   — excluded (retired provider; ~25 definition sites removed; no alias may
               resurrect it; Antigravity (agy) is the canonical Google CLI agent)
Python       — runtime  (excluded from agent registry; visible as tool/runtime only)
Node.js      — runtime  (excluded from agent registry)
Bun          — runtime  (excluded from agent registry)
Git          — developer tool / VCS (excluded from agent registry)
Docker       — system tool (excluded from agent registry; kept under tools)
vscode-cli   — developer tool (excluded from agent registry)
```

## F. Execution verification (how completion is now proven)

For every task the orchestrator now records, on the `Task` object itself
(`task.verification`):

1. workspace snapshot **before** execution (`exec_cwd`);
2. real provider execution (subprocess, PID, streamed stdout, exit code, timeout);
3. error-output / unusable-output guard on **every** attempt (1, 2, 3);
4. report + code-fence extraction to the workspace;
5. workspace snapshot **after** and independent diff;
6. `verify_files()`: every candidate artifact must exist, be a file, and be non-empty
   (the orchestrator's own `task_*.md` report does not count for build roles);
7. outcomes: verified artifacts → `COMPLETED` (with `verification.ok = true` and artifact
   list); real run without any verifiable artifact (e.g. only a Markdown plan) →
   `PLAN_GENERATED` ("PLAN GENERATED — DELIVERABLE NOT VERIFIED"); error output →
   retry/fallback → honest `FAILED`. Mission level: `COMPLETED` | `PARTIAL` | `FAILED`.

The agent's natural-language claim is never accepted as proof (§35/§41 regression tests
below prove both directions).

## G. Tests

| Suite | Result |
|-------|--------|
| `ruff check src tests core` | **passed** (0 issues in configured scope) |
| `ruff format` (configured files) | clean |
| `pytest tests` (full suite) | **5053 passed**, 4 skipped, 0 failed |
| `tests/test_forensic_remediation.py` (new) | **23 passed** |
| `tests/test_autonomous_fallback.py` (existing fabrication regression) | 5 passed |
| `npx tsc --noEmit` (frontend) | 0 errors |
| `npx vitest run` (frontend) | 30 / 30 passed |
| Tauri build | not executed on this Linux CI host (Windows/NNSIS target); `src-tauri` sources unchanged by this remediation |

New regression coverage maps directly to the brief's critical tests:
§36 retired-Gemini (4 tests) · §37 runtime≠agent (4) · §38 no synthetic swarm (3) ·
§35 markdown-only ≠ completed (2) · §41 independent artifact verification (5) ·
§8/§15 retry-path guard + no fabricated completion string (2) · §9/§24 installed ≠ active (1) ·
§39 missing binary → raise (1) · mock-results-fail contract (1).
