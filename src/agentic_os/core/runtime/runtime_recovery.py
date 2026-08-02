"""Runtime recovery — automatic crash recovery workflow with backoff.

Integrates with :class:`RuntimePolicyEngine` for retry-limit and
exponential-backoff decisions.  Publishes ``runtime.crashed`` and
``runtime.recovered`` events on state transitions.
"""

from __future__ import annotations

import asyncio
from typing import Any

from agentic_os.core.runtime.runtime import RestartPolicy, Runtime, RuntimeStatus
from agentic_os.core.runtime.runtime_events import (
    publish_runtime_crashed,
    publish_runtime_recovered,
)
from agentic_os.core.runtime.runtime_policy import RuntimePolicyEngine
from agentic_os.infrastructure.logging import get_logger

__all__ = [
    "RuntimeRecovery",
]

log = get_logger("runtime.recovery")

_DEFAULT_MAX_RETRIES = 3


class RuntimeRecovery:
    """Automatic crash recovery for runtimes.

    Uses a :class:`RuntimePolicyEngine` to decide *whether* and *when*
    to restart.  Re-entrant recovery for the same runtime is prevented
    via an in-flight set.

    Usage::

        recovery = RuntimeRecovery(bus=my_bus)
        ok = await recovery.attempt_recovery(runtime)
    """

    def __init__(
        self,
        policy_engine: RuntimePolicyEngine | None = None,
        bus: Any = None,
    ) -> None:
        self._policy = policy_engine or RuntimePolicyEngine()
        self._bus = bus
        # runtime_id -> current attempt counter
        self._retry_counts: dict[str, int] = {}
        # runtime_ids currently being recovered (prevent re-entrancy)
        self._recovering: set[str] = set()

    # ── Recovery ────────────────────────────────────────────────────────────

    async def attempt_recovery(
        self,
        runtime: Runtime,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_base: float = 2.0,
        backoff_max: float = 60.0,
    ) -> bool:
        """Attempt to recover *runtime* using the configured restart policy.

        The workflow:

        1. Check the restart policy (never / on-failure / always / backoff).
        2. If throttled (retries exhausted), return ``False``.
        3. Compute exponential-backoff delay with jitter.
        4. Publish ``runtime.crashed`` (first attempt only).
        5. Sleep for the backoff delay.
        6. Increment retry count.
        7. Publish ``runtime.recovered``.

        Args:
            runtime: The :class:`Runtime` instance to recover.
            max_retries: Maximum restart attempts allowed.
            backoff_base: Exponent base for backoff calculation.
            backoff_max: Maximum backoff delay in seconds.

        Returns:
            ``True`` if recovery was attempted (caller responsible for
            actually restarting the process).
        """
        if runtime.id in self._recovering:
            log.warning("recovery.already_in_progress", runtime_id=runtime.id)
            return False

        self._recovering.add(runtime.id)
        try:
            return await self._do_attempt(runtime, max_retries, backoff_base, backoff_max)
        finally:
            self._recovering.discard(runtime.id)

    async def _do_attempt(
        self,
        runtime: Runtime,
        max_retries: int,
        backoff_base: float,
        backoff_max: float,
    ) -> bool:
        count = self._retry_counts.get(runtime.id, 0)

        # Resolve restart policy from metadata (fall back to ON_FAILURE)
        policy_name = runtime.metadata.get("restart_policy", RestartPolicy.ON_FAILURE.value)
        try:
            policy = RestartPolicy(policy_name)
        except ValueError:
            policy = RestartPolicy.ON_FAILURE

        # Policy gate
        if not self._policy.should_restart(count, runtime.status.value, policy, max_retries):
            log.warning(
                "recovery.skipped",
                runtime_id=runtime.id,
                reason="policy denies restart",
                attempt=count,
                policy=policy.value,
                status=runtime.status.value,
            )
            return False

        # Throttle gate
        if self._policy.is_throttled(count, max_retries):
            log.warning(
                "recovery.throttled",
                runtime_id=runtime.id,
                attempt=count,
                max_retries=max_retries,
            )
            return False

        # Backoff
        delay = self._policy.get_delay(count, backoff_base, backoff_max)
        log.info(
            "recovery.attempting",
            runtime_id=runtime.id,
            attempt=count + 1,
            delay_seconds=round(delay, 2),
        )

        # Publish crash event on first attempt (if error available)
        if count == 0 and runtime.last_error:
            await publish_runtime_crashed(
                self._bus,
                runtime.id,
                runtime.name,
                error=runtime.last_error,
            )

        # Backoff sleep
        await asyncio.sleep(delay)

        # Advance retry counter
        self._retry_counts[runtime.id] = count + 1

        # Publish recovered event
        await publish_runtime_recovered(
            self._bus,
            runtime.id,
            runtime.name,
            attempt=count + 1,
        )

        log.info("recovery.succeeded", runtime_id=runtime.id, attempt=count + 1)
        return True

    async def recover_all(
        self,
        runtimes: dict[str, Runtime],
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ) -> list[str]:
        """Attempt to recover every crashed or failed runtime in *runtimes*.

        Args:
            runtimes: Mapping of ``runtime_id → Runtime``.
            max_retries: Maximum restart attempts per runtime.

        Returns:
            List of runtime IDs that were successfully recovered.
        """
        recovered: list[str] = []
        for rid, runtime in runtimes.items():
            if runtime.status in (RuntimeStatus.CRASHED, RuntimeStatus.FAILED):
                ok = await self.attempt_recovery(runtime, max_retries)
                if ok:
                    recovered.append(rid)
        return recovered

    # ── Retry count management ──────────────────────────────────────────────

    async def reset_retry_count(self, runtime_id: str) -> None:
        """Reset the retry counter for *runtime_id*.

        Call this after a successful manual restart or when a runtime
        has been stable for a significant period.
        """
        self._retry_counts.pop(runtime_id, None)
        log.debug("recovery.retry_count_reset", runtime_id=runtime_id)

    def get_retry_count(self, runtime_id: str) -> int:
        """Return the current retry count for *runtime_id* (0 if never retried)."""
        return self._retry_counts.get(runtime_id, 0)
