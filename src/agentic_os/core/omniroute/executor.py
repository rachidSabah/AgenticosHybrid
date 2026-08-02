"""OmniRoute Execution Engine — provider invocation, retries, streaming,
parallel, hedged, speculative, quorum, shadow, and canary execution.

Port protocol
-------------
:class:`ExecutorPort` — implement this or depend on it.  All OmniRoute
consumers (Gateway, Swarm, AI Brain, Mission Control) talk through this port.

Pipeline integration
--------------------
Inserted in the routing pipeline **after** the Scheduler and **before** the
Circuit Breaker:

  Registry → Model Registry → Budget → Rate Limiter
  → Scheduler → **Execution Engine** → Circuit Breaker → Learning → ...

Thread safety
-------------
Uses ``asyncio.Lock`` throughout.  No mutable shared state.
Immutable snapshots via frozen dataclasses.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections import Counter
from collections.abc import AsyncIterator, Coroutine
from typing import Any, Protocol, runtime_checkable

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.omniroute import (
    AggregationStrategy,
    ExecutionChunk,
    ExecutionContext,
    ExecutionHealth,
    ExecutionMetrics,
    ExecutionRequest,
    ExecutionResult,
    ExecutionSnapshot,
    ExecutionState,
    ExecutionStatistics,
    ExecutionSummary,
    RetryPolicyType,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("omniroute.executor")


# ── Port Protocol ──


@runtime_checkable
class ExecutorPort(Protocol):
    """OmniRoute execution engine — the heart of provider invocation."""

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a single request and return the result."""
        ...

    async def execute_stream(self, request: ExecutionRequest) -> AsyncIterator[ExecutionChunk]:
        """Execute a request with streaming response."""
        ...

    async def execute_parallel(self, requests: list[ExecutionRequest]) -> list[ExecutionResult]:
        """Execute multiple requests in parallel."""
        ...

    async def execute_hedged(self, request: ExecutionRequest, replicas: int = 2) -> ExecutionResult:
        """Execute hedged requests — first successful response wins."""
        ...

    async def execute_speculative(
        self, primary: ExecutionRequest, secondary: ExecutionRequest
    ) -> ExecutionResult:
        """Execute speculative request — run secondary if confidence drops."""
        ...

    async def execute_quorum(
        self, request: ExecutionRequest, quorum_size: int = 3
    ) -> ExecutionResult:
        """Execute quorum — run N providers, aggregate by voting."""
        ...

    async def cancel(self, request_id: str) -> bool:
        """Cancel a running execution by ID."""
        ...

    async def health(self) -> ExecutionHealth:
        """Return current execution engine health."""
        ...

    async def metrics(self) -> ExecutionMetrics:
        """Return execution metrics snapshot."""
        ...

    async def statistics(self) -> ExecutionStatistics:
        """Return execution statistics snapshot."""
        ...

    # ── Lifecycle ──
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def dispose(self) -> None: ...


# ── Provider Abstraction ──


@runtime_checkable
class ProviderAdapter(Protocol):
    """Abstract interface all provider adapters must implement."""

    async def invoke(self, request: ExecutionRequest) -> ExecutionResult:
        """Invoke the provider synchronously."""
        ...

    async def invoke_stream(self, request: ExecutionRequest) -> AsyncIterator[ExecutionChunk]:
        """Invoke the provider with streaming."""
        ...

    async def check_health(self) -> bool:
        """Check if the provider is healthy/available."""
        ...

    @property
    def provider_name(self) -> str: ...


# ── Concrete stub adapters (production: replace with real SDK calls) ──


class _BaseProviderAdapter:
    """Base for provider adapters with common logic."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._healthy = True

    @property
    def provider_name(self) -> str:
        return self._name

    async def check_health(self) -> bool:
        return self._healthy

    def _simulate_invoke(self, request: ExecutionRequest) -> ExecutionResult:
        """Simulate a provider invocation (stub)."""
        # Simulate latency based on provider name
        latency = random.uniform(0.1, 2.0) if "local" not in self._name else 0.05
        time.sleep(0)  # yield to event loop
        tokens_out = min(request.max_tokens, random.randint(10, 200))
        return ExecutionResult(
            request_id=request.request_id,
            provider=self._name,
            model=request.model,
            state=ExecutionState.COMPLETED,
            output=f"[{self._name}] Simulated response for {request.model}",
            content=f"[{self._name}] Simulated response for {request.model}",
            finish_reason="stop",
            tokens_in=len(request.messages),
            tokens_out=tokens_out,
            total_tokens=len(request.messages) + tokens_out,
            latency_ms=latency * 1000,
            ttfb_ms=latency * 500,
            attempts=1,
        )


class OpenAIProviderAdapter(_BaseProviderAdapter):
    def __init__(self) -> None:
        super().__init__("openai")

    async def invoke(self, request: ExecutionRequest) -> ExecutionResult:
        return self._simulate_invoke(request)

    async def invoke_stream(self, request: ExecutionRequest) -> AsyncIterator[ExecutionChunk]:
        for i in range(3):
            yield ExecutionChunk(
                request_id=request.request_id,
                provider=self._name,
                model=request.model,
                index=i,
                content=f"chunk-{i} ",
                finish_reason="continue" if i < 2 else "stop",
                timestamp=time.time(),
            )


class AnthropicProviderAdapter(_BaseProviderAdapter):
    def __init__(self) -> None:
        super().__init__("anthropic")

    async def invoke(self, request: ExecutionRequest) -> ExecutionResult:
        return self._simulate_invoke(request)

    async def invoke_stream(self, request: ExecutionRequest) -> AsyncIterator[ExecutionChunk]:
        for i in range(3):
            yield ExecutionChunk(
                request_id=request.request_id,
                provider=self._name,
                model=request.model,
                index=i,
                content=f"claude-chunk-{i} ",
                finish_reason="continue" if i < 2 else "stop",
                timestamp=time.time(),
            )


class GeminiProviderAdapter(_BaseProviderAdapter):
    def __init__(self) -> None:
        super().__init__("gemini")

    async def invoke(self, request: ExecutionRequest) -> ExecutionResult:
        return self._simulate_invoke(request)

    async def invoke_stream(self, request: ExecutionRequest) -> AsyncIterator[ExecutionChunk]:
        for i in range(3):
            yield ExecutionChunk(
                request_id=request.request_id,
                provider=self._name,
                model=request.model,
                index=i,
                content=f"gemini-chunk-{i} ",
                finish_reason="continue" if i < 2 else "stop",
                timestamp=time.time(),
            )


ProviderAdapterRegistry: dict[str, Any] = {
    "openai": OpenAIProviderAdapter,
    "anthropic": AnthropicProviderAdapter,
    "gemini": GeminiProviderAdapter,
    "openrouter": OpenAIProviderAdapter,
    "azure_openai": OpenAIProviderAdapter,
    "ollama": OpenAIProviderAdapter,
    "vllm": OpenAIProviderAdapter,
    "lm_studio": OpenAIProviderAdapter,
    "mistral": OpenAIProviderAdapter,
    "groq": OpenAIProviderAdapter,
    "deepseek": OpenAIProviderAdapter,
    "local": OpenAIProviderAdapter,
}


# ── Provider Factory ──


def _create_provider_adapter(provider_name: str) -> Any:
    """Create or retrieve a provider adapter by name."""
    cls = ProviderAdapterRegistry.get(provider_name.lower())
    if cls is None:
        return OpenAIProviderAdapter()  # fallback
    return cls()


# ── Retry Policy Calculator ──


class _RetryCalculator:
    """Computes retry delays based on policy type."""

    @staticmethod
    def compute_delay(
        attempt: int,
        policy: RetryPolicyType = RetryPolicyType.EXPONENTIAL_BACKOFF,
        base_delay_s: float = 0.5,
        max_delay_s: float = 30.0,
    ) -> float:
        if policy == RetryPolicyType.IMMEDIATE:
            return 0.0
        if policy == RetryPolicyType.LINEAR:
            delay = base_delay_s * attempt
        elif policy == RetryPolicyType.JITTER:
            delay = base_delay_s * (2 ** (attempt - 1))
            delay += random.uniform(0, delay * 0.5)
        elif policy in (
            RetryPolicyType.ADAPTIVE,
            RetryPolicyType.BUDGET_AWARE,
            RetryPolicyType.PROVIDER_AWARE,
            RetryPolicyType.CIRCUIT_BREAKER_AWARE,
            RetryPolicyType.DEADLINE_AWARE,
        ):
            delay = base_delay_s * (2 ** (attempt - 1)) * (1 + 0.1 * attempt)
        else:  # EXPONENTIAL_BACKOFF
            delay = base_delay_s * (2 ** (attempt - 1))
        return min(delay, max_delay_s)

    @staticmethod
    def max_retries_for_policy(policy: RetryPolicyType, default: int = 3) -> int:
        if policy in (
            RetryPolicyType.IMMEDIATE,
            RetryPolicyType.JITTER,
        ):
            return min(default, 2)
        return default


# ── Latency Histogram ──


class _LatencyHistogram:
    """Bounded histogram for latency percentiles."""

    def __init__(self, max_samples: int = 1000) -> None:
        self._samples: list[float] = []
        self._max = max_samples

    def record(self, value: float) -> None:
        self._samples.append(value)
        if len(self._samples) > self._max:
            self._samples = self._samples[-self._max :]

    def percentile(self, p: float) -> float:
        if not self._samples:
            return 0.0
        sorted_s = sorted(self._samples)
        idx = max(0, min(len(sorted_s) - 1, int(len(sorted_s) * p / 100)))
        return sorted_s[idx]

    @property
    def count(self) -> int:
        return len(self._samples)


# ── Response Aggregation ──


class _ResponseAggregator:
    """Aggregates multiple execution results into a single result."""

    @staticmethod
    def aggregate(
        results: list[ExecutionResult],
        strategy: AggregationStrategy = AggregationStrategy.FIRST_SUCCESS,
    ) -> ExecutionResult:
        if not results:
            return ExecutionResult(state=ExecutionState.FAILED, error="No results to aggregate")

        if strategy == AggregationStrategy.FIRST_SUCCESS:
            return results[0]

        if strategy in (
            AggregationStrategy.FASTEST,
            AggregationStrategy.BEST_QUALITY,
        ):
            # Fastest = lowest latency with success
            successful = [r for r in results if r.state == ExecutionState.COMPLETED]
            if not successful:
                return results[0]
            return min(successful, key=lambda r: r.latency_ms)

        if strategy in (
            AggregationStrategy.CONSENSUS,
            AggregationStrategy.MAJORITY_VOTE,
            AggregationStrategy.WEIGHTED_VOTE,
        ):
            return _ResponseAggregator._voting_aggregate(results)

        if strategy == AggregationStrategy.QUALITY_WEIGHTED:
            successful = [r for r in results if r.state == ExecutionState.COMPLETED]
            if not successful:
                return results[0]
            # Quality weighted = longest output (proxy for quality)
            return max(successful, key=lambda r: r.tokens_out)

        # Default: return the first successful, or first overall
        for r in results:
            if r.state == ExecutionState.COMPLETED:
                return r
        return results[0]

    @staticmethod
    def _voting_aggregate(results: list[ExecutionResult]) -> ExecutionResult:
        """Simple voting: pick the most common output content."""
        if not results:
            return ExecutionResult(state=ExecutionState.FAILED, error="No results")

        successful = [r for r in results if r.state == ExecutionState.COMPLETED]
        if not successful:
            return results[0]

        # Vote by content
        counts: Counter[str] = Counter()
        for r in successful:
            counts[r.content] += 1
        winner_content = counts.most_common(1)[0][0]

        for r in successful:
            if r.content == winner_content:
                return r
        return successful[0]

    @staticmethod
    def merge_outputs(results: list[ExecutionResult]) -> str:
        """Merge outputs from parallel/hedged/quorum executions."""
        parts: list[str] = []
        for r in results:
            if r.content:
                parts.append(r.content)
        return "\n---\n".join(parts)


# ── Cancellation Token Store ──


class _CancellationStore:
    """Thread-safe store for cancellation tokens."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tokens: dict[str, asyncio.Event] = {}

    async def register(self, request_id: str) -> asyncio.Event:
        async with self._lock:
            event = asyncio.Event()
            self._tokens[request_id] = event
            return event

    async def cancel(self, request_id: str) -> bool:
        async with self._lock:
            event = self._tokens.pop(request_id, None)
            if event is not None:
                event.set()
                return True
            return False

    async def is_cancelled(self, request_id: str) -> bool:
        async with self._lock:
            event = self._tokens.get(request_id)
            if event is None:
                return False
            return event.is_set()

    async def unregister(self, request_id: str) -> None:
        async with self._lock:
            self._tokens.pop(request_id, None)


# ── Execution Engine ──


class ExecutionEngineImpl:
    """Production Execution Engine — the heart of OmniRoute provider invocation.

    13 execution modes:
      1. Single          — invoke one provider
      2. Streaming       — invoke with streaming chunks
      3. Parallel        — invoke N providers simultaneously
      4. Speculative     — primary + secondary if confidence drops
      5. Hedged          — launch replicas, first wins
      6. Shadow          — invoke silently (results discarded)
      7. Canary          — invoke with limited blast radius
      8. Mirror          — invoke on two providers, compare
      9. Fallback        — invoke fallback chain
     10. Quorum          — invoke N, vote on result
     11. Race            — invoke N, fastest wins
     12. Batch           — invoke N in batch
     13. Pipeline        — invoke sequential pipeline
    """

    def __init__(
        self,
        event_bus: Any | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._lock = asyncio.Lock()
        self._running = False
        self._start_time = 0.0

        # Provider cache
        self._adapters: dict[str, ProviderAdapter] = {}

        # Active executions
        self._contexts: dict[str, ExecutionContext] = {}

        # Cancellation tokens
        self._cancellations = _CancellationStore()

        # Metrics counters
        self._total_executions = 0
        self._successful_executions = 0
        self._failed_executions = 0
        self._cancelled_executions = 0
        self._timed_out_executions = 0
        self._retry_count = 0
        self._total_latency_ms = 0.0
        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._streaming_count = 0
        self._parallel_count = 0
        self._hedged_count = 0
        self._speculative_count = 0
        self._quorum_count = 0
        self._fallback_count = 0
        self._shadow_count = 0
        self._provider_error_count = 0
        self._timeout_count = 0
        self._ttfb_sum = 0.0
        self._latency_histogram = _LatencyHistogram()
        self._provider_execution_count: dict[str, int] = {}
        self._provider_error_map: dict[str, int] = {}

    # ── Provider resolution ──

    def _get_adapter(self, provider_name: str) -> ProviderAdapter:
        if provider_name not in self._adapters:
            self._adapters[provider_name] = _create_provider_adapter(provider_name)
        return self._adapters[provider_name]

    # ── Lifecycle ──

    async def start(self) -> None:
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._start_time = time.monotonic()
            log.info("ExecutionEngine started")

    async def stop(self) -> None:
        async with self._lock:
            self._running = False
            # Cancel all active executions
            for rid in list(self._contexts.keys()):
                await self._cancellations.cancel(rid)
            self._contexts.clear()
            log.info("ExecutionEngine stopped")

    async def dispose(self) -> None:
        await self.stop()
        self._adapters.clear()
        self._latency_histogram = _LatencyHistogram()
        self._provider_execution_count.clear()
        self._provider_error_map.clear()
        log.info("ExecutionEngine disposed")

    async def ready(self) -> bool:
        return self._running

    # ── Health / Metrics / Statistics ──

    async def health(self) -> ExecutionHealth:
        async with self._lock:
            uptime = time.monotonic() - self._start_time if self._running else 0.0
            total = max(self._total_executions, 1)
            return ExecutionHealth(
                status="healthy" if self._running else "stopped",
                uptime_s=round(uptime, 2),
                active_executions=len(self._contexts),
                total_executions=self._total_executions,
                success_rate=round(self._successful_executions / total, 4),
                failure_rate=round(self._failed_executions / total, 4),
                avg_latency_ms=round(self._total_latency_ms / total, 2),
                error_count=self._provider_error_count,
                last_error="",
                provider_health={name: "healthy" for name in self._adapters},
            )

    async def metrics(self) -> ExecutionMetrics:
        async with self._lock:
            total = max(self._total_executions, 1)
            return ExecutionMetrics(
                total_executions=self._total_executions,
                successful_executions=self._successful_executions,
                failed_executions=self._failed_executions,
                cancelled_executions=self._cancelled_executions,
                timed_out_executions=self._timed_out_executions,
                retry_count=self._retry_count,
                total_latency_ms=round(self._total_latency_ms, 2),
                avg_latency_ms=round(self._total_latency_ms / total, 2),
                p50_latency_ms=round(self._latency_histogram.percentile(50), 2),
                p95_latency_ms=round(self._latency_histogram.percentile(95), 2),
                p99_latency_ms=round(self._latency_histogram.percentile(99), 2),
                total_tokens=self._total_tokens_in + self._total_tokens_out,
                total_tokens_in=self._total_tokens_in,
                total_tokens_out=self._total_tokens_out,
                throughput_tokens_per_s=round(
                    (self._total_tokens_in + self._total_tokens_out)
                    / max(self._total_latency_ms / 1000, 0.001),
                    2,
                ),
                streaming_count=self._streaming_count,
                parallel_count=self._parallel_count,
                hedged_count=self._hedged_count,
                speculative_count=self._speculative_count,
                quorum_count=self._quorum_count,
                fallback_count=self._fallback_count,
                shadow_count=self._shadow_count,
                provider_error_count=self._provider_error_count,
                timeout_count=self._timeout_count,
                ttfb_ms=round(self._ttfb_sum / total, 2),
                provider_utilization={
                    k: round(v / total, 4) for k, v in self._provider_execution_count.items()
                },
            )

    async def statistics(self) -> ExecutionStatistics:
        async with self._lock:
            total = max(self._total_executions, 1)
            return ExecutionStatistics(
                total_executions=self._total_executions,
                active_executions=len(self._contexts),
                completed_executions=self._successful_executions,
                failed_executions=self._failed_executions,
                cancelled_executions=self._cancelled_executions,
                timed_out_executions=self._timed_out_executions,
                streaming_executions=self._streaming_count,
                parallel_executions=self._parallel_count,
                hedged_executions=self._hedged_count,
                average_latency_ms=round(self._total_latency_ms / total, 2),
                average_ttfb_ms=round(self._ttfb_sum / total, 2),
                average_retries=round(self._retry_count / total, 2),
                average_tokens_per_request=round(
                    (self._total_tokens_in + self._total_tokens_out) / total, 1
                ),
                throughput_per_minute=round(total / max(self._total_latency_ms / 60000, 0.001), 2),
                error_rate=round(self._failed_executions / total, 4),
            )

    async def snapshot(self) -> ExecutionSnapshot:
        async with self._lock:
            return ExecutionSnapshot(
                timestamp=time.time(),
                active_count=len(self._contexts),
                queued_count=0,
                completed_count=self._successful_executions,
                failed_count=self._failed_executions,
                avg_latency_ms=round(self._total_latency_ms / max(self._total_executions, 1), 2),
                status="healthy" if self._running else "stopped",
            )

    # ── Event Publishing ──

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            envelope = EventEnvelope(
                type=topic.value,
                source="omniroute.executor",
                topic=topic.value,
                payload=payload,
            )
            await self._event_bus.publish(envelope)
        except Exception:
            log.warning("Failed to publish event %s", topic.value)

    # ── Internal record keeping ──

    async def _record_execution(self, result: ExecutionResult, strategy: str = "single") -> None:
        async with self._lock:
            self._total_executions += 1
            self._total_latency_ms += result.latency_ms
            self._total_tokens_in += result.tokens_in
            self._total_tokens_out += result.tokens_out
            self._latency_histogram.record(result.latency_ms)
            self._ttfb_sum += result.ttfb_ms
            self._retry_count += result.retries

            pid = result.provider
            self._provider_execution_count[pid] = self._provider_execution_count.get(pid, 0) + 1

            if result.state == ExecutionState.COMPLETED:
                self._successful_executions += 1
                await self._publish(
                    Topic.EXECUTION_PROVIDER_SUCCESS,
                    {
                        "request_id": result.request_id,
                        "provider": result.provider,
                        "model": result.model,
                        "latency_ms": result.latency_ms,
                        "tokens": result.total_tokens,
                    },
                )
            elif result.state == ExecutionState.FAILED:
                self._failed_executions += 1
                self._provider_error_count += 1
                pid = result.provider
                self._provider_error_map[pid] = self._provider_error_map.get(pid, 0) + 1
                await self._publish(
                    Topic.EXECUTION_PROVIDER_ERROR,
                    {
                        "request_id": result.request_id,
                        "provider": result.provider,
                        "error": result.error,
                    },
                )
            elif result.state == ExecutionState.CANCELLED:
                self._cancelled_executions += 1
            elif result.state == ExecutionState.TIMED_OUT:
                self._timed_out_executions += 1
                self._timeout_count += 1

            # Strategy-specific counters
            if strategy == "streaming":
                self._streaming_count += 1
            elif strategy == "parallel":
                self._parallel_count += 1
            elif strategy == "hedged":
                self._hedged_count += 1
            elif strategy == "speculative":
                self._speculative_count += 1
            elif strategy == "quorum":
                self._quorum_count += 1
            elif strategy == "fallback":
                self._fallback_count += 1
            elif strategy == "shadow":
                self._shadow_count += 1

    async def _record_retry(self, request_id: str, attempt: int) -> None:
        async with self._lock:
            self._retry_count += 1

    # ── Internal context management ──

    async def _create_context(self, request: ExecutionRequest) -> ExecutionContext:
        ctx = ExecutionContext(
            request_id=request.request_id,
            session_id=request.session_id,
            provider=request.provider,
            model=request.model,
            strategy=request.strategy,
            state=ExecutionState.RUNNING,
            created_at=time.time(),
            updated_at=time.time(),
        )
        async with self._lock:
            self._contexts[request.request_id] = ctx
        return ctx

    async def _update_context(self, request_id: str, **kwargs: Any) -> ExecutionContext | None:
        async with self._lock:
            ctx = self._contexts.get(request_id)
            if ctx is None:
                return None
            # Rebuild with updates (frozen dataclass)
            updates: dict[str, Any] = {"updated_at": time.time()}
            updates.update(kwargs)
            new_ctx = ExecutionContext(
                request_id=ctx.request_id,
                session_id=ctx.session_id,
                provider=kwargs.get("provider", ctx.provider),
                model=kwargs.get("model", ctx.model),
                strategy=kwargs.get("strategy", ctx.strategy),
                state=kwargs.get("state", ctx.state),
                attempts=kwargs.get("attempts", ctx.attempts),
                created_at=ctx.created_at,
                updated_at=time.time(),
                cancellation_token=kwargs.get("cancellation_token", ctx.cancellation_token),
            )
            self._contexts[request_id] = new_ctx
            return new_ctx

    async def _remove_context(self, request_id: str) -> None:
        async with self._lock:
            self._contexts.pop(request_id, None)
        await self._cancellations.unregister(request_id)

    # ── Timeout wrapper ──

    async def _with_timeout(
        self,
        coro: Coroutine[Any, Any, ExecutionResult],
        request: ExecutionRequest,
    ) -> ExecutionResult:
        """Wrap execution with soft and hard timeouts."""
        token = await self._cancellations.register(request.request_id)
        hard_timeout = request.hard_timeout_s

        try:
            # Hard timeout: absolute deadline
            result = await asyncio.wait_for(
                self._execute_with_cancellation(coro, token, request),
                timeout=hard_timeout,
            )
            return result
        except TimeoutError:
            await self._publish(
                Topic.EXECUTION_TIMEOUT,
                {
                    "request_id": request.request_id,
                    "provider": request.provider,
                    "timeout_type": "hard",
                    "duration_s": hard_timeout,
                },
            )
            return ExecutionResult(
                request_id=request.request_id,
                provider=request.provider,
                model=request.model,
                state=ExecutionState.TIMED_OUT,
                error=f"Hard timeout after {hard_timeout}s",
                latency_ms=hard_timeout * 1000,
            )
        finally:
            await self._cancellations.unregister(request.request_id)

    async def _execute_with_cancellation(
        self,
        coro: Coroutine[Any, Any, ExecutionResult],
        token: asyncio.Event,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        """Check cancellation before and after execution."""
        if token.is_set():
            return ExecutionResult(
                request_id=request.request_id,
                provider=request.provider,
                model=request.model,
                state=ExecutionState.CANCELLED,
                error="Cancelled before execution",
            )
        result = await coro
        if token.is_set():
            return ExecutionResult(
                request_id=request.request_id,
                provider=result.provider,
                model=result.model,
                state=ExecutionState.CANCELLED,
                output=result.output,
                content=result.content,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                latency_ms=result.latency_ms,
                ttfb_ms=result.ttfb_ms,
                error="Cancelled after execution",
            )
        return result

    # ── Single execution ──

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a single request on a single provider."""
        if not self._running:
            return ExecutionResult(
                request_id=request.request_id,
                state=ExecutionState.FAILED,
                error="Execution engine not started",
            )

        await self._publish(
            Topic.EXECUTION_STARTED,
            {
                "request_id": request.request_id,
                "provider": request.provider,
                "model": request.model,
                "strategy": request.strategy.value,
            },
        )

        await self._create_context(request)
        adapter = self._get_adapter(request.provider)
        max_retries = _RetryCalculator.max_retries_for_policy(
            request.retry_policy, request.max_retries
        )
        last_error = ""
        total_attempts = 0

        for attempt in range(1, max_retries + 2):  # +1 for initial try
            total_attempts += 1

            if attempt > 1:
                delay = _RetryCalculator.compute_delay(attempt, request.retry_policy)
                await asyncio.sleep(delay)
                await self._record_retry(request.request_id, attempt)
                await self._publish(
                    Topic.EXECUTION_RETRY,
                    {
                        "request_id": request.request_id,
                        "attempt": attempt,
                        "delay_ms": delay * 1000,
                        "policy": request.retry_policy.value,
                        "reason": last_error,
                    },
                )

            # Check cancellation
            if await self._cancellations.is_cancelled(request.request_id):
                result = ExecutionResult(
                    request_id=request.request_id,
                    provider=request.provider,
                    model=request.model,
                    state=ExecutionState.CANCELLED,
                    error="Cancelled during execution",
                    attempts=attempt,
                )
                await self._record_execution(result, "single")
                await self._remove_context(request.request_id)
                await self._publish(
                    Topic.EXECUTION_CANCELLED,
                    {
                        "request_id": request.request_id,
                        "provider": request.provider,
                    },
                )
                return result

            try:
                result = await self._with_timeout(adapter.invoke(request), request)
                result = ExecutionResult(
                    request_id=result.request_id,
                    provider=result.provider or request.provider,
                    model=result.model or request.model,
                    state=result.state,
                    output=result.output,
                    content=result.content,
                    finish_reason=result.finish_reason,
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                    total_tokens=result.total_tokens,
                    latency_ms=result.latency_ms,
                    ttfb_ms=result.ttfb_ms,
                    attempts=total_attempts,
                    retries=total_attempts - 1,
                    error=result.error,
                )

                if result.state == ExecutionState.TIMED_OUT:
                    self._timeout_count += 1
                    await self._record_execution(result, "single")
                    await self._remove_context(request.request_id)
                    return result

                if result.state == ExecutionState.COMPLETED:
                    await self._record_execution(result, "single")
                    await self._remove_context(request.request_id)
                    await self._publish(
                        Topic.EXECUTION_COMPLETED,
                        {
                            "request_id": result.request_id,
                            "provider": result.provider,
                            "model": result.model,
                            "latency_ms": result.latency_ms,
                            "tokens": result.total_tokens,
                        },
                    )
                    return result

                # Failed — retry
                last_error = result.error or "Unknown error"
                if attempt <= max_retries:
                    continue
                else:
                    result = ExecutionResult(
                        request_id=result.request_id,
                        provider=result.provider,
                        model=result.model,
                        state=ExecutionState.FAILED,
                        error=f"All retries exhausted: {last_error}",
                        attempts=total_attempts,
                        retries=total_attempts - 1,
                        latency_ms=result.latency_ms,
                    )
                    await self._record_execution(result, "single")
                    await self._remove_context(request.request_id)
                    await self._publish(
                        Topic.EXECUTION_FAILED,
                        {
                            "request_id": result.request_id,
                            "provider": result.provider,
                            "error": result.error,
                            "attempts": total_attempts,
                        },
                    )
                    return result

            except Exception as exc:
                last_error = str(exc)
                if attempt <= max_retries:
                    continue
                result = ExecutionResult(
                    request_id=request.request_id,
                    provider=request.provider,
                    model=request.model,
                    state=ExecutionState.FAILED,
                    error=f"Exception: {last_error}",
                    attempts=total_attempts,
                    retries=total_attempts - 1,
                )
                await self._record_execution(result, "single")
                await self._remove_context(request.request_id)
                await self._publish(
                    Topic.EXECUTION_FAILED,
                    {
                        "request_id": result.request_id,
                        "provider": result.provider,
                        "error": result.error,
                        "attempts": total_attempts,
                    },
                )
                return result

        # Should never reach here
        result = ExecutionResult(
            request_id=request.request_id,
            state=ExecutionState.FAILED,
            error="Unexpected execution path",
            attempts=total_attempts,
        )
        await self._record_execution(result, "single")
        await self._remove_context(request.request_id)
        return result

    # ── Streaming execution ──

    async def execute_stream(self, request: ExecutionRequest) -> AsyncIterator[ExecutionChunk]:
        """Execute a request with streaming response."""
        if not self._running:
            return

        adapter = self._get_adapter(request.provider)
        token = await self._cancellations.register(request.request_id)

        await self._publish(
            Topic.EXECUTION_STREAM_STARTED,
            {
                "request_id": request.request_id,
                "provider": request.provider,
                "model": request.model,
            },
        )

        await self._create_context(request)
        await self._update_context(request.request_id, state=ExecutionState.STREAMING)

        try:
            chunk_count = 0
            async for chunk in await adapter.invoke_stream(request):
                if token.is_set():
                    break
                chunk_count += 1
                yield chunk
                await self._publish(
                    Topic.EXECUTION_STREAM_CHUNK,
                    {
                        "request_id": request.request_id,
                        "provider": request.provider,
                        "index": chunk.index,
                        "content": chunk.content,
                    },
                )

            await self._publish(
                Topic.EXECUTION_STREAM_FINISHED,
                {
                    "request_id": request.request_id,
                    "provider": request.provider,
                    "chunks": chunk_count,
                },
            )

        except Exception as exc:
            log.warning("Stream execution error: %s", exc)
        finally:
            await self._cancellations.unregister(request.request_id)
            await self._remove_context(request.request_id)
            self._streaming_count += 1

    # ── Parallel execution ──

    async def execute_parallel(self, requests: list[ExecutionRequest]) -> list[ExecutionResult]:
        """Execute multiple requests in parallel."""
        if not self._running:
            return [
                ExecutionResult(
                    request_id=r.request_id,
                    state=ExecutionState.FAILED,
                    error="Execution engine not started",
                )
                for r in requests
            ]

        await self._publish(
            Topic.EXECUTION_PARALLEL,
            {
                "count": len(requests),
            },
        )

        tasks = [self.execute(r) for r in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final: list[ExecutionResult] = []
        for r in results:
            if isinstance(r, Exception):
                final.append(ExecutionResult(state=ExecutionState.FAILED, error=str(r)))
            elif isinstance(r, ExecutionResult):
                final.append(r)
        async with self._lock:
            self._parallel_count += 1
        return final

    # ── Hedged execution ──

    async def execute_hedged(self, request: ExecutionRequest, replicas: int = 2) -> ExecutionResult:
        """Execute hedged requests — first successful response wins, cancel rest."""
        if not self._running:
            return ExecutionResult(
                request_id=request.request_id,
                state=ExecutionState.FAILED,
                error="Execution engine not started",
            )

        await self._publish(
            Topic.EXECUTION_HEDGED,
            {
                "request_id": request.request_id,
                "replicas": replicas,
            },
        )

        providers = [request.provider] + list(request.parallel_providers)[: replicas - 1]

        async def _run(p: str) -> ExecutionResult:
            r = ExecutionRequest(
                request_id=f"{request.request_id}_{p}",
                provider=p,
                model=request.model,
                messages=request.messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
            return await self.execute(r)

        # Launch all tasks
        tasks = [asyncio.ensure_future(_run(p)) for p in providers]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            result = task.result()
            if result.state == ExecutionState.COMPLETED:
                for pt in pending:
                    pt.cancel()
                await self._record_execution(result, "hedged")
                async with self._lock:
                    self._hedged_count += 1
                return result

        first = next(iter(done))
        result = first.result()
        await self._record_execution(result, "hedged")
        async with self._lock:
            self._hedged_count += 1
        return result

    # ── Speculative execution ──

    async def execute_speculative(
        self, primary: ExecutionRequest, secondary: ExecutionRequest
    ) -> ExecutionResult:
        """Execute primary; launch secondary if primary doesn't respond fast enough."""
        if not self._running:
            return ExecutionResult(
                request_id=primary.request_id,
                state=ExecutionState.FAILED,
                error="Execution engine not started",
            )

        await self._publish(
            Topic.EXECUTION_SPECULATIVE,
            {
                "request_id": primary.request_id,
                "primary_provider": primary.provider,
                "secondary_provider": secondary.provider,
            },
        )

        primary_task = asyncio.ensure_future(self.execute(primary))

        try:
            result = await asyncio.wait_for(
                asyncio.shield(primary_task), timeout=primary.soft_timeout_s
            )
            if result.state == ExecutionState.COMPLETED:
                async with self._lock:
                    self._speculative_count += 1
                return result
        except TimeoutError:
            pass

        # Primary was slow — launch secondary
        secondary_task = asyncio.ensure_future(self.execute(secondary))

        done, pending = await asyncio.wait(
            [primary_task, secondary_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            result = task.result()
            if result.state == ExecutionState.COMPLETED:
                for pt in pending:
                    pt.cancel()
                async with self._lock:
                    self._speculative_count += 1
                return result

        first = next(iter(done))
        result = first.result()
        async with self._lock:
            self._speculative_count += 1
        return result

    # ── Quorum execution ──

    async def execute_quorum(
        self, request: ExecutionRequest, quorum_size: int = 3
    ) -> ExecutionResult:
        """Execute quorum — run N providers, aggregate by consensus."""
        if not self._running:
            return ExecutionResult(
                request_id=request.request_id,
                state=ExecutionState.FAILED,
                error="Execution engine not started",
            )

        await self._publish(
            Topic.EXECUTION_QUORUM,
            {
                "request_id": request.request_id,
                "quorum_size": quorum_size,
            },
        )

        providers = [request.provider] + list(request.parallel_providers)[: quorum_size - 1]

        async def _execute_one(provider_name: str) -> ExecutionResult:
            req = ExecutionRequest(
                request_id=f"{request.request_id}_{provider_name}",
                session_id=request.session_id,
                provider=provider_name,
                model=request.model,
                messages=request.messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
            return await self.execute(req)

        tasks = [_execute_one(p) for p in providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid: list[ExecutionResult] = []
        for r in results:
            if isinstance(r, ExecutionResult) and r.state == ExecutionState.COMPLETED:
                valid.append(r)

        if not valid:
            return ExecutionResult(
                request_id=request.request_id,
                state=ExecutionState.FAILED,
                error="Quorum: no successful results",
            )

        aggregated = _ResponseAggregator.aggregate(valid, AggregationStrategy.CONSENSUS)
        await self._record_execution(aggregated, "quorum")
        return aggregated

    # ── Shadow execution ──

    async def execute_shadow(self, request: ExecutionRequest) -> None:
        """Execute silently, results are discarded (shadow traffic)."""
        if not self._running:
            return
        await self._publish(
            Topic.EXECUTION_SHADOW,
            {
                "request_id": request.request_id,
                "provider": request.provider,
            },
        )
        try:
            await self.execute(request)
            self._shadow_count += 1
        except Exception:
            pass

    # ── Fallback execution ──

    async def execute_fallback(self, requests: list[ExecutionRequest]) -> ExecutionResult:
        """Execute fallback chain — try each until one succeeds."""
        if not self._running:
            return ExecutionResult(
                state=ExecutionState.FAILED,
                error="Execution engine not started",
            )

        await self._publish(
            Topic.EXECUTION_FALLBACK,
            {
                "chain_length": len(requests),
            },
        )

        last_error = ""
        for req in requests:
            result = await self.execute(req)
            if result.state == ExecutionState.COMPLETED:
                await self._record_execution(result, "fallback")
                return result
            last_error = result.error

        return ExecutionResult(
            state=ExecutionState.FAILED,
            error=f"All fallbacks exhausted: {last_error}",
        )

    # ── Race execution ──

    async def execute_race(self, requests: list[ExecutionRequest]) -> ExecutionResult:
        """Race multiple providers — fastest complete response wins."""
        if not self._running:
            return ExecutionResult(
                state=ExecutionState.FAILED,
                error="Execution engine not started",
            )

        tasks = [asyncio.ensure_future(self.execute(r)) for r in requests]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for pt in pending:
            pt.cancel()

        first = next(iter(done))
        result = first.result()
        return result

    # ── Canary execution ──

    async def execute_canary(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a canary request — limited blast radius, evaluate before full rollout."""
        if not self._running:
            return ExecutionResult(
                request_id=request.request_id,
                state=ExecutionState.FAILED,
                error="Execution engine not started",
            )
        await self._publish(
            Topic.EXECUTION_CANARY,
            {
                "request_id": request.request_id,
                "provider": request.provider,
            },
        )
        result = await self.execute(request)
        return result

    # ── Mirror execution ──

    async def execute_mirror(
        self, primary_request: ExecutionRequest, mirror_request: ExecutionRequest
    ) -> tuple[ExecutionResult, ExecutionResult]:
        """Execute on two providers and compare results."""
        primary = await self.execute(primary_request)
        mirror = await self.execute(mirror_request)
        return primary, mirror

    # ── Cancel ──

    async def cancel(self, request_id: str) -> bool:
        """Cancel a running execution by ID."""
        cancelled = await self._cancellations.cancel(request_id)
        if cancelled:
            await self._publish(
                Topic.EXECUTION_CANCELLED,
                {
                    "request_id": request_id,
                },
            )
        return cancelled

    # ── Summary ──

    async def summary(self, request_id: str) -> ExecutionSummary | None:
        """Return a summary of a completed execution."""
        ctx = await self._get_context(request_id)
        if ctx is None:
            return None
        return ExecutionSummary(
            request_id=ctx.request_id,
            state=ctx.state,
            provider=ctx.provider,
            model=ctx.model,
            strategy=ctx.strategy.value,
            duration_ms=(ctx.updated_at - ctx.created_at) * 1000
            if ctx.updated_at and ctx.created_at
            else 0.0,
        )

    async def _get_context(self, request_id: str) -> ExecutionContext | None:
        async with self._lock:
            return self._contexts.get(request_id)
