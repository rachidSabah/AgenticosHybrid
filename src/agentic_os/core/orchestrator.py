"""Orchestrator kernel — the brain of the vertical slice.

Wires the event bus to the agent behaviors:

    Planner  → plans an incoming request into a Task
    Dispatcher → picks a Role/provider and spawns an Agent, runs the provider
    Supervisor → watches completion/failure and publishes outcomes

All coordination happens *through the bus*; the kernel only connects handlers.
"""

from __future__ import annotations

from agentic_os.config import Settings
from agentic_os.core.registry import AgentRegistry, ProviderRegistry
from agentic_os.domain.agent import Agent, Role, Task, TaskStatus
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("core.orchestrator")


class Orchestrator:
    def __init__(
        self,
        bus: EventBus,
        registry: AgentRegistry,
        providers: ProviderRegistry,
        settings: Settings,
    ) -> None:
        self.bus = bus
        self.registry = registry
        self.providers = providers
        self.settings = settings
        self._provider_rr_idx = 0  # round-robin index for real providers

    async def start(self) -> None:
        # Seed a default set of roles (declarative; one Agent runtime).
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

    # ── Public entry: create a task from a user request ──
    async def create_task(self, title: str, role: str, description: str = "") -> Task:
        task = Task(title=title, role=role, description=description)
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

    # ── Planner ──
    async def _on_task_created(self, event: EventEnvelope) -> None:
        task = self._canonical_task(event.payload.get("id"))
        if task is None:
            return
        task.status = TaskStatus.PLANNED
        task.touch()
        log.info("planner.plan", task=task.id, role=task.role)
        await self.bus.publish(event.route_to(Topic.TASK_PLANNED))

    # ── Task Dispatcher ──
    async def _on_task_planned(self, event: EventEnvelope) -> None:
        task = self._canonical_task(event.payload.get("id"))
        if task is None:
            return

        # Provider selection: prefer real (non-mock) providers with round-robin.
        provider = None
        all_providers = self.providers.list_providers()
        real_providers = [p for p in all_providers if p.name != "mock" and "mock" not in p.kind]

        if real_providers:
            # Round-robin across real providers for load distribution
            idx = self._provider_rr_idx % len(real_providers)
            self._provider_rr_idx += 1
            provider_name = real_providers[idx].name
            provider = self.providers.get(provider_name)
            log.info(
                "dispatcher.real_provider_selected",
                provider=provider_name,
                task=task.id,
                rr_index=idx,
                real_count=len(real_providers),
            )
        else:
            # Fall back to configured default or first available
            provider = (
                self.providers.get(self.settings.provider_default) or self.providers.default()
            )

        if provider is None:
            log.error("dispatcher.no_provider")
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

    async def dispatch_task(self, task: Task) -> None:
        """Re-dispatch a task during recovery (spawns a fresh agent attempt).

        The attempt count lives on the Task (the durable unit of work), not on
        the transient Agent, so the recovery cap is enforced correctly.
        """
        # Prefer real (non-mock) providers for recovery too
        all_providers = self.providers.list_providers()
        real_providers = [p for p in all_providers if p.name != "mock" and "mock" not in p.kind]
        if real_providers:
            provider = self.providers.get(real_providers[0].name)
        else:
            provider = (
                self.providers.get(self.settings.provider_default) or self.providers.default()
            )
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
            return
        task.status = TaskStatus.IN_PROGRESS
        task.touch()
        try:
            result = await provider.execute(agent, task)
            agent.mark_completed()
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.touch()
            await self.bus.publish(
                EventEnvelope(
                    type="agent.completed",
                    source="supervisor",
                    topic=Topic.AGENT_COMPLETED.value,
                    payload={"agent_id": agent.id, "task_id": task.id, "result": result},
                )
            )
        except Exception as exc:  # noqa: BLE001
            agent.mark_failed()
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.touch()
            log.warning("supervisor.failure", agent=agent.id, error=str(exc))
            await self.bus.publish(
                EventEnvelope(
                    type="agent.failed",
                    source="supervisor",
                    topic=Topic.AGENT_FAILED.value,
                    payload={"agent_id": agent.id, "task_id": task.id, "reason": str(exc)},
                )
            )

    def _canonical_task(self, task_id: str | None) -> Task | None:
        """Resolve the registry's authoritative Task copy by id."""
        if not task_id:
            return None
        return self.registry.get_task(task_id)

    # ── Supervisor outcomes ──
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
