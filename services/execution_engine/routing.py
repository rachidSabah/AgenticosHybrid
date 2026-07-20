from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.contracts.execution_engine import (
    EngineCapabilities,
    EngineHealthState,
    EngineTelemetry,
    EngineType,
)
from core.logging import get_logger

_log = get_logger(__name__)

__all__ = [
    "RoutingStrategy",
    "RoutingDecision",
    "RouterRegistry",
    "FastestRouter",
    "LowestCostRouter",
    "HighestQualityRouter",
    "CapabilityBasedRouter",
    "LoadBalancingRouter",
    "FailoverRouter",
    "CustomRouter",
]

# Engine quality scores (higher = better) based on known model/engine quality
_QUALITY_SCORES: dict[EngineType, float] = {
    EngineType.CLAUDE_CODE: 0.95,
    EngineType.GEMINI_CLI: 0.88,
    EngineType.CODEX_CLI: 0.90,
    EngineType.HERMES: 0.75,
    EngineType.OPENHANDS: 0.85,
    EngineType.AIDER: 0.80,
    EngineType.CONTINUE: 0.82,
    EngineType.CLINE: 0.83,
    EngineType.ROO_CODE: 0.78,
    EngineType.LOCAL: 0.60,
    EngineType.CUSTOM: 0.70,
}

# Per-token cost estimates (USD) for each engine
_COST_PER_TOKEN: dict[EngineType, float] = {
    EngineType.CLAUDE_CODE: 0.000015,
    EngineType.GEMINI_CLI: 0.000005,
    EngineType.CODEX_CLI: 0.000010,
    EngineType.HERMES: 0.0,
    EngineType.OPENHANDS: 0.000008,
    EngineType.AIDER: 0.000006,
    EngineType.CONTINUE: 0.000012,
    EngineType.CLINE: 0.000014,
    EngineType.ROO_CODE: 0.000007,
    EngineType.LOCAL: 0.0,
    EngineType.CUSTOM: 0.000010,
}

# Estimated average latency (seconds) per task for each engine
_AVG_LATENCY_S: dict[EngineType, float] = {
    EngineType.CLAUDE_CODE: 15.0,
    EngineType.GEMINI_CLI: 10.0,
    EngineType.CODEX_CLI: 20.0,
    EngineType.HERMES: 2.0,
    EngineType.OPENHANDS: 25.0,
    EngineType.AIDER: 12.0,
    EngineType.CONTINUE: 18.0,
    EngineType.CLINE: 14.0,
    EngineType.ROO_CODE: 16.0,
    EngineType.LOCAL: 1.0,
    EngineType.CUSTOM: 10.0,
}


class RoutingStrategy(StrEnum):
    FASTEST = "fastest"
    LOWEST_COST = "lowest_cost"
    HIGHEST_QUALITY = "highest_quality"
    CAPABILITY_BASED = "capability_based"
    LOAD_BALANCING = "load_balancing"
    FAILOVER = "failover"
    CUSTOM = "custom"


@dataclass
class RoutingDecision:
    selected_engine: EngineType
    strategy: RoutingStrategy
    reason: str = ""
    alternatives: list[EngineType] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class RoutingContext:
    engine_health: dict[str, EngineHealthState] = field(default_factory=dict)
    engine_telemetry: dict[str, EngineTelemetry] = field(default_factory=dict)
    engine_capabilities: dict[str, EngineCapabilities] = field(default_factory=dict)
    task_goal: str = ""
    required_capabilities: list[str] = field(default_factory=list)


class FastestRouter:
    def select(self, available: list[EngineType], context: RoutingContext | None = None) -> RoutingDecision:
        if not available:
            raise ValueError("No available engines to select from")
        sorted_engines = sorted(available, key=lambda e: _AVG_LATENCY_S.get(e, float("inf")))
        return RoutingDecision(
            selected_engine=sorted_engines[0],
            strategy=RoutingStrategy.FASTEST,
            reason=f"Selected {sorted_engines[0].value} with lowest avg latency ({_AVG_LATENCY_S.get(sorted_engines[0], 0):.1f}s)",
            alternatives=sorted_engines[1:],
        )


class LowestCostRouter:
    def select(self, available: list[EngineType], context: RoutingContext | None = None) -> RoutingDecision:
        if not available:
            raise ValueError("No available engines to select from")
        zero_cost = [e for e in available if _COST_PER_TOKEN.get(e, 0) == 0]
        if zero_cost:
            target = zero_cost[0]
        else:
            sorted_engines = sorted(available, key=lambda e: _COST_PER_TOKEN.get(e, float("inf")))
            target = sorted_engines[0]
        return RoutingDecision(
            selected_engine=target,
            strategy=RoutingStrategy.LOWEST_COST,
            reason=f"Selected {target.value} with lowest cost (${_COST_PER_TOKEN.get(target, 0):.8f}/token)",
            alternatives=[e for e in available if e != target],
            confidence=1.0,
        )


class HighestQualityRouter:
    def select(self, available: list[EngineType], context: RoutingContext | None = None) -> RoutingDecision:
        if not available:
            raise ValueError("No available engines to select from")
        sorted_engines = sorted(available, key=lambda e: _QUALITY_SCORES.get(e, 0), reverse=True)
        return RoutingDecision(
            selected_engine=sorted_engines[0],
            strategy=RoutingStrategy.HIGHEST_QUALITY,
            reason=f"Selected {sorted_engines[0].value} with highest quality score ({_QUALITY_SCORES.get(sorted_engines[0], 0):.2f})",
            alternatives=sorted_engines[1:],
        )


class CapabilityBasedRouter:
    def select(self, available: list[EngineType], context: RoutingContext | None = None) -> RoutingDecision:
        if not available:
            raise ValueError("No available engines to select from")
        if not context or not context.required_capabilities:
            return FastestRouter().select(available, context)

        scored = []
        for engine in available:
            caps = context.engine_capabilities.get(engine.value)
            if caps:
                matched = sum(1 for c in context.required_capabilities if c in caps.features)
                scored.append((engine, matched))
            else:
                scored.append((engine, 0))
        scored.sort(key=lambda x: x[1], reverse=True)
        return RoutingDecision(
            selected_engine=scored[0][0],
            strategy=RoutingStrategy.CAPABILITY_BASED,
            reason=f"Selected {scored[0][0].value} matching {scored[0][1]}/{len(context.required_capabilities)} required capabilities",
            alternatives=[e for e, _ in scored[1:]],
        )


class LoadBalancingRouter:
    def __init__(self) -> None:
        self._counter: dict[EngineType, int] = {}

    def select(self, available: list[EngineType], context: RoutingContext | None = None) -> RoutingDecision:
        if not available:
            raise ValueError("No available engines to select from")
        for engine in available:
            self._counter.setdefault(engine, 0)
        sorted_engines = sorted(available, key=lambda e: self._counter.get(e, 0))
        target = sorted_engines[0]
        self._counter[target] = self._counter.get(target, 0) + 1
        return RoutingDecision(
            selected_engine=target,
            strategy=RoutingStrategy.LOAD_BALANCING,
            reason=f"Round-robin selected {target.value} (load count: {self._counter[target]})",
            alternatives=sorted_engines[1:],
        )


class FailoverRouter:
    def __init__(self, primary: list[EngineType]) -> None:
        self._primary_order = primary

    def select(self, available: list[EngineType], context: RoutingContext | None = None) -> RoutingDecision:
        for engine in self._primary_order:
            if engine in available:
                return RoutingDecision(
                    selected_engine=engine,
                    strategy=RoutingStrategy.FAILOVER,
                    reason=f"Primary engine {engine.value} is available",
                    alternatives=[e for e in self._primary_order if e != engine and e in available],
                )
        if available:
            return RoutingDecision(
                selected_engine=available[0],
                strategy=RoutingStrategy.FAILOVER,
                reason=f"No primary engine available, fell back to {available[0].value}",
                alternatives=available[1:],
                confidence=0.5,
            )
        raise ValueError("No available engines to select from")


class CustomRouter:
    def __init__(self, selector: Callable[[list[EngineType], RoutingContext | None], RoutingDecision]) -> None:
        self._selector = selector

    def select(self, available: list[EngineType], context: RoutingContext | None = None) -> RoutingDecision:
        return self._selector(available, context)


_ROUTER_MAP: dict[RoutingStrategy, type] = {
    RoutingStrategy.FASTEST: FastestRouter,
    RoutingStrategy.LOWEST_COST: LowestCostRouter,
    RoutingStrategy.HIGHEST_QUALITY: HighestQualityRouter,
    RoutingStrategy.CAPABILITY_BASED: CapabilityBasedRouter,
    RoutingStrategy.LOAD_BALANCING: LoadBalancingRouter,
    RoutingStrategy.FAILOVER: FailoverRouter,
}


class RouterRegistry:
    def __init__(self) -> None:
        self._routers: dict[str, Any] = {}
        self._default_strategy: RoutingStrategy = RoutingStrategy.FASTEST
        self._load_balancer = LoadBalancingRouter()

    def get_router(self, strategy: RoutingStrategy | str) -> Any:
        if isinstance(strategy, str):
            strategy = RoutingStrategy(strategy)
        if strategy == RoutingStrategy.LOAD_BALANCING:
            return self._load_balancer
        router_cls = _ROUTER_MAP.get(strategy)
        if not router_cls:
            raise ValueError(f"Unknown routing strategy: {strategy}")
        return router_cls()

    def register_custom(self, name: str, router: CustomRouter) -> None:
        self._routers[name] = router

    def select(
        self,
        available: list[EngineType],
        strategy: RoutingStrategy | str | None = None,
        context: RoutingContext | None = None,
    ) -> RoutingDecision:
        if strategy is None:
            strategy = self._default_strategy
        if isinstance(strategy, str):
            strategy = RoutingStrategy(strategy)
        router = self.get_router(strategy)
        return router.select(available, context)
