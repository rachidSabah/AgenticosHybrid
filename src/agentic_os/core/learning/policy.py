"""Policy engine — manages and evaluates optimization policies."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.learning import OptimizationPolicy, OptimizationTarget, PolicyEffect
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.learning import PolicyPort

log = get_logger("learning.policy")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PolicyEngine(PolicyPort):
    """In-memory policy engine implementing ``PolicyPort``.

    Stores ``OptimizationPolicy`` records in a dict and evaluates
    conditions via ``check_policy``. Policies are prioritized by
    their ``priority`` field (higher value = higher priority).
    """

    def __init__(self) -> None:
        self._policies: dict[str, OptimizationPolicy] = {}

    # ── CRUD ──

    async def create_policy(self, policy: OptimizationPolicy) -> OptimizationPolicy:
        if policy.id in self._policies:
            raise ValueError(f"Policy '{policy.id}' already exists")
        self._policies[policy.id] = policy
        log.info("Policy created", policy_id=policy.id, name=policy.name)
        return policy

    async def get_policy(self, policy_id: str) -> OptimizationPolicy | None:
        return self._policies.get(policy_id)

    async def list_policies(self) -> Sequence[OptimizationPolicy]:
        return sorted(
            self._policies.values(),
            key=lambda p: p.priority,
            reverse=True,
        )

    async def update_policy(self, policy: OptimizationPolicy) -> OptimizationPolicy:
        existing = self._policies.get(policy.id)
        if existing is None:
            raise ValueError(f"Policy '{policy.id}' not found")
        updated = OptimizationPolicy(
            id=policy.id,
            name=policy.name,
            description=policy.description,
            target=policy.target,
            effect=policy.effect,
            conditions=policy.conditions,
            priority=policy.priority,
            enabled=policy.enabled,
            created_at=existing.created_at,
            updated_at=_utcnow(),
        )
        self._policies[policy.id] = updated
        log.info("Policy updated", policy_id=policy.id)
        return updated

    async def delete_policy(self, policy_id: str) -> None:
        if policy_id not in self._policies:
            raise ValueError(f"Policy '{policy_id}' not found")
        del self._policies[policy_id]
        log.info("Policy deleted", policy_id=policy_id)

    # ── Evaluation ──

    async def check_policy(
        self,
        target: OptimizationTarget,
        context: dict[str, Any],
    ) -> bool:
        """Evaluate all enabled policies for the given target and context.

        Iterates policies sorted by priority (descending). If any policy
        has effect ``DENY`` and all its conditions match, the check fails.
        If any policy has effect ``REQUIRE_APPROVAL`` and all its conditions
        match, the check also fails (requires external approval).

        Args:
            target: The optimization target to check.
            context: Contextual information for condition evaluation.

        Returns:
            True if all matching policies allow the action, False otherwise.
        """
        relevant = [
            p
            for p in self._policies.values()
            if p.enabled and (p.target is None or p.target == target)
        ]
        relevant.sort(key=lambda p: p.priority, reverse=True)

        for policy in relevant:
            if not self._conditions_match(policy.conditions, context):
                continue

            if policy.effect in (PolicyEffect.DENY, PolicyEffect.REQUIRE_APPROVAL):
                log.info(
                    "Policy blocked action",
                    policy_id=policy.id,
                    effect=policy.effect.value,
                    target=target.value,
                )
                return False

        return True

    # ── Internals ──

    @staticmethod
    def _conditions_match(
        conditions: dict[str, Any],
        context: dict[str, Any],
    ) -> bool:
        """Check if all conditions are satisfied by the given context.

        Supports simple equality, numeric comparison operators (gt, gte,
        lt, lte), and nested key access via dot-separated paths.
        """
        for key, expected in conditions.items():
            actual = context.get(key)

            if isinstance(expected, dict) and "op" in expected:
                op = expected["op"]
                val = expected["value"]
                if actual is None:
                    return False

                if op == "gt" and not (actual > val):
                    return False
                if op == "gte" and not (actual >= val):
                    return False
                if op == "lt" and not (actual < val):
                    return False
                if op == "lte" and not (actual <= val):
                    return False
                if op == "eq" and not (actual == val):
                    return False
                if op == "neq" and not (actual != val):
                    return False
                if op == "in" and actual not in val:
                    return False
                if op == "contains" and val not in actual:
                    return False
            elif isinstance(expected, str) and expected.startswith("$context."):
                expected_path = expected[len("$context.") :]
                expected_value = context
                for part in expected_path.split("."):
                    if isinstance(expected_value, dict):
                        expected_value = expected_value.get(part)
                    else:
                        expected_value = None
                        break
                if actual != expected_value:
                    return False
            else:
                if actual != expected:
                    return False

        return True
