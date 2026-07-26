"""Tests for runtime events — event creation, field validation, publish helpers."""

import pytest

from agentic_os.core.runtime.runtime_events import (
    RUNTIME_EVENTS,
    RuntimeEvent,
    make_runtime_event,
    publish_runtime_command,
    publish_runtime_command_failed,
    publish_runtime_crashed,
    publish_runtime_discovered,
    publish_runtime_event,
    publish_runtime_health_changed,
    publish_runtime_heartbeat,
    publish_runtime_ready,
    publish_runtime_recovered,
    publish_runtime_registered,
    publish_runtime_removed,
    publish_runtime_restarted,
    publish_runtime_session_closed,
    publish_runtime_session_created,
    publish_runtime_started,
    publish_runtime_stopped,
)


class TestRuntimeEvent:
    def test_construction(self) -> None:
        event = RuntimeEvent(topic="runtime.started", runtime_id="rt-1", runtime_name="test")
        assert event.topic == "runtime.started"
        assert event.runtime_id == "rt-1"
        assert event.runtime_name == "test"
        assert event.timestamp is not None
        assert event.payload == {}
        assert event.session_id is None

    def test_to_dict(self) -> None:
        event = RuntimeEvent(
            topic="runtime.crashed",
            runtime_id="rt-1",
            runtime_name="test",
            payload={"error": "OOM"},
            session_id="sess-1",
        )
        d = event.to_dict()
        assert d["topic"] == "runtime.crashed"
        assert d["runtime_id"] == "rt-1"
        assert d["payload"]["error"] == "OOM"
        assert d["session_id"] == "sess-1"

    def test_make_runtime_event(self) -> None:
        event = make_runtime_event("runtime.ready", "rt-1", "test", pid=123)
        assert event.topic == "runtime.ready"
        assert event.payload["pid"] == 123

    def test_make_runtime_event_no_extra(self) -> None:
        event = make_runtime_event("runtime.stopped", "rt-1", "test")
        assert event.payload == {}


class TestRUNTIME_EVENTS:
    def test_event_names(self) -> None:
        assert RUNTIME_EVENTS["RUNTIME_DISCOVERED"] == "runtime.discovered"
        assert RUNTIME_EVENTS["RUNTIME_STARTED"] == "runtime.started"
        assert RUNTIME_EVENTS["RUNTIME_READY"] == "runtime.ready"
        assert RUNTIME_EVENTS["RUNTIME_STOPPED"] == "runtime.stopped"
        assert RUNTIME_EVENTS["RUNTIME_CRASHED"] == "runtime.crashed"
        assert RUNTIME_EVENTS["RUNTIME_RESTARTED"] == "runtime.restarted"
        assert RUNTIME_EVENTS["RUNTIME_RECOVERED"] == "runtime.recovered"
        assert RUNTIME_EVENTS["RUNTIME_HEALTH_CHANGED"] == "runtime.health.changed"

    def test_all_events_have_unique_values(self) -> None:
        values = list(RUNTIME_EVENTS.values())
        assert len(values) == len(set(values))

    def test_key_count(self) -> None:
        assert len(RUNTIME_EVENTS) >= 20  # at least 20 event types


class TestPublishHelpers:
    @pytest.mark.asyncio
    async def test_publish_runtime_event_with_bus(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append((topic, data))

        await publish_runtime_event(_Bus(), "test.topic", "rt-1", "test-rt", key="val")
        assert len(events) == 1
        assert events[0][0] == "test.topic"

    @pytest.mark.asyncio
    async def test_publish_runtime_event_no_bus(self) -> None:
        """Should not crash when bus is None."""
        await publish_runtime_event(None, "test.topic", "rt-1", "test-rt")

    @pytest.mark.asyncio
    async def test_publish_runtime_discovered(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append(topic)

        await publish_runtime_discovered(_Bus(), "rt-1", "test")
        assert "runtime.discovered" in events

    @pytest.mark.asyncio
    async def test_publish_runtime_registered(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append(topic)

        await publish_runtime_registered(_Bus(), "rt-1", "test")
        assert "runtime.registered" in events

    @pytest.mark.asyncio
    async def test_publish_runtime_started(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append((topic, data))

        await publish_runtime_started(_Bus(), "rt-1", "test", pid=123)
        topic, data = events[0]
        assert topic == "runtime.started"
        assert data["payload"]["pid"] == 123

    @pytest.mark.asyncio
    async def test_publish_runtime_ready(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append(topic)

        await publish_runtime_ready(_Bus(), "rt-1", "test")
        assert "runtime.ready" in events

    @pytest.mark.asyncio
    async def test_publish_runtime_stopped(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append((topic, data))

        await publish_runtime_stopped(_Bus(), "rt-1", "test", exit_code=0)
        assert events[0][0] == "runtime.stopped"

    @pytest.mark.asyncio
    async def test_publish_runtime_crashed(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append((topic, data))

        await publish_runtime_crashed(_Bus(), "rt-1", "test", error="OOM")
        assert events[0][0] == "runtime.crashed"
        assert events[0][1]["payload"]["error"] == "OOM"

    @pytest.mark.asyncio
    async def test_publish_runtime_restarted(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append(topic)

        await publish_runtime_restarted(_Bus(), "rt-1", "test")
        assert "runtime.restarted" in events

    @pytest.mark.asyncio
    async def test_publish_runtime_recovered(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append(topic)

        await publish_runtime_recovered(_Bus(), "rt-1", "test")
        assert "runtime.recovered" in events

    @pytest.mark.asyncio
    async def test_publish_runtime_health_changed(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append((topic, data))

        await publish_runtime_health_changed(
            _Bus(), "rt-1", "test", old_health="healthy", new_health="unhealthy"
        )
        assert events[0][0] == "runtime.health.changed"

    @pytest.mark.asyncio
    async def test_publish_runtime_session_created(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append((topic, data))

        await publish_runtime_session_created(_Bus(), "rt-1", "test", session_id="sess-1")
        assert events[0][0] == "runtime.session.created"

    @pytest.mark.asyncio
    async def test_publish_runtime_session_closed(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append(topic)

        await publish_runtime_session_closed(_Bus(), "rt-1", "test", session_id="sess-1")
        assert "runtime.session.closed" in events

    @pytest.mark.asyncio
    async def test_publish_runtime_heartbeat(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append(topic)

        await publish_runtime_heartbeat(_Bus(), "rt-1", "test")
        assert "runtime.heartbeat" in events

    @pytest.mark.asyncio
    async def test_publish_runtime_command_started(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append((topic, data))

        await publish_runtime_command(_Bus(), "rt-1", "test", "echo hello", status="started")
        assert events[0][0] == "runtime.command.started"

    @pytest.mark.asyncio
    async def test_publish_runtime_command_completed(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append((topic, data))

        await publish_runtime_command(_Bus(), "rt-1", "test", "echo hello", status="completed")
        assert events[0][0] == "runtime.command.completed"

    @pytest.mark.asyncio
    async def test_publish_runtime_command_failed(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append((topic, data))

        await publish_runtime_command_failed(_Bus(), "rt-1", "test", "bad cmd", error="not found")
        assert events[0][0] == "runtime.command.failed"

    @pytest.mark.asyncio
    async def test_publish_runtime_removed(self) -> None:
        events = []

        class _Bus:
            async def publish(self, topic: str, data: object) -> None:
                events.append(topic)

        await publish_runtime_removed(_Bus(), "rt-1", "test")
        assert "runtime.removed" in events

    @pytest.mark.asyncio
    async def test_all_publish_helpers_accept_no_bus(self) -> None:
        """None of the helpers should crash when bus is None."""
        await publish_runtime_discovered(None, "rt-1", "test")
        await publish_runtime_registered(None, "rt-1", "test")
        await publish_runtime_started(None, "rt-1", "test")
        await publish_runtime_ready(None, "rt-1", "test")
        await publish_runtime_stopped(None, "rt-1", "test")
        await publish_runtime_crashed(None, "rt-1", "test", error="err")
        await publish_runtime_restarted(None, "rt-1", "test")
        await publish_runtime_recovered(None, "rt-1", "test")
        await publish_runtime_health_changed(None, "rt-1", "test", old_health="a", new_health="b")
        await publish_runtime_session_created(None, "rt-1", "test", session_id="s")
        await publish_runtime_session_closed(None, "rt-1", "test", session_id="s")
        await publish_runtime_heartbeat(None, "rt-1", "test")
        await publish_runtime_command(None, "rt-1", "test", "cmd")
        await publish_runtime_command_failed(None, "rt-1", "test", "cmd", error="e")
        await publish_runtime_removed(None, "rt-1", "test")
