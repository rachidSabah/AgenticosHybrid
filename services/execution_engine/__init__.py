"""Universal Execution Engine Framework — v0.5.0

An execution-engine-neutral AI Operating System that discovers, manages,
benchmarks, orchestrates, and routes work across multiple execution engines
through a unified abstraction layer.

Every execution engine — Claude Code, Gemini CLI, Codex CLI, Hermes,
OpenHands, Aider, Continue, Cline, Roo Code, Local Engines, Custom Engines —
is treated as an interchangeable runtime provider, integrated exclusively
through the ``ExecutionEnginePort`` protocol (12-method universal interface).

Components:
  - port: ExecutionEnginePort protocol (12 methods: initialize, shutdown,
    health_check, execute, cancel, stream, benchmark, version, configuration,
    telemetry, discover_capabilities, supports, estimate_cost, estimate_latency)
  - models: ExecutionTask, ExecutionSession, ExecutionMetrics,
    ExecutionBenchmarkResult, ExecutionPlan
  - discovery: EngineDiscovery — auto-discover engines on PATH, common install
    dirs, WSL, Docker, environment variables, Windows Registry, binary signatures
  - routing: RouterRegistry — 6 built-in strategies (fastest, lowest cost,
    highest quality, capability-based, load balancing, failover) + custom
  - adapters: 11 adapter implementations (Claude Code, Gemini CLI, Codex CLI,
    Hermes, OpenHands, Aider, Continue, Cline, Roo Code, Local, Custom)
  - manager: ExecutionEngineManager — facade that orchestrates discovery,
    registration, routing, execution, sessions, benchmarks, telemetry
  - events: 23 task/engine lifecycle event publishers for EventBus
"""

from __future__ import annotations

from services.execution_engine.adapters import (
    AiderAdapter,
    BaseExecutionEngineAdapter,
    ClaudeCodeAdapter,
    ClineAdapter,
    CodexCliAdapter,
    ContinueAdapter,
    CustomEngineAdapter,
    GeminiCliAdapter,
    HermesAdapter,
    LocalEngineAdapter,
    OpenHandsAdapter,
    RooCodeAdapter,
)
from services.execution_engine.discovery import EngineDiscovery, discovery_result_from_dict
from services.execution_engine.manager import ExecutionEngineManager
from services.execution_engine.models import (
    ExecutionBenchmarkResult,
    ExecutionMetrics,
    ExecutionPlan,
    ExecutionSession,
    ExecutionSessionStatus,
    ExecutionTask,
    ExecutionTaskPriority,
    ExecutionTaskStatus,
)
from services.execution_engine.routing import (
    CapabilityBasedRouter,
    CustomRouter,
    FailoverRouter,
    FastestRouter,
    HighestQualityRouter,
    LoadBalancingRouter,
    LowestCostRouter,
    RouterRegistry,
    RoutingContext,
    RoutingDecision,
    RoutingStrategy,
)

__all__ = [
    "AiderAdapter",
    "BaseExecutionEngineAdapter",
    "CapabilityBasedRouter",
    "ClaudeCodeAdapter",
    "ClineAdapter",
    "CodexCliAdapter",
    "ContinueAdapter",
    "CustomEngineAdapter",
    "CustomRouter",
    "EngineDiscovery",
    "ExecutionBenchmarkResult",
    "ExecutionEngineManager",
    "ExecutionMetrics",
    "ExecutionPlan",
    "ExecutionSession",
    "ExecutionSessionStatus",
    "ExecutionTask",
    "ExecutionTaskPriority",
    "ExecutionTaskStatus",
    "FailoverRouter",
    "FastestRouter",
    "GeminiCliAdapter",
    "HermesAdapter",
    "HighestQualityRouter",
    "LoadBalancingRouter",
    "LocalEngineAdapter",
    "LowestCostRouter",
    "OpenHandsAdapter",
    "RooCodeAdapter",
    "RouterRegistry",
    "RoutingContext",
    "RoutingDecision",
    "RoutingStrategy",
    "discovery_result_from_dict",
]
