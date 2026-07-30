"""Phase 17 — CodeGenerationPlanner.

Generates PLANS for new artifacts (capabilities, agents, workflows,
planners, tools, orchestrators, strategies) — NOT executable code.

The planner produces a GenerationPlan blueprint that describes:
  - what to create
  - why (rationale + evidence)
  - dependencies
  - affected modules
  - validation strategy
  - rollout + rollback steps

Plans are reviewed by SafetyValidator before any generation happens.
Phase 17 never directly overwrites existing production code.
"""

from __future__ import annotations

from typing import Any

from agentic_os.core.evolution.domain import (
    GenerationPlan,
    GenerationTargetType,
    ImprovementProposal,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("evolution.code_gen")


class CodeGenerationPlanner:
    """Generates artifact blueprints from improvement proposals."""

    def __init__(self) -> None:
        self._plans: list[GenerationPlan] = []
        self._stats: dict[str, Any] = {
            "total_plans": 0,
            "by_type": {t.value: 0 for t in GenerationTargetType},
        }

    # ── Public API ──────────────────────────────────────────────────

    async def plan_from_proposal(self, proposal: ImprovementProposal) -> GenerationPlan | None:
        """Generate a plan for a proposal. Returns None if not applicable."""
        target_type = self._map_improvement_to_target(proposal.type)
        if target_type is None:
            return None

        blueprint = self._build_blueprint(proposal, target_type)
        deps = self._identify_dependencies(proposal, target_type)
        affected = self._identify_affected_modules(proposal, target_type)
        rollout = self._build_rollout_steps(proposal, target_type)
        rollback = self._build_rollback_steps(proposal, target_type)

        plan = GenerationPlan(
            target_type=target_type,
            name=proposal.title,
            description=proposal.description,
            blueprint=blueprint,
            dependencies=deps,
            affected_modules=affected,
            validation_strategy=self._build_validation_strategy(target_type),
            rollout_steps=rollout,
            rollback_steps=rollback,
            status="draft",
        )

        self._plans.append(plan)
        self._stats["total_plans"] += 1
        self._stats["by_type"][target_type.value] = (
            self._stats["by_type"].get(target_type.value, 0) + 1
        )
        # Cap stored plans
        if len(self._plans) > 200:
            self._plans = self._plans[-200:]

        log.info(
            "Generation plan created",
            plan_id=plan.id,
            target_type=target_type.value,
            name=plan.name,
        )
        return plan

    def list_plans(
        self, target_type: GenerationTargetType | str | None = None
    ) -> list[GenerationPlan]:
        if target_type is None:
            return list(self._plans)
        if isinstance(target_type, str):
            try:
                target_type = GenerationTargetType(target_type)
            except ValueError:
                return []
        return [p for p in self._plans if p.target_type == target_type]

    def get_plan(self, plan_id: str) -> GenerationPlan | None:
        for p in self._plans:
            if p.id == plan_id:
                return p
        return None

    def update_plan_status(self, plan_id: str, status: str) -> bool:
        plan = self.get_plan(plan_id)
        if plan is None:
            return False
        plan.status = status
        return True

    def stats(self) -> dict[str, Any]:
        return {**self._stats, "stored": len(self._plans)}

    # ── Mapping ─────────────────────────────────────────────────────

    def _map_improvement_to_target(self, imp_type: Any) -> GenerationTargetType | None:
        """Map ImprovementType → GenerationTargetType."""
        mapping = {
            "capability_expansion": GenerationTargetType.CAPABILITY,
            "new_agent": GenerationTargetType.AGENT,
            "new_workflow": GenerationTargetType.WORKFLOW,
            "new_planner": GenerationTargetType.PLANNER,
            "new_tool": GenerationTargetType.TOOL,
            "new_orchestrator": GenerationTargetType.ORCHESTRATOR,
            "new_strategy": GenerationTargetType.STRATEGY,
        }
        imp_value = imp_type.value if hasattr(imp_type, "value") else str(imp_type)
        return mapping.get(imp_value)

    # ── Blueprint building ──────────────────────────────────────────

    def _build_blueprint(
        self, proposal: ImprovementProposal, target_type: GenerationTargetType
    ) -> dict[str, Any]:
        """Build the artifact blueprint."""
        blueprint: dict[str, Any] = {
            "name": proposal.title,
            "type": target_type.value,
            "rationale": proposal.rationale,
            "target_capability": proposal.target_capability,
            "expected_impact": proposal.expected_impact,
        }

        if target_type == GenerationTargetType.CAPABILITY:
            blueprint["interface"] = {
                "name": proposal.target_capability,
                "methods": [],
            }
            blueprint["adapter_pattern"] = "hexagonal"
        elif target_type == GenerationTargetType.AGENT:
            blueprint["agent_spec"] = {
                "name": proposal.title,
                "capabilities": [proposal.target_capability] if proposal.target_capability else [],
                "provider": "auto",
            }
        elif target_type == GenerationTargetType.WORKFLOW:
            blueprint["workflow_spec"] = {
                "name": proposal.title,
                "stages": [],
                "dag": True,
            }
        elif target_type == GenerationTargetType.PLANNER:
            blueprint["planner_spec"] = {
                "name": proposal.title,
                "strategy": "greedy",
            }
        elif target_type == GenerationTargetType.TOOL:
            blueprint["tool_spec"] = {
                "name": proposal.title,
                "input_schema": {},
                "requires_approval": False,
            }
        elif target_type == GenerationTargetType.ORCHESTRATOR:
            blueprint["orchestrator_spec"] = {
                "name": proposal.title,
                "pattern": "pipeline",
            }
        elif target_type == GenerationTargetType.STRATEGY:
            blueprint["strategy_spec"] = {
                "name": proposal.title,
                "decision_factors": [],
            }

        return blueprint

    def _identify_dependencies(
        self, proposal: ImprovementProposal, target_type: GenerationTargetType
    ) -> list[str]:
        """Identify dependencies for the new artifact."""
        deps: list[str] = []
        # All artifacts depend on the EventBus
        deps.append("agentic_os.ports.event_bus")
        if target_type in {
            GenerationTargetType.CAPABILITY,
            GenerationTargetType.AGENT,
            GenerationTargetType.TOOL,
        }:
            deps.append("agentic_os.domain.events")
        if target_type == GenerationTargetType.AGENT:
            deps.append("agentic_os.core.brains.registry")
        if target_type == GenerationTargetType.WORKFLOW:
            deps.append("agentic_os.core.workflow.engine")
        if target_type == GenerationTargetType.ORCHESTRATOR:
            deps.append("agentic_os.core.orchestration.framework")
        return deps

    def _identify_affected_modules(
        self, proposal: ImprovementProposal, target_type: GenerationTargetType
    ) -> list[str]:
        """Identify modules that will be affected."""
        affected: list[str] = []
        if proposal.target_module:
            affected.append(proposal.target_module)
        # New artifacts go in their respective packages
        type_to_package = {
            GenerationTargetType.CAPABILITY: "agentic_os.core.capability",
            GenerationTargetType.AGENT: "agentic_os.core.runtime",
            GenerationTargetType.WORKFLOW: "agentic_os.core.workflow",
            GenerationTargetType.PLANNER: "agentic_os.core.orchestration",
            GenerationTargetType.TOOL: "agentic_os.adapters",
            GenerationTargetType.ORCHESTRATOR: "agentic_os.core.orchestration",
            GenerationTargetType.STRATEGY: "agentic_os.core.executive",
            GenerationTargetType.MODULE: "agentic_os.core",
        }
        pkg = type_to_package.get(target_type, "agentic_os.core")
        if pkg not in affected:
            affected.append(pkg)
        return affected

    def _build_validation_strategy(self, target_type: GenerationTargetType) -> dict[str, Any]:
        """Build validation strategy for the artifact."""
        return {
            "unit_tests": True,
            "integration_tests": True,
            "api_compatibility": True,
            "performance_benchmark": target_type
            in {GenerationTargetType.ORCHESTRATOR, GenerationTargetType.PLANNER},
            "security_scan": True,
        }

    def _build_rollout_steps(
        self, proposal: ImprovementProposal, target_type: GenerationTargetType
    ) -> list[dict[str, Any]]:
        """Build rollout steps."""
        return [
            {"step": 1, "action": "create_artifact", "status": "pending"},
            {"step": 2, "action": "register_with_kernel", "status": "pending"},
            {"step": 3, "action": "run_unit_tests", "status": "pending"},
            {"step": 4, "action": "run_integration_tests", "status": "pending"},
            {"step": 5, "action": "enable_in_production", "status": "pending"},
        ]

    def _build_rollback_steps(
        self, proposal: ImprovementProposal, target_type: GenerationTargetType
    ) -> list[dict[str, Any]]:
        """Build rollback steps."""
        return [
            {"step": 1, "action": "disable_artifact", "status": "pending"},
            {"step": 2, "action": "unregister_from_kernel", "status": "pending"},
            {"step": 3, "action": "verify_rollback", "status": "pending"},
        ]
