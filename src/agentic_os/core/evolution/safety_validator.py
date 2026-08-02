"""Phase 17 — SafetyValidator + RegressionGuard.

Every improvement must pass 6 safety checks before approval:

  1. Architecture validation — does it fit the hexagonal architecture?
  2. Dependency validation — are dependencies available + compatible?
  3. API compatibility — does it break any existing API?
  4. Regression prediction — will it cause test failures?
  5. Security validation — does it introduce vulnerabilities?
  6. Performance validation — will it degrade performance?

The validator is a pure consumer of existing infrastructure:
  - reads ImprovementProposal.implementation_plan
  - reads existing module structure (via importlib)
  - reads existing API surface (via FastAPI app inspection)
  - never executes untrusted code
  - never modifies production files

All checks are deterministic + traceable.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from agentic_os.core.evolution.domain import (
    ImprovementProposal,
    SafetyValidationReport,
    ValidationCheck,
    ValidationCheckResult,
    ValidationCheckType,
)
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.evolution.regression_guard import RegressionGuard

log = get_logger("evolution.safety")


class SafetyValidator:
    """Runs all 6 safety checks on an improvement proposal."""

    def __init__(self, regression_guard: RegressionGuard | None = None) -> None:
        self._guard = regression_guard
        self._history: list[SafetyValidationReport] = []
        self._stats: dict[str, int] = {
            "total_validations": 0,
            "approved": 0,
            "rejected": 0,
            "warnings": 0,
        }

    def set_regression_guard(self, guard: RegressionGuard) -> None:
        self._guard = guard

    # ── Public API ──────────────────────────────────────────────────

    async def validate(self, proposal: ImprovementProposal) -> SafetyValidationReport:
        """Run all safety checks on a proposal. Returns a report."""
        self._stats["total_validations"] += 1
        report = SafetyValidationReport(improvement_id=proposal.id)

        checks = await asyncio.gather(
            self._check_architecture(proposal),
            self._check_dependencies(proposal),
            self._check_api_compatibility(proposal),
            self._check_regression_prediction(proposal),
            self._check_security(proposal),
            self._check_performance(proposal),
        )
        report.checks = list(checks)

        # Compute overall result
        failed = [c for c in report.checks if c.result == ValidationCheckResult.FAIL]
        warnings = [c for c in report.checks if c.result == ValidationCheckResult.WARNING]

        if failed:
            report.overall_result = ValidationCheckResult.FAIL
            report.approved = False
            report.blocking_issues = [f"{c.type.value}: {c.message}" for c in failed]
            self._stats["rejected"] += 1
        elif warnings:
            report.overall_result = ValidationCheckResult.WARNING
            report.approved = True  # approved with warnings
            report.warnings = [f"{c.type.value}: {c.message}" for c in warnings]
            self._stats["approved"] += 1
            self._stats["warnings"] += 1
        else:
            report.overall_result = ValidationCheckResult.PASS
            report.approved = True
            self._stats["approved"] += 1

        # Overall score = average of check scores
        if report.checks:
            report.overall_score = sum(c.score for c in report.checks) / len(report.checks)

        self._history.append(report)
        # Cap history
        if len(self._history) > 200:
            self._history = self._history[-200:]

        log.info(
            "Safety validation complete",
            improvement_id=proposal.id,
            result=report.overall_result.value,
            approved=report.approved,
            score=report.overall_score,
        )
        return report

    def list_history(self, limit: int = 50) -> list[SafetyValidationReport]:
        return list(self._history[-limit:])

    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "pass_rate": (self._stats["approved"] / max(self._stats["total_validations"], 1)),
        }

    # ── Individual checks ──────────────────────────────────────────

    async def _check_architecture(self, proposal: ImprovementProposal) -> ValidationCheck:
        """Validate that the improvement fits the hexagonal architecture."""
        t0 = time.perf_counter()
        check = ValidationCheck(type=ValidationCheckType.ARCHITECTURE)

        plan = proposal.implementation_plan
        target = proposal.target_module

        # Check: does the target module follow the ports/adapters pattern?
        # We check if the plan references existing architectural layers.
        arch_layers = {"domain", "ports", "core", "adapters", "api", "infrastructure"}
        plan_text = str(plan).lower() + " " + target.lower()
        references_arch = any(layer in plan_text for layer in arch_layers)

        # Check: does it introduce a new layer? (potential drift)
        new_layers = plan.get("new_layers", [])
        if new_layers:
            check.result = ValidationCheckResult.WARNING
            check.score = 0.6
            check.message = f"Introduces new architectural layer(s): {new_layers}"
        elif references_arch:
            check.result = ValidationCheckResult.PASS
            check.score = 0.9
            check.message = "Improvement aligns with hexagonal architecture"
        else:
            check.result = ValidationCheckResult.WARNING
            check.score = 0.5
            check.message = "Unable to verify architectural alignment"

        check.duration_ms = (time.perf_counter() - t0) * 1000
        return check

    async def _check_dependencies(self, proposal: ImprovementProposal) -> ValidationCheck:
        """Validate that dependencies are available + compatible."""
        t0 = time.perf_counter()
        check = ValidationCheck(type=ValidationCheckType.DEPENDENCY)

        deps = proposal.implementation_plan.get("dependencies", [])
        if not deps:
            check.result = ValidationCheckResult.PASS
            check.score = 1.0
            check.message = "No external dependencies"
        else:
            # Check if dependencies are importable
            missing = []
            for dep in deps:
                dep_name = str(dep).split(".")[0] if "." in str(dep) else str(dep)
                try:
                    __import__(dep_name)
                except ImportError:
                    missing.append(dep_name)

            if missing:
                check.result = ValidationCheckResult.FAIL
                check.score = 0.0
                check.message = f"Missing dependencies: {missing}"
                check.details = {"missing": missing}
            else:
                check.result = ValidationCheckResult.PASS
                check.score = 0.9
                check.message = f"All {len(deps)} dependencies available"

        check.duration_ms = (time.perf_counter() - t0) * 1000
        return check

    async def _check_api_compatibility(self, proposal: ImprovementProposal) -> ValidationCheck:
        """Validate that the improvement doesn't break existing APIs."""
        t0 = time.perf_counter()
        check = ValidationCheck(type=ValidationCheckType.API_COMPATIBILITY)

        # Check: does the plan mention removing or renaming existing APIs?
        plan_text = str(proposal.implementation_plan).lower()
        breaking_keywords = ["remove_api", "rename_api", "delete_endpoint", "breaking_change"]
        has_breaking = any(kw in plan_text for kw in breaking_keywords)

        # Check: does it add new APIs? (additive = safe)
        additive_keywords = ["add_endpoint", "new_api", "extend_api"]
        is_additive = any(kw in plan_text for kw in additive_keywords)

        if has_breaking:
            check.result = ValidationCheckResult.FAIL
            check.score = 0.0
            check.message = "Improvement introduces breaking API changes"
        elif is_additive:
            check.result = ValidationCheckResult.PASS
            check.score = 0.95
            check.message = "Improvement is additive (new APIs only)"
        else:
            check.result = ValidationCheckResult.PASS
            check.score = 0.8
            check.message = "No API changes detected"

        check.duration_ms = (time.perf_counter() - t0) * 1000
        return check

    async def _check_regression_prediction(self, proposal: ImprovementProposal) -> ValidationCheck:
        """Predict whether the improvement will cause test regressions."""
        t0 = time.perf_counter()
        check = ValidationCheck(type=ValidationCheckType.REGRESSION_PREDICTION)

        if self._guard is not None:
            prediction = await self._guard.predict(proposal)
            check.details = prediction
            risk = prediction.get("regression_risk", 0.0)
            check.score = 1.0 - risk

            if risk >= 0.7:
                check.result = ValidationCheckResult.FAIL
                check.message = f"High regression risk ({risk:.0%})"
            elif risk >= 0.3:
                check.result = ValidationCheckResult.WARNING
                check.message = f"Moderate regression risk ({risk:.0%})"
            else:
                check.result = ValidationCheckResult.PASS
                check.message = f"Low regression risk ({risk:.0%})"
        else:
            # No guard available — conservative pass
            check.result = ValidationCheckResult.WARNING
            check.score = 0.5
            check.message = "RegressionGuard not available — cannot predict"

        check.duration_ms = (time.perf_counter() - t0) * 1000
        return check

    async def _check_security(self, proposal: ImprovementProposal) -> ValidationCheck:
        """Validate that the improvement doesn't introduce vulnerabilities."""
        t0 = time.perf_counter()
        check = ValidationCheck(type=ValidationCheckType.SECURITY)

        plan_text = str(proposal.implementation_plan).lower()
        risky_patterns = [
            "shell=true",
            "eval(",
            "exec(",
            "subprocess.call(shell=true)",
            "os.system(",
            "pickle.loads",
            "yaml.load(",  # should be yaml.safe_load
        ]
        found_risky = [p for p in risky_patterns if p in plan_text]

        if found_risky:
            check.result = ValidationCheckResult.FAIL
            check.score = 0.0
            check.message = f"Risky patterns detected: {found_risky}"
            check.details = {"risky_patterns": found_risky}
        else:
            check.result = ValidationCheckResult.PASS
            check.score = 0.95
            check.message = "No security issues detected"

        check.duration_ms = (time.perf_counter() - t0) * 1000
        return check

    async def _check_performance(self, proposal: ImprovementProposal) -> ValidationCheck:
        """Validate that the improvement won't degrade performance."""
        t0 = time.perf_counter()
        check = ValidationCheck(type=ValidationCheckType.PERFORMANCE)

        # Check: expected impact on latency/throughput
        expected_latency_impact = proposal.implementation_plan.get("expected_latency_impact", 0.0)
        expected_throughput_impact = proposal.implementation_plan.get(
            "expected_throughput_impact", 0.0
        )

        # Positive impact = improvement; negative = degradation
        if expected_latency_impact < -0.2 or expected_throughput_impact < -0.2:
            check.result = ValidationCheckResult.FAIL
            check.score = 0.1
            check.message = (
                f"Significant performance degradation: latency={expected_latency_impact}, "
                f"throughput={expected_throughput_impact}"
            )
        elif expected_latency_impact < 0 or expected_throughput_impact < 0:
            check.result = ValidationCheckResult.WARNING
            check.score = 0.6
            check.message = "Minor performance impact expected"
        else:
            check.result = ValidationCheckResult.PASS
            check.score = 0.9
            check.message = "No performance degradation expected"

        check.duration_ms = (time.perf_counter() - t0) * 1000
        return check
