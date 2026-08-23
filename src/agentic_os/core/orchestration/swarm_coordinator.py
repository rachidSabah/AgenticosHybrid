"""Phase 14 — Swarm Execution & Collaborative Agent Fabric.

Builds on the existing SwarmManager, CommunicationBus, and AgentRole
infrastructure. Adds:
  - SwarmCoordinator: wraps SwarmManager with BrainRegistry-driven
    team formation, consensus, shared memory, and failure recovery
  - ConsensusManager: majority/weighted/confidence/leader-override
  - SharedMissionMemory: shared context + working + decision memory
  - DynamicRoleAssigner: assigns roles based on capabilities
  - Failure recovery: brain.removed → swarm detects → replaces

All additive — existing SwarmManager, CommunicationBus, and
OrchestrationFramework are unchanged.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.orchestration.communication import CommunicationBus
    from agentic_os.core.orchestration.swarm import SwarmManager
    from agentic_os.core.orchestrator import Orchestrator
    from agentic_os.ports.event_bus import EventBus

log = get_logger("swarm.phase14")


def _new_id() -> str:
    return uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── Enums ──────────────────────────────────────────────────────────────


class ConsensusType(StrEnum):
    MAJORITY = "majority"
    WEIGHTED = "weighted"
    CONFIDENCE = "confidence"
    LEADER_OVERRIDE = "leader_override"


class SwarmRole(StrEnum):
    LEADER = "leader"
    PLANNER = "planner"
    RESEARCHER = "researcher"
    CODER = "coder"
    REVIEWER = "reviewer"
    VALIDATOR = "validator"
    EXECUTOR = "executor"
    OBSERVER = "observer"


class SwarmPhase(StrEnum):
    CREATED = "created"
    FORMING = "forming"
    ACTIVE = "active"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    DISBANDED = "disbanded"


# Map swarm roles to orchestrator roles understood by the dispatcher.
# "executor"/"leader"/"observer" intentionally fall through to keys absent
# from _ROLE_CAPABILITY_MAP (no required capabilities → any real provider).
_SWARM_ROLE_TO_ORCHESTRATOR_ROLE: dict[str, str] = {
    SwarmRole.CODER.value: "coding",
    SwarmRole.PLANNER.value: "planner",
    SwarmRole.RESEARCHER.value: "research",
    SwarmRole.REVIEWER.value: "reviewer",
    SwarmRole.VALIDATOR.value: "coding",
    SwarmRole.LEADER.value: "planner",
    SwarmRole.EXECUTOR.value: "executor",
    SwarmRole.OBSERVER.value: "executor",
}


# ── Consensus Result ───────────────────────────────────────────────────


class ConsensusResult:
    __slots__ = (
        "id",
        "swarm_id",
        "consensus_type",
        "proposal",
        "votes",
        "result",
        "confidence",
        "created_at",
    )

    def __init__(
        self,
        swarm_id: str = "",
        consensus_type: ConsensusType = ConsensusType.MAJORITY,
        proposal: str = "",
        votes: dict[str, str] | None = None,
        result: str = "",
        confidence: float = 0.0,
        consensus_id: str = "",
    ) -> None:
        self.id: str = consensus_id or _new_id()
        self.swarm_id: str = swarm_id
        self.consensus_type: ConsensusType = consensus_type
        self.proposal: str = proposal
        self.votes: dict[str, str] = votes or {}
        self.result: str = result
        self.confidence: float = confidence
        self.created_at: str = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "swarm_id": self.swarm_id,
            "consensus_type": self.consensus_type.value,
            "proposal": self.proposal,
            "votes": dict(self.votes),
            "result": self.result,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


# ── Shared Mission Memory ──────────────────────────────────────────────


class SharedMissionMemory:
    """Shared memory accessible by all swarm members.

    Partitions:
      - shared_context: mission-level context (read by all)
      - working_memory: temporary per-task data
      - decision_memory: recorded decisions
    """

    def __init__(self, mission_id: str = "") -> None:
        self.mission_id: str = mission_id
        self._lock = asyncio.Lock()
        self._shared_context: dict[str, Any] = {}
        self._working_memory: dict[str, Any] = {}
        self._decision_memory: list[dict[str, Any]] = []

    async def set_context(self, key: str, value: Any) -> None:
        async with self._lock:
            self._shared_context[key] = value

    async def get_context(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._shared_context.get(key, default)

    async def set_working(self, key: str, value: Any) -> None:
        async with self._lock:
            self._working_memory[key] = value

    async def get_working(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._working_memory.get(key, default)

    async def record_decision(self, decision: dict[str, Any]) -> None:
        async with self._lock:
            self._decision_memory.append(decision)

    async def get_decisions(self) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._decision_memory)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "context_keys": list(self._shared_context.keys()),
            "working_keys": list(self._working_memory.keys()),
            "decision_count": len(self._decision_memory),
        }


# ── Consensus Manager ──────────────────────────────────────────────────


class ConsensusManager:
    """Manages consensus voting for swarms."""

    def __init__(self) -> None:
        self._results: list[ConsensusResult] = []

    async def run_consensus(
        self,
        swarm_id: str,
        proposal: str,
        votes: dict[str, str],
        consensus_type: ConsensusType = ConsensusType.MAJORITY,
        member_weights: dict[str, float] | None = None,
        member_confidence: dict[str, float] | None = None,
    ) -> ConsensusResult:
        """Run a consensus vote and return the result.

        Args:
            swarm_id: The swarm running the consensus.
            proposal: What is being voted on.
            votes: dict of {member_id: "yes"/"no"/"abstain"}.
            consensus_type: How to resolve the vote.
            member_weights: For WEIGHTED consensus: {member_id: weight}.
            member_confidence: For CONFIDENCE consensus: {member_id: confidence}.
        """
        result_str = ""
        confidence = 0.0

        if consensus_type == ConsensusType.MAJORITY:
            yes = sum(1 for v in votes.values() if v == "yes")
            no = sum(1 for v in votes.values() if v == "no")
            result_str = "approved" if yes > no else ("rejected" if no > yes else "tie")
            confidence = yes / max(len(votes), 1)

        elif consensus_type == ConsensusType.WEIGHTED:
            weights = member_weights or {}
            yes_weight = sum(weights.get(m, 1.0) for m, v in votes.items() if v == "yes")
            no_weight = sum(weights.get(m, 1.0) for m, v in votes.items() if v == "no")
            total = yes_weight + no_weight
            result_str = "approved" if yes_weight > no_weight else "rejected"
            confidence = yes_weight / max(total, 1.0)

        elif consensus_type == ConsensusType.CONFIDENCE:
            confidences = member_confidence or {}
            yes_conf = sum(confidences.get(m, 0.5) for m, v in votes.items() if v == "yes")
            no_conf = sum(confidences.get(m, 0.5) for m, v in votes.items() if v == "no")
            result_str = "approved" if yes_conf > no_conf else "rejected"
            confidence = yes_conf / max(yes_conf + no_conf, 1.0)

        elif consensus_type == ConsensusType.LEADER_OVERRIDE:
            # Leader decides — first "yes" or "no" vote wins
            for v in votes.values():
                if v == "yes":
                    result_str = "approved"
                    break
                elif v == "no":
                    result_str = "rejected"
                    break
            else:
                result_str = "no_vote"
            confidence = 1.0 if result_str != "no_vote" else 0.0

        cr = ConsensusResult(
            swarm_id=swarm_id,
            consensus_type=consensus_type,
            proposal=proposal,
            votes=votes,
            result=result_str,
            confidence=round(confidence, 3),
        )
        self._results.append(cr)
        if len(self._results) > 200:
            self._results = self._results[-200:]
        return cr

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._results[-limit:]]


# ── Dynamic Role Assigner ──────────────────────────────────────────────


class DynamicRoleAssigner:
    """Assigns roles to swarm members based on their capabilities."""

    # Map capability string → role
    _CAPABILITY_TO_ROLE: dict[str, SwarmRole] = {
        "coding": SwarmRole.CODER,
        "code_generation": SwarmRole.CODER,
        "reasoning": SwarmRole.PLANNER,
        "testing": SwarmRole.VALIDATOR,
        "validation": SwarmRole.VALIDATOR,
        "research": SwarmRole.RESEARCHER,
        "documentation": SwarmRole.RESEARCHER,
        "review": SwarmRole.REVIEWER,
        "security": SwarmRole.REVIEWER,
        "terminal": SwarmRole.EXECUTOR,
        "file_operations": SwarmRole.EXECUTOR,
        "chat": SwarmRole.EXECUTOR,
    }

    def assign_roles(
        self,
        members: list[dict[str, Any]],
        existing_leader: str | None = None,
    ) -> dict[str, SwarmRole]:
        """Assign roles to members based on their capabilities.

        Args:
            members: List of member dicts with at least 'id' and 'capabilities'.
            existing_leader: If set, this member keeps the LEADER role.

        Returns:
            dict of {member_id: SwarmRole}
        """
        assignments: dict[str, SwarmRole] = {}
        used_roles: set[SwarmRole] = set()

        # If there's an existing leader, keep it
        if existing_leader:
            assignments[existing_leader] = SwarmRole.LEADER
            used_roles.add(SwarmRole.LEADER)

        for member in members:
            mid = str(member.get("id", ""))
            if not mid or mid in assignments:
                continue

            caps = member.get("capabilities", [])
            if isinstance(caps, (list, tuple)):
                caps = [str(c).lower() for c in caps]
            else:
                caps = []

            # Find the best matching role
            best_role = SwarmRole.EXECUTOR  # default
            for cap in caps:
                role = self._CAPABILITY_TO_ROLE.get(cap)
                if role and role not in used_roles:
                    best_role = role
                    break

            # First member without a leader becomes the leader
            if SwarmRole.LEADER not in used_roles:
                best_role = SwarmRole.LEADER

            assignments[mid] = best_role
            used_roles.add(best_role)

        return assignments


# ── Swarm Coordinator ──────────────────────────────────────────────────


class SwarmCoordinator:
    """Coordinates swarm lifecycle: creation, team formation, execution,
    consensus, shared memory, and failure recovery.

    Wraps the existing SwarmManager — does NOT replace it.
    """

    def __init__(
        self,
        bus: EventBus,
        swarm_manager: SwarmManager | None = None,
        brain_registry: BrainRegistry | None = None,
        comm_bus: CommunicationBus | None = None,
        orchestrator: Orchestrator | None = None,
    ) -> None:
        self._bus = bus
        self._swarm_mgr = swarm_manager
        self._registry = brain_registry
        self._comm = comm_bus
        self._orchestrator = orchestrator
        self._started = False
        self._subs: list[str] = []

        # Phase 14 components
        self._consensus = ConsensusManager()
        self._role_assigner = DynamicRoleAssigner()
        self._shared_memories: dict[str, SharedMissionMemory] = {}  # swarm_id → memory
        self._swarm_members: dict[str, list[dict[str, Any]]] = {}  # swarm_id → members
        self._swarm_roles: dict[str, dict[str, SwarmRole]] = {}  # swarm_id → {member_id: role}
        self._swarm_phases: dict[str, SwarmPhase] = {}  # swarm_id → phase
        self._swarm_mission_meta: dict[str, dict[str, Any]] = {}  # swarm_id → {title, source, created_at}
        self._swarm_history: list[dict[str, Any]] = []

    @property
    def consensus_manager(self) -> ConsensusManager:
        return self._consensus

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        # Subscribe to brain.removed for failure recovery
        try:
            sub_id = await self._bus.subscribe("brain.removed", self._on_brain_removed)
            self._subs.append(sub_id)
        except Exception:
            log.exception("Failed to subscribe to brain.removed")
        log.info("SwarmCoordinator started")

    async def stop(self) -> None:
        self._started = False
        for sub_id in self._subs:
            try:
                await self._bus.unsubscribe(sub_id)
            except Exception:
                pass
        self._subs.clear()
        log.info("SwarmCoordinator stopped")

    # ── Team Formation ─────────────────────────────────────────────

    async def create_team(
        self,
        goal: str = "",
        required_capabilities: list[str] | None = None,
        max_members: int = 5,
    ) -> dict[str, Any]:
        """Form an optimal team from discovered runtimes.

        Selection uses: capabilities, health, latency, availability,
        confidence, and historical success — never random.
        """
        required_capabilities = required_capabilities or ["chat"]
        members: list[dict[str, Any]] = []

        if self._registry is not None:
            try:
                brains = await self._registry.list_all()
                scored: list[tuple[dict[str, Any], float]] = []
                for b in brains:
                    caps = list(b.capabilities) if b.capabilities else []
                    health_score = b.health / 100.0
                    latency_score = max(0.0, 1.0 - (b.latency / 5000.0)) if b.latency > 0 else 0.5
                    cap_match = sum(1 for c in required_capabilities if c in caps) / max(
                        len(required_capabilities), 1
                    )
                    availability = 1.0 if b.health >= 50 else 0.0
                    # Confidence = weighted combination
                    confidence = (
                        health_score * 0.35
                        + latency_score * 0.25
                        + cap_match * 0.25
                        + availability * 0.15
                    )
                    scored.append(
                        (
                            {
                                "id": b.id,
                                "name": b.display_name,
                                "capabilities": caps,
                                "health": b.health,
                                "latency": b.latency,
                                "confidence": round(confidence, 3),
                            },
                            confidence,
                        )
                    )
                # Sort by confidence descending — best members first
                scored.sort(key=lambda x: x[1], reverse=True)
                members = [s[0] for s in scored[:max_members]]
            except Exception:
                log.exception("Failed to form team from BrainRegistry")

        # Assign roles
        roles = self._role_assigner.assign_roles(members)

        # Create shared memory
        swarm_id = _new_id()
        self._shared_memories[swarm_id] = SharedMissionMemory(mission_id=swarm_id)
        self._swarm_members[swarm_id] = members
        self._swarm_roles[swarm_id] = roles
        self._swarm_phases[swarm_id] = SwarmPhase.CREATED

        # Publish swarm.created
        await self._publish(
            "swarm.created",
            {
                "swarm_id": swarm_id,
                "goal": goal,
                "members": [m["id"] for m in members],
                "roles": {k: v.value for k, v in roles.items()},
            },
        )

        self._swarm_history.append(
            {
                "swarm_id": swarm_id,
                "goal": goal,
                "member_count": len(members),
                "created_at": _now_iso(),
                "phase": SwarmPhase.CREATED.value,
            }
        )

        log.info(
            "Swarm %s created with %d members for goal: %s",
            swarm_id,
            len(members),
            goal,
        )
        return {
            "swarm_id": swarm_id,
            "goal": goal,
            "members": members,
            "roles": {k: v.value for k, v in roles.items()},
            "phase": SwarmPhase.CREATED.value,
        }

    # ── Collaborative Execution ───────────────────────────────────

    async def execute_swarm(
        self, swarm_id: str, tasks: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Execute a collaborative mission across the swarm.

        Tasks are assigned to members based on their roles.
        Outputs are collected and merged.
        """
        if swarm_id not in self._swarm_members:
            return {"error": f"Swarm {swarm_id} not found"}

        members = self._swarm_members[swarm_id]
        roles = self._swarm_roles.get(swarm_id, {})
        tasks = tasks or []

        self._swarm_phases[swarm_id] = SwarmPhase.EXECUTING
        await self._publish(
            "swarm.execution.started",
            {"swarm_id": swarm_id, "task_count": len(tasks), "member_count": len(members)},
        )

        # Assign tasks to members by role
        task_assignments: list[dict[str, Any]] = []
        for i, task in enumerate(tasks):
            member_idx = i % max(len(members), 1)
            member = members[member_idx] if members else {}
            assigned_role = roles.get(member.get("id", ""), SwarmRole.EXECUTOR)
            task_assignments.append(
                {
                    "task_id": task.get("id", f"task-{i}"),
                    "title": task.get("title", ""),
                    "assigned_to": member.get("id", ""),
                    "assigned_name": member.get("name", ""),
                    "role": assigned_role.value,
                    "status": "assigned",
                }
            )

        # Execute each assignment through the real Orchestrator.  The domain
        # Task object is mutated in place — status/result/error reflect the
        # real provider execution.  Never fabricate success: a task left in
        # PENDING means no executable provider matched, which we report
        # honestly instead of marking it completed.
        executed_assignments: list[dict[str, Any]] = []
        if self._orchestrator is None:
            # No orchestrator wired — never invent results.
            for a in task_assignments:
                a["status"] = "unexecuted"
                a["error"] = "SwarmCoordinator has no orchestrator wired"
                executed_assignments.append(a)
        else:
            from agentic_os.domain.agent import Task, TaskStatus

            for a in task_assignments:
                domain_task = Task(
                    title=a["title"] or "Swarm task",
                    role=_SWARM_ROLE_TO_ORCHESTRATOR_ROLE.get(a.get("role", ""), "executor"),
                    description=a.get("description", ""),
                    user_prompt=a.get("user_prompt", "") or a["title"] or "",
                    mission_id=swarm_id,
                )
                try:
                    await self._orchestrator.dispatch_task(domain_task)
                except Exception as exc:  # provider raised outside dispatch
                    domain_task.status = TaskStatus.FAILED
                    domain_task.error = str(exc)

                if domain_task.status == TaskStatus.COMPLETED:
                    a["status"] = "completed"
                    a["output"] = domain_task.result or ""
                elif domain_task.status == TaskStatus.FAILED:
                    a["status"] = "failed"
                    a["error"] = domain_task.error or "Execution failed"
                else:
                    # PENDING after dispatch → no executable provider matched.
                    a["status"] = "pending"
                    a["error"] = "No executable provider matched this role"
                a["task_id"] = domain_task.id
                executed_assignments.append(a)

        completed = sum(1 for a in executed_assignments if a["status"] == "completed")
        failed = sum(1 for a in executed_assignments if a["status"] == "failed")
        total = len(executed_assignments)
        pending = total - completed - failed

        if total == 0:
            phase = SwarmPhase.COMPLETED
        elif failed > 0:
            phase = SwarmPhase.FAILED
        elif pending > 0:
            # No hard failures but some tasks could not execute — honest
            # per-assignment status carries the reason.
            phase = SwarmPhase.COMPLETED
        else:
            phase = SwarmPhase.COMPLETED
        self._swarm_phases[swarm_id] = phase

        await self._publish(
            "swarm.execution.failed" if failed > 0 else "swarm.execution.completed",
            {
                "swarm_id": swarm_id,
                "completed": completed,
                "failed": failed,
                "pending": pending,
            },
        )

        # Record in shared memory
        shared_mem = self._shared_memories.get(swarm_id)
        if shared_mem:
            await shared_mem.record_decision(
                {
                    "type": "execution_complete",
                    "swarm_id": swarm_id,
                    "task_count": total,
                    "completed": completed,
                    "failed": failed,
                }
            )

        return {
            "swarm_id": swarm_id,
            "phase": phase.value,
            "assignments": executed_assignments,
            "merged_result": {
                "total_tasks": total,
                "completed": completed,
                "failed": failed,
                "pending": pending,
            },
        }

    # ── Consensus ──────────────────────────────────────────────────

    async def run_consensus(
        self,
        swarm_id: str,
        proposal: str,
        votes: dict[str, str] | None = None,
        consensus_type: ConsensusType = ConsensusType.MAJORITY,
    ) -> dict[str, Any]:
        """Run a consensus vote within the swarm."""
        votes = votes or {}
        await self._publish(
            "swarm.consensus.started",
            {"swarm_id": swarm_id, "proposal": proposal, "consensus_type": consensus_type.value},
        )
        result = await self._consensus.run_consensus(
            swarm_id=swarm_id,
            proposal=proposal,
            votes=votes,
            consensus_type=consensus_type,
        )
        await self._publish(
            "swarm.consensus.completed",
            result.to_dict(),
        )
        return result.to_dict()

    # ── Rebalance ──────────────────────────────────────────────────

    async def rebalance(self, swarm_id: str) -> dict[str, Any]:
        """Rebalance the swarm by re-scoring members from BrainRegistry."""
        if swarm_id not in self._swarm_members:
            return {"error": f"Swarm {swarm_id} not found"}

        if self._registry is None:
            return {"swarm_id": swarm_id, "rebalanced": False, "reason": "no registry"}

        try:
            brains = await self._registry.list_all()
            brain_map = {b.id: b for b in brains}
            members = self._swarm_members[swarm_id]
            updated = 0
            for m in members:
                brain = brain_map.get(m["id"])
                if brain:
                    m["health"] = brain.health
                    m["latency"] = brain.latency
                    updated += 1
        except Exception:
            log.exception("Failed to rebalance swarm %s", swarm_id)
            return {"swarm_id": swarm_id, "rebalanced": False}

        await self._publish(
            "swarm.rebalanced",
            {"swarm_id": swarm_id, "updated_members": updated},
        )
        return {"swarm_id": swarm_id, "rebalanced": True, "updated_members": updated}

    # ── Disband ────────────────────────────────────────────────────

    async def disband(self, swarm_id: str) -> dict[str, Any]:
        """Disband a swarm."""
        if swarm_id not in self._swarm_phases:
            return {"error": f"Swarm {swarm_id} not found"}

        self._swarm_phases[swarm_id] = SwarmPhase.DISBANDED
        await self._publish(
            "swarm.disbanded",
            {"swarm_id": swarm_id},
        )

        # Update history
        for h in self._swarm_history:
            if h["swarm_id"] == swarm_id:
                h["phase"] = SwarmPhase.DISBANDED.value
                break

        return {"swarm_id": swarm_id, "status": "disbanded"}

    # ── Failure Recovery ───────────────────────────────────────────

    async def _on_brain_removed(self, event: Any) -> None:
        """Handle brain.removed — detect if a swarm member is lost."""
        payload = event.payload or {}
        brain_id = str(payload.get("id", ""))

        for swarm_id, members in list(self._swarm_members.items()):
            lost_member = None
            for m in members:
                if m.get("id") == brain_id:
                    lost_member = m
                    break

            if lost_member:
                log.warning(
                    "Swarm %s: member %s (%s) removed — searching for replacement",
                    swarm_id,
                    brain_id,
                    lost_member.get("name", ""),
                )
                # Remove the lost member
                self._swarm_members[swarm_id] = [m for m in members if m.get("id") != brain_id]
                await self._publish(
                    "swarm.member.left",
                    {"swarm_id": swarm_id, "member_id": brain_id},
                )

                # Find a replacement from BrainRegistry
                if self._registry is not None:
                    try:
                        brains = await self._registry.list_all()
                        existing_ids = {m["id"] for m in self._swarm_members[swarm_id]}
                        for b in brains:
                            if b.id not in existing_ids and b.health >= 50:
                                replacement = {
                                    "id": b.id,
                                    "name": b.display_name,
                                    "capabilities": list(b.capabilities) if b.capabilities else [],
                                    "health": b.health,
                                    "latency": b.latency,
                                }
                                self._swarm_members[swarm_id].append(replacement)
                                await self._publish(
                                    "swarm.member.joined",
                                    {
                                        "swarm_id": swarm_id,
                                        "member_id": b.id,
                                        "name": b.display_name,
                                    },
                                )
                                log.info(
                                    "Swarm %s: replacement %s added",
                                    swarm_id,
                                    b.display_name,
                                )
                                break
                    except Exception:
                        log.exception("Failed to find replacement for swarm %s", swarm_id)

    # ── Query ──────────────────────────────────────────────────────

    def get_swarm_status(self, swarm_id: str) -> dict[str, Any]:
        """Return the live status of a swarm."""
        if swarm_id not in self._swarm_phases:
            return {"error": f"Swarm {swarm_id} not found"}
        return {
            "swarm_id": swarm_id,
            "phase": self._swarm_phases[swarm_id].value,
            "member_count": len(self._swarm_members.get(swarm_id, [])),
            "roles": {k: v.value for k, v in self._swarm_roles.get(swarm_id, {}).items()},
            "shared_memory": self._shared_memories.get(swarm_id, SharedMissionMemory()).to_dict(),
        }

    def list_swarms(self) -> list[dict[str, Any]]:
        """List all swarms.

        Exposes name/status/topology/created_at so the Mission Control swarm
        view can bind to real state (the frontend matches on ``status``).
        """
        results: list[dict[str, Any]] = []
        for sid, phase in self._swarm_phases.items():
            members = self._swarm_members.get(sid, [])
            mission_meta = self._swarm_mission_meta.get(sid, {})
            # Mission-triggered swarms derive their status from the phase;
            # real (manually created) swarms are active while phase=executing.
            status = phase.value if phase != SwarmPhase.EXECUTING else "executing"
            results.append(
                {
                    "swarm_id": sid,
                    "name": mission_meta.get("title", sid),
                    "status": status,
                    "topology": mission_meta.get("topology", "mission"),
                    "phase": phase.value,
                    "member_count": len(members),
                    "members": [m.get("id") for m in members if isinstance(m, dict)],
                    "created_at": mission_meta.get("created_at"),
                    "source": mission_meta.get("source", "swarm"),
                }
            )
        return results

    def complete_mission(self, mission_id: str, failed: bool = False) -> None:
        """Transition a mission-triggered swarm to COMPLETED/FAILED.

        Called when a mission finishes so swarm state reflects real task
        outcome instead of staying 'executing' forever.
        """
        swarm_id = f"mission-{mission_id}"
        if swarm_id not in self._swarm_phases:
            return
        new_phase = SwarmPhase.FAILED if failed else SwarmPhase.COMPLETED
        self._swarm_phases[swarm_id] = new_phase
        self._swarm_history.append(
            {
                "swarm_id": swarm_id,
                "phase": new_phase.value,
                "completed_at": _now_iso(),
                "source": "mission",
            }
        )

    def record_mission(
        self,
        mission_id: str,
        title: str,
        agents: list[str] | None = None,
    ) -> dict[str, Any]:
        """Register a prompt mission as a mission-triggered swarm execution.

        Called when a mission starts so prompt-driven work surfaces in swarm
        orchestration (swarm list + history + EventBus) without requiring a
        manual /api/swarm/create. The pseudo swarm id is prefixed with
        "mission-" so real swarms and mission triggers stay distinguishable.
        """
        agents = [a for a in (agents or []) if a]
        swarm_id = f"mission-{mission_id}"
        if swarm_id not in self._swarm_phases:
            self._swarm_phases[swarm_id] = SwarmPhase.EXECUTING
        if swarm_id not in self._swarm_members:
            self._swarm_members[swarm_id] = [{"id": name, "role": "member"} for name in agents]
        if swarm_id not in self._swarm_roles:
            self._swarm_roles[swarm_id] = {}
        self._swarm_mission_meta[swarm_id] = {
            "title": title,
            "source": "mission",
            "created_at": _now_iso(),
        }
        entry = {
            "swarm_id": swarm_id,
            "goal": title,
            "member_count": len(self._swarm_members[swarm_id]),
            "created_at": _now_iso(),
            "phase": SwarmPhase.EXECUTING.value,
            "source": "mission",
        }
        self._swarm_history.append(entry)
        return entry

    def get_swarm_members(self, swarm_id: str) -> list[dict[str, Any]]:
        return self._swarm_members.get(swarm_id, [])

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._swarm_history[-limit:]

    def get_consensus_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._consensus.get_history(limit=limit)

    # ── Internals ──────────────────────────────────────────────────

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        from agentic_os.domain.events import EventEnvelope

        try:
            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="swarm.coordinator",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)
