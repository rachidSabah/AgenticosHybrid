"""Tests for RuntimeRecovery — crash sequencing, cooldown, max retries, policy."""

import asyncio

import pytest

from agentic_os.core.runtime.runtime import RestartPolicy, Runtime, RuntimeStatus
from agentic_os.core.runtime.runtime_recovery import RuntimeRecovery


@pytest.fixture
def recovery() -> RuntimeRecovery:
    return RuntimeRecovery()


@pytest.mark.asyncio
class TestRuntimeRecovery:
    async def test_attempt_recovery_returns_true(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="recoverable", status=RuntimeStatus.CRASHED)
        r.metadata["restart_policy"] = RestartPolicy.ALWAYS.value
        result = await recovery.attempt_recovery(r, max_retries=3)
        assert result is True

    async def test_attempt_recovery_throttled(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="throttled", status=RuntimeStatus.CRASHED)
        r.metadata["restart_policy"] = RestartPolicy.ALWAYS.value
        # Exhaust retries
        recovery._retry_counts[r.id] = 3
        result = await recovery.attempt_recovery(r, max_retries=3)
        assert result is False

    async def test_attempt_recovery_policy_never(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="never-recover", status=RuntimeStatus.CRASHED)
        r.metadata["restart_policy"] = RestartPolicy.NEVER.value
        result = await recovery.attempt_recovery(r)
        assert result is False

    async def test_attempt_recovery_on_failure_crashed(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="crashed-rt", status=RuntimeStatus.CRASHED)
        r.metadata["restart_policy"] = RestartPolicy.ON_FAILURE.value
        result = await recovery.attempt_recovery(r)
        assert result is True

    async def test_attempt_recovery_on_failure_stopped(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="stopped-no-recover", status=RuntimeStatus.STOPPED)
        r.metadata["restart_policy"] = RestartPolicy.ON_FAILURE.value
        result = await recovery.attempt_recovery(r)
        assert result is False  # stopped is not a failure

    async def test_attempt_recovery_on_crash_crashed(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="crash-recover", status=RuntimeStatus.CRASHED)
        r.metadata["restart_policy"] = RestartPolicy.ON_CRASH.value
        result = await recovery.attempt_recovery(r)
        assert result is True

    async def test_attempt_recovery_on_crash_failed(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="failed-not-crashed", status=RuntimeStatus.FAILED)
        r.metadata["restart_policy"] = RestartPolicy.ON_CRASH.value
        result = await recovery.attempt_recovery(r)
        assert result is False  # failed is not crashed

    async def test_attempt_recovery_backoff(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="backoff-rt", status=RuntimeStatus.CRASHED)
        r.metadata["restart_policy"] = RestartPolicy.BACKOFF.value
        result = await recovery.attempt_recovery(r, backoff_base=0.1, backoff_max=0.5)
        assert result is True

    async def test_attempt_recovery_re_entrant_blocked(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="re-entrant", status=RuntimeStatus.CRASHED)
        r.metadata["restart_policy"] = RestartPolicy.ALWAYS.value
        recovery._recovering.add(r.id)
        result = await recovery.attempt_recovery(r)
        assert result is False  # already in progress

    async def test_attempt_recovery_increments_count(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="count-test", status=RuntimeStatus.CRASHED)
        r.metadata["restart_policy"] = RestartPolicy.ALWAYS.value
        await recovery.attempt_recovery(r, backoff_base=0.1, backoff_max=0.5)
        assert recovery.get_retry_count(r.id) == 1

    async def test_attempt_recovery_multiple_increments(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="multi-count", status=RuntimeStatus.CRASHED)
        r.metadata["restart_policy"] = RestartPolicy.ALWAYS.value
        for _ in range(3):
            await recovery.attempt_recovery(r, max_retries=5, backoff_base=0.1, backoff_max=0.3)
        assert recovery.get_retry_count(r.id) == 3

    async def test_attempt_recovery_publishes_crashed_on_first(
        self, recovery: RuntimeRecovery
    ) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append((topic, data))

        r = Runtime(
            name="pub-crash",
            status=RuntimeStatus.CRASHED,
            last_error="something broke",
        )
        r.metadata["restart_policy"] = RestartPolicy.ALWAYS.value
        rec = RuntimeRecovery(bus=_Bus())
        await rec.attempt_recovery(r, backoff_base=0.1, backoff_max=0.3)
        # First attempt with error should publish crashed event
        crash_events = [e for e in events if "crashed" in e[0]]
        assert len(crash_events) >= 1

    async def test_reset_retry_count(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="reset-test", status=RuntimeStatus.CRASHED)
        r.metadata["restart_policy"] = RestartPolicy.ALWAYS.value
        await recovery.attempt_recovery(r, backoff_base=0.1, backoff_max=0.3)
        assert recovery.get_retry_count(r.id) == 1
        await recovery.reset_retry_count(r.id)
        assert recovery.get_retry_count(r.id) == 0

    async def test_get_retry_count_default(self, recovery: RuntimeRecovery) -> None:
        assert recovery.get_retry_count("unknown") == 0

    async def test_recover_all(self, recovery: RuntimeRecovery) -> None:
        r1 = Runtime(name="r1", status=RuntimeStatus.CRASHED)
        r2 = Runtime(name="r2", status=RuntimeStatus.STOPPED)  # not recoverable
        r3 = Runtime(name="r3", status=RuntimeStatus.FAILED)
        r1.metadata["restart_policy"] = RestartPolicy.ALWAYS.value
        r2.metadata["restart_policy"] = RestartPolicy.ALWAYS.value
        r3.metadata["restart_policy"] = RestartPolicy.ALWAYS.value

        runtimes = {r.id: r for r in [r1, r2, r3]}
        recovered = await recovery.recover_all(
            runtimes,
            max_retries=3,
        )
        # r1 crashed -> recovered, r2 stopped -> depends on policy, r3 failed -> default
        assert isinstance(recovered, list)

    async def test_attempt_recovery_with_backoff_sleep(self, recovery: RuntimeRecovery) -> None:
        """Verify that recovery actually sleeps (approximate)."""
        r = Runtime(name="sleep-test", status=RuntimeStatus.CRASHED)
        r.metadata["restart_policy"] = RestartPolicy.ALWAYS.value
        t0 = asyncio.get_event_loop().time()
        await recovery.attempt_recovery(r, backoff_base=0.05, backoff_max=0.1)
        elapsed = asyncio.get_event_loop().time() - t0
        assert elapsed >= 0.04  # at least some sleep happened

    async def test_invalid_policy_falls_back_to_on_failure(self, recovery: RuntimeRecovery) -> None:
        r = Runtime(name="bad-policy", status=RuntimeStatus.CRASHED)
        r.metadata["restart_policy"] = "invalid_policy_value"
        result = await recovery.attempt_recovery(r)
        assert result is True  # falls back to ON_FAILURE, crashed qualifies

    async def test_recover_all_recovered_list(self, recovery: RuntimeRecovery) -> None:
        r1 = Runtime(name="will-recover", status=RuntimeStatus.CRASHED)
        r2 = Runtime(name="will-skip", status=RuntimeStatus.READY)
        r1.metadata["restart_policy"] = RestartPolicy.ALWAYS.value
        r2.metadata["restart_policy"] = RestartPolicy.ALWAYS.value
        runtimes = {r1.id: r1, r2.id: r2}
        recovered = await recovery.recover_all(runtimes, max_retries=3)
        assert len(recovered) >= 1
