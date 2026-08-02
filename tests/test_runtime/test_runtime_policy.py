"""Tests for RuntimePolicyEngine — restart decisions, backoff, jitter, throttle."""

import random

import pytest

from agentic_os.core.runtime.runtime import RestartPolicy
from agentic_os.core.runtime.runtime_policy import RuntimePolicyEngine


@pytest.fixture
def policy() -> RuntimePolicyEngine:
    return RuntimePolicyEngine()


class TestRuntimePolicyEngine:
    def test_should_restart_never(self, policy: RuntimePolicyEngine) -> None:
        assert policy.should_restart(0, "crashed", RestartPolicy.NEVER) is False
        assert policy.should_restart(99, "crashed", RestartPolicy.NEVER) is False

    def test_should_restart_always(self, policy: RuntimePolicyEngine) -> None:
        assert policy.should_restart(0, "crashed", RestartPolicy.ALWAYS, max_retries=3) is True
        assert policy.should_restart(1, "crashed", RestartPolicy.ALWAYS, max_retries=3) is True
        assert policy.should_restart(2, "crashed", RestartPolicy.ALWAYS, max_retries=3) is True
        assert policy.should_restart(3, "crashed", RestartPolicy.ALWAYS, max_retries=3) is False

    def test_should_restart_on_failure(self, policy: RuntimePolicyEngine) -> None:
        assert policy.should_restart(0, "crashed", RestartPolicy.ON_FAILURE) is True
        assert policy.should_restart(0, "failed", RestartPolicy.ON_FAILURE) is True
        assert policy.should_restart(0, "stopped", RestartPolicy.ON_FAILURE) is False
        assert policy.should_restart(0, "ready", RestartPolicy.ON_FAILURE) is False

    def test_should_restart_on_crash(self, policy: RuntimePolicyEngine) -> None:
        assert policy.should_restart(0, "crashed", RestartPolicy.ON_CRASH) is True
        assert policy.should_restart(0, "failed", RestartPolicy.ON_CRASH) is False
        assert policy.should_restart(0, "stopped", RestartPolicy.ON_CRASH) is False

    def test_should_restart_backoff(self, policy: RuntimePolicyEngine) -> None:
        assert policy.should_restart(0, "crashed", RestartPolicy.BACKOFF, max_retries=5) is True
        assert policy.should_restart(4, "crashed", RestartPolicy.BACKOFF, max_retries=5) is True
        assert policy.should_restart(5, "crashed", RestartPolicy.BACKOFF, max_retries=5) is False

    def test_should_restart_default_policy(self, policy: RuntimePolicyEngine) -> None:
        # Default is ON_FAILURE
        assert policy.should_restart(0, "crashed") is True
        assert policy.should_restart(0, "ready") is False

    def test_should_restart_exhausted_retries(self, policy: RuntimePolicyEngine) -> None:
        assert policy.should_restart(3, "crashed", RestartPolicy.ON_FAILURE, max_retries=3) is False
        assert policy.should_restart(10, "crashed", RestartPolicy.ALWAYS, max_retries=3) is False

    def test_get_delay_exponential(self, policy: RuntimePolicyEngine) -> None:
        d0 = policy.get_delay(0)
        d1 = policy.get_delay(1)
        d2 = policy.get_delay(2)
        d3 = policy.get_delay(3)
        # Each should be >= the corresponding power of 2
        assert d0 >= 1.0  # 2^0
        assert d1 >= 2.0  # 2^1
        assert d2 >= 4.0  # 2^2
        assert d3 >= 8.0  # 2^3

    def test_get_delay_with_max(self, policy: RuntimePolicyEngine) -> None:
        # Very high attempt should be capped
        d = policy.get_delay(10, backoff_base=2.0, backoff_max=60.0)
        assert d <= 66.0  # 60 + 10% jitter

    def test_get_delay_negative_attempt(self, policy: RuntimePolicyEngine) -> None:
        d = policy.get_delay(-1)
        assert d >= 1.0  # treated as attempt 0

    def test_get_delay_jitter_range(self, policy: RuntimePolicyEngine) -> None:
        random.seed(42)
        delays = [policy.get_delay(3) for _ in range(100)]
        # All should be >= 8.0 (base) and <= 8.8 (base + 10% jitter)
        assert all(8.0 <= d <= 8.8 for d in delays)

    def test_get_delay_reproducible_seed(self, policy: RuntimePolicyEngine) -> None:
        random.seed(12345)
        d1 = policy.get_delay(2)
        random.seed(12345)
        d2 = policy.get_delay(2)
        assert d1 == d2

    def test_is_throttled(self, policy: RuntimePolicyEngine) -> None:
        assert policy.is_throttled(3, max_retries=3) is True
        assert policy.is_throttled(5, max_retries=3) is True
        assert policy.is_throttled(2, max_retries=3) is False
        assert policy.is_throttled(0, max_retries=3) is False

    def test_is_throttled_default_max(self, policy: RuntimePolicyEngine) -> None:
        assert policy.is_throttled(3) is True  # default max is 3
        assert policy.is_throttled(2) is False

    def test_should_batch(self, policy: RuntimePolicyEngine) -> None:
        assert policy.should_batch(0) is False
        assert policy.should_batch(1) is False
        assert policy.should_batch(2) is True
        assert policy.should_batch(5) is True
        assert policy.should_batch(10) is True
        assert policy.should_batch(11) is False

    def test_should_batch_custom_max(self, policy: RuntimePolicyEngine) -> None:
        assert policy.should_batch(5, max_batch_size=5) is True
        assert policy.should_batch(6, max_batch_size=5) is False

    def test_backoff_custom_base(self, policy: RuntimePolicyEngine) -> None:
        d = policy.get_delay(2, backoff_base=3.0)
        assert d >= 9.0  # 3^2
        assert d <= 9.9  # +10% jitter

    def test_backoff_custom_base_and_max(self, policy: RuntimePolicyEngine) -> None:
        d = policy.get_delay(10, backoff_base=2.0, backoff_max=10.0)
        assert d <= 11.0  # 10 + 10%
