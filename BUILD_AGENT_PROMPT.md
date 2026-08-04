# MASTER BUILD PROMPT — AgenticOS: Local Run, Full Agent Binding & End-to-End Execution Pipeline

You are a senior full-stack AI systems engineer working on **AgenticOS** (repo: `AgenticosHybrid` — Python monorepo backend + Next.js "Mission Control" frontend) on the developer's Windows 10 machine (git-bash/MSYS shell). Your mission has TWO parts, both mandatory:

**PART A — Make the execution pipeline real:** prompts submitted in Prompt Center must actually reach a bound AI agent, execute, stream output, and complete. No UI-only progress, no optimistic state, no fake "executing".
**PART B — Stabilize + bind:** frontend `localhost:3000`, backend port `8000`, dashboard fully live, every AI agent installed on this machine discovered, validated, bound, and shown Healthy with live latency.

Work continuously, no checkpoints, no "what next" questions. Finish, verify, and report with real evidence.

---

## 0. Environment & Non-Negotiable Commands (Windows / MSYS)

- Shell is **git-bash (MSYS)**: POSIX syntax. `npm` REQUIRES Windows-native paths: `npm --prefix "E:/Agenticos/apps/mission-control" run dev` (never `/e/...` — exit 127).
- Backend start (MUST have `PYTHONPATH="src"` — the Hermes agent's venv bleeds into child-process import path otherwise, causing pydantic-core ABI crashes):
  `cd /e/Agenticos && PYTHONPATH="src" uv run python -m agentic_os serve` (port 8000)
- Frontend: `npm --prefix "E:/Agenticos/apps/mission-control" run dev` (port 3000)
- Verification gates (in order, all must pass): `uv run ruff check` → `uv run ruff format --check` → `uv run ty check` (if configured) → `PYTHONPATH="src" uv run pytest tests/` → `npx tsc --noEmit` in mission-control → `npm run build` → browser check: **zero console errors on every view**.
- `services/` is excluded from ruff (standalone layer). Test files importing `services.runtime_discovery.*` need the repo-root `sys.path` shim + `E402` per-file ignore (see AGENTS.md).
- **Quality mandate — no regression, no degrade, preserve everything.** Every fix must be verified across all working features (all 38 sidebar views render with live data) before claiming done. Never weaken assertions. Kill mocks from prod UI. All UI must be driven by live EventBus state, never placeholder data.
- **Known Windows quirks:** `signal.SIGKILL/SIGWINCH` missing — use `getattr(signal, 'SIGKILL', signal.SIGTERM)`; FastAPI route ordering — static routes before `{path_param}` or 404s; `create_app()` captures a stale Platform before background init — memoize + live-update; background tasks with sync I/O block the event loop — `asyncio.to_thread()` + timeouts. Method named `list` shadows builtins in annotations — rename to `list_all`.

## 0.5 Already-Applied State (do NOT re-break, do NOT re-discover)

- **Duplicate React key `hermes` — FIXED locally** in `apps/mission-control/src/lib/store.ts`: `hydrate()` now dedupes providers by normalized slug (healthy > degraded > unknown). Provider count 13 → 11. Verified: tsc clean, `npm run build` clean, Mission Orchestrator renders 11 unique agents, console zero-error. Keep the fix; extend the principle (Part A §4) to canonical identities.
- Backend currently boots healthy when started with `PYTHONPATH="src"`; `/healthz` and `/api/agents` return 200. Do not assume it stays healthy — the auto_bind wedge (Issue #1) may re-fire on a fresh first-launch state.
- `BUILD_AGENT_PROMPT.md` history: this file supersedes the earlier stabilization-only prompt. Do not treat `apps/mission-control/package-lock.json` as editable — remote is source of truth.

---

# PART A — PROMPT CENTER → AGENT EXECUTION PIPELINE (CRITICAL)

## A1. CRITICAL ISSUE — Prompt Center → Agent Execution Pipeline

The Prompt Center currently accepts prompts and creates missions, but the connected agents are not actually receiving or executing the assigned work.

**Current observed behavior**
- Prompt submitted → Mission created → Mission appears in Mission Orchestrator → Tasks created → Status remains "executing" → Connected agents remain idle → No evidence that Claude Code, Hermes, OpenCode, AGY, Gemini or other agents actually receive the prompt.

**This is NOT a UI issue. This is an end-to-end orchestration failure.**

Investigate the ENTIRE execution pipeline. Verify every stage:

```
Prompt Center
↓ Mission creation
↓ Mission planner
↓ Task generation
↓ Task queue
↓ Mission scheduler
↓ Agent scheduler
↓ EventBus
↓ Dispatcher
↓ Provider adapter
↓ Runtime
↓ CLI/API
↓ Agent receives prompt
↓ Agent executes
↓ Streaming response
↓ Mission status updates
↓ Dashboard
```

Determine exactly where execution stops. Verify every EventBus topic, queue, dispatcher, runtime adapter, provider adapter, websocket event, acknowledgement, and task lifecycle.

**Expected lifecycle:** `NEW → QUEUED → ASSIGNED → DISPATCHED → ACKNOWLEDGED → RUNNING → STREAMING → COMPLETED`

**Current behavior appears to stop before DISPATCHED. Find the exact breakpoint.**

Rules:
- Do not fake progress. Do not mark tasks running unless an agent has acknowledged receipt.
- Mission status must reflect actual execution.
- Reference implementation to check first: the Phase 17 distributed execution fabric (`src/agentic_os/cluster/` — `distributed_controller.py`, `distributed_executor.py`, `heartbeat_manager.py`, `node_registry.py`, `transport.py`) may have shadowed or forked the local dispatch path — trace how a local (non-cluster) task reaches a provider adapter, and whether the cluster executor is required for local dispatch.

## A2. MISSION ORCHESTRATOR VALIDATION

Current screen: **Connected Agents** shows 7 online / 0 active while multiple missions are "executing". Logically inconsistent — if missions are executing, at least one agent must become active.

Investigate: Mission Scheduler, Distributed Scheduler, Global Mission Scheduler, Task Dispatcher, Agent Registry, Brain Registry, Provider Registry, Runtime Registry, Distributed Executor, EventBus.

Ensure `Agent Active / Agent Busy / Agent Idle / Mission Executing / Mission Completed / Task Assigned / Task Running` are ALL driven by live execution state rather than optimistic UI state.

## A3. AGENT REGISTRY CONSOLIDATION

Mission Orchestrator currently shows duplicate logical agents. Examples:
- `claude_code` and `Claude Code`
- `hermes` and `Hermes Agent`
- `auto:opencode` and `OpenCode`

These represent the same underlying runtimes. **Normalize them.** Each physical runtime must appear exactly once. Provider aliases, runtime aliases, display names, brain names, CLI names must all resolve to a single canonical agent identity.

- Unknown placeholder brains (Git, Node, Python, Gemini Cli) should NOT appear Healthy unless actually bound.
- "Unknown" should only mean *not yet validated* — never *missing data*.

Design a canonical identity resolution (e.g. canonical slug registry: `hermes`, `claude-code`, `opencode`, `agy`, `gemini-cli`, ...) shared between backend registry and frontend store, so every view renders one row per physical runtime with one live status.

## A4. PROMPT DELIVERY VERIFICATION

For every dispatched prompt, the system must track and the dashboard must expose:
`Prompt ID → Mission ID → Task ID → Assigned Agent → Assigned Runtime → Provider → Transport → Dispatch timestamp → Agent acknowledgement → Execution start → Streaming output → Completion timestamp → Return value → Error (if any)`

The dashboard must expose this information so prompt routing can be debugged.

## A5. FULL END-TO-END EXECUTION VALIDATION (HARD ACCEPTANCE TEST)

After fixes, execute a real Prompt Center request, e.g. `"Build a responsive company website"`. Verify ALL:

- ✓ Prompt accepted
- ✓ Mission created
- ✓ Tasks generated
- ✓ Tasks assigned
- ✓ Agent becomes ACTIVE
- ✓ Agent receives prompt
- ✓ Provider invoked
- ✓ Runtime executes
- ✓ Streaming output visible
- ✓ Mission progresses
- ✓ Mission completes
- ✓ Final response returned
- ✓ Mission history persisted
- ✓ Dashboard updates in real time

Evidence required: EventBus logs, dispatcher logs, provider logs, runtime logs, agent acknowledgement, browser console, network requests, WebSocket messages, final completed mission.

**Do not consider the task complete until a real prompt has been successfully executed end-to-end by a real bound AI agent. No UI state may ever claim a mission is "executing", an agent is "healthy", or a provider is "active" unless there is corresponding backend execution state and an acknowledgement from the runtime. The UI must reflect actual system state, not optimistic or inferred state.**

---

# PART B — STABILIZATION & FULL AGENT BINDING

## B1. CRITICAL — Backend event-loop wedge from unbounded deep PATH scan ("Backend Offline" root cause)

**Symptom:** Backend boots (Kernel started, runtimes + providers bound) but ~1 minute later the event loop blocks for hours; every HTTP request times out (`curl /healthz` → HTTP 000 / exit 28); frontend shows "Backend Offline — Retrying...". Log spam: `auto_bind.unknown_detected` per binary.

**Root cause (partially traced):** `src/agentic_os/adapters/providers/auto_bind.py` — `_detect_unknown_agents()` iterates `_common_install_dirs()` which includes every PATH directory, and **on Windows PATH contains `C:\WINDOWS\system32`, `C:\WINDOWS\SysWOW64`, Git `usr/bin`, Hermes venv Scripts — thousands of binaries**. Each unknown binary gets a synchronous subprocess `--version` probe with a 5s timeout, executed **on the asyncio event loop** → hours of blocking, API dead. The probe is invoked with `probe_unknown=True` from `/binding/deep-scan` and `/binding/discover?mode=deep` (`src/agentic_os/api/app.py` ~5520–5580).

**Hypothesis for the auto-trigger (verify and fix):** On first boot there was no cached install report, so the boot-scheduled installer background task (`kernel.py:469` → `asyncio.create_task(_installer_bg())` → `services/installer/engine.py:first_launch()` → `run_full_install()`) ran full discovery including a deep unknown-agent probe. Subsequent boots have the cache → background verification only (observed: second boot stayed healthy). Trace `run_full_install` Phase 2/3 (`_discover_runtimes`, `_bind_providers`) and the Discovery Framework scheduler (`core/discovery/scheduler.py` `_scan_loop` + `framework.discover_and_register`) for any deep probe path.

**Required fixes (class-level, not symptom):**
1. **Exclude Windows system dirs** from `_common_install_dirs()`/scan candidates: `C:\WINDOWS\system32`, `C:\WINDOWS\SysWOW64`, `C:\Windows\SystemApps`, `Microsoft.WindowsApps`, plus any dir matching `Windows`/`Program Files*` unless it's a known agent install path. A deep scan must only ever probe plausible agent binaries, never the OS.
2. **Run the probe off the event loop**: wrap `_detect_unknown_agents`/`auto_discover_and_bind` in `asyncio.to_thread()` (or ThreadPoolExecutor) so even a large scan cannot block HTTP/WebSocket. Add a hard cap (≤ 200 probes) and a config toggle (env var, e.g. `AGENTICOS_AUTOBIND_PROBE=0`).
3. Per-binary timeout AND an overall deadline (e.g. 30s budget); log progress every 25 probes.
4. Installer first-launch path must NOT deep-probe automatically — surface scan (known names via `shutil.which`) only at boot; deep probe strictly on-demand from the UI button.
5. Verify: restart backend, `curl --max-time 10 http://localhost:8000/healthz` returns 200 fast, `/api/brains` + `/api/agents` return live JSON. Let it run 10+ minutes — the log must never show `auto_bind.unknown_detected` on its own.

## B2. Bind ALL AI agents on this machine

Current state: 4 runtimes discovered (agy_cli, opencode, python, git); 5 providers bound (claude-code, hermes, opencode, agy, gemini-cli); 8 brains; `gemini-cli` detection **timed out** during boot; several brains show `Unknown` in Mission Orchestrator.

Tasks:
1. Find every AI agent CLI actually installed on this machine (`shutil.which` + known install dirs): claude, claude-code, codex, opencode, aider, agy, gemini, gemini-cli, ollama, hermes, qwen-code, cursor-agent, copilot, gpt-engineer, swe-agent, lm-studio, open-interpreter, etc. — enumerate against the catalog in `auto_bind.py` `KNOWN_AGENTS` and any provider catalog in the installer service.
2. Make each installed agent **bind successfully**: validate with sane per-tool timeouts (`gemini-cli --version` hangs — use `--help` or a bounded timeout), then register as a provider so Executive Command / Agent Constellation / Binding Center show it **Healthy** with live latency. No fake "healthy" — status must come from real probes.
3. Ensure the UI button flow (`runScan("surface")` in `agent-binding-center.tsx`) completes without hanging and reflects real results.
4. Any `subprocess.run(..., timeout=5)` that can hang on Windows interactive CLIs needs a shorter timeout + kill fallback (Popen + terminate).

## B3. RUNTIME DASHBOARD CRASH (confirmed in code)

**Current runtime exception:** `TypeError: _rt_health.toLowerCase is not a function` in `src/views/runtime-dashboard.tsx`.

Current code: `HEALTH_COLORS[rt.health?.toLowerCase()]` (lines 911 and 1196) — assumes `health` is always a string.

- Investigate why the API returns `number | boolean | enum | object | null`.
- Fix at the root: **normalize runtime health values** in one place (backend serialization AND/OR frontend store). Accepted values: `healthy | degraded | offline | unknown | starting | stopping | failed`. Only after normalization may `toLowerCase()` ever be called.
- **Search the entire frontend for identical assumptions.** Never call `toLowerCase()`, `toUpperCase()`, `trim()`, `split()`, `replace()`, `match()`, `startsWith()`, `endsWith()` on unknown API values. Use `safeString()` / equivalent normalization everywhere (`apps/mission-control/src/lib/safe.ts` exists — extend and apply it).

## B4. Operational robustness (from observed failures)

1. **Zombie port 3000:** killing the npm wrapper leaves the Next.js child alive holding port 3000 (EADDRINUSE on restart). Document the process-tree caveat; use `netstat -ano | grep :3000` + `taskkill /PID <pid> /F` before restart. Add a dev note to README/AGENTS.md.
2. **`npm run build` vs `next dev` cache collision:** production build while dev runs corrupts `.next` (webpack `__webpack_modules__[moduleId] is not a function`, React Client Manifest errors). Never run build while dev is live; `rm -rf .next` after a collision.
3. **SQLite cross-thread warning** at boot — create/access the connection in a single thread, or per-thread connection / `check_same_thread=False` with a lock (prefer the lock; never loosen safety silently).
4. **Hermes venv PYTHONPATH bleeding:** keep `PYTHONPATH="src"` prefix (documented; do not "fix" by editing global env).

---

## Definition of Done (report with evidence)

1. `git status` clean except intentional changes; no secrets touched.
2. **PART A accepted:** a real prompt executed end-to-end by a real bound agent — completed mission in Mission Orchestrator, agent went ACTIVE, streaming output observed, EventBus/dispatcher/provider logs show the full lifecycle, dashboard reflects actual state. No optimistic state anywhere.
3. **PART B accepted:** backend boots with `PYTHONPATH="src" uv run python -m agentic_os serve`; `/healthz` 200 < 1s; stays responsive 10+ min (no auto deep-scan); all real AI agents on the machine discovered, validated, bound, shown **Healthy** with live latency; Runtime Dashboard renders without exceptions.
4. Frontend: `localhost:3000` renders every view with live EventBus data; **zero console errors across all tabs** (Mission Overview, Prompt Center, AI Agent Binding, Mission Orchestrator, Agent Constellation, Provider Control Center, Runtime Dashboard, plus all others).
5. Gates: ruff check + format pass, pytest suite passes (`PYTHONPATH="src" uv run pytest tests/`), `npx tsc --noEmit` clean, `npm run build` clean.
6. Final report: root cause → change → evidence (curl output, test counts, EventBus logs, browser console) for each issue. No claims without proof.
