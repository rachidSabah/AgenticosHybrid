"""Swarm Validation Engine — validates task outputs, plans, and agent results.

Implements schema validation, output validation, security validation,
policy validation, capability validation, execution validation, and quality scoring.
"""

from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.orchestration import (
    AgentDescriptor,
    AgentTask,
    OrchestrationPlan,
    ValidationResult,
    ValidationStatus,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.orchestration import ValidationPort

log = get_logger("orchestration.validation")


class ValidationEngine(ValidationPort):
    """Validates task outputs, plans, and agent-task assignments."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def validate_output(
        self,
        task: AgentTask,
        schema: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate a task's output."""
        errors: list[str] = []
        warnings: list[str] = []

        # Check for required fields
        if not task.output_data and task.status.value == "completed":
            warnings.append("Task completed but has no output data")

        # Schema validation
        if schema and task.output_data:
            missing_fields = [k for k in schema.get("required", []) if k not in task.output_data]
            if missing_fields:
                errors.append(f"Missing required fields: {missing_fields}")

        # Type validation
        if schema and task.output_data:
            type_map = schema.get("type_map", {})
            for field, expected_type_name in type_map.items():
                if field in task.output_data:
                    actual_type = type(task.output_data[field]).__name__
                    if actual_type != expected_type_name:
                        warnings.append(
                            f"Field '{field}' expected {expected_type_name}, got {actual_type}"
                        )

        status = ValidationStatus.FAILED if errors else ValidationStatus.PASSED
        score = max(0.0, 1.0 - len(errors) * 0.3 - len(warnings) * 0.1)

        result = ValidationResult(
            target_id=task.id,
            target_type="task",
            status=status,
            errors=tuple(errors),
            warnings=tuple(warnings),
            score=score,
            validator_name="output_validator",
        )

        await self._publish_event(result)
        return result

    async def validate_plan(self, plan: OrchestrationPlan) -> ValidationResult:
        """Validate a plan's structure and dependencies."""
        errors: list[str] = []
        warnings: list[str] = []

        # Check for empty plan
        if not plan.subtasks:
            errors.append("Plan has no subtasks")

        # Check dependency integrity
        task_ids = {t.id for t in plan.subtasks}
        for task in plan.subtasks:
            for dep in task.depends_on:
                if dep not in task_ids:
                    errors.append(f"Task '{task.id}' depends on unknown task '{dep}'")

        # Check for circular dependencies
        if await self._has_circular_deps(plan.subtasks):
            errors.append("Plan contains circular dependencies")

        status = ValidationStatus.FAILED if errors else ValidationStatus.PASSED
        score = 1.0 - len(errors) * 0.25

        result = ValidationResult(
            target_id=plan.id,
            target_type="plan",
            status=status,
            errors=tuple(errors),
            warnings=tuple(warnings),
            score=max(0.0, score),
            validator_name="plan_validator",
        )

        await self._publish_event(result)
        return result

    async def validate_security(
        self,
        task: AgentTask,
        agent: AgentDescriptor,
    ) -> ValidationResult:
        """Validate security constraints for task-agent assignment."""
        errors: list[str] = []
        warnings: list[str] = []

        # Check agent is healthy
        if agent.health_status != "healthy":
            warnings.append(f"Agent '{agent.name}' health is {agent.health_status}")

        # Check agent has required capabilities inferred from task
        task_keywords = set(task.title.lower().split())
        required_caps = {"code", "test", "deploy", "research", "analyze", "design"}
        matched = task_keywords & required_caps
        if matched and not agent.capabilities:
            errors.append(
                f"Agent '{agent.name}' has no capabilities for task with keywords: {matched}"
            )

        status = ValidationStatus.FAILED if errors else ValidationStatus.PASSED
        result = ValidationResult(
            target_id=task.id,
            target_type="task",
            status=status,
            errors=tuple(errors),
            warnings=tuple(warnings),
            score=0.0 if errors else 0.8,
            validator_name="security_validator",
            details={"agent_id": agent.agent_id, "agent_health": agent.health_status},
        )

        await self._publish_event(result)
        return result

    async def validate_policy(
        self,
        task: AgentTask,
        policies: dict[str, Any],
    ) -> ValidationResult:
        """Validate a task against execution policies."""
        errors: list[str] = []

        max_priority = policies.get("max_priority", 10)
        if task.priority > max_priority:
            errors.append(f"Task priority {task.priority} exceeds max {max_priority}")

        max_timeout = policies.get("max_timeout_seconds", 3600)
        if task.timeout_seconds > max_timeout:
            errors.append(f"Task timeout {task.timeout_seconds}s exceeds max {max_timeout}s")

        status = ValidationStatus.FAILED if errors else ValidationStatus.PASSED
        result = ValidationResult(
            target_id=task.id,
            target_type="task",
            status=status,
            errors=tuple(errors),
            score=1.0 if not errors else 0.0,
            validator_name="policy_validator",
        )

        await self._publish_event(result)
        return result

    async def _has_circular_deps(self, tasks: tuple[AgentTask, ...]) -> bool:
        """Detect circular dependencies among tasks."""
        task_map = {t.id: t for t in tasks}
        visited: set[str] = set()
        in_stack: set[str] = set()

        def _dfs(task_id: str) -> bool:
            if task_id in in_stack:
                return True
            if task_id in visited:
                return False
            task = task_map.get(task_id)
            if not task or not task.depends_on:
                visited.add(task_id)
                return False
            in_stack.add(task_id)
            for dep in task.depends_on:
                if _dfs(dep):
                    return True
            in_stack.discard(task_id)
            visited.add(task_id)
            return False

        for t in tasks:
            if _dfs(t.id):
                return True
        return False

    async def _publish_event(self, result: ValidationResult) -> None:
        topic = (
            Topic.ORCH_VALIDATION_PASSED
            if result.status == ValidationStatus.PASSED
            else Topic.ORCH_VALIDATION_FAILED
        )
        try:
            await self._bus.publish(
                EventEnvelope(
                    type="event",
                    source="validation-engine",
                    topic=topic.value,
                    payload=result.to_dict(),
                )
            )
        except Exception as exc:
            log.warning("Publish failed", error=str(exc))
