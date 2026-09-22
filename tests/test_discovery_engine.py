"""Discovery engine tests (spec §21).

These assert the *contract*: nothing appears without real evidence.
"""

from __future__ import annotations

import pytest

from agentic_os.core.brains.probes import (
    classify,
    derive_capabilities,
    run_probe_sequence,
)
from agentic_os.core.brains.schema import (
    KIND_AI_AGENT_CLI,
    KIND_DEV_RUNTIME,
    KIND_VCS,
    STATUS_HEALTHY,
    STATUS_NOT_FOUND,
    STATUS_UNAVAILABLE,
    Capability,
    DiscoveredAgent,
    DiscoverySnapshot,
)


def test_missing_executable_is_not_found():
    """T4: an absent binary must not appear."""
    a = DiscoveredAgent(id="agent:gemini", name="gemini", status=STATUS_NOT_FOUND)
    assert not a.is_active()


def test_healthy_agent_is_active():
    a = DiscoveredAgent(
        id="agent:agy",
        name="agy",
        kind=KIND_AI_AGENT_CLI,
        version="1.2.8",
        status=STATUS_HEALTHY,
    )
    assert a.is_active()
    assert a.is_agent()


def test_runtimes_are_not_agents():
    """T: git/node/python are runtimes, never AI agents (§4)."""
    for kind in (KIND_VCS, KIND_DEV_RUNTIME):
        a = DiscoveredAgent(id="x", name="x", kind=kind, status=STATUS_HEALTHY)
        assert not a.is_agent()
        assert not a.is_active()


def test_active_agents_excludes_runtimes():
    snap = DiscoverySnapshot(
        agents=[
            DiscoveredAgent(id="a", name="agy", kind=KIND_AI_AGENT_CLI, status=STATUS_HEALTHY),
            DiscoveredAgent(id="g", name="git", kind=KIND_VCS, status=STATUS_HEALTHY),
        ]
    )
    assert len(snap.active_agents()) == 1
    assert snap.active_agents()[0].name == "agy"
    assert len(snap.runtimes()) == 1
    assert snap.runtimes()[0].name == "git"


def test_empty_snapshot_reports_zero():
    """T1: no agents => zero everywhere, not a decorative count."""
    snap = DiscoverySnapshot()
    assert snap.candidates_seen == 0
    assert len(snap.active_agents()) == 0
    assert snap.to_dict()["counts"]["active"] == 0


def test_no_fabricated_defaults():
    """§19/§20: telemetry fields must be None, never 0/'ONLINE'."""
    a = DiscoveredAgent(id="x", name="x")
    assert a.version is None
    assert a.health_score is None
    assert a.throughput is None
    assert a.session_count is None
    assert a.heartbeat is None
    assert a.capabilities == []


def test_capability_carries_provenance():
    """§7: every capability states how it was learned."""
    c = Capability(capability="mcp", source="help_text", confidence="inferred")
    assert c.source and c.confidence


def test_unavailable_agent_not_active():
    a = DiscoveredAgent(id="x", name="gemini", status=STATUS_UNAVAILABLE)
    assert not a.is_active()


def test_classify_rejects_runtimes():

    assert classify("git", "") == KIND_VCS
    assert classify("node", "") == KIND_DEV_RUNTIME
    assert classify("python", "") == KIND_DEV_RUNTIME


def test_classify_accepts_agent_with_evidence():

    help_text = "An AI coding agent. Chat with an LLM to generate code."
    assert classify("someagent", help_text) == KIND_AI_AGENT_CLI


def test_classify_unknown_without_evidence():
    """§4: no evidence => unknown, not agent."""
    from agentic_os.core.brains.schema import KIND_UNKNOWN

    assert classify("mysterybin", "") == KIND_UNKNOWN


def test_capabilities_derived_from_evidence_only():

    assert derive_capabilities("") == []
    caps = derive_capabilities("supports mcp and file editing and terminal")
    names = {c.capability for c in caps}
    assert "mcp" in names
    assert "file_editing" in names
    assert all(c.source == "help_text" for c in caps)


@pytest.mark.asyncio
async def test_probe_sequence_marks_missing_executable():
    from agentic_os.core.brains.probes import run_probe_sequence


    agent = await run_probe_sequence("definitely-not-real-xyz", "")
    assert agent.status == STATUS_NOT_FOUND
    assert agent.version is None
    assert agent.health_score is None


@pytest.mark.asyncio
async def test_probe_sequence_rejects_fake_agent_binary(monkeypatch, tmp_path):
    """T6: an AI-looking name with no evidence must be rejected (§21)."""
    import agentic_os.core.brains.probes as probes

    fake = tmp_path / "totallyfakeagent.exe"
    fake.write_text("not a real agent", encoding="utf-8")

    async def fake_run(cmd, timeout):
        # Executes but produces no version and no help output.
        return 1, "", ""

    monkeypatch.setattr(probes, "_run", fake_run)

    agent = await run_probe_sequence("totallyfakeagent", str(fake))
    assert not agent.is_active()
    assert agent.version is None
    assert agent.health_score is None
