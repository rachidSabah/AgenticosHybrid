"""Agent cgroups — quota enforcement, freeze/resume/kill, bus accounting.

No mocks: usage is recorded through the real manager API and through real
EventEnvelope publishes on a real LocalBus; ledgers land in tmp_path.
"""

from __future__ import annotations

import asyncio

import pytest

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.core.cgroups.agent_cgroups import (
    AdmissionRefused,
    AgentCgroupManager,
    AgentQuota,
    CgroupError,
)


@pytest.fixture
def mgr(tmp_path):
    return AgentCgroupManager(data_dir=str(tmp_path / "cg"))


@pytest.fixture
def bus():
    return LocalBus()


# ── quotas: token budget ─────────────────────────────────────────────────────


def test_token_budget_enforced(mgr):
    mgr.set_quota("agent:a", AgentQuota(token_budget=100))
    mgr.admit("agent:a")
    mgr.record_tokens("agent:a", 60)
    mgr.record_tokens("agent:a", 40)
    with pytest.raises(AdmissionRefused) as exc:
        mgr.admit("agent:a")
    assert "token budget exhausted" in str(exc.value)
    assert mgr.status("agent:a")["tokens_used"] == 100


def test_token_overrun_midflight_flags_exceeded(mgr):
    mgr.set_quota("agent:a", AgentQuota(token_budget=50))
    mgr.admit("agent:a")
    status = mgr.record_tokens("agent:a", 80)
    assert status["exceeded_dimension"] == "token_budget"
    assert status["tokens_used"] == 80


def test_no_quota_means_no_limit(mgr):
    mgr.admit("agent:noquota")
    mgr.record_tokens("agent:noquota", 10**9)
    mgr.record_tool_call("agent:noquota")
    assert mgr.status("agent:noquota")["tokens_used"] == 10**9


# ── quotas: tool calls + llm slots ───────────────────────────────────────────


def test_tool_call_cap_enforced(mgr):
    mgr.set_quota("agent:t", AgentQuota(tool_call_cap=2))
    mgr.admit("agent:t")
    mgr.record_tool_call("agent:t")
    mgr.record_tool_call("agent:t")
    with pytest.raises(AdmissionRefused) as exc:
        mgr.admit("agent:t")
    assert "tool-call cap reached" in str(exc.value)


def test_concurrent_llm_slots_enforced_and_released(mgr):
    mgr.set_quota("agent:l", AgentQuota(max_concurrent_llm=2))
    mgr.admit("agent:l", llm_slot=True)
    mgr.admit("agent:l", llm_slot=True)
    with pytest.raises(AdmissionRefused) as exc:
        mgr.admit("agent:l", llm_slot=True)
    assert "concurrent llm slots exhausted" in str(exc.value).lower()
    mgr.release_llm_slot("agent:l")
    status = mgr.admit("agent:l", llm_slot=True)
    assert status["llm_slots_active"] == 2


# ── wall clock with freeze accounting ────────────────────────────────────────


def test_wall_clock_freeze_pauses_the_clock(mgr):
    mgr.set_quota("agent:w", AgentQuota(wall_clock_s=0.15))
    mgr.admit("agent:w")
    mgr.freeze("agent:w")
    import time

    time.sleep(0.25)
    frozen_status = mgr.status("agent:w")
    assert frozen_status["state"] == "frozen"
    # while frozen, the clock is paused: still under budget
    mgr.resume("agent:w")
    status = mgr.admit("agent:w")
    assert status["state"] == "running"
    # exceed after resume
    import time as t

    t.sleep(0.16)
    with pytest.raises(AdmissionRefused) as exc:
        mgr.admit("agent:w")
    assert "wall-clock budget exhausted" in str(exc.value)


# ── freeze / resume / kill state machine ─────────────────────────────────────


def test_frozen_refuses_admission_until_resumed(mgr):
    mgr.set_quota("agent:f", AgentQuota(token_budget=1000))
    mgr.admit("agent:f")
    mgr.freeze("agent:f")
    with pytest.raises(AdmissionRefused) as exc:
        mgr.admit("agent:f")
    assert "frozen" in str(exc.value)
    mgr.resume("agent:f")
    assert mgr.admit("agent:f")["state"] == "running"


def test_kill_is_terminal(mgr):
    mgr.admit("agent:k")
    mgr.kill("agent:k", reason="operator stop")
    with pytest.raises(AdmissionRefused) as exc:
        mgr.admit("agent:k")
    assert "killed" in str(exc.value)
    assert "operator stop" in str(exc.value)
    with pytest.raises(CgroupError):
        mgr.resume("agent:k")
    with pytest.raises(CgroupError):
        mgr.set_quota("agent:k", AgentQuota(token_budget=1))


def test_status_all_lists_every_group(mgr):
    mgr.set_quota("agent:x", AgentQuota(token_budget=10))
    mgr.admit("agent:y")
    rows = {r["agent_id"]: r for r in mgr.status_all()}
    assert set(rows) == {"agent:x", "agent:y"}


# ── bus integration: real events accounted, real events published ──────────


async def test_bus_events_account_usage(bus, tmp_path):
    from agentic_os.domain.events import EventEnvelope

    mgr = AgentCgroupManager(data_dir=str(tmp_path / "cg2"), bus=bus)
    await mgr.attach_bus(bus)
    await bus.start()
    mgr.set_quota("agent:bus", AgentQuota(token_budget=1000, tool_call_cap=10))
    await bus.publish(
        EventEnvelope(
            type="cost.recorded",
            source="agent:bus",
            topic="system",
            payload={"total_tokens": 120},
        )
    )
    await bus.publish(
        EventEnvelope(
            type="mcp.tool_invoked",
            source="agent:bus",
            topic="system",
            payload={"tool": "fs.read"},
        )
    )
    await asyncio.sleep(0.2)  # let the bus worker run handlers
    status = mgr.status("agent:bus")
    assert status["tokens_used"] == 120
    assert status["tool_calls"] == 1


async def test_cgroup_publishes_enforcement_events(bus, tmp_path):
    from agentic_os.domain.events import EventEnvelope

    seen: list[str] = []

    async def spy(envelope: EventEnvelope) -> None:
        seen.append(str(envelope.type))

    await bus.subscribe("system", spy)
    await bus.start()

    mgr = AgentCgroupManager(data_dir=str(tmp_path / "cg3"), bus=bus)
    mgr.set_quota("agent:pub", AgentQuota(token_budget=10))
    mgr.admit("agent:pub")
    mgr.record_tokens("agent:pub", 10)  # hits the budget -> exceeded event
    mgr.freeze("agent:pub")
    mgr.kill("agent:pub", reason="test")
    await asyncio.sleep(0.2)
    assert "cgroup.exceeded" in seen
    assert "cgroup.frozen" in seen
    assert "cgroup.killed" in seen


# ── ledger persistence ───────────────────────────────────────────────────────


def test_ledger_persisted_and_reloaded(tmp_path):
    m1 = AgentCgroupManager(data_dir=str(tmp_path / "led"))
    m1.set_quota("agent:led", AgentQuota(token_budget=5))
    m1.admit("agent:led")
    m1.record_tokens("agent:led", 5)
    m2 = AgentCgroupManager(data_dir=str(tmp_path / "led"))
    rows = m2.ledger("agent:led")
    kinds = [r["kind"] for r in rows]
    assert "quota_set" in kinds
    assert "activated" in kinds
    assert "tokens" in kinds
