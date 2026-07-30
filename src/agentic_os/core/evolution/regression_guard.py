"""Phase 17 — RegressionGuard.

Predicts whether an improvement will cause test regressions by analyzing:
  - affected modules + their test coverage
  - dependency graph impact
  - historical regression patterns
  - API surface changes

The guard NEVER runs tests directly — it predicts risk based on static
analysis. The actual test suite is the final safety net.
"""

from __future__ import annotations

from typing import Any

from agentic_os.core.evolution.domain import ImprovementProposal
from agentic_os.infrastructure.logging import get_logger

log = get_logger("evolution.regression_guard")


class RegressionGuard:
    """Predicts regression risk for proposed improvements."""

    def __init__(self) -> None:
        self._history: list[dict[str, Any]] = []
        self._module_risk_cache: dict[str, float] = {}
        self._stats: dict[str, int] = {
            "predictions_made": 0,
            "high_risk": 0,
            "moderate_risk": 0,
            "low_risk": 0,
        }

    # ── Public API ──────────────────────────────────────────────────

    async def predict(self, proposal: ImprovementProposal) -> dict[str, Any]:
        """Predict regression risk for a proposal. Returns risk assessment."""
        self._stats["predictions_made"] += 1

        risk_factors: list[dict[str, Any]] = []
        total_risk = 0.0

        # Factor 1: affected modules
        affected = proposal.implementation_plan.get("affected_modules", [])
        if affected:
            module_risk = self._assess_module_risk(affected)
            risk_factors.append(
                {
                    "factor": "affected_modules",
                    "risk": module_risk,
                    "details": {"modules": affected, "count": len(affected)},
                }
            )
            total_risk += module_risk * 0.4

        # Factor 2: API changes
        api_changes = proposal.implementation_plan.get("api_changes", {})
        if api_changes:
            api_risk = self._assess_api_risk(api_changes)
            risk_factors.append(
                {
                    "factor": "api_changes",
                    "risk": api_risk,
                    "details": api_changes,
                }
            )
            total_risk += api_risk * 0.3

        # Factor 3: dependency changes
        dep_changes = proposal.implementation_plan.get("dependency_changes", [])
        if dep_changes:
            dep_risk = self._assess_dependency_risk(dep_changes)
            risk_factors.append(
                {
                    "factor": "dependency_changes",
                    "risk": dep_risk,
                    "details": {"changes": dep_changes},
                }
            )
            total_risk += dep_risk * 0.2

        # Factor 4: complexity
        complexity = proposal.implementation_plan.get("complexity", "medium")
        complexity_risk = {"low": 0.1, "medium": 0.3, "high": 0.6}.get(complexity, 0.3)
        risk_factors.append(
            {
                "factor": "complexity",
                "risk": complexity_risk,
                "details": {"level": complexity},
            }
        )
        total_risk += complexity_risk * 0.1

        # Clamp to [0, 1]
        total_risk = min(1.0, max(0.0, total_risk))

        # Categorize
        if total_risk >= 0.7:
            self._stats["high_risk"] += 1
        elif total_risk >= 0.3:
            self._stats["moderate_risk"] += 1
        else:
            self._stats["low_risk"] += 1

        result = {
            "improvement_id": proposal.id,
            "regression_risk": round(total_risk, 3),
            "risk_level": (
                "high" if total_risk >= 0.7 else "moderate" if total_risk >= 0.3 else "low"
            ),
            "risk_factors": risk_factors,
            "recommendation": (
                "reject"
                if total_risk >= 0.7
                else "proceed_with_caution"
                if total_risk >= 0.3
                else "proceed"
            ),
        }

        self._history.append(result)
        if len(self._history) > 200:
            self._history = self._history[-200:]

        return result

    def list_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._history[-limit:])

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    # ── Risk assessment helpers ─────────────────────────────────────

    def _assess_module_risk(self, modules: list[str]) -> float:
        """Assess risk based on which modules are affected."""
        # Critical modules have higher regression risk
        critical_modules = {
            "kernel",
            "event_bus",
            "brain_registry",
            "api",
            "security",
            "executive",
            "cognitive",
            "ecosystem",
            "cluster",
        }
        risk = 0.0
        for mod in modules:
            mod_lower = str(mod).lower()
            if any(crit in mod_lower for crit in critical_modules):
                risk += 0.3
            else:
                risk += 0.1
        return min(1.0, risk)

    def _assess_api_risk(self, changes: dict[str, Any]) -> float:
        """Assess risk based on API changes."""
        risk = 0.0
        if changes.get("removed_endpoints"):
            risk += 0.5
        if changes.get("renamed_endpoints"):
            risk += 0.3
        if changes.get("modified_schemas"):
            risk += 0.2
        if changes.get("added_endpoints"):
            risk += 0.0  # additive = safe
        return min(1.0, risk)

    def _assess_dependency_risk(self, changes: list[str]) -> float:
        """Assess risk based on dependency changes."""
        risk = 0.0
        for change in changes:
            change_lower = str(change).lower()
            if "remove" in change_lower:
                risk += 0.4
            elif "upgrade" in change_lower or "downgrade" in change_lower:
                risk += 0.2
            elif "add" in change_lower:
                risk += 0.05
        return min(1.0, risk)
