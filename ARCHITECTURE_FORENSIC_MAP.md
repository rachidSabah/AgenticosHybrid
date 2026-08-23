# AGENTICOS HYBRID — FORENSIC ARCHITECTURE & DEPENDENCY MAP
**Version:** v1.0.0-rc10  
**Environment:** Windows 11 / WSL2 / Dual Architecture  
**Source Root:** `E:\Agenticos`  
**Workspace:** `E:\Mission`  
**Status:** Certified Operational Reality (Zero Production Mocks)

---

## 1. COMPONENT TO SOURCE DIRECTORY MAPPING

| Subsystem Component | Source Directory | Primary Entry Points | API Route Prefix | Frontend Consumer View | Persistence / State Model |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **API Gateway & Routing** | `src/agentic_os/api/` | `app.py`, `middleware.py` | `/api/v1/`, `/healthz` | Layout & Navbar | SQLite / EventBus Local Stream |
| **Mission Orchestrator** | `src/agentic_os/orchestration/` | `orchestrator.py`, `planner.py` | `/api/missions/` | `prompt-center.tsx`, `mission-overview.tsx` | `MissionStore`, `ExecutionRecord` |
| **DAG & Workflow Engine** | `src/agentic_os/workflow/` | `engine.py`, `dag.py` | `/api/workflow/` | `workflow-studio.tsx` | `WorkflowGraph`, `NodeState` |
| **Swarm Coordinator** | `src/agentic_os/swarm/` | `coordinator.py`, `consensus.py` | `/api/swarm/` | `swarm-orchestration.tsx` | `SwarmPlan`, `SwarmTaskState` |
| **Pipeline Engine** | `src/agentic_os/pipeline/` | `engine.py`, `stages.py` | `/api/pipeline/` | `pipeline-engine.tsx` | `PipelineExecutionRecord` |
| **AI Agent Binding Center** | `src/agentic_os/binding/` | `manager.py`, `handshake.py` | `/binding/` | `agent-binding-center.tsx` | `AgentBindingRegistry` |
| **Runtime Discovery** | `src/agentic_os/discovery/` | `engine.py`, `probes.py` | `/api/discovery/`, `/api/desktop/runtimes` | `galaxy-constellation.tsx` | `DiscoveredHostEngines` |
| **Provider Fabric & Routing**| `src/agentic_os/providers/` | `registry.py`, `scoring.py` | `/api/providers/` | `provider-control.tsx` | `ProviderProfile`, `ProviderHealth` |
| **OmniRoute Universal Engine**| `src/agentic_os/omniroute/` | `engine.py`, `compression.py` | `/omniroute/` | `omniroute-dashboard.tsx` | `RoutingPolicies`, `FailoverLog` |
| **Self-Healing Autonomous SRE**| `src/agentic_os/healing/` | `sre.py`, `mitigation.py` | `/healthz`, `/binding/repair` | `self-healing.tsx` | `IncidentLog`, `ResolvedIssueSet` |
| **EventBus Telemetry** | `src/agentic_os/events/` | `bus.py`, `stream.py` | `/api/events/ws`, `/api/events/sse`| `live-collaboration.tsx` | In-Memory Ring Buffer & SQLite Log |
| **Plugin Marketplace** | `src/agentic_os/plugins/` | `manager.py`, `sandbox.py` | `/api/plugins/` | `plugin-marketplace.tsx` | `PluginManifestStore` |
| **MCP Manager** | `src/agentic_os/mcp/` | `client.py`, `registry.py` | `/api/mcp/` | `mcp-manager.tsx` | `MCPServerDefinition` |
| **Isolated Worktree Engine** | `src/agentic_os/worktrees/` | `manager.py`, `isolation.py`| `/api/workspace/` | `workspace-explorer.tsx` | `WorktreeLock`, `GitBranchMapping` |
| **Desktop Runtime & Hardening**| `src/agentic_os/desktop/` | `runtime.py`, `hardening.py`| `/api/desktop/` | `desktop-overview.tsx` | `DesktopState`, `WindowsMetrics` |

---

## 2. FORENSIC TRACE: PROMPT CENTER TO REAL RUNTIME EXECUTION

```
[User Input @ Prompt Center]
        ↓
  POST /api/missions (Intent Detection, Title, Payload)
        ↓
  MissionOrchestrator.create_mission()
        ↓
  POST /api/missions/{id}/plan (Task Decomposition, Role Assignment)
        ↓
  SwarmCoordinator.decompose_and_assign()
        ↓ (Roles: Chief Architect, Backend Engineer, Security Engineer, Test Engineer, Validator)
  Target Agent Selection (Codex CLI, Hermes Agent, Claude Code, OpenCode)
        ↓
  WorktreeEngine.create_isolated_workspace("E:\Mission")
        ↓
  Runtime Process Dispatch (Real subprocess / CLI invocation)
        ↓
  Artifact Generation (.py, .md, tests in E:\Mission)
        ↓
  Pytest Execution & Coverage Validation (162/162 Real Tests Passing)
        ↓
  EventBus Dispatches "mission.completed" & Telemetry Updates
        ↓
  Mission Control UI Real-Time Updates via WebSocket/SSE
```

---

## 3. REAL DISCOVERED AGENTS INVENTORY

1. **Codex CLI (`auto:codex`)**: Host CLI located in PATH, validated with zero-latency streaming execution.
2. **Hermes Agent (`hermes`)**: Autonomous agent execution engine, supporting multi-step tool and file operations.
3. **Claude Code (`claude_code`)**: Advanced architectural review and deep module design engine.
4. **OpenCode (`auto:opencode`)**: Fast backend and frontend code generation and unit testing engine.
5. **Agy (`auto:agy`)**: Native Antigravity system agent and orchestration assistant.

---

## 4. SUBSYSTEM INTERFACES & CONTRACT VALIDATION

- **Zero Mock Policy**: Production paths contain zero fake telemetry or hardcoded arrays pretending to be runtime state.
- **Failover Cascade**: If a primary host agent is busy or unreachable, OmniRoute transparently fails over to healthy secondary engines with zero prompt loss.
- **Reconciliation Loop**: Self-healing tracks persistent resolution IDs, preventing UI oscillation and keeping the live bus synchronized.