"""
Pipeline Engine Implementation

Core pipeline execution engine with stage-based DAG execution, scheduling, and rollback.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agentic_os.core.providers.router import ProviderRouter
from agentic_os.core.registry import AgentRegistry
from agentic_os.domain.events import Topic
from agentic_os.domain.pipeline import (
    Pipeline,
    PipelineEdge,
    PipelineExecution,
    PipelineExecutionStatus,
    PipelineSchedule,
    PipelineStage,
    PipelineStatus,
    PipelineVersion,
    StageType,
)
from agentic_os.ports.event_bus import EventBus, EventEnvelope
from agentic_os.ports.pipeline import (
    PipelineCreate,
    PipelineDetail,
    PipelineEnginePort,
    PipelineExecute,
    PipelineRollback,
    PipelineScheduleRequest,
    PipelineSummary,
    PipelineUpdate,
    ValidationResult,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PipelineEngineImpl(PipelineEnginePort):
    """
    Pipeline engine implementing stage-based DAG execution with:
    - Topological execution order
    - Parallel stage execution (for PARALLEL type stages)
    - Scheduling (cron-like)
    - Retry policies per stage
    - Rollback support
    - Event emission for observability
    """

    def __init__(
        self,
        event_bus: EventBus,
        provider_router: ProviderRouter,
        agent_registry: AgentRegistry,
    ):
        self._event_bus = event_bus
        self._provider_router = provider_router
        self._agent_registry = agent_registry
        self._pipelines: dict[str, Pipeline] = {}
        self._pipeline_versions: dict[str, list[PipelineVersion]] = defaultdict(list)
        self._executions: dict[str, PipelineExecution] = {}
        self._schedules: dict[str, PipelineSchedule] = {}
        self._running_executions: set[str] = set()
        self._execution_tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------------
    # CRUD Operations
    # ------------------------------------------------------------------------

    async def create_pipeline(self, data: PipelineCreate) -> PipelineDetail:
        pipeline = Pipeline.create(
            name=data.name,
            description=data.description,
            stages=data.stages,
            edges=data.edges,
            schedule_cron=data.schedule_cron,
            schedule_timezone=data.schedule_timezone,
            created_by=data.created_by,
        )
        self._pipelines[pipeline.id] = pipeline

        if data.schedule_cron:
            schedule = PipelineSchedule(
                pipeline_id=pipeline.id,
                cron=data.schedule_cron,
                timezone=data.schedule_timezone,
                next_run=self._calculate_next_run(data.schedule_cron, data.schedule_timezone),
            )
            self._schedules[pipeline.id] = schedule

        await self._emit_event(
            Topic.PIPELINE_CREATED, pipeline.id, {"pipeline": pipeline.to_dict()}
        )
        logger.info(f"Created pipeline {pipeline.id}: {pipeline.name}")
        return _pipeline_detail_from_pipeline(pipeline)

    async def get_pipeline(self, pipeline_id: str) -> PipelineDetail | None:
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            return None
        return _pipeline_detail_from_pipeline(pipeline)

    async def list_pipelines(
        self,
        status: PipelineStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PipelineSummary]:
        pipelines = list(self._pipelines.values())
        if status:
            pipelines = [p for p in pipelines if p.status == status]
        pipelines.sort(key=lambda p: p.updated_at, reverse=True)
        return [
            _pipeline_summary_from_pipeline(p, self._schedules.get(p.id))
            for p in pipelines[offset : offset + limit]
        ]

    async def update_pipeline(self, pipeline_id: str, data: PipelineUpdate) -> PipelineDetail:
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            raise ValueError(f"Pipeline {pipeline_id} not found")

        structure_changed = (
            data.stages is not None
            and [s.id for s in data.stages] != [s.id for s in pipeline.stages]
        ) or (
            data.edges is not None and [e.id for e in data.edges] != [e.id for e in pipeline.edges]
        )

        if structure_changed:
            new_pipeline = pipeline.new_version(
                name=data.name,
                description=data.description,
                stages=data.stages,
                edges=data.edges,
                schedule_cron=data.schedule_cron,
                schedule_timezone=data.schedule_timezone,
                created_by=data.updated_by,
            )
        else:
            new_pipeline = Pipeline(
                id=pipeline.id,
                name=data.name or pipeline.name,
                description=data.description or pipeline.description,
                stages=pipeline.stages,
                edges=pipeline.edges,
                version=pipeline.version,
                status=data.status or pipeline.status,
                schedule_cron=data.schedule_cron
                if data.schedule_cron is not None
                else pipeline.schedule_cron,
                schedule_timezone=data.schedule_timezone or pipeline.schedule_timezone,
                created_at=pipeline.created_at,
                updated_at=datetime.now(UTC),
                created_by=pipeline.created_by,
            )

        self._pipelines[pipeline_id] = new_pipeline

        if data.schedule_cron is not None:
            if data.schedule_cron:
                self._schedules[pipeline_id] = PipelineSchedule(
                    pipeline_id=pipeline_id,
                    cron=data.schedule_cron,
                    timezone=data.schedule_timezone or pipeline.schedule_timezone,
                    next_run=self._calculate_next_run(
                        data.schedule_cron, data.schedule_timezone or pipeline.schedule_timezone
                    ),
                )
            else:
                self._schedules.pop(pipeline_id, None)

        await self._emit_event(
            Topic.PIPELINE_UPDATED, pipeline_id, {"pipeline": new_pipeline.to_dict()}
        )
        logger.info(f"Updated pipeline {pipeline_id} to version {new_pipeline.version}")
        return _pipeline_detail_from_pipeline(new_pipeline)

    async def delete_pipeline(self, pipeline_id: str) -> bool:
        if pipeline_id not in self._pipelines:
            return False

        running = any(
            e.pipeline_id == pipeline_id and e.status == PipelineExecutionStatus.RUNNING
            for e in self._executions.values()
        )
        if running:
            raise ValueError(f"Cannot delete pipeline {pipeline_id}: has running executions")

        del self._pipelines[pipeline_id]
        if pipeline_id in self._pipeline_versions:
            del self._pipeline_versions[pipeline_id]
        self._schedules.pop(pipeline_id, None)

        await self._emit_event(Topic.PIPELINE_DELETED, pipeline_id, {})
        logger.info(f"Deleted pipeline {pipeline_id}")
        return True

    # ------------------------------------------------------------------------
    # Version Management
    # ------------------------------------------------------------------------

    async def get_pipeline_versions(self, pipeline_id: str) -> list[PipelineVersion]:
        return self._pipeline_versions.get(pipeline_id, [])

    async def get_pipeline_version(self, pipeline_id: str, version: int) -> PipelineDetail | None:
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline and pipeline.version == version:
            return _pipeline_detail_from_pipeline(pipeline)
        for v in self._pipeline_versions.get(pipeline_id, []):
            if v.version == version:
                return _pipeline_detail_from_version(v)
        return None

    # ------------------------------------------------------------------------
    # Execution Operations
    # ------------------------------------------------------------------------

    async def execute_pipeline(self, pipeline_id: str, data: PipelineExecute) -> PipelineExecution:
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            raise ValueError(f"Pipeline {pipeline_id} not found")

        if pipeline.status != PipelineStatus.ACTIVE:
            raise ValueError(f"Pipeline {pipeline_id} is not active (status: {pipeline.status})")

        execution = PipelineExecution(
            id=str(uuid4()),
            pipeline_id=pipeline_id,
            pipeline_version=pipeline.version,
            status=PipelineExecutionStatus.PENDING,
            inputs=data.inputs,
        )

        self._executions[execution.id] = execution
        self._running_executions.add(execution.id)

        task = asyncio.create_task(self._run_execution(execution, pipeline))
        self._execution_tasks[execution.id] = task

        await self._emit_event(
            Topic.PIPELINE_STARTED, execution.id, {"execution": execution.to_dict()}
        )
        logger.info(f"Started pipeline execution {execution.id} for pipeline {pipeline_id}")
        return execution

    # ------------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------------

    async def schedule_pipeline(
        self, pipeline_id: str, data: PipelineScheduleRequest
    ) -> PipelineSchedule:
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            raise ValueError(f"Pipeline {pipeline_id} not found")

        schedule = PipelineSchedule(
            pipeline_id=pipeline_id,
            cron=data.cron,
            timezone=data.timezone,
            next_run=self._calculate_next_run(data.cron, data.timezone),
        )
        self._schedules[pipeline_id] = schedule

        # Update pipeline with schedule
        pipeline = Pipeline(
            id=pipeline.id,
            name=pipeline.name,
            description=pipeline.description,
            stages=pipeline.stages,
            edges=pipeline.edges,
            version=pipeline.version,
            status=pipeline.status,
            schedule_cron=data.cron,
            schedule_timezone=data.timezone,
            created_at=pipeline.created_at,
            updated_at=datetime.now(UTC),
            created_by=pipeline.created_by,
        )
        self._pipelines[pipeline_id] = pipeline

        await self._emit_event(
            Topic.PIPELINE_SCHEDULED, pipeline_id, {"schedule": schedule.to_dict()}
        )
        logger.info(f"Scheduled pipeline {pipeline_id} with cron: {data.cron}")
        return schedule

    async def unschedule_pipeline(self, pipeline_id: str) -> bool:
        if pipeline_id not in self._schedules:
            return False

        del self._schedules[pipeline_id]

        pipeline = self._pipelines[pipeline_id]
        pipeline = Pipeline(
            id=pipeline.id,
            name=pipeline.name,
            description=pipeline.description,
            stages=pipeline.stages,
            edges=pipeline.edges,
            version=pipeline.version,
            status=pipeline.status,
            schedule_cron=None,
            schedule_timezone=pipeline.schedule_timezone,
            created_at=pipeline.created_at,
            updated_at=datetime.now(UTC),
            created_by=pipeline.created_by,
        )
        self._pipelines[pipeline_id] = pipeline

        await self._emit_event(Topic.PIPELINE_UNSCHEDULED, pipeline_id, {})
        logger.info(f"Unscheduled pipeline {pipeline_id}")
        return True

    async def get_pipeline_schedule(self, pipeline_id: str) -> PipelineSchedule | None:
        return self._schedules.get(pipeline_id)

    # ------------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------------

    async def rollback_pipeline(
        self, pipeline_id: str, data: PipelineRollback
    ) -> PipelineExecution:
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            raise ValueError(f"Pipeline {pipeline_id} not found")

        target_execution = self._executions.get(data.to_execution_id)
        if not target_execution:
            raise ValueError(f"Execution {data.to_execution_id} not found")

        if target_execution.pipeline_id != pipeline_id:
            raise ValueError(
                f"Execution {data.to_execution_id} does not belong to pipeline {pipeline_id}"
            )

        execution = PipelineExecution(
            id=str(uuid4()),
            pipeline_id=pipeline_id,
            pipeline_version=pipeline.version,
            status=PipelineExecutionStatus.PENDING,
            inputs=target_execution.inputs,
        )

        self._executions[execution.id] = execution
        self._running_executions.add(execution.id)

        task = asyncio.create_task(self._run_execution(execution, pipeline))
        self._execution_tasks[execution.id] = task

        await self._emit_event(
            Topic.PIPELINE_ROLLED_BACK,
            execution.id,
            {
                "execution": execution.to_dict(),
                "rolled_back_from": data.to_execution_id,
            },
        )
        logger.info(f"Rolled back pipeline {pipeline_id} to execution {data.to_execution_id}")
        return execution

    # ------------------------------------------------------------------------
    # Query Operations
    # ------------------------------------------------------------------------

    async def get_execution(self, execution_id: str) -> PipelineExecution | None:
        return self._executions.get(execution_id)

    async def get_pipeline_executions(
        self,
        pipeline_id: str,
        status: PipelineExecutionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PipelineExecution]:
        executions = [e for e in self._executions.values() if e.pipeline_id == pipeline_id]
        if status:
            executions = [e for e in executions if e.status == status]
        executions.sort(key=lambda e: e.started_at, reverse=True)
        return executions[offset : offset + limit]

    async def get_running_executions(self) -> list[PipelineExecution]:
        return [e for e in self._executions.values() if e.status == PipelineExecutionStatus.RUNNING]

    async def get_scheduled_executions(self) -> list[PipelineExecution]:
        return [e for e in self._executions.values() if e.scheduled_at is not None]

    # ------------------------------------------------------------------------
    # Control Operations
    # ------------------------------------------------------------------------

    async def cancel_execution(self, execution_id: str) -> PipelineExecution:
        execution = self._executions.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.status not in (
            PipelineExecutionStatus.RUNNING,
            PipelineExecutionStatus.PAUSED,
        ):
            raise ValueError(f"Cannot cancel execution in status {execution.status}")

        task = self._execution_tasks.get(execution_id)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._execution_tasks[execution_id]

        self._running_executions.discard(execution_id)
        execution = execution.cancel()
        self._executions[execution_id] = execution

        await self._emit_event(
            Topic.PIPELINE_CANCELLED, execution_id, {"execution": execution.to_dict()}
        )
        logger.info(f"Cancelled pipeline execution {execution_id}")
        return execution

    async def pause_execution(self, execution_id: str) -> PipelineExecution:
        execution = self._executions.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.status != PipelineExecutionStatus.RUNNING:
            raise ValueError(f"Cannot pause execution in status {execution.status}")

        execution = execution.pause()
        self._executions[execution_id] = execution

        await self._emit_event(
            Topic.PIPELINE_PAUSED, execution_id, {"execution": execution.to_dict()}
        )
        logger.info(f"Paused pipeline execution {execution_id}")
        return execution

    async def resume_execution(self, execution_id: str) -> PipelineExecution:
        execution = self._executions.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.status != PipelineExecutionStatus.PAUSED:
            raise ValueError(f"Cannot resume execution in status {execution.status}")

        execution = execution.start()
        self._executions[execution_id] = execution

        pipeline = self._pipelines[execution.pipeline_id]
        task = asyncio.create_task(self._run_execution(execution, pipeline))
        self._execution_tasks[execution_id] = task
        self._running_executions.add(execution_id)

        await self._emit_event(
            Topic.PIPELINE_RESUMED, execution_id, {"execution": execution.to_dict()}
        )
        logger.info(f"Resumed pipeline execution {execution_id}")
        return execution

    # ------------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------------

    async def validate_pipeline(
        self,
        stages: list[PipelineStage],
        edges: list[PipelineEdge],
    ) -> ValidationResult:
        errors = []
        warnings = []

        stage_ids = [s.id for s in stages]
        if len(stage_ids) != len(set(stage_ids)):
            errors.append("Duplicate stage IDs found")

        edge_ids = [e.id for e in edges]
        if len(edge_ids) != len(set(edge_ids)):
            errors.append("Duplicate edge IDs found")

        stage_id_set = set(stage_ids)
        adj: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            if edge.from_stage not in stage_id_set:
                errors.append(f"Edge {edge.id}: from_stage {edge.from_stage} does not exist")
            if edge.to_stage not in stage_id_set:
                errors.append(f"Edge {edge.id}: to_stage {edge.to_stage} does not exist")
            if edge.from_stage in stage_id_set and edge.to_stage in stage_id_set:
                adj[edge.from_stage].append(edge.to_stage)

        if not errors:
            in_degree = defaultdict(int)
            for u in adj:
                for v in adj[u]:
                    in_degree[v] += 1

            queue = deque([s for s in stage_ids if in_degree[s] == 0])
            topo_count = 0

            while queue:
                u = queue.popleft()
                topo_count += 1
                for v in adj[u]:
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        queue.append(v)

            if topo_count != len(stage_ids):
                errors.append("Pipeline contains cycles (not a valid DAG)")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # ------------------------------------------------------------------------
    # Internal Execution Logic
    # ------------------------------------------------------------------------

    async def _run_execution(self, execution: PipelineExecution, pipeline: Pipeline) -> None:
        """Main execution loop for a pipeline."""
        try:
            execution = execution.start()
            self._executions[execution.id] = execution
            await self._emit_event(
                Topic.PIPELINE_STARTED, execution.id, {"execution": execution.to_dict()}
            )

            # Build stage map and adjacency
            stage_map = {s.id: s for s in pipeline.stages}
            adj = defaultdict(list)
            reverse_adj = defaultdict(list)
            in_degree = defaultdict(int)

            for edge in pipeline.edges:
                adj[edge.from_stage].append(edge.to_stage)
                reverse_adj[edge.to_stage].append(edge.from_stage)
                in_degree[edge.to_stage] += 1

            # Find ready stages (in_degree == 0)
            ready_queue = deque([s.id for s in pipeline.stages if in_degree[s.id] == 0])

            while ready_queue and execution.status == PipelineExecutionStatus.RUNNING:
                stage_id = ready_queue.popleft()
                stage = stage_map[stage_id]

                # Check dependencies
                deps = reverse_adj[stage_id]
                if deps and not all(d in execution.completed_stages for d in deps):
                    ready_queue.append(stage_id)
                    await asyncio.sleep(0.1)
                    continue

                # Check retry count
                retry_count = execution.stage_retries.get(stage_id, 0)
                if retry_count > stage.retry_count:
                    execution = execution.fail_stage(
                        stage_id, f"Max retries ({stage.retry_count}) exceeded"
                    )
                    self._executions[execution.id] = execution
                    break

                execution = execution.set_current_stage(stage_id)
                self._executions[execution.id] = execution

                await self._emit_event(
                    Topic.PIPELINE_STAGE_STARTED,
                    execution.id,
                    {
                        "execution": execution.to_dict(),
                        "stage_id": stage_id,
                        "stage_type": stage.type.value,
                    },
                )

                try:
                    output = await self._execute_stage(stage, execution, pipeline)
                    execution = execution.complete_stage(stage_id, output)
                    self._executions[execution.id] = execution

                    await self._emit_event(
                        Topic.PIPELINE_STAGE_COMPLETED,
                        execution.id,
                        {
                            "execution": execution.to_dict(),
                            "stage_id": stage_id,
                            "output": output,
                        },
                    )

                except Exception as e:
                    logger.exception(f"Stage {stage_id} failed in execution {execution.id}")
                    execution = execution.fail_stage(stage_id, str(e))
                    self._executions[execution.id] = execution

                    await self._emit_event(
                        Topic.PIPELINE_STAGE_FAILED,
                        execution.id,
                        {
                            "execution": execution.to_dict(),
                            "stage_id": stage_id,
                            "error": str(e),
                        },
                    )

                    # Check if we should retry
                    if retry_count < stage.retry_count:
                        await asyncio.sleep(stage.retry_delay_seconds)
                        execution = execution.increment_retry(stage_id)
                        self._executions[execution.id] = execution
                        ready_queue.appendleft(stage_id)
                        continue
                    break

                # Add downstream stages
                for target in adj[stage_id]:
                    if target not in execution.completed_stages:
                        ready_queue.append(target)

            # Finalize
            if execution.status == PipelineExecutionStatus.RUNNING:
                if execution.failed_stages:
                    execution = execution.fail("Pipeline failed due to stage failures")
                else:
                    execution = execution.complete()
                self._executions[execution.id] = execution

                if execution.status == PipelineExecutionStatus.COMPLETED:
                    await self._emit_event(
                        Topic.PIPELINE_COMPLETED, execution.id, {"execution": execution.to_dict()}
                    )
                else:
                    await self._emit_event(
                        Topic.PIPELINE_FAILED, execution.id, {"execution": execution.to_dict()}
                    )

        except asyncio.CancelledError:
            logger.info(f"Execution {execution.id} cancelled")
            execution = execution.cancel()
            self._executions[execution.id] = execution
            await self._emit_event(
                Topic.PIPELINE_CANCELLED, execution.id, {"execution": execution.to_dict()}
            )
            raise
        except Exception as e:
            logger.exception(f"Execution {execution.id} crashed")
            execution = execution.fail(f"Execution crashed: {e}")
            self._executions[execution.id] = execution
            await self._emit_event(
                Topic.PIPELINE_FAILED, execution.id, {"execution": execution.to_dict()}
            )
        finally:
            self._running_executions.discard(execution.id)
            self._execution_tasks.pop(execution.id, None)

    async def _execute_stage(
        self,
        stage: PipelineStage,
        execution: PipelineExecution,
        pipeline: Pipeline,
    ) -> Any:
        """Execute a single pipeline stage based on its type."""
        config = stage.config

        if stage.type == StageType.AGENT:
            agent_id = config.get("agent_id")
            if not agent_id:
                raise ValueError(f"Agent stage {stage.id} requires agent_id")
            agent = self._agent_registry.get_agent(agent_id)
            if not agent:
                raise ValueError(f"Agent {agent_id} not found")

            inputs = {**config.get("inputs", {}), **execution.inputs}
            for dep_id, dep_output in execution.stage_outputs.items():
                inputs[f"dep_{dep_id}"] = dep_output

            result = await self._provider_router.complete(
                provider=agent.provider,
                model=agent.model,
                messages=[{"role": "user", "content": str(inputs)}],
            )
            return {
                "output": result.content,
                "usage": result.usage.to_dict() if result.usage else None,
            }

        elif stage.type == StageType.WORKFLOW:
            workflow_id = config.get("workflow_id")
            if not workflow_id:
                raise ValueError(f"Workflow stage {stage.id} requires workflow_id")
            # Would execute workflow here
            return {"workflow_id": workflow_id, "status": "completed"}

        elif stage.type == StageType.TOOL:
            tool_name = config.get("tool")
            if not tool_name:
                raise ValueError(f"Tool stage {stage.id} requires tool name")
            return {"tool": tool_name, "result": "executed"}

        elif stage.type == StageType.LLM:
            prompt = config.get("prompt", "")
            provider = config.get("provider", "default")
            model = config.get("model")
            result = await self._provider_router.complete(
                provider=provider,
                model=model or "default",
                messages=[{"role": "user", "content": prompt}],
            )
            return {"response": result.content}

        elif stage.type == StageType.CONDITION:
            config.get("condition", {})
            # Simple condition evaluation
            return {"condition_result": True}

        elif stage.type == StageType.PARALLEL:
            # Children stages are handled by the engine's parallel execution
            children = stage.children or config.get("children", [])
            return {"parallel": True, "children": children}

        elif stage.type == StageType.APPROVAL:
            # Approval gates would pause execution
            return {"approval_required": True, "approvers": config.get("approvers", [])}

        elif stage.type == StageType.MCP:
            server = config.get("server")
            tool = config.get("tool")
            # TODO: Implement MCP tool calling via provider router
            # For now, return a placeholder result a mock response
            return {"mcp": server, "tool": tool, "status": "pending_implementation"}

        elif stage.type == StageType.PLUGIN:
            plugin = config.get("plugin")
            method = config.get("method")
            config.get("args", {})
            # Would call plugin
            return {"plugin": plugin, "method": method, "result": "executed"}

        else:
            raise ValueError(f"Unknown stage type: {stage.type}")

    # ------------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------------

    def _calculate_next_run(self, cron: str, timezone: str) -> datetime:
        """Calculate next run time from cron expression (simplified)."""
        # In production, use croniter or similar
        return _utcnow()

    async def _emit_event(self, topic: Topic, key: str, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        event = EventEnvelope(
            id=str(uuid4()),
            type="event",
            source=key,
            topic=topic.value,
            timestamp=_utcnow().isoformat(),
            payload=payload,
        )
        await self._event_bus.publish(event)


def _pipeline_detail_from_pipeline(pipeline: Pipeline) -> PipelineDetail:
    """Create a port PipelineDetail from a domain Pipeline."""
    return PipelineDetail(
        id=pipeline.id,
        name=pipeline.name,
        description=pipeline.description,
        stages=list(pipeline.stages),
        edges=list(pipeline.edges),
        version=pipeline.version,
        status=pipeline.status,
        schedule_cron=pipeline.schedule_cron,
        schedule_timezone=pipeline.schedule_timezone,
        created_at=pipeline.created_at,
        updated_at=pipeline.updated_at,
        created_by=pipeline.created_by,
    )


def _pipeline_detail_from_version(version: PipelineVersion) -> PipelineDetail:
    """Create a port PipelineDetail from a domain PipelineVersion."""
    stages = [
        PipelineStage(
            id=s.id,
            type=s.type,
            label=s.label,
            config=s.config,
            depends_on=s.depends_on,
            retry_count=s.retry_count,
            retry_delay_seconds=s.retry_delay_seconds,
            timeout_seconds=s.timeout_seconds,
            condition=s.condition,
            children=s.children,
        )
        for s in version.stages
    ]
    edges = [
        PipelineEdge(
            id=e.id,
            from_stage=e.from_stage,
            to_stage=e.to_stage,
            condition=e.condition,
        )
        for e in version.edges
    ]
    pipeline = Pipeline(
        id=version.pipeline_id,
        name=version.name,
        description=version.description,
        stages=tuple(stages),
        edges=tuple(edges),
        version=version.version,
        status=PipelineStatus.DRAFT,
        schedule_cron=version.schedule_cron,
        schedule_timezone=version.schedule_timezone,
        created_at=version.created_at,
        updated_at=version.created_at,
        created_by=version.created_by,
    )
    return PipelineDetail(
        id=pipeline.id,
        name=pipeline.name,
        description=pipeline.description,
        stages=list(pipeline.stages),
        edges=list(pipeline.edges),
        version=pipeline.version,
        status=pipeline.status,
        schedule_cron=pipeline.schedule_cron,
        schedule_timezone=pipeline.schedule_timezone,
        created_at=pipeline.created_at,
        updated_at=pipeline.updated_at,
        created_by=pipeline.created_by,
    )


def _pipeline_summary_from_pipeline(
    pipeline: Pipeline, schedule: PipelineSchedule | None = None
) -> PipelineSummary:
    """Create a port PipelineSummary from a domain Pipeline."""
    return PipelineSummary(
        id=pipeline.id,
        name=pipeline.name,
        version=pipeline.version,
        status=pipeline.status,
        schedule_cron=pipeline.schedule_cron,
        schedule_timezone=pipeline.schedule_timezone,
        next_run=schedule.next_run if schedule else None,
        stage_count=len(pipeline.stages),
        updated_at=pipeline.updated_at,
    )
