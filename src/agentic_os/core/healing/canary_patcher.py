"""
Phase 3 — Autonomous Canary Patch Simulator & Ephemeral Worktree Validator.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CanaryDeployment:
    deployment_id: str
    incident_id: str
    remediation_title: str
    worktree_path: str
    tests_total: int
    tests_passed: int
    status: str
    rca_postmortem: str
    canary_passed: bool
    created_at: float = field(default_factory=time.time)


class CanaryPatcher:
    """Spins up isolated ephemeral worktree branches, simulates patches, and triggers canary rollbacks."""

    def __init__(self) -> None:
        self._deployments: list[CanaryDeployment] = []

    def simulate_and_deploy_patch(
        self, incident_id: str, title: str, patch_diff: str
    ) -> CanaryDeployment:
        """Record a canary deployment REQUEST without fabricating results.

        Spec §15/§16: no worktree is created, no patch is applied and no
        tests are run here. The previous stub returned tests_total=48 /
        tests_passed=48, canary_passed=True and a templated RCA — fabricated
        evidence of a deployment that never happened. Honest zeros only.
        """
        dep_id = f"canary-{uuid.uuid4().hex[:8]}"
        rca = (
            f"CANARY REQUEST RECORDED for {incident_id}:\n"
            f"- Requested remediation: {title}\n"
            "- NOT EXECUTED: no ephemeral worktree was created and no patch was applied.\n"
            "- NO DATA: no test suite was run; pass counts are 0, not evidence of success."
        )
        dep = CanaryDeployment(
            deployment_id=dep_id,
            incident_id=incident_id,
            remediation_title=title,
            worktree_path="",
            tests_total=0,
            tests_passed=0,
            status="not_executed",
            rca_postmortem=rca,
            canary_passed=False,
        )
        self._deployments.append(dep)
        return dep

    def rollback_canary(self, deployment_id: str) -> dict[str, Any]:
        dep = next((d for d in self._deployments if d.deployment_id == deployment_id), None)
        if dep:
            dep.status = "rolled_back"
            return {"deployment_id": deployment_id, "status": "rolled_back", "success": True}
        return {"deployment_id": deployment_id, "status": "not_found", "success": False}

    def list_canaries(self) -> list[dict[str, Any]]:
        return [d.__dict__ for d in self._deployments]


canary_patcher = CanaryPatcher()
