"""
Workflow Engine Implementation

Core workflow execution engine with DAG traversal, versioning, replay, and approval gates.
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
from agentic_os.domain.workflow import (
    NodeType,
    Workflow,
    WorkflowEdge,
    WorkflowExecution,
    WorkflowExecutionStatus,
    WorkflowNode,
    WorkflowStatus,
    WorkflowVersion,
)
from agentic_os.ports.event_bus import EventBus, EventEnvelope
from agentic_os.ports.workflow import (
    ValidationResult,
    WorkflowApproval,
    WorkflowCreate,
    WorkflowDetail,
    WorkflowEnginePort,
    WorkflowExecute,
    WorkflowReplay,
    WorkflowSummary,
    WorkflowUpdate,
)

logger = logging.getLogger(__name__)


class WorkflowEngineImpl(WorkflowEnginePort):
    """
    Workflow engine implementing DAG-based execution with:
    - Topological sort for execution order
    - Node-level state tracking
    - Approval gates
    - Replay from any node
    - Version management
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
        self._workflows: dict[str, Workflow] = {}
        self._workflow_versions: dict[str, list[WorkflowVersion]] = defaultdict(list)
        self._executions: dict[str, WorkflowExecution] = {}
        self._running_executions: set[str] = set()
        self._execution_tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------------
    # CRUD Operations
    # ------------------------------------------------------------------------

    async def create_workflow(self, data: WorkflowCreate) -> WorkflowDetail:
        workflow = Workflow.create(
            name=data.name,
            description=data.description,
            nodes=data.nodes,
            edges=data.edges,
            template_id=data.template_id,
            created_by=data.created_by,
        )
        self._workflows[workflow.id] = workflow
        await self._emit_event(
            Topic.WORKFLOW_CREATED, workflow.id, {"workflow": workflow.to_dict()}
        )
        logger.info(f"Created workflow {workflow.id}: {workflow.name}")
        return _workflow_detail_from_workflow(workflow)

    async def get_workflow(self, workflow_id: str) -> WorkflowDetail | None:
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return None
        return _workflow_detail_from_workflow(workflow)

    async def list_workflows(
        self,
        status: WorkflowStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowSummary]:
        workflows = list(self._workflows.values())
        if status:
            workflows = [w for w in workflows if w.status == status]
        workflows.sort(key=lambda w: w.updated_at, reverse=True)
        return [_workflow_summary_from_workflow(w) for w in workflows[offset : offset + limit]]

    async def update_workflow(self, workflow_id: str, data: WorkflowUpdate) -> WorkflowDetail:
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Check if structure changed (nodes/edges) - if so, create new version
        structure_changed = (
            data.nodes is not None and [n.id for n in data.nodes] != [n.id for n in workflow.nodes]
        ) or (
            data.edges is not None and [e.id for e in data.edges] != [e.id for e in workflow.edges]
        )

        if structure_changed:
            new_workflow = workflow.new_version(
                name=data.name,
                description=data.description,
                nodes=data.nodes,
                edges=data.edges,
                created_by=data.updated_by,
            )
        else:
            new_workflow = Workflow(
                id=workflow.id,
                name=data.name or workflow.name,
                description=data.description or workflow.description,
                nodes=workflow.nodes,
                edges=workflow.edges,
                version=workflow.version,
                status=workflow.status,
                template_id=workflow.template_id,
                created_at=workflow.created_at,
                updated_at=datetime.now(UTC),
                created_by=workflow.created_by,
            )

        self._workflows[workflow_id] = new_workflow
        await self._emit_event(
            Topic.WORKFLOW_UPDATED, workflow_id, {"workflow": new_workflow.to_dict()}
        )
        logger.info(f"Updated workflow {workflow_id} to version {new_workflow.version}")
        return _workflow_detail_from_workflow(new_workflow)

    async def delete_workflow(self, workflow_id: str) -> bool:
        if workflow_id not in self._workflows:
            return False

        # Check for running executions
        running = any(
            e.workflow_id == workflow_id and e.status == WorkflowExecutionStatus.RUNNING
            for e in self._executions.values()
        )
        if running:
            raise ValueError(f"Cannot delete workflow {workflow_id}: has running executions")

        del self._workflows[workflow_id]
        if workflow_id in self._workflow_versions:
            del self._workflow_versions[workflow_id]
        await self._emit_event(Topic.WORKFLOW_DELETED, workflow_id, {})
        logger.info(f"Deleted workflow {workflow_id}")
        return True

    # ------------------------------------------------------------------------
    # Version Management
    # ------------------------------------------------------------------------

    async def get_workflow_versions(self, workflow_id: str) -> list[WorkflowVersion]:
        return self._workflow_versions.get(workflow_id, [])

    async def get_workflow_version(self, workflow_id: str, version: int) -> WorkflowDetail | None:
        workflow = self._workflows.get(workflow_id)
        if workflow and workflow.version == version:
            return _workflow_detail_from_workflow(workflow)
        # Check historical versions
        for v in self._workflow_versions.get(workflow_id, []):
            if v.version == version:
                return _workflow_detail_from_version(v)
        return None

    # ------------------------------------------------------------------------
    # Execution Operations
    # ------------------------------------------------------------------------

    async def execute_workflow(self, workflow_id: str, data: WorkflowExecute) -> WorkflowExecution:
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        if workflow.status != WorkflowStatus.ACTIVE:
            raise ValueError(f"Workflow {workflow_id} is not active (status: {workflow.status})")

        execution = WorkflowExecution.create(
            workflow_id=workflow_id,
            workflow_version=workflow.version,
            inputs=data.inputs,
            parent_execution_id=data.parent_execution_id,
            replay_from_node=data.replay_from_node,
        )

        self._executions[execution.id] = execution
        self._running_executions.add(execution.id)

        # Start execution in background
        task = asyncio.create_task(self._run_execution(execution, workflow))
        self._execution_tasks[execution.id] = task

        await self._emit_event(
            Topic.WORKFLOW_STARTED, execution.id, {"execution": execution.to_dict()}
        )
        logger.info(f"Started workflow execution {execution.id} for workflow {workflow_id}")
        return execution

    async def replay_workflow(self, workflow_id: str, data: WorkflowReplay) -> WorkflowExecution:
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        execution = WorkflowExecution.create(
            workflow_id=workflow_id,
            workflow_version=data.version or workflow.version,
            inputs=data.inputs or {},
            replay_from_node=data.from_node,
        )

        self._executions[execution.id] = execution
        self._running_executions.add(execution.id)

        task = asyncio.create_task(self._run_execution(execution, workflow))
        self._execution_tasks[execution.id] = task

        await self._emit_event(
            Topic.WORKFLOW_REPLAYED, execution.id, {"execution": execution.to_dict()}
        )
        logger.info(f"Replayed workflow execution {execution.id} for workflow {workflow_id}")
        return execution

    async def approve_workflow(self, workflow_id: str, data: WorkflowApproval) -> WorkflowExecution:
        # Find execution for this workflow that's awaiting approval
        execution = None
        for e in self._executions.values():
            if (
                e.workflow_id == workflow_id
                and e.status == WorkflowExecutionStatus.AWAITING_APPROVAL
            ):
                if e.pending_approval == data.node_id:
                    execution = e
                    break

        if not execution:
            raise ValueError(f"No execution awaiting approval for node {data.node_id}")

        updated = execution.decide_approval(
            node_id=data.node_id,
            approved=data.approved,
            decided_by=data.decided_by,
            reason=data.reason,
        )
        self._executions[execution.id] = updated

        if data.approved:
            await self._emit_event(
                Topic.WORKFLOW_APPROVAL_DECIDED,
                execution.id,
                {
                    "execution": updated.to_dict(),
                    "approved": True,
                    "node_id": data.node_id,
                },
            )
        else:
            await self._emit_event(
                Topic.WORKFLOW_APPROVAL_DECIDED,
                execution.id,
                {
                    "execution": updated.to_dict(),
                    "approved": False,
                    "node_id": data.node_id,
                },
            )

        logger.info(
            f"Approval {'approved' if data.approved else 'denied'} for execution "
            f"{execution.id}, node {data.node_id}"
        )
        return updated

    # ------------------------------------------------------------------------
    # Query Operations
    # ------------------------------------------------------------------------

    async def get_execution(self, execution_id: str) -> WorkflowExecution | None:
        return self._executions.get(execution_id)

    async def get_workflow_executions(
        self,
        workflow_id: str,
        status: WorkflowExecutionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowExecution]:
        executions = [e for e in self._executions.values() if e.workflow_id == workflow_id]
        if status:
            executions = [e for e in executions if e.status == status]
        executions.sort(key=lambda e: e.started_at, reverse=True)
        return executions[offset : offset + limit]

    async def get_running_executions(self) -> list[WorkflowExecution]:
        return [e for e in self._executions.values() if e.status == WorkflowExecutionStatus.RUNNING]

    # ------------------------------------------------------------------------
    # Control Operations
    # ------------------------------------------------------------------------

    async def cancel_execution(self, execution_id: str) -> WorkflowExecution:
        execution = self._executions.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.status not in (
            WorkflowExecutionStatus.RUNNING,
            WorkflowExecutionStatus.PAUSED,
            WorkflowExecutionStatus.AWAITING_APPROVAL,
        ):
            raise ValueError(f"Cannot cancel execution in status {execution.status}")

        # Cancel the running task
        task = self._execution_tasks.get(execution_id)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._execution_tasks[execution_id]

        self._running_executions.discard(execution_id)
        updated = execution.cancel()
        self._executions[execution_id] = updated

        await self._emit_event(
            Topic.WORKFLOW_CANCELLED, execution_id, {"execution": updated.to_dict()}
        )
        logger.info(f"Cancelled workflow execution {execution_id}")
        return updated

    async def pause_execution(self, execution_id: str) -> WorkflowExecution:
        execution = self._executions.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.status != WorkflowExecutionStatus.RUNNING:
            raise ValueError(f"Cannot pause execution in status {execution.status}")

        updated = execution.pause()
        self._executions[execution_id] = updated

        await self._emit_event(
            Topic.WORKFLOW_PAUSED, execution_id, {"execution": updated.to_dict()}
        )
        logger.info(f"Paused workflow execution {execution_id}")
        return updated

    async def resume_execution(self, execution_id: str) -> WorkflowExecution:
        execution = self._executions.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.status != WorkflowExecutionStatus.PAUSED:
            raise ValueError(f"Cannot resume execution in status {execution.status}")

        updated = execution.start()
        self._executions[execution_id] = updated

        task = asyncio.create_task(
            self._run_execution(updated, self._workflows[execution.workflow_id])
        )
        self._execution_tasks[execution_id] = task
        self._running_executions.add(execution_id)

        await self._emit_event(
            Topic.WORKFLOW_RESUMED, execution_id, {"execution": updated.to_dict()}
        )
        logger.info(f"Resumed workflow execution {execution_id}")
        return updated

    # ------------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------------

    async def validate_workflow(
        self,
        nodes: list[WorkflowNode],
        edges: list[WorkflowEdge],
    ) -> ValidationResult:
        errors = []
        warnings = []

        # Check for duplicate node IDs
        node_ids = [n.id for n in nodes]
        if len(node_ids) != len(set(node_ids)):
            errors.append("Duplicate node IDs found")

        # Check for duplicate edge IDs
        edge_ids = [e.id for e in edges]
        if len(edge_ids) != len(set(edge_ids)):
            errors.append("Duplicate edge IDs found")

        # Build adjacency list for cycle detection
        node_id_set = set(node_ids)
        adj: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            if edge.source not in node_id_set:
                errors.append(f"Edge {edge.id}: source node {edge.source} does not exist")
            if edge.target not in node_id_set:
                errors.append(f"Edge {edge.id}: target node {edge.target} does not exist")
            if edge.source in node_id_set and edge.target in node_id_set:
                adj[edge.source].append(edge.target)

        # Check for cycles using Kahn's algorithm
        if not errors:
            in_degree = defaultdict(int)
            for u in adj:
                for v in adj[u]:
                    in_degree[v] += 1

            queue = deque([n for n in node_ids if in_degree[n] == 0])
            topo_count = 0

            while queue:
                u = queue.popleft()
                topo_count += 1
                for v in adj[u]:
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        queue.append(v)

            if topo_count != len(node_ids):
                errors.append("Workflow contains cycles (not a valid DAG)")

        # Check for start/end nodes
        has_start = any(n.type == NodeType.START for n in nodes)
        has_end = any(n.type == NodeType.END for n in nodes)
        if not has_start:
            warnings.append("Workflow has no START node")
        if not has_end:
            warnings.append("Workflow has no END node")

        # Check for unreachable nodes (optional warning)
        # Could add more sophisticated analysis here

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # ------------------------------------------------------------------------
    # Internal Execution Logic
    # ------------------------------------------------------------------------

    async def _run_execution(self, execution: WorkflowExecution, workflow: Workflow) -> None:
        """Main execution loop for a workflow."""
        try:
            # Update execution to running
            execution = execution.start()
            self._executions[execution.id] = execution
            await self._emit_event(
                Topic.WORKFLOW_STARTED, execution.id, {"execution": execution.to_dict()}
            )

            # Build execution plan
            node_map = {n.id: n for n in workflow.nodes}
            adj = defaultdict(list)
            reverse_adj = defaultdict(list)
            in_degree = defaultdict(int)

            for edge in workflow.edges:
                adj[edge.source].append(edge.target)
                reverse_adj[edge.target].append(edge.source)
                in_degree[edge.target] += 1

            # Find start nodes (in_degree == 0)
            ready_queue = deque([n.id for n in workflow.nodes if in_degree[n.id] == 0])

            # Handle replay: if replaying from a specific node, only execute from there
            if execution.replay_from_node:
                ready_queue = deque([execution.replay_from_node])

            while ready_queue and execution.status == WorkflowExecutionStatus.RUNNING:
                node_id = ready_queue.popleft()
                node = node_map[node_id]

                # Skip if already completed
                if node_id in execution.completed_nodes:
                    continue

                # Check if all dependencies completed
                deps = reverse_adj[node_id]
                if deps and not all(d in execution.completed_nodes for d in deps):
                    # Re-queue for later
                    ready_queue.append(node_id)
                    continue

                # Execute node
                execution = execution.set_current_node(node_id)
                self._executions[execution.id] = execution
                await self._emit_event(
                    Topic.WORKFLOW_NODE_STARTED,
                    execution.id,
                    {
                        "execution": execution.to_dict(),
                        "node_id": node_id,
                        "node_type": node.type.value,
                    },
                )

                try:
                    output = await self._execute_node(node, execution, workflow)
                    execution = execution.complete_node(node_id, output)
                    self._executions[execution.id] = execution
                    await self._emit_event(
                        Topic.WORKFLOW_NODE_COMPLETED,
                        execution.id,
                        {
                            "execution": execution.to_dict(),
                            "node_id": node_id,
                            "output": output,
                        },
                    )
                except ApprovalRequired as e:
                    # Node requires approval - pause execution
                    execution = execution.request_approval(node_id, e.context)
                    self._executions[execution.id] = execution
                    await self._emit_event(
                        Topic.WORKFLOW_APPROVAL_REQUESTED,
                        execution.id,
                        {
                            "execution": execution.to_dict(),
                            "node_id": node_id,
                            "context": e.context,
                        },
                    )
                    # Execution will be resumed via approve_workflow
                    return
                except Exception as e:
                    logger.exception(f"Node {node_id} failed in execution {execution.id}")
                    execution = execution.fail(str(e), failed_node=node_id)
                    self._executions[execution.id] = execution
                    await self._emit_event(
                        Topic.WORKFLOW_NODE_FAILED,
                        execution.id,
                        {
                            "execution": execution.to_dict(),
                            "node_id": node_id,
                            "error": str(e),
                        },
                    )
                    # Continue to fail the workflow
                    break

                # Add downstream nodes to ready queue
                for target in adj[node_id]:
                    if target not in execution.completed_nodes:
                        ready_queue.append(target)

            # Check final status
            if execution.status == WorkflowExecutionStatus.RUNNING:
                if execution.failed_nodes:
                    execution = execution.fail("Workflow failed due to node failures")
                else:
                    execution = execution.complete()
                self._executions[execution.id] = execution

                if execution.status == WorkflowExecutionStatus.COMPLETED:
                    await self._emit_event(
                        Topic.WORKFLOW_COMPLETED, execution.id, {"execution": execution.to_dict()}
                    )
                else:
                    await self._emit_event(
                        Topic.WORKFLOW_FAILED, execution.id, {"execution": execution.to_dict()}
                    )

        except asyncio.CancelledError:
            logger.info(f"Execution {execution.id} cancelled")
            execution = execution.cancel()
            self._executions[execution.id] = execution
            await self._emit_event(
                Topic.WORKFLOW_CANCELLED, execution.id, {"execution": execution.to_dict()}
            )
            raise
        except Exception as e:
            logger.exception(f"Execution {execution.id} crashed")
            execution = execution.fail(f"Execution crashed: {e}")
            self._executions[execution.id] = execution
            await self._emit_event(
                Topic.WORKFLOW_FAILED, execution.id, {"execution": execution.to_dict()}
            )
        finally:
            self._running_executions.discard(execution.id)
            self._execution_tasks.pop(execution.id, None)

    async def _execute_node(
        self,
        node: WorkflowNode,
        execution: WorkflowExecution,
        workflow: Workflow,
    ) -> Any:
        """Execute a single workflow node based on its type."""
        config = node.config

        if node.type == NodeType.START:
            return {"status": "started", "inputs": execution.inputs}

        elif node.type == NodeType.END:
            # Return final output
            return {"status": "completed", "result": execution.node_outputs}

        elif node.type == NodeType.AGENT:
            # Execute agent via provider router
            agent_id = config.get("agent_id")
            if not agent_id:
                raise ValueError("Agent node requires agent_id in config")

            agent = self._agent_registry.get_agent(agent_id)
            if not agent:
                raise ValueError(f"Agent {agent_id} not found")

            # Prepare inputs from node config and execution context
            inputs = {**config.get("inputs", {}), **execution.inputs}

            # Add outputs from completed dependency nodes
            for dep_id, dep_output in execution.node_outputs.items():
                inputs[f"dep_{dep_id}"] = dep_output

            # Route to provider
            result = await self._provider_router.complete(
                provider=agent.provider,
                model=agent.model,
                messages=[{"role": "user", "content": str(inputs)}],
            )
            return {
                "output": result.content,
                "usage": result.usage.to_dict() if result.usage else None,
            }

        elif node.type == NodeType.TOOL:
            # Execute tool
            tool_name = config.get("tool")
            if not tool_name:
                raise ValueError("Tool node requires tool name in config")
            # Tool execution would go through provider or direct tool calling
            # For now return mock
            return {"tool": tool_name, "result": "executed"}

        elif node.type == NodeType.APPROVAL:
            # Raise approval exception to pause execution
            raise ApprovalRequired(config.get("context", {"message": "Approval required"}))

        elif node.type == NodeType.CONDITION:
            # Evaluate condition
            config.get("condition", {})
            # Simple condition evaluation - extend as needed
            return {"condition_result": True}

        elif node.type == NodeType.PARALLEL:
            # Parallel execution marker - actual parallelism handled by engine
            return {"parallel": True, "children": node.config.get("children", [])}

        elif node.type == NodeType.SUBWORKFLOW:
            # Execute subworkflow
            sub_id = node.subworkflow_id
            if not sub_id:
                raise ValueError("Subworkflow node requires subworkflow_id")
            # Would launch subworkflow execution and wait
            return {"subworkflow": sub_id, "status": "completed"}

        elif node.type == NodeType.LLM:
            # Direct LLM call
            prompt = config.get("prompt", "")
            return {"prompt": prompt, "response": "llm_response"}

        else:
            raise ValueError(f"Unknown node type: {node.type}")

    # ------------------------------------------------------------------------
    # Event Emission
    # ------------------------------------------------------------------------

    async def _emit_event(self, topic: Topic, key: str, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        event = EventEnvelope(
            id=str(uuid4()),
            type="event",
            source=key,
            topic=topic.value,
            timestamp=datetime.now(UTC).isoformat(),
            payload=payload,
        )
        await self._event_bus.publish(event)


class ApprovalRequired(Exception):
    """Exception raised when a workflow node requires approval."""

    def __init__(self, context: dict[str, Any]):
        self.context = context
        super().__init__("Approval required")


# ------------------------------------------------------------------------
# Type Helpers (needed for the Workflow class)
# ------------------------------------------------------------------------


def _workflow_detail_from_workflow(workflow: Workflow) -> WorkflowDetail:
    """Create a port WorkflowDetail from a domain Workflow."""
    return WorkflowDetail(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        nodes=list(workflow.nodes),
        edges=list(workflow.edges),
        version=workflow.version,
        status=workflow.status,
        template_id=workflow.template_id,
        created_at=workflow.created_at.isoformat(),
        updated_at=workflow.updated_at.isoformat(),
        created_by=workflow.created_by,
    )


def _workflow_detail_from_version(version: WorkflowVersion) -> WorkflowDetail:
    """Create a port WorkflowDetail from a domain WorkflowVersion."""
    nodes = [
        WorkflowNode(
            id=n.id,
            type=n.type,
            label=n.label,
            config=n.config,
            position=n.position,
            subworkflow_id=n.subworkflow_id,
        )
        for n in version.nodes
    ]
    edges = [
        WorkflowEdge(
            id=e.id,
            source=e.source,
            target=e.target,
            source_handle=e.source_handle,
            target_handle=e.target_handle,
            condition=e.condition,
        )
        for e in version.edges
    ]
    workflow = Workflow(
        id=version.workflow_id,
        name=version.name,
        description=version.description,
        nodes=tuple(nodes),
        edges=tuple(edges),
        version=version.version,
        status=WorkflowStatus.DRAFT,
        template_id=None,
        created_at=version.created_at,
        updated_at=version.created_at,
        created_by=version.created_by,
    )
    return WorkflowDetail(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        nodes=list(workflow.nodes),
        edges=list(workflow.edges),
        version=workflow.version,
        status=workflow.status,
        template_id=workflow.template_id,
        created_at=workflow.created_at.isoformat(),
        updated_at=workflow.updated_at.isoformat(),
        created_by=workflow.created_by,
    )


def _workflow_summary_from_workflow(workflow: Workflow) -> WorkflowSummary:
    """Create a port WorkflowSummary from a domain Workflow."""
    return WorkflowSummary(
        id=workflow.id,
        name=workflow.name,
        version=workflow.version,
        status=workflow.status,
        updated_at=workflow.updated_at.isoformat(),
    )
