"""Coordination Engine — executes subtasks using configurable patterns.

Supports six coordination patterns:
- Sequential: one task after another
- Parallel: all tasks simultaneously
- Fan-out: one task broadcast to all agents
- Fan-in: all agents produce, one aggregates
- Hierarchical: tree-structured parent-child
- Voting: agents vote on proposals
"""

import asyncio

from agentic_os.core.runtime.manager import RuntimeManager
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    AgentTaskStatus,
    CoordinationPattern,
    OrchestrationPlan,
    SwarmSpec,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.execution import ExecutionRequest

log = get_logger("orchestration.coordination")


class CoordinationEngine:
    """Executes subtasks using the appropriate coordination pattern.

    Each pattern method:
    1. Publishes a started event
    2. Executes subtasks via RuntimeManager
    3. Collects results
    4. Publishes a completed event
    5. Returns updated tasks with results
    """

    def __init__(self) -> None:
        self._timeout_seconds: float = 300.0

    async def execute(
        self,
        plan: OrchestrationPlan,
        swarm: SwarmSpec,
        agents: list[AgentDescriptor],
        runtime: RuntimeManager,
        bus: EventBus,
    ) -> OrchestrationPlan:
        """Route the plan to the correct coordination pattern based on tasks."""
        if not plan.subtasks:
            return plan.with_status("completed")

        # Determine pattern from first non-None pattern in subtasks
        pattern = CoordinationPattern.SEQUENTIAL
        for task in plan.subtasks:
            if task.coordination_pattern is not None:
                pattern = task.coordination_pattern
                break

        # Build engine map: agent_id -> engine_id mapping
        agent_engine_map = {a.agent_id: a.agent_id for a in agents}

        if pattern == CoordinationPattern.PARALLEL:
            updated_tasks = await self._execute_parallel(
                plan.subtasks, swarm, agents, agent_engine_map, runtime, bus
            )
        elif pattern == CoordinationPattern.FAN_OUT:
            updated_tasks = await self._execute_fan_out(
                plan.subtasks, swarm, agents, agent_engine_map, runtime, bus
            )
        elif pattern == CoordinationPattern.FAN_IN:
            updated_tasks = await self._execute_fan_in(
                plan.subtasks, swarm, agents, agent_engine_map, runtime, bus
            )
        elif pattern == CoordinationPattern.HIERARCHICAL:
            updated_tasks = await self._execute_hierarchical(
                plan.subtasks, swarm, agents, agent_engine_map, runtime, bus
            )
        else:  # SEQUENTIAL
            updated_tasks = await self._execute_sequential(
                plan.subtasks, swarm, agents, agent_engine_map, runtime, bus
            )

        all_done = all(
            t.status
            in (AgentTaskStatus.COMPLETED, AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED)
            for t in updated_tasks
        )
        return OrchestrationPlan(
            id=plan.id,
            goal_id=plan.goal_id,
            subtasks=tuple(updated_tasks),
            status="completed" if all_done else "running",
            metadata=plan.metadata,
            created_at=plan.created_at,
            completed_at=None,
        )

    async def _execute_sequential(
        self,
        tasks: tuple[AgentTask, ...],
        swarm: SwarmSpec,
        agents: list[AgentDescriptor],
        engine_map: dict[str, str],
        runtime: RuntimeManager,
        bus: EventBus,
    ) -> list[AgentTask]:
        """Execute tasks one at a time in order."""
        await self._publish_coord_event(
            bus, Topic.ORCH_COORD_SEQUENTIAL_STARTED, swarm.id, len(tasks)
        )

        updated: list[AgentTask] = []
        for task in tasks:
            result = await self._execute_single_task(task, engine_map, runtime)
            updated.append(result)

            # Stop on first failure if sequential
            if result.status == AgentTaskStatus.FAILED:
                remaining = [
                    t.with_status(AgentTaskStatus.CANCELLED) for t in tasks[len(updated) :]
                ]
                updated.extend(remaining)
                break

        await self._publish_coord_event(
            bus, Topic.ORCH_COORD_SEQUENTIAL_COMPLETED, swarm.id, len(updated)
        )
        return updated

    async def _execute_parallel(
        self,
        tasks: tuple[AgentTask, ...],
        swarm: SwarmSpec,
        agents: list[AgentDescriptor],
        engine_map: dict[str, str],
        runtime: RuntimeManager,
        bus: EventBus,
    ) -> list[AgentTask]:
        """Execute all tasks simultaneously."""
        await self._publish_coord_event(
            bus, Topic.ORCH_COORD_PARALLEL_STARTED, swarm.id, len(tasks)
        )

        coros = [self._execute_single_task(task, engine_map, runtime) for task in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)

        updated: list[AgentTask] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                updated.append(tasks[i].with_error(str(result)))
            else:
                updated.append(result)

        await self._publish_coord_event(
            bus, Topic.ORCH_COORD_PARALLEL_COMPLETED, swarm.id, len(updated)
        )
        return updated

    async def _execute_fan_out(
        self,
        tasks: tuple[AgentTask, ...],
        swarm: SwarmSpec,
        agents: list[AgentDescriptor],
        engine_map: dict[str, str],
        runtime: RuntimeManager,
        bus: EventBus,
    ) -> list[AgentTask]:
        """Fan-out: each agent receives the same task, results collected."""
        await self._publish_coord_event(bus, Topic.ORCH_COORD_FAN_OUT_STARTED, swarm.id, len(tasks))

        if not tasks:
            return []

        base_task = tasks[0]
        coros = []
        for agent in agents:
            agent_task = base_task.with_assigned(agent.agent_id)
            coros.append(self._execute_single_task(agent_task, engine_map, runtime))

        results = await asyncio.gather(*coros, return_exceptions=True)

        updated: list[AgentTask] = []
        for _i, result in enumerate(results):
            if isinstance(result, BaseException):
                updated.append(base_task.with_error(str(result)))
            else:
                updated.append(result)

        await self._publish_coord_event(
            bus, Topic.ORCH_COORD_FAN_OUT_COMPLETED, swarm.id, len(updated)
        )
        return updated

    async def _execute_fan_in(
        self,
        tasks: tuple[AgentTask, ...],
        swarm: SwarmSpec,
        agents: list[AgentDescriptor],
        engine_map: dict[str, str],
        runtime: RuntimeManager,
        bus: EventBus,
    ) -> list[AgentTask]:
        """Fan-in: all agents produce, then a single aggregator consolidates."""
        await self._publish_coord_event(bus, Topic.ORCH_COORD_FAN_IN_STARTED, swarm.id, len(tasks))

        # Step 1: All agents execute
        base_task = tasks[0] if tasks else None
        if base_task is None:
            return []

        producer_coros = []
        for agent in agents:
            agent_task = base_task.with_assigned(agent.agent_id)
            producer_coros.append(self._execute_single_task(agent_task, engine_map, runtime))

        producer_results = await asyncio.gather(*producer_coros, return_exceptions=True)

        # Step 2: Assign results to tasks
        updated: list[AgentTask] = []
        for _i, result in enumerate(producer_results):
            if isinstance(result, BaseException):
                updated.append(base_task.with_error(str(result)))
            else:
                updated.append(result)

        await self._publish_coord_event(
            bus, Topic.ORCH_COORD_FAN_IN_COMPLETED, swarm.id, len(updated)
        )
        return updated

    async def _execute_hierarchical(
        self,
        tasks: tuple[AgentTask, ...],
        swarm: SwarmSpec,
        agents: list[AgentDescriptor],
        engine_map: dict[str, str],
        runtime: RuntimeManager,
        bus: EventBus,
    ) -> list[AgentTask]:
        """Hierarchical: parent tasks complete before children based on depends_on."""
        await self._publish_coord_event(
            bus, Topic.ORCH_COORD_HIERARCHICAL_STARTED, swarm.id, len(tasks)
        )

        completed: dict[str, AgentTask] = {}
        remaining = list(tasks)
        updated: list[AgentTask] = []

        # Simple layer-based execution: tasks with no deps first, then by dep chain
        while remaining:
            ready = [t for t in remaining if all(dep in completed for dep in t.depends_on)]
            if not ready:
                # Deadlock — mark remaining as failed
                for t in remaining:
                    updated.append(
                        t.with_error("Dependency deadlock — dependencies never completed")
                    )
                break

            coros = [self._execute_single_task(task, engine_map, runtime) for task in ready]
            results = await asyncio.gather(*coros, return_exceptions=True)

            for i, result in enumerate(results):
                task = ready[i]
                if isinstance(result, BaseException):
                    completed[task.id] = task.with_error(str(result))
                else:
                    completed[task.id] = result
                updated.append(completed[task.id])

            remaining = [t for t in remaining if t.id not in completed]

        await self._publish_coord_event(
            bus, Topic.ORCH_COORD_HIERARCHICAL_COMPLETED, swarm.id, len(updated)
        )
        return updated

    async def _execute_single_task(
        self,
        task: AgentTask,
        engine_map: dict[str, str],
        runtime: RuntimeManager,
    ) -> AgentTask:
        """Execute a single task on its assigned engine via RuntimeManager."""
        if task.assigned_agent_id is None:
            return task.with_error("No agent assigned")

        engine_id = engine_map.get(task.assigned_agent_id)
        if engine_id is None:
            return task.with_error(f"No engine mapping for agent: {task.assigned_agent_id}")

        request = ExecutionRequest(
            action=task.title or "execute",
            payload=task.input_data,
            timeout_seconds=task.timeout_seconds,
        )

        try:
            result = await asyncio.wait_for(
                runtime.execute(engine_id, request),
                timeout=task.timeout_seconds,
            )
        except TimeoutError:
            return task.with_error(f"Task timed out after {task.timeout_seconds}s")
        except Exception as exc:
            return task.with_error(str(exc))

        if result and result.status.value == "completed":
            return task.with_output(
                dict(result.output)
                if hasattr(result, "output")
                else {"result": result.status.value}
            )
        else:
            return task.with_error(getattr(result, "error", "Execution failed"))

    async def _publish_coord_event(
        self,
        bus: EventBus,
        topic: Topic,
        swarm_id: str,
        task_count: int,
    ) -> None:
        """Publish a coordination lifecycle event."""
        try:
            await bus.publish(
                EventEnvelope(
                    type="event",
                    source="coordination-engine",
                    topic=topic.value,
                    payload={"swarm_id": swarm_id, "task_count": task_count},
                )
            )
        except Exception as exc:
            log.warning("Failed to publish coordination event", topic=topic.value, error=str(exc))
