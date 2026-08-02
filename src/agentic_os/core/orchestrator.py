"""Orchestrator kernel — the brain of the vertical slice.

Wires the event bus to the agent behaviors:

    Planner  → plans an incoming request into a Task
    Dispatcher → picks a Role/provider and spawns an Agent, runs the provider
    Supervisor → watches completion/failure and publishes outcomes

All coordination happens *through the bus*; the kernel only connects handlers.

Recovery policy (implemented in ``_run_provider``):
  1. Provider.execute() fails
  2. Retry same provider once (retry_count=1)
  3. If retry fails, pick the next healthy provider and retry (retry_count=2)
  4. If no other provider available OR retry also fails, mark task FAILED
  5. Never silently abandon a task

Every execution attempt is recorded in the ExecutionLog (if wired) so
Mission Control can render the full execution history per task/mission.
"""

from __future__ import annotations

import time as _time
from typing import TYPE_CHECKING

from agentic_os.config import Settings
from agentic_os.core.registry import AgentRegistry, ProviderRegistry
from agentic_os.domain.agent import Agent, Role, Task, TaskStatus
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

if TYPE_CHECKING:
    from agentic_os.core.execution_log import ExecutionLog

log = get_logger("core.orchestrator")

_MAX_SAME_PROVIDER_RETRIES = 1
_MAX_TOTAL_ATTEMPTS = 3

_ROLE_CAPABILITY_MAP: dict[str, list[str]] = {
    "coding": ["coding"],
    "planner": ["planning", "coding", "reasoning"],
    "research": ["research", "reasoning"],
    "reviewer": ["reasoning", "coding"],
    "devops": ["terminal", "coding"],
}

_PROVIDER_COOLDOWN_S = 30.0


class Orchestrator:
    def __init__(
        self,
        bus: EventBus,
        registry: AgentRegistry,
        providers: ProviderRegistry,
        settings: Settings,
        execution_log: "ExecutionLog | None" = None,
    ) -> None:
        self.bus = bus
        self.registry = registry
        self.providers = providers
        self.settings = settings
        self.execution_log = execution_log
        self._provider_rr_idx = 0
        self._failed_providers: dict[str, float] = {}

    async def start(self) -> None:
        for role in _default_roles():
            self.registry.register_role(role)
        await self.bus.subscribe(Topic.TASK_CREATED.value, self._on_task_created)
        await self.bus.subscribe(Topic.TASK_PLANNED.value, self._on_task_planned)
        await self.bus.subscribe(Topic.TASK_DISPATCHED.value, self._on_task_dispatched)
        await self.bus.subscribe(Topic.AGENT_COMPLETED.value, self._on_agent_completed)
        await self.bus.subscribe(Topic.AGENT_FAILED.value, self._on_agent_failed)
        log.info("orchestrator.started", roles=len(self.registry.roles()))

    async def stop(self) -> None:
        pass

    async def create_task(
        self,
        title: str,
        role: str,
        description: str = "",
        user_prompt: str = "",
        mission_id: str = "",
    ) -> Task:
        task = Task(
            title=title,
            role=role,
            description=description,
            user_prompt=user_prompt,
            mission_id=mission_id,
        )
        self.registry.register_task(task)
        await self.bus.publish(
            EventEnvelope(
                type="task.created",
                source="api",
                topic=Topic.TASK_CREATED.value,
                payload=task.model_dump(),
            )
        )
        return task

    async def _on_task_created(self, event: EventEnvelope) -> None:
        task = self._canonical_task(event.payload.get("id"))
        if task is None:
            return
        task.status = TaskStatus.PLANNED
        task.touch()
        log.info("planner.plan", task=task.id, role=task.role)
        await self.bus.publish(event.route_to(Topic.TASK_PLANNED))

    async def _on_task_planned(self, event: EventEnvelope) -> None:
        task = self._canonical_task(event.payload.get("id"))
        if task is None:
            return
        provider = self._select_provider(task.role)
        if provider is None:
            log.error("dispatcher.no_provider", task=task.id, role=task.role)
            return
        agent = self.registry.spawn(role=task.role, provider=provider.info.name)
        agent.mark_running(task.id)
        task.status = TaskStatus.DISPATCHED
        task.assigned_agent_id = agent.id
        task.touch()
        log.info("dispatcher.assign", task=task.id, agent=agent.id, provider=provider.info.name)
        await self.bus.publish(
            EventEnvelope(
                type="task.dispatched",
                source="dispatcher",
                topic=Topic.TASK_DISPATCHED.value,
                payload={"task_id": task.id, "agent_id": agent.id},
            )
        )

    def _select_provider(self, role: str):
        all_providers = self.providers.list_providers()
        if not all_providers:
            return None
        required_caps = _ROLE_CAPABILITY_MAP.get(role, [])
        now = _time.monotonic()
        self._failed_providers = {
            name: ts
            for name, ts in self._failed_providers.items()
            if now - ts < _PROVIDER_COOLDOWN_S
        }
        real_candidates = []
        for p in all_providers:
            if p.name == "mock" or "mock" in p.kind:
                continue
            if p.name in self._failed_providers:
                continue
            if required_caps:
                provider_caps = set(p.capabilities) if hasattr(p, "capabilities") else set()
                if provider_caps and not provider_caps.intersection(required_caps):
                    continue
            real_candidates.append(p)
        if real_candidates:
            idx = self._provider_rr_idx % len(real_candidates)
            self._provider_rr_idx += 1
            chosen = real_candidates[idx]
            provider = self.providers.get(chosen.name)
            log.info(
                "dispatcher.real_provider_selected",
                provider=chosen.name,
                task_role=role,
                required_caps=required_caps,
                rr_index=idx,
                real_count=len(real_candidates),
                failed_in_cooldown=len(self._failed_providers),
            )
            return provider
        log.info(
            "dispatcher.fallback_to_default",
            task_role=role,
            failed_in_cooldown=len(self._failed_providers),
        )
        return self.providers.get(self.settings.provider_default) or self.providers.default()

    def _mark_provider_failed(self, provider_name: str) -> None:
        self._failed_providers[provider_name] = _time.monotonic()
        log.info(
            "dispatcher.provider_marked_failed",
            provider=provider_name,
            cooldown_s=_PROVIDER_COOLDOWN_S,
        )

    async def dispatch_task(self, task: Task) -> None:
        provider = self._select_provider(task.role)
        if provider is None:
            return
        task.attempts += 1
        agent = self.registry.spawn(role=task.role, provider=provider.info.name)
        agent.mark_running(task.id)
        task.status = TaskStatus.IN_PROGRESS
        task.assigned_agent_id = agent.id
        task.touch()
        await self._run_provider(agent, task)

    async def _on_task_dispatched(self, event: EventEnvelope) -> None:
        task = self._canonical_task(event.payload.get("task_id"))
        agent_id = event.payload.get("agent_id")
        if not agent_id:
            return
        agent = self.registry.get_agent(agent_id)
        if task is None or agent is None:
            return
        await self._run_provider(agent, task)

    async def _run_provider(self, agent: Agent, task: Task) -> None:
        provider = self.providers.get(agent.provider)
        if provider is None:
            log.error("provider.not_found", provider=agent.provider, agent=agent.id)
            await self._fail_task(agent, task, f"Provider '{agent.provider}' not found")
            return

        task.status = TaskStatus.IN_PROGRESS
        task.assigned_agent_id = agent.id
        task.touch()

        await self.bus.publish(
            EventEnvelope(
                type="task.started",
                source="orchestrator",
                topic="task.started",
                payload={
                    "task_id": task.id,
                    "agent_id": agent.id,
                    "provider": agent.provider,
                    "title": task.title,
                    "mission_id": task.mission_id,
                },
            )
        )

        start_time = _time.monotonic()
        log.info(
            "execution.started",
            task=task.id,
            agent=agent.id,
            provider=agent.provider,
            mission_id=task.mission_id,
            title=task.title,
        )

        # Attempt 1
        exec_rec = self._start_execution(agent, task, provider, retry_count=0)
        try:
            result = await provider.execute(agent, task)
            elapsed = _time.monotonic() - start_time
            agent.mark_completed()
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.touch()
            self._finish_execution(exec_rec, "completed", stdout=result)
            log.info(
                "execution.completed",
                task=task.id,
                agent=agent.id,
                mission_id=task.mission_id,
                elapsed_s=round(elapsed, 3),
                result_len=len(result) if result else 0,
            )
            await self._publish_completed(agent, task, result, elapsed)
            return
        except Exception as exc:
            elapsed = _time.monotonic() - start_time
            self._finish_execution(exec_rec, "failed", stderr=str(exc), error=str(exc))
            log.warning(
                "execution.failed",
                agent=agent.id,
                task=task.id,
                mission_id=task.mission_id,
                provider=agent.provider,
                error=str(exc),
                elapsed_s=round(elapsed, 3),
                attempt=1,
            )

        # Attempt 2: retry same provider
        if task.attempts < _MAX_TOTAL_ATTEMPTS:
            task.attempts += 1
            log.info(
                "execution.retry_same_provider",
                task=task.id,
                agent=agent.id,
                provider=agent.provider,
                attempt=2,
            )
            exec_rec2 = self._start_execution(agent, task, provider, retry_count=1)
            try:
                result = await provider.execute(agent, task)
                elapsed = _time.monotonic() - start_time
                agent.mark_completed()
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.error = None
                task.touch()
                self._finish_execution(exec_rec2, "completed", stdout=result)
                log.info(
                    "execution.completed_after_retry",
                    task=task.id,
                    agent=agent.id,
                    provider=agent.provider,
                    attempt=2,
                    elapsed_s=round(elapsed, 3),
                )
                await self._publish_completed(agent, task, result, elapsed, recovered=True)
                return
            except Exception as exc2:
                self._finish_execution(exec_rec2, "failed", stderr=str(exc2), error=str(exc2))
                log.warning(
                    "execution.retry_failed",
                    agent=agent.id,
                    task=task.id,
                    provider=agent.provider,
                    attempt=2,
                    error=str(exc2),
                )

        # Attempt 3: fallback to next healthy provider
        self._mark_provider_failed(agent.provider)
        fallback_provider = self._pick_fallback_provider(
            current_name=agent.provider,
            role=task.role,
        )
        if fallback_provider is not None and task.attempts < _MAX_TOTAL_ATTEMPTS:
            task.attempts += 1
            log.info(
                "execution.fallback_provider",
                task=task.id,
                original_provider=agent.provider,
                fallback_provider=fallback_provider.info.name,
                attempt=3,
            )
            fallback_agent = self.registry.spawn(
                role=task.role,
                provider=fallback_provider.info.name,
            )
            fallback_agent.mark_running(task.id)
            task.assigned_agent_id = fallback_agent.id
            task.touch()
            exec_rec3 = self._start_execution(
                fallback_agent, task, fallback_provider, retry_count=2
            )
            try:
                result = await fallback_provider.execute(fallback_agent, task)
                elapsed = _time.monotonic() - start_time
                fallback_agent.mark_completed()
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.error = None
                task.touch()
                self._finish_execution(exec_rec3, "completed", stdout=result)
                log.info(
                    "execution.completed_after_fallback",
                    task=task.id,
                    agent=fallback_agent.id,
                    provider=fallback_provider.info.name,
                    attempt=3,
                    elapsed_s=round(elapsed, 3),
                )
                await self._publish_completed(
                    fallback_agent, task, result, elapsed, recovered=True, fallback=True
                )
                return
            except Exception as exc3:
                self._finish_execution(exec_rec3, "failed", stderr=str(exc3), error=str(exc3))
                log.warning(
                    "execution.fallback_failed",
                    agent=fallback_agent.id,
                    task=task.id,
                    provider=fallback_provider.info.name,
                    attempt=3,
                    error=str(exc3),
                )
                agent.mark_failed()
                await self._fail_task(
                    fallback_agent, task, f"All {task.attempts} attempts failed. Last error: {exc3}"
                )
                return

        agent.mark_failed()
        await self._fail_task(
            agent,
            task,
            f"Execution failed after {task.attempts} attempt(s). No fallback provider available.",
        )

    def _pick_fallback_provider(self, current_name: str, role: str = ""):
        all_providers = self.providers.list_providers()
        required_caps = _ROLE_CAPABILITY_MAP.get(role, [])
        now = _time.monotonic()
        self._failed_providers = {
            name: ts
            for name, ts in self._failed_providers.items()
            if now - ts < _PROVIDER_COOLDOWN_S
        }
        candidates = []
        for p in all_providers:
            if p.name == "mock" or "mock" in p.kind:
                continue
            if p.name == current_name:
                continue
            if p.name in self._failed_providers:
                continue
            if required_caps:
                provider_caps = set(p.capabilities) if hasattr(p, "capabilities") else set()
                if provider_caps and not provider_caps.intersection(required_caps):
                    continue
            candidates.append(p)
        if not candidates:
            return None
        idx = self._provider_rr_idx % len(candidates)
        self._provider_rr_idx += 1
        return self.providers.get(candidates[idx].name)

    def _start_execution(self, agent: Agent, task: Task, provider, retry_count: int):
        if self.execution_log is None:
            return None
        strategy_name = type(provider).__name__
        if hasattr(provider, "strategy"):
            strategy_name = type(provider.strategy).__name__
        runtime_kind = provider.info.kind if hasattr(provider, "info") else ""
        cmd_preview = ""
        prompt_preview = ""
        try:
            if hasattr(provider, "strategy") and hasattr(provider, "bin_path"):
                cmd = provider.strategy.build_command(task, provider.bin_path)
                cmd_preview = " ".join(str(c) for c in cmd[:8])[:300]
                prompt_preview = provider.strategy.build_prompt(task)
        except Exception:
            pass
        return self.execution_log.start(
            task_id=task.id,
            agent_id=agent.id,
            provider=agent.provider,
            runtime=runtime_kind,
            strategy=strategy_name,
            mission_id=task.mission_id,
            command=cmd_preview,
            prompt_preview=prompt_preview,
            retry_count=retry_count,
        )

    def _finish_execution(self, exec_rec, status: str, **kwargs) -> None:
        if exec_rec is None or self.execution_log is None:
            return
        self.execution_log.finish(exec_rec.execution_id, status, **kwargs)

    async def _publish_completed(
        self,
        agent: Agent,
        task: Task,
        result: str,
        elapsed: float,
        recovered: bool = False,
        fallback: bool = False,
    ) -> None:
        await self.bus.publish(
            EventEnvelope(
                type="task.completed",
                source="orchestrator",
                topic="task.completed",
                payload={
                    "task_id": task.id,
                    "agent_id": agent.id,
                    "provider": agent.provider,
                    "result": result[:500] if result else "",
                    "elapsed_s": round(elapsed, 3),
                    "mission_id": task.mission_id,
                    "recovered": recovered,
                    "fallback": fallback,
                },
            )
        )
        await self.bus.publish(
            EventEnvelope(
                type="agent.completed",
                source="supervisor",
                topic=Topic.AGENT_COMPLETED.value,
                payload={
                    "agent_id": agent.id,
                    "task_id": task.id,
                    "result": result[:500] if result else "",
                    "elapsed_s": round(elapsed, 3),
                },
            )
        )

    async def _fail_task(self, agent: Agent, task: Task, error: str) -> None:
        elapsed = 0.0
        agent.mark_failed()
        task.status = TaskStatus.FAILED
        task.error = error
        task.touch()
        log.warning(
            "execution.abandoned",
            agent=agent.id,
            task=task.id,
            mission_id=task.mission_id,
            error=error,
            attempts=task.attempts,
        )
        await self.bus.publish(
            EventEnvelope(
                type="task.failed",
                source="orchestrator",
                topic="task.failed",
                payload={
                    "task_id": task.id,
                    "agent_id": agent.id,
                    "provider": agent.provider,
                    "error": error,
                    "elapsed_s": round(elapsed, 3),
                    "mission_id": task.mission_id,
                    "attempts": task.attempts,
                },
            )
        )
        await self.bus.publish(
            EventEnvelope(
                type="agent.failed",
                source="supervisor",
                topic=Topic.AGENT_FAILED.value,
                payload={
                    "agent_id": agent.id,
                    "task_id": task.id,
                    "reason": error,
                    "elapsed_s": round(elapsed, 3),
                },
            )
        )

    def _canonical_task(self, task_id: str | None) -> Task | None:
        if not task_id:
            return None
        return self.registry.get_task(task_id)

    async def _on_agent_completed(self, event: EventEnvelope) -> None:
        log.info("supervisor.completed", task=event.payload.get("task_id"))

    async def _on_agent_failed(self, event: EventEnvelope) -> None:
        log.warning("supervisor.failed", task=event.payload.get("task_id"))


def _default_roles() -> list[Role]:
    return [
        Role(name="planner", description="Decomposes requests into tasks."),
        Role(name="coding", description="Writes and edits code.", allowed_tools=["edit", "run"]),
        Role(name="research", description="Gathers information."),
        Role(name="reviewer", description="Reviews changes."),
        Role(name="devops", description="Builds, deploys, operates."),
    ]
