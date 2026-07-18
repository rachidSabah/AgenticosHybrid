"""Tests for CommunicationBus (Phase 4, M3)."""

import pytest

from agentic_os.core.orchestration.communication import CommunicationBus
from agentic_os.domain.orchestration import AgentMessage


class _MockBus:
    def __init__(self):
        self.events = []

    async def publish(self, envelope):
        self.events.append(envelope)


@pytest.fixture
def bus():
    return _MockBus()


@pytest.fixture
def comm(bus):
    return CommunicationBus(bus=bus)


class TestCommunicationBus:
    async def test_send_message(self, comm, bus) -> None:
        msg = AgentMessage(
            source_agent_id="a1",
            target_agent_id="a2",
            swarm_id="s1",
            payload={"text": "hello"},
        )
        result = await comm.send_message(msg)
        assert result.id == msg.id
        assert comm.history_size == 1

    async def test_send_message_publishes_event(self, comm, bus) -> None:
        msg = AgentMessage(source_agent_id="a1", target_agent_id="a2", swarm_id="s1")
        await comm.send_message(msg)
        topics = [e.topic for e in bus.events]
        assert "orchestration.msg_sent" in topics

    async def test_broadcast(self, comm, bus) -> None:
        result = await comm.broadcast(
            source_agent_id="a1",
            swarm_id="s1",
            payload={"alert": "all hands"},
        )
        assert result.target_agent_id is None
        assert result.message_type == "broadcast"
        assert comm.history_size == 1

    async def test_broadcast_publishes_event(self, comm, bus) -> None:
        await comm.broadcast(source_agent_id="a1", swarm_id="s1", payload={})
        topics = [e.topic for e in bus.events]
        assert "orchestration.msg_broadcast" in topics

    async def test_send_response(self, comm, bus) -> None:
        original = AgentMessage(
            source_agent_id="a1",
            target_agent_id="a2",
            swarm_id="s1",
            payload={"question": "status?"},
        )
        response = await comm.send_response(original, {"status": "ok"})
        assert response.correlation_id == original.id
        assert response.source_agent_id == "a2"
        assert response.target_agent_id == "a1"

    async def test_receive_message(self, comm, bus) -> None:
        msg = AgentMessage(source_agent_id="a1", target_agent_id="a2", swarm_id="s1")
        result = await comm.receive_message(msg)
        assert result.id == msg.id
        topics = [e.topic for e in bus.events]
        assert "orchestration.msg_received" in topics

    async def test_get_history(self, comm, bus) -> None:
        for i in range(5):
            msg = AgentMessage(source_agent_id=f"a{i}", target_agent_id="dst", swarm_id="s1")
            await comm.send_message(msg)
        history = await comm.get_history(limit=3)
        assert len(history) == 3

    async def test_get_history_filter_by_swarm(self, comm, bus) -> None:
        await comm.send_message(
            AgentMessage(source_agent_id="a1", target_agent_id="a2", swarm_id="s1")
        )
        await comm.send_message(
            AgentMessage(source_agent_id="a3", target_agent_id="a4", swarm_id="s2")
        )
        history = await comm.get_history(swarm_id="s1")
        assert len(history) == 1

    async def test_get_history_filter_by_agent(self, comm, bus) -> None:
        await comm.send_message(
            AgentMessage(source_agent_id="a1", target_agent_id="a2", swarm_id="s1")
        )
        await comm.send_message(
            AgentMessage(source_agent_id="a3", target_agent_id="a4", swarm_id="s1")
        )
        history = await comm.get_history(agent_id="a1")
        assert len(history) == 1

    async def test_clear_history(self, comm, bus) -> None:
        await comm.send_message(
            AgentMessage(source_agent_id="a1", target_agent_id="a2", swarm_id="s1")
        )
        assert comm.history_size == 1
        await comm.clear_history()
        assert comm.history_size == 0

    async def test_history_buffer_limited(self, bus) -> None:
        comm = CommunicationBus(bus=bus, history_max=3)
        for i in range(5):
            await comm.send_message(
                AgentMessage(source_agent_id=f"a{i}", target_agent_id="dst", swarm_id="s1")
            )
        assert comm.history_size == 3

    async def test_history_filter_no_match(self, comm, bus) -> None:
        await comm.send_message(
            AgentMessage(source_agent_id="a1", target_agent_id="a2", swarm_id="s1")
        )
        history = await comm.get_history(swarm_id="nonexistent")
        assert history == []

    async def test_broadcast_response_roundtrip(self, comm, bus) -> None:
        broadcast = await comm.broadcast(
            source_agent_id="a1", swarm_id="s1", payload={"cmd": "update"}
        )
        response = await comm.send_response(broadcast, {"status": "done"})
        assert response.correlation_id == broadcast.id

    async def test_empty_history(self, comm, bus) -> None:
        history = await comm.get_history()
        assert history == []
