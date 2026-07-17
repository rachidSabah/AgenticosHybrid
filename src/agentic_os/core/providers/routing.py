"""Routing policies + Cost tracker + Rate limit monitor.

Routing policies choose a (provider, model) for a request. Multiple strategies
are provided; the orchestrator selects one via config (ADR-0006). Cost tracker
records token usage and derives spend. Rate limit monitor enforces a simple
token-bucket-ish budget per provider.
"""

from __future__ import annotations

from agentic_os.core.providers.manager import ModelManagerImpl, ProviderManagerImpl
from agentic_os.domain.provider_mgmt import CostRecord
from agentic_os.infrastructure.logging import get_logger

log = get_logger("providers.routing")


class LatencyRoutingPolicy:
    """Prefer the lowest-latency healthy provider for a capability."""

    def __init__(self, manager: ProviderManagerImpl, health) -> None:
        self._manager = manager
        self._health = health

    async def select(
        self, capability: str, candidates: list[tuple[str, str]]
    ) -> tuple[str, str] | None:
        healthy = [
            (p, m) for (p, m) in candidates if self._health.status(p) in ("healthy", "unknown")
        ]
        if not healthy:
            return None

        # Order by live latency when known, else by model cost as a proxy.
        def _sort_key(pm: tuple[str, str]) -> float:
            rec = self._health._status.get(pm[0])
            model = self._manager.get_model(pm[0], pm[1])
            base = rec.latency_ms if rec else 0.0
            return base + (model.input_cost_per_1k if model else 0.0)

        return min(healthy, key=_sort_key)


class CostRoutingPolicy:
    """Prefer the cheapest model that satisfies the capability."""

    def __init__(self, model_manager: ModelManagerImpl) -> None:
        self._mm = model_manager

    async def select(
        self, capability: str, candidates: list[tuple[str, str]]
    ) -> tuple[str, str] | None:
        models = [self._mm._manager.get_model(p, m) for (p, m) in candidates]
        models = [m for m in models if m is not None and capability in m.capabilities]
        if not models:
            return None
        best = min(models, key=lambda m: m.input_cost_per_1k + m.output_cost_per_1k)
        return best.provider, best.id


class RoundRobinRoutingPolicy:
    """Distribute load evenly across candidate providers."""

    def __init__(self) -> None:
        self._idx = 0

    async def select(
        self, capability: str, candidates: list[tuple[str, str]]
    ) -> tuple[str, str] | None:
        if not candidates:
            return None
        pick = candidates[self._idx % len(candidates)]
        self._idx += 1
        return pick


class CostTrackerImpl:
    def __init__(self) -> None:
        self._records: list[CostRecord] = []

    async def record(
        self, provider: str, model: str, task_id: str, input_tokens: int, output_tokens: int
    ) -> float:
        mi = getattr(self, "_mm", None)
        rate_in = rate_out = 0.0
        if mi is not None:
            m = mi.get_model(provider, model)
            if m:
                rate_in, rate_out = m.input_cost_per_1k, m.output_cost_per_1k
        cost = input_tokens / 1000.0 * rate_in + output_tokens / 1000.0 * rate_out
        rec = CostRecord(
            provider=provider,
            model=model,
            task_id=task_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
        )
        self._records.append(rec)
        return cost

    def bind_models(self, mm: ModelManagerImpl) -> None:
        self._mm = mm

    def total_cost(self, provider: str | None = None) -> float:
        return sum(r.cost for r in self._records if provider is None or r.provider == provider)

    def records(self) -> list[CostRecord]:
        return list(self._records)


class RateLimitMonitorImpl:
    def __init__(self) -> None:
        self._limits: dict[str, int] = {}
        self._used: dict[str, int] = {}

    def set_limit(self, provider: str, limit: int) -> None:
        self._limits[provider] = limit
        self._used.setdefault(provider, 0)

    def consume(self, provider: str, weight: int = 1) -> bool:
        limit = self._limits.get(provider, 0)
        if limit <= 0:
            return True  # unlimited
        used = self._used.get(provider, 0)
        if used + weight > limit:
            return False
        self._used[provider] = used + weight
        return True

    def remaining(self, provider: str) -> int:
        limit = self._limits.get(provider, 0)
        if limit <= 0:
            return -1  # unlimited sentinel
        return limit - self._used.get(provider, 0)
