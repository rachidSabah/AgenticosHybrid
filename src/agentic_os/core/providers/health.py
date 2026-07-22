"""Provider Health Monitor + Benchmarking + Failover.

Periodically probes every registered provider's ``healthcheck()`` and publishes
``provider.health`` events. Maintains a live status map consumed by routing and
failover. Benchmarking runs a trivial echo task to measure latency/quality.
"""

from __future__ import annotations

import time
from datetime import UTC

from agentic_os.core.providers.manager import ProviderManagerImpl
from agentic_os.core.scheduler import Scheduler
from agentic_os.domain.agent import Agent, Task
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.provider_mgmt import (
    BenchmarkResult,
    ProviderHealthRecord,
    ProviderHealthStatus,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("providers.health")


class ProviderHealthMonitorImpl:
    def __init__(
        self,
        bus: EventBus,
        manager: ProviderManagerImpl,
        scheduler: Scheduler,
        interval: float = 10.0,
    ) -> None:
        self._bus = bus
        self._manager = manager
        self._scheduler = scheduler
        self._interval = interval
        self._status: dict[str, ProviderHealthRecord] = {}

    async def start(self) -> None:
        self._scheduler.every(self._interval, self._tick)

    async def stop(self) -> None:
        pass

    def status(self, provider: str) -> str:
        return self._status.get(provider, ProviderHealthRecord(provider=provider)).status.value

    async def check_now(self, provider: str) -> bool:
        adapter = self._manager.get(provider)
        rec = self._status.setdefault(provider, ProviderHealthRecord(provider=provider))
        if adapter is None:
            rec.status = ProviderHealthStatus.DOWN
            rec.error = "not registered"
            return False
        t0 = time.perf_counter()
        try:
            ok = await adapter.healthcheck()
            rec.latency_ms = (time.perf_counter() - t0) * 1000.0
            rec.status = ProviderHealthStatus.HEALTHY if ok else ProviderHealthStatus.DOWN
            rec.error = None
        except Exception as exc:  # noqa: BLE001
            rec.status = ProviderHealthStatus.DOWN
            rec.error = str(exc)
            ok = False
        from datetime import datetime

        rec.last_checked = datetime.now(UTC)
        await self._bus.publish(
            EventEnvelope(
                type="provider.health",
                source="provider-health",
                topic=Topic.PROVIDER_HEALTH.value,
                payload=rec.model_dump(),
            )
        )
        return ok

    async def benchmark(self, provider: str, model: str) -> BenchmarkResult:
        adapter = self._manager.get(provider)
        if adapter is None:
            return BenchmarkResult(
                provider=provider,
                model=model,
                latency_ms=0.0,
                success=False,
                error="not registered",
            )
        t0 = time.perf_counter()
        try:
            agent = Agent(id="bench", role="benchmark", provider=provider)
            task = Task(title="reply with the single word: pong", role="benchmark")
            out = await adapter.execute(agent, task)
            latency = (time.perf_counter() - t0) * 1000.0
            success = "pong" in out.lower()
            return BenchmarkResult(
                provider=provider,
                model=model,
                latency_ms=latency,
                success=success,
                score=1.0 if success else 0.0,
            )
        except Exception as exc:  # noqa: BLE001
            return BenchmarkResult(
                provider=provider,
                model=model,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                success=False,
                error=str(exc),
            )

    async def _tick(self) -> None:
        for name in list(self._manager._providers.keys()):
            await self.check_now(name)


class FailoverPolicyImpl:
    async def next_provider(self, failed: str, capability: str, healthy: list[str]) -> str | None:
        candidates = [p for p in healthy if p != failed]
        return candidates[0] if candidates else None
