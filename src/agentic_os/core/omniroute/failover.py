"""OmniRoute Circuit Breaker Engine — production provider resilience layer.

Implements the standard three-state machine (CLOSED → OPEN → HALF_OPEN → CLOSED)
with per-provider failure tracking, configurable thresholds, sliding-window rate
calculation, EventBus integration, and full observability.

RouterEngine, BudgetEngine, Gateway, Learning Engine, and AI Brain all depend
on this engine to filter unhealthy or degraded providers.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.omniroute import (
    CircuitBreakerConfig,
    CircuitBreakerState,
    FailoverState,
    ProviderCircuitMetrics,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("omniroute.circuit_breaker")

DEFAULT_CONFIG = CircuitBreakerConfig()


# ── Port Protocol ──


@runtime_checkable
class CircuitBreakerPort(Protocol):
    """Port for the Circuit Breaker Engine."""

    async def record_success(self, provider: str, latency_ms: float = 0.0) -> None:
        """Record a successful request to provider."""
        ...

    async def record_failure(
        self, provider: str, failure_type: str = "unknown", latency_ms: float = 0.0
    ) -> None:
        """Record a failure for provider with a failure type classification."""
        ...

    async def allow_request(self, provider: str) -> bool:
        """Check if request is allowed to this provider based on circuit state."""
        ...

    async def provider_state(self, provider: str) -> CircuitBreakerState | None:
        """Get current circuit state for a provider."""
        ...

    async def reset(self, provider: str) -> bool:
        """Reset circuit breaker to CLOSED for a provider. Returns True if found."""
        ...

    async def trip(self, provider: str) -> bool:
        """Manually trip (OPEN) the circuit for a provider. Returns True if found."""
        ...

    async def half_open(self, provider: str) -> bool:
        """Manually set a provider to HALF_OPEN for probe testing."""
        ...

    async def close(self, provider: str) -> bool:
        """Manually close the circuit for a provider. Returns True if found."""
        ...

    async def statistics(self) -> dict[str, Any]:
        """Aggregate circuit breaker statistics across all providers."""
        ...

    async def all_states(self) -> dict[str, CircuitBreakerState]:
        """Return circuit state for all tracked providers."""
        ...

    async def healthy_providers(self) -> list[str]:
        """Return list of providers currently accepting traffic (CLOSED or HALF_OPEN)."""
        ...

    async def open_providers(self) -> list[str]:
        """Return list of providers with OPEN circuits."""
        ...


# ── Sliding Window Failure Tracker ──


class _SlidingWindow:
    """Sliding-window failure tracker using a deque of timestamps."""

    __slots__ = ("_window", "_max_size")

    def __init__(self, max_size: int = 10) -> None:
        self._window: deque[float] = deque(maxlen=max_size)
        self._max_size = max_size

    def add(self, value: float) -> None:
        self._window.append(value)

    def count_in_window(self, since: float) -> int:
        """Count entries with timestamp > since."""
        now = time.monotonic()
        return sum(1 for t in self._window if now - t < since)

    @property
    def total(self) -> int:
        return len(self._window)

    @property
    def full(self) -> bool:
        return len(self._window) >= self._max_size

    def clear(self) -> None:
        self._window.clear()


# ── Internal Mutable Provider State ──


@dataclass
class _ProviderState:
    """Mutable runtime state for a single provider's circuit breaker."""

    provider: str
    config: CircuitBreakerConfig = field(default_factory=lambda: DEFAULT_CONFIG)

    # State machine
    state: FailoverState = FailoverState.CLOSED

    # Counters
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    total_requests: int = 0
    last_failure_time: datetime | None = None
    last_success_time: datetime | None = None
    circuit_open_until: datetime | None = None
    half_open_attempts: int = 0
    half_open_probe_successes: int = 0

    # Latency tracking
    total_latency_ms: float = 0.0
    latency_sample_count: int = 0

    # Failure type counters
    timeout_count: int = 0
    http_failure_count: int = 0
    auth_failure_count: int = 0
    rate_limit_failure_count: int = 0
    network_failure_count: int = 0
    unavailable_count: int = 0

    # Sliding window for failure rate calculation
    failures_window: _SlidingWindow = field(default_factory=lambda: _SlidingWindow(10))
    successes_window: _SlidingWindow = field(default_factory=lambda: _SlidingWindow(10))

    # Uptime tracking
    first_seen: float = 0.0
    last_state_change: float = 0.0
    total_trip_count: int = 0
    total_recovery_count: int = 0
    total_time_spent_open: float = 0.0

    @property
    def failure_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return round(self.failure_count / total, 4)

    @property
    def average_latency_ms(self) -> float:
        if self.latency_sample_count == 0:
            return 0.0
        return round(self.total_latency_ms / self.latency_sample_count, 2)

    @property
    def uptime_ratio(self) -> float:
        if self.first_seen == 0:
            return 0.0
        elapsed = time.monotonic() - self.first_seen
        if elapsed <= 0:
            return 1.0
        open_ratio = self.total_time_spent_open / elapsed
        return round(max(0.0, 1.0 - open_ratio), 4)

    def snapshot(self) -> CircuitBreakerState:
        return CircuitBreakerState(
            provider=self.provider,
            state=self.state,
            failure_count=self.failure_count,
            success_count=self.success_count,
            consecutive_failures=self.consecutive_failures,
            last_failure=self.last_failure_time,
            last_success=self.last_success_time,
            circuit_open_until=self.circuit_open_until,
            half_open_attempts=self.half_open_attempts,
            half_open_probe_successes=self.half_open_probe_successes,
            config=self.config,
        )

    def metric_snapshot(self) -> ProviderCircuitMetrics:
        return ProviderCircuitMetrics(
            success_count=self.success_count,
            failure_count=self.failure_count,
            consecutive_failures=self.consecutive_failures,
            failure_rate=self.failure_rate,
            last_failure=self.last_failure_time,
            last_success=self.last_success_time,
            average_latency_ms=self.average_latency_ms,
            timeout_count=self.timeout_count,
            http_failures=self.http_failure_count,
            authentication_failures=self.auth_failure_count,
            rate_limit_failures=self.rate_limit_failure_count,
            network_failures=self.network_failure_count,
            provider_unavailable_count=self.unavailable_count,
        )

    def should_trip(self) -> bool:
        """Check if the circuit should transition from CLOSED to OPEN."""
        if self.total_requests < self.config.minimum_request_count:
            return False
        if self.consecutive_failures >= self.config.failure_threshold:
            return True
        # Sliding window check
        if self.failures_window.full:
            recent_failures = self.failures_window.count_in_window(60.0)
            recent_successes = self.successes_window.count_in_window(60.0)
            total_recent = recent_failures + recent_successes
            if total_recent >= self.config.minimum_request_count:
                rate = recent_failures / max(total_recent, 1)
                threshold = self.config.failure_threshold / max(self.config.sliding_window_size, 1)
                if rate >= threshold and recent_failures >= self.config.failure_threshold:
                    return True
        return False


# ── Concrete Implementation ──


class CircuitBreakerEngineImpl:
    """Production Circuit Breaker Engine.

    Implements the standard three-state machine per provider:

        CLOSED → (failure threshold exceeded) → OPEN
        OPEN → (recovery timeout expires) → HALF_OPEN
        HALF_OPEN → (probe success) → CLOSED
        HALF_OPEN → (probe fails) → OPEN

    All mutable state is protected by ``asyncio.Lock``.
    """

    def __init__(
        self,
        event_bus: Any | None = None,
        global_config: CircuitBreakerConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._global_config = global_config or DEFAULT_CONFIG
        self._lock = asyncio.Lock()
        self._started = False
        self._start_time: float = 0.0

        # Per-provider state
        self._providers: dict[str, _ProviderState] = {}

        # Observability counters
        self._trip_count_total = 0
        self._recovery_count_total = 0
        self._total_recovery_time = 0.0
        self._state_transitions: dict[str, int] = {}

    # ── Lifecycle ──

    async def initialize(self) -> None:
        log.info("CircuitBreakerEngine initializing")

    async def start(self) -> None:
        self._started = True
        self._start_time = time.monotonic()
        log.info("CircuitBreakerEngine started")

    async def stop(self) -> None:
        self._started = False
        log.info("CircuitBreakerEngine stopped")

    async def dispose(self) -> None:
        await self.stop()
        async with self._lock:
            self._providers.clear()
            self._trip_count_total = 0
            self._recovery_count_total = 0
        log.info("CircuitBreakerEngine disposed")

    async def health(self) -> dict[str, Any]:
        async with self._lock:
            open_count = sum(
                1 for p in self._providers.values() if p.state == FailoverState.CIRCUIT_OPEN
            )
        return {
            "status": "healthy" if self._started else "stopped",
            "started": self._started,
            "tracked_providers": len(self._providers),
            "open_circuits": open_count,
        }

    async def ready(self) -> bool:
        return self._started

    async def metadata(self) -> dict[str, Any]:
        return {
            "type": "CircuitBreakerEngineImpl",
            "version": "1.0.0",
            "started": self._started,
            "tracked_providers": len(self._providers),
            "global_config": {
                "failure_threshold": self._global_config.failure_threshold,
                "minimum_request_count": self._global_config.minimum_request_count,
                "recovery_timeout_seconds": self._global_config.recovery_timeout_seconds,
                "half_open_probe_count": self._global_config.half_open_probe_count,
                "sliding_window_size": self._global_config.sliding_window_size,
            },
        }

    async def dependencies(self) -> list[str]:
        return []

    async def capabilities(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "circuit_breaker_state_machine",
                "description": "CLOSED/OPEN/HALF_OPEN state transitions",
            },
            {
                "name": "failure_tracking",
                "description": "Per-provider failure type classification and counting",
            },
            {
                "name": "sliding_window_rate_calc",
                "description": "Sliding-window failure rate calculation",
            },
            {"name": "probe_traffic_control", "description": "HALF_OPEN probe traffic limiting"},
            {
                "name": "observability",
                "description": "Trip count, recovery count, availability, latency metrics",
            },
        ]

    # ── Internal helpers ──

    def _get_or_create(self, provider: str) -> _ProviderState:
        if provider not in self._providers:
            now = time.monotonic()
            self._providers[provider] = _ProviderState(
                provider=provider,
                config=self._global_config,
                state=FailoverState.CLOSED,
                first_seen=now,
                last_state_change=now,
            )
        return self._providers[provider]

    async def _transition(self, provider: str, to_state: FailoverState, reason: str = "") -> None:
        ps = self._get_or_create(provider)
        old = ps.state
        if old == to_state:
            return
        ps.state = to_state
        ps.last_state_change = time.monotonic()
        key = f"{old.value}→{to_state.value}"
        self._state_transitions[key] = self._state_transitions.get(key, 0) + 1
        log.info("Circuit %s: %s → %s (%s)", provider, old.value, to_state.value, reason)

        # Publish event
        if to_state == FailoverState.CIRCUIT_OPEN:
            self._trip_count_total += 1
            ps.total_trip_count += 1
            ps.circuit_open_until = datetime.now(UTC) + timedelta(
                seconds=ps.config.recovery_timeout_seconds
            )
            await self._publish(
                Topic.PROVIDER_CIRCUIT_OPENED,
                {
                    "provider": provider,
                    "reason": reason,
                    "failure_count": ps.failure_count,
                    "consecutive_failures": ps.consecutive_failures,
                    "recovery_timeout_seconds": ps.config.recovery_timeout_seconds,
                },
            )
        elif to_state == FailoverState.CIRCUIT_HALF_OPEN:
            ps.half_open_attempts = 0
            ps.half_open_probe_successes = 0
            await self._publish(
                Topic.PROVIDER_CIRCUIT_HALF_OPEN,
                {
                    "provider": provider,
                    "reason": reason,
                    "failure_count": ps.failure_count,
                },
            )
        elif to_state == FailoverState.CLOSED:
            if old == FailoverState.CIRCUIT_HALF_OPEN:
                self._recovery_count_total += 1
                ps.total_recovery_count += 1
            ps.consecutive_failures = 0
            ps.half_open_attempts = 0
            ps.half_open_probe_successes = 0
            ps.failures_window.clear()
            await self._publish(
                Topic.PROVIDER_CIRCUIT_CLOSED,
                {
                    "provider": provider,
                    "reason": reason,
                },
            )

    # ── Public API ──

    async def record_success(self, provider: str, latency_ms: float = 0.0) -> None:
        if not self._started:
            return
        async with self._lock:
            ps = self._get_or_create(provider)
            ps.success_count += 1
            ps.total_requests += 1
            ps.consecutive_failures = 0
            ps.last_success_time = datetime.now(UTC)
            ps.successes_window.add(time.monotonic())
            if latency_ms > 0:
                ps.total_latency_ms += latency_ms
                ps.latency_sample_count += 1

            # HALF_OPEN → CLOSED transition
            if ps.state == FailoverState.CIRCUIT_HALF_OPEN:
                ps.half_open_probe_successes += 1
                if ps.half_open_probe_successes >= ps.config.half_open_probe_count:
                    await self._transition(provider, FailoverState.CLOSED, "probe_success")
            elif ps.state == FailoverState.CLOSED:
                # Check if we should stay CLOSED (reduced failure rate)
                pass

        await self._publish(
            Topic.PROVIDER_SUCCESS_RECORDED,
            {
                "provider": provider,
                "state": ps.state.value,
                "success_count": ps.success_count,
                "latency_ms": round(latency_ms, 2),
            },
        )

    async def record_failure(
        self, provider: str, failure_type: str = "unknown", latency_ms: float = 0.0
    ) -> None:
        if not self._started:
            return
        async with self._lock:
            ps = self._get_or_create(provider)
            ps.failure_count += 1
            ps.total_requests += 1
            ps.consecutive_failures += 1
            ps.last_failure_time = datetime.now(UTC)
            ps.failures_window.add(time.monotonic())

            # Classify failure type
            ft = failure_type.lower()
            if ft in ("timeout", "deadline_exceeded"):
                ps.timeout_count += 1
            elif ft in ("http", "http_error", "http_5xx", "http_4xx"):
                ps.http_failure_count += 1
            elif ft in ("auth", "authentication", "unauthorized", "forbidden"):
                ps.auth_failure_count += 1
            elif ft in ("rate_limit", "rate_limited", "too_many_requests", "quota"):
                ps.rate_limit_failure_count += 1
            elif ft in ("network", "connection", "dns", "timeout"):
                ps.network_failure_count += 1
            elif ft in ("unavailable", "service_unavailable", "down", "503"):
                ps.unavailable_count += 1

            if latency_ms > 0:
                ps.total_latency_ms += latency_ms
                ps.latency_sample_count += 1

            # State transitions
            if ps.state == FailoverState.CLOSED and ps.should_trip():
                await self._transition(
                    provider, FailoverState.CIRCUIT_OPEN, "failure_threshold_exceeded"
                )
            elif ps.state == FailoverState.CIRCUIT_HALF_OPEN:
                await self._transition(provider, FailoverState.CIRCUIT_OPEN, "probe_failed")

        await self._publish(
            Topic.PROVIDER_FAILURE_RECORDED,
            {
                "provider": provider,
                "failure_type": failure_type,
                "state": ps.state.value,
                "failure_count": ps.failure_count,
                "consecutive_failures": ps.consecutive_failures,
            },
        )

    async def allow_request(self, provider: str) -> bool:
        if not self._started:
            return True
        async with self._lock:
            ps = self._get_or_create(provider)

            if ps.state == FailoverState.CLOSED:
                return True

            if ps.state == FailoverState.CIRCUIT_OPEN:
                # Check recovery timeout
                now = datetime.now(UTC)
                if ps.circuit_open_until and now >= ps.circuit_open_until:
                    await self._transition(
                        provider, FailoverState.CIRCUIT_HALF_OPEN, "recovery_timeout"
                    )
                    return True
                return False

            if ps.state == FailoverState.CIRCUIT_HALF_OPEN:
                if ps.half_open_attempts < ps.config.half_open_probe_count:
                    ps.half_open_attempts += 1
                    return True
                return False

            return True

    async def provider_state(self, provider: str) -> CircuitBreakerState | None:
        async with self._lock:
            ps = self._providers.get(provider)
            if ps is None:
                return None
            return ps.snapshot()

    async def reset(self, provider: str) -> bool:
        async with self._lock:
            if provider not in self._providers:
                return False
            ps = self._providers[provider]
            was_open = ps.state == FailoverState.CIRCUIT_OPEN
            # Reset all counters
            new_ps = _ProviderState(provider=provider, config=ps.config)
            new_ps.first_seen = ps.first_seen
            self._providers[provider] = new_ps
            if was_open:
                self._recovery_count_total += 1
            return True

    async def trip(self, provider: str) -> bool:
        async with self._lock:
            self._get_or_create(provider)
            await self._transition(provider, FailoverState.CIRCUIT_OPEN, "manual_trip")
            return True

    async def half_open(self, provider: str) -> bool:
        async with self._lock:
            self._get_or_create(provider)
            await self._transition(provider, FailoverState.CIRCUIT_HALF_OPEN, "manual_half_open")
            return True

    async def close(self, provider: str) -> bool:
        async with self._lock:
            self._get_or_create(provider)
            await self._transition(provider, FailoverState.CLOSED, "manual_close")
            return True

    async def statistics(self) -> dict[str, Any]:
        async with self._lock:
            states = {t.value: 0 for t in FailoverState}
            total_latency = 0.0
            latency_samples = 0
            for ps in self._providers.values():
                states[ps.state.value] = states.get(ps.state.value, 0) + 1
                total_latency += ps.total_latency_ms
                latency_samples += ps.latency_sample_count
            uptime = time.monotonic() - self._start_time if self._started else 0.0
            total_failures = sum(ps.failure_count for ps in self._providers.values())
            total_successes = sum(ps.success_count for ps in self._providers.values())
            total_trips = sum(ps.total_trip_count for ps in self._providers.values())
            total_recoveries = sum(ps.total_recovery_count for ps in self._providers.values())
            return {
                "tracked_providers": len(self._providers),
                "state_distribution": states,
                "total_failures": total_failures,
                "total_successes": total_successes,
                "total_trips": total_trips,
                "total_recoveries": total_recoveries,
                "avg_latency_ms": round(total_latency / max(latency_samples, 1), 2),
                "engine_uptime_seconds": round(uptime, 2),
                "state_transitions": dict(self._state_transitions),
            }

    async def all_states(self) -> dict[str, CircuitBreakerState]:
        async with self._lock:
            return {p: ps.snapshot() for p, ps in self._providers.items()}

    async def healthy_providers(self) -> list[str]:
        async with self._lock:
            return [
                p
                for p, ps in self._providers.items()
                if ps.state != FailoverState.CIRCUIT_OPEN and ps.state != FailoverState.IDLE
            ]

    async def open_providers(self) -> list[str]:
        async with self._lock:
            return [
                p for p, ps in self._providers.items() if ps.state == FailoverState.CIRCUIT_OPEN
            ]

    async def provider_metrics(self, provider: str) -> ProviderCircuitMetrics | None:
        async with self._lock:
            ps = self._providers.get(provider)
            if ps is None:
                return None
            return ps.metric_snapshot()

    # ── EventBus helper ──

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            envelope = EventEnvelope(
                type=topic.value,
                source="omniroute.circuit_breaker",
                topic=topic.value,
                payload=payload,
            )
            await self._event_bus.publish(envelope)
        except Exception:
            log.warning("Failed to publish event %s", topic.value, exc_info=True)


__all__ = [
    "CircuitBreakerPort",
    "CircuitBreakerEngineImpl",
    "_ProviderState",
    "_SlidingWindow",
]
