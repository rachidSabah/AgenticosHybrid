from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from core.contracts.execution_engine import (
    EngineConfig,
    EngineDiscoveryResult,
    EngineHealthState,
    EngineTelemetry,
    EngineType,
    ExecutionEngineError,
    ExecutionEnginePort,
)
from core.event_bus.bus import EventBus
from core.logging import get_logger
from services.execution_engine.adapters import (
    AiderAdapter,
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
from services.execution_engine.discovery import EngineDiscovery
from services.execution_engine.events import (
    ExecutionEventPublisher,
    publish_engine_discovered,
    publish_engine_enabled,
    publish_engine_disabled,
    publish_engine_registered,
    publish_engine_unregistered,
    publish_route_failover,
    publish_route_selected,
    publish_task_cancelled,
    publish_task_completed,
    publish_task_created,
    publish_task_dispatched,
    publish_task_failed,
    publish_task_progress,
    publish_task_queued,
    publish_task_started,
    publish_task_timeout,
)
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
    CustomRouter,
    RouterRegistry,
    RoutingContext,
    RoutingDecision,
    RoutingStrategy,
)

_log = get_logger(__name__)

__all__ = ["ExecutionEngineManager"]


_ENGINE_ADAPTER_MAP: dict[EngineType, type] = {
    EngineType.CLAUDE_CODE: ClaudeCodeAdapter,
    EngineType.GEMINI_CLI: GeminiCliAdapter,
    EngineType.CODEX_CLI: CodexCliAdapter,
    EngineType.HERMES: HermesAdapter,
    EngineType.OPENHANDS: OpenHandsAdapter,
    EngineType.AIDER: AiderAdapter,
    EngineType.CONTINUE: ContinueAdapter,
    EngineType.CLINE: ClineAdapter,
    EngineType.ROO_CODE: RooCodeAdapter,
    EngineType.LOCAL: LocalEngineAdapter,
    EngineType.CUSTOM: CustomEngineAdapter,
}


class ExecutionEngineManager:
    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus
        self._discovery = EngineDiscovery()
        self._router_registry = RouterRegistry()
        self._engines: dict[str, ExecutionEnginePort] = {}
        self._engine_configs: dict[str, EngineConfig] = {}
        self._engine_health: dict[str, EngineHealthState] = {}
        self._engine_telemetry: dict[str, EngineTelemetry] = {}
        self._tasks: dict[str, ExecutionTask] = {}
        self._sessions: dict[str, ExecutionSession] = {}
        self._metrics: dict[str, ExecutionMetrics] = {}
        self._results: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._initialized = False
        self._event_publisher = ExecutionEventPublisher(bus) if bus else None

    async def initialize(self) -> None:
        if self._initialized:
            return
        discovered = await self._discovery.discover_all()
        for result in discovered:
            if result.found and result.healthy:
                config = EngineConfig(
                    type=result.engine_type,
                    name=result.name,
                    binary_path=result.binary_path,
                    version=result.version,
                )
                try:
                    await self.register_engine(config)
                except Exception as e:
                    _log.warning("Failed to register discovered engine %s: %s", result.name, e)
        self._initialized = True
        _log.info("ExecutionEngineManager initialized with %d engines", len(self._engines))

    async def shutdown(self) -> None:
        async with self._lock:
            for name, engine in self._engines.items():
                try:
                    await engine.shutdown()
                except Exception as e:
                    _log.warning("Error shutting down engine %s: %s", name, e)
            self._engines.clear()
            self._engine_configs.clear()
            self._engine_health.clear()
            self._initialized = False

    async def discover_engines(self) -> list[EngineDiscoveryResult]:
        results = await self._discovery.discover_all()
        for result in results:
            if self._bus:
                await publish_engine_discovered(
                    self._bus, result.engine_type.value, result.name,
                    result.version, result.binary_path,
                )
        return results

    async def register_engine(self, config: EngineConfig) -> ExecutionEnginePort:
        adapter_cls = _ENGINE_ADAPTER_MAP.get(config.type, CustomEngineAdapter)
        engine = adapter_cls(config)
        await engine.initialize(config)
        async with self._lock:
            self._engines[config.name] = engine
            self._engine_configs[config.name] = config
            health = await engine.health_check()
            self._engine_health[config.name] = health
            self._engine_telemetry[config.name] = await engine.telemetry()
            self._metrics[config.name] = ExecutionMetrics(
                engine_type=config.type,
                engine_name=config.name,
            )
        if self._bus:
            await publish_engine_registered(self._bus, config.type.value, config.name)
        _log.info("Registered engine", name=config.name, type=config.type.value)
        return engine

    async def unregister_engine(self, name: str) -> None:
        async with self._lock:
            engine = self._engines.pop(name, None)
            self._engine_configs.pop(name, None)
            self._engine_health.pop(name, None)
            self._engine_telemetry.pop(name, None)
            self._metrics.pop(name, None)
        if engine:
            try:
                await engine.shutdown()
            except Exception as e:
                _log.warning("Error shutting down engine %s: %s", name, e)
        if self._bus:
            await publish_engine_unregistered(self._bus, "", name)

    async def enable_engine(self, name: str) -> None:
        async with self._lock:
            config = self._engine_configs.get(name)
            if config:
                config.enabled = True
        if self._bus:
            await publish_engine_enabled(self._bus, config.type.value if config else "", name)

    async def disable_engine(self, name: str) -> None:
        async with self._lock:
            config = self._engine_configs.get(name)
            if config:
                config.enabled = False
        if self._bus:
            await publish_engine_disabled(self._bus, config.type.value if config else "", name)

    def get_engine(self, name: str) -> ExecutionEnginePort | None:
        return self._engines.get(name)

    def list_engines(self) -> list[dict[str, Any]]:
        result = []
        for name, config in self._engine_configs.items():
            health = self._engine_health.get(name)
            telemetry = self._engine_telemetry.get(name)
            result.append({
                "name": name,
                "type": config.type.value,
                "enabled": config.enabled,
                "version": config.version,
                "healthy": health.healthy if health else False,
                "initialized": health.initialized if health else False,
                "tasks_completed": telemetry.tasks_completed if telemetry else 0,
                "tasks_failed": telemetry.tasks_failed if telemetry else 0,
            })
        return result

    async def get_health(self, name: str) -> EngineHealthState | None:
        engine = self._engines.get(name)
        if not engine:
            return None
        health = await engine.health_check()
        async with self._lock:
            self._engine_health[name] = health
        return health

    async def get_telemetry(self, name: str) -> EngineTelemetry | None:
        engine = self._engines.get(name)
        if not engine:
            return self._engine_telemetry.get(name)
        telemetry = await engine.telemetry()
        async with self._lock:
            self._engine_telemetry[name] = telemetry
        return telemetry

    async def execute(
        self,
        goal: str,
        *,
        engine_name: str | None = None,
        engine_type: EngineType | None = None,
        strategy: RoutingStrategy | str | None = None,
        session_id: str | None = None,
        priority: ExecutionTaskPriority = ExecutionTaskPriority.NORMAL,
        task_input: dict[str, Any] | None = None,
        timeout_s: float = 600.0,
    ) -> ExecutionTask:
        task = ExecutionTask(
            goal=goal,
            priority=priority,
            input=task_input or {},
            session_id=session_id,
            timeout_s=timeout_s,
        )
        async with self._lock:
            self._tasks[task.task_id] = task
        if self._bus:
            await publish_task_created(self._bus, task.task_id, "", goal)

        engine = await self._select_engine(engine_name, engine_type, strategy, goal)
        task.engine_name = engine.name
        task.engine_type = engine.engine_type

        task.status = ExecutionTaskStatus.QUEUED
        if self._bus:
            await publish_task_queued(self._bus, task.task_id, task.engine_type.value)

        await self._execute_on_engine(task, engine)
        return task

    async def execute_plan(self, plan: ExecutionPlan) -> list[ExecutionTask]:
        results = []
        for task in plan.tasks:
            result = await self.execute(
                goal=task.goal,
                engine_type=task.engine_type,
                strategy=plan.routing_strategy,
                session_id=task.session_id,
                priority=task.priority,
                task_input=task.input,
                timeout_s=task.timeout_s,
            )
            results.append(result)
        return results

    async def execute_on_engine(self, task: ExecutionTask, engine_name: str) -> ExecutionTask:
        engine = self._engines.get(engine_name)
        if not engine:
            task.status = ExecutionTaskStatus.FAILED
            task.error = f"Engine '{engine_name}' not found"
            return task
        return await self._execute_on_engine(task, engine)

    async def _execute_on_engine(self, task: ExecutionTask, engine: ExecutionEnginePort) -> ExecutionTask:
        task.status = ExecutionTaskStatus.DISPATCHED
        if self._bus:
            await publish_task_dispatched(self._bus, task.task_id, task.engine_type.value, engine.name)

        try:
            health = await engine.health_check()
            if not health.healthy:
                task.status = ExecutionTaskStatus.FAILED
                task.error = f"Engine {engine.name} is unhealthy"
                return task
        except Exception as e:
            task.status = ExecutionTaskStatus.FAILED
            task.error = f"Health check failed: {e}"
            return task

        task.status = ExecutionTaskStatus.RUNNING
        task.started_at = datetime.now(UTC)
        if self._bus:
            await publish_task_started(self._bus, task.task_id, task.engine_type.value)

        try:
            result = await asyncio.wait_for(
                engine.execute(task),
                timeout=task.timeout_s,
            )
            task.duration_s = time.monotonic() - (task.started_at.timestamp() if task.started_at else 0)
            task.status = ExecutionTaskStatus.COMPLETED
            task.output = result
            task.completed_at = datetime.now(UTC)
            if self._bus:
                await publish_task_completed(self._bus, task.task_id, task.engine_type.value, task.duration_s)
        except asyncio.TimeoutError:
            task.status = ExecutionTaskStatus.TIMEOUT
            task.error = f"Task timed out after {task.timeout_s}s"
            task.completed_at = datetime.now(UTC)
            if self._bus:
                await publish_task_timeout(self._bus, task.task_id, task.engine_type.value)
        except ExecutionEngineError as e:
            task.status = ExecutionTaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now(UTC)
            if self._bus:
                await publish_task_failed(self._bus, task.task_id, task.engine_type.value, str(e))
        except Exception as e:
            task.status = ExecutionTaskStatus.FAILED
            task.error = f"Unexpected error: {e}"
            task.completed_at = datetime.now(UTC)
            if self._bus:
                await publish_task_failed(self._bus, task.task_id, task.engine_type.value, str(e))

        async with self._lock:
            self._tasks[task.task_id] = task
            self._results[task.task_id] = task.output
            self._update_metrics(task)

        return task

    async def cancel_task(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status in (ExecutionTaskStatus.COMPLETED, ExecutionTaskStatus.FAILED,
                                ExecutionTaskStatus.CANCELLED, ExecutionTaskStatus.TIMEOUT):
                return False
            engine = self._engines.get(task.engine_name)

        cancelled = False
        if engine:
            try:
                cancelled = await engine.cancel(task_id)
            except Exception as e:
                _log.warning("Cancel request failed: %s", e)

        async with self._lock:
            task.status = ExecutionTaskStatus.CANCELLED
            task.completed_at = datetime.now(UTC)
            if self._bus:
                await publish_task_cancelled(self._bus, task_id, task.engine_type.value)

        return cancelled

    async def execute_with_failover(
        self,
        goal: str,
        *,
        preferred_engines: list[str],
        fallback_engines: list[str] | None = None,
    ) -> ExecutionTask:
        all_engines = preferred_engines + (fallback_engines or [])
        last_error = None

        for engine_name in all_engines:
            engine = self._engines.get(engine_name)
            if not engine:
                continue
            config = self._engine_configs.get(engine_name)
            if config and not config.enabled:
                continue

            task = ExecutionTask(goal=goal, engine_name=engine_name)
            result = await self._execute_on_engine(task, engine)
            if result.status == ExecutionTaskStatus.COMPLETED:
                return result
            last_error = result.error

            if engine_name in preferred_engines and fallback_engines:
                if self._bus:
                    await publish_route_failover(
                        self._bus, engine_name, fallback_engines[0],
                        f"Failover: {result.error}",
                    )

        task = ExecutionTask(goal=goal, status=ExecutionTaskStatus.FAILED, error=f"All engines failed: {last_error}")
        return task

    async def benchmark_engine(self, engine_name: str, tasks: list[str]) -> ExecutionBenchmarkResult:
        engine = self._engines.get(engine_name)
        if not engine:
            raise ValueError(f"Engine '{engine_name}' not found")

        benchmark = ExecutionBenchmarkResult(
            engine_type=self._engine_configs.get(engine_name, EngineConfig(type=EngineType.CUSTOM, name=engine_name)).type,
            engine_name=engine_name,
            tasks_run=len(tasks),
            started_at=datetime.now(UTC),
        )
        durations = []

        for goal in tasks:
            try:
                task = ExecutionTask(goal=goal, engine_name=engine_name)
                start = time.monotonic()
                await engine.execute(task)
                duration = time.monotonic() - start
                durations.append(duration)
                benchmark.tasks_passed += 1
            except Exception:
                benchmark.tasks_failed += 1

        benchmark.completed_at = datetime.now(UTC)
        benchmark.total_duration_s = sum(durations)
        benchmark.avg_duration_s = benchmark.total_duration_s / max(1, len(durations))
        benchmark.error_rate = benchmark.tasks_failed / max(1, benchmark.tasks_run)

        if durations:
            sorted_d = sorted(durations)
            n = len(sorted_d)
            benchmark.p50_duration_s = sorted_d[n // 2] if n else 0
            benchmark.p95_duration_s = sorted_d[int(n * 0.95)] if n > 0 else 0
            benchmark.p99_duration_s = sorted_d[int(n * 0.99)] if n > 0 else 0

        return benchmark

    def get_task(self, task_id: str) -> ExecutionTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return [t.to_dict() for t in tasks[:limit]]

    async def create_session(self, engine_name: str) -> ExecutionSession:
        session = ExecutionSession(
            engine_type=self._engine_configs.get(engine_name, EngineConfig(type=EngineType.CUSTOM, name=engine_name)).type,
            engine_name=engine_name,
        )
        async with self._lock:
            self._sessions[session.session_id] = session
        if self._bus:
            from services.execution_engine.events import publish_session_created
            await publish_session_created(self._bus, session.session_id, session.engine_type.value)
        return session

    def get_session(self, session_id: str) -> ExecutionSession | None:
        return self._sessions.get(session_id)

    def get_metrics(self, engine_name: str) -> ExecutionMetrics | None:
        return self._metrics.get(engine_name)

    def get_all_metrics(self) -> list[ExecutionMetrics]:
        return list(self._metrics.values())

    async def _select_engine(
        self,
        engine_name: str | None,
        engine_type: EngineType | None,
        strategy: RoutingStrategy | str | None,
        goal: str,
    ) -> ExecutionEnginePort:
        if engine_name:
            engine = self._engines.get(engine_name)
            if engine:
                return engine
            raise ExecutionEngineError(engine_name, f"Engine '{engine_name}' not found")

        available = self._available_engines(engine_type)
        if not available:
            raise ExecutionEngineError("none", "No available engines")

        context = RoutingContext(
            engine_health=dict(self._engine_health),
            engine_telemetry=dict(self._engine_telemetry),
            task_goal=goal,
        )
        decision = self._router_registry.select(available, strategy, context)

        if self._bus:
            await publish_route_selected(
                self._bus,
                decision.strategy.value,
                decision.selected_engine.value,
                [e.value for e in decision.alternatives],
            )

        selected_name = decision.selected_engine.value
        for name, engine in self._engines.items():
            if engine.engine_type == decision.selected_engine:
                return engine
            if name == selected_name:
                return engine

        return self._engines[decision.selected_engine.value]

    def _available_engines(self, engine_type: EngineType | None = None) -> list[EngineType]:
        types = set()
        for name, config in self._engine_configs.items():
            if not config.enabled:
                continue
            health = self._engine_health.get(name)
            if health and not health.healthy:
                continue
            if engine_type and config.type != engine_type:
                continue
            types.add(config.type)
        return list(types)

    def _update_metrics(self, task: ExecutionTask) -> None:
        metrics = self._metrics.get(task.engine_name)
        if not metrics:
            metrics = ExecutionMetrics(
                engine_type=task.engine_type,
                engine_name=task.engine_name,
            )
        success = task.status == ExecutionTaskStatus.COMPLETED
        metrics.record_task(task.duration_s, success)
        self._metrics[task.engine_name] = metrics
