"""Runtime policy engine — restart, batch, and backoff decision logic.

Pure logic with no side effects — all methods are deterministic given
their inputs (except for random jitter in ``get_delay``).
"""

from __future__ import annotations

import random

from agentic_os.core.runtime.runtime import RestartPolicy
from agentic_os.infrastructure.logging import get_logger

__all__ = [
    "RuntimePolicyEngine",
]

log = get_logger("runtime.policy")

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 2.0
DEFAULT_BACKOFF_MAX = 60.0
JITTER_FACTOR = 0.1


class RuntimePolicyEngine:
    """Policy engine for runtime lifecycle decisions.

    All methods are pure (no side effects) except for the random jitter
    introduced in :meth:`get_delay`.
    """

    # ── Restart decisions ───────────────────────────────────────────────────

    def should_restart(
        self,
        restart_count: int,
        status: str,
        policy: RestartPolicy = RestartPolicy.ON_FAILURE,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> bool:
        """Decide whether a runtime should be restarted.

        Args:
            restart_count: Number of restarts already attempted.
            status: Current ``RuntimeStatus`` value (e.g. ``"crashed"``).
            policy: The restart policy to evaluate.
            max_retries: Maximum restarts allowed.

        Returns:
            ``True`` if a restart should be attempted.
        """
        if policy == RestartPolicy.NEVER:
            return False

        if policy == RestartPolicy.ALWAYS:
            return restart_count < max_retries

        if policy == RestartPolicy.ON_FAILURE:
            return status in ("failed", "crashed") and restart_count < max_retries

        if policy == RestartPolicy.ON_CRASH:
            return status == "crashed" and restart_count < max_retries

        if policy == RestartPolicy.BACKOFF:
            return restart_count < max_retries

        return False

    # ── Backoff ─────────────────────────────────────────────────────────────

    def get_delay(
        self,
        attempt: int,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        backoff_max: float = DEFAULT_BACKOFF_MAX,
    ) -> float:
        """Calculate exponential backoff delay with jitter.

        ``delay = min(backoff_base ** attempt, backoff_max) + jitter``

        Jitter is a uniform random value in ``[0, 0.1 * base_delay]``.

        Args:
            attempt: Zero-indexed attempt number.
            backoff_base: Base for exponential backoff (default 2.0).
            backoff_max: Maximum delay in seconds (default 60.0).

        Returns:
            Delay in seconds.
        """
        if attempt < 0:
            attempt = 0
        base_delay = min(backoff_base**attempt, backoff_max)
        jitter = random.uniform(0, JITTER_FACTOR * base_delay)
        return base_delay + jitter

    # ── Throttle ────────────────────────────────────────────────────────────

    def is_throttled(
        self,
        restart_count: int,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> bool:
        """Check if a runtime is throttled (exceeded max retries).

        Args:
            restart_count: Number of restarts already attempted.
            max_retries: Maximum restarts allowed.

        Returns:
            ``True`` if the runtime should not be restarted further.
        """
        return restart_count >= max_retries

    # ── Batching ────────────────────────────────────────────────────────────

    def should_batch(
        self,
        queue_depth: int,
        max_batch_size: int = 10,
    ) -> bool:
        """Decide whether a runtime should batch queued tasks.

        Args:
            queue_depth: Current queue depth of the runtime.
            max_batch_size: Maximum tasks per batch.

        Returns:
            ``True`` if batching is advised.
        """
        return 2 <= queue_depth <= max_batch_size
