"""Tests for BrainRegistry — central registry for all known AI brains.

Covers lifecycle, registration, lookup, search, update, unregister, event
publishing, merge behaviour, and concurrency.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from agentic_os.core.brains.registry import BrainRegistry
from agentic_os.domain.brains import BrainRecord, BrainRuntime, BrainStatus, BrainType, BrainVendor
from agentic_os.domain.events import Topic

# ═══════════════════════════════════════════════════════════════════════
# Lifecycle
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRegistryLifecycle:
    """start / stop behaviour."""

    async def test_initial_state(self) -> None:
        registry = BrainRegistry()
        assert registry._started is False
        assert registry._event_bus is None
        assert len(registry._brains) == 0

    async def test_start_sets_started(self, mock_event_bus: AsyncMock) -> None:
        registry = BrainRegistry()
        await registry.start(event_bus=mock_event_bus)
        assert registry._started is True
        assert registry._event_bus is mock_event_bus

    async def test_start_without_bus(self) -> None:
        registry = BrainRegistry()
        await registry.start()
        assert registry._started is True
        assert registry._event_bus is None

    async def test_stop_clears_state(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()
        await registry.register(sample_record)
        await registry.stop()
        assert registry._started is False
        assert len(registry._brains) == 0

    async def test_stop_when_not_started_is_safe(self) -> None:
        registry = BrainRegistry()
        await registry.stop()  # should not raise


# ═══════════════════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRegistryRegister:
    """register() — new brain, update existing, merge, event publishing."""

    async def test_register_new_brain(
        self, mock_event_bus: AsyncMock, sample_record: BrainRecord
    ) -> None:
        registry = BrainRegistry()
        await registry.start(event_bus=mock_event_bus)
        stored = await registry.register(sample_record)
        assert stored.id == sample_record.id
        assert stored.display_name == sample_record.display_name
        assert len(registry._brains) == 1

    async def test_register_returns_record(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()
        stored = await registry.register(sample_record)
        assert stored is sample_record  # same object for new records

    async def test_register_update_existing_preserves_fields(
        self, sample_record: BrainRecord
    ) -> None:
        """Registering the same id again should merge, keeping existing defaults."""
        registry = BrainRegistry()
        await registry.start()
        original = sample_record
        await registry.register(original)

        updated = BrainRecord(
            id=original.id,
            display_name="Updated Brain",
            brain_type=original.brain_type,
            vendor=original.vendor,
            runtime=original.runtime,
            version="2.0.0",
            status=BrainStatus.IDLE,
        )
        stored = await registry.register(updated)
        assert stored.id == original.id
        assert stored.display_name == "Updated Brain"
        assert stored.version == "2.0.0"

    async def test_register_merge_keeps_existing_capabilities(
        self, sample_record: BrainRecord
    ) -> None:
        """When new record has empty capabilities, existing ones should survive."""
        registry = BrainRegistry()
        await registry.start()
        existing = replace(sample_record, capabilities=("chat", "vision"))
        await registry.register(existing)

        new_record = BrainRecord(
            id=existing.id,
            display_name="Merge Test",
            brain_type=existing.brain_type,
            vendor=existing.vendor,
            runtime=existing.runtime,
            version="1.0.0",
            status=BrainStatus.IDLE,
            capabilities=(),  # empty — should keep existing
        )
        stored = await registry.register(new_record)
        assert "chat" in stored.capabilities
        assert "vision" in stored.capabilities

    async def test_register_merge_metadata(self, sample_record: BrainRecord) -> None:
        """Metadata from both records should be merged."""
        registry = BrainRegistry()
        await registry.start()
        existing = replace(sample_record, metadata={"key1": "val1", "key2": "old"})
        await registry.register(existing)

        new_record = BrainRecord(
            id=existing.id,
            display_name="Meta Merge",
            brain_type=existing.brain_type,
            vendor=existing.vendor,
            runtime=existing.runtime,
            version="1.0.0",
            status=BrainStatus.IDLE,
            metadata={"key2": "new", "key3": "val3"},
        )
        stored = await registry.register(new_record)
        assert stored.metadata["key1"] == "val1"
        assert stored.metadata["key2"] == "new"
        assert stored.metadata["key3"] == "val3"

    async def test_register_publishes_brain_registered_event(
        self, mock_event_bus: AsyncMock, sample_record: BrainRecord
    ) -> None:
        registry = BrainRegistry()
        await registry.start(event_bus=mock_event_bus)
        await registry.register(sample_record)
        mock_event_bus.publish.assert_called_once()
        call_args = mock_event_bus.publish.call_args[0][0]
        assert call_args.topic == Topic.BRAIN_REGISTERED.value
        assert call_args.source == "brain_registry"

    async def test_register_update_publishes_brain_updated_event(
        self, mock_event_bus: AsyncMock, sample_record: BrainRecord
    ) -> None:
        registry = BrainRegistry()
        await registry.start(event_bus=mock_event_bus)
        await registry.register(sample_record)
        mock_event_bus.publish.reset_mock()

        updated = replace(sample_record, version="2.0.0")
        await registry.register(updated)
        mock_event_bus.publish.assert_called_once()
        call_args = mock_event_bus.publish.call_args[0][0]
        assert call_args.topic == Topic.BRAIN_UPDATED.value


# ═══════════════════════════════════════════════════════════════════════
# Unregister
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRegistryUnregister:
    """unregister() — removal and event publishing."""

    async def test_unregister_existing_brain(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()
        await registry.register(sample_record)
        result = await registry.unregister(sample_record.id)
        assert result is True
        assert await registry.count() == 0

    async def test_unregister_unknown_brain(self) -> None:
        registry = BrainRegistry()
        await registry.start()
        result = await registry.unregister("nonexistent")
        assert result is False

    async def test_unregister_publishes_brain_removed_event(
        self, mock_event_bus: AsyncMock, sample_record: BrainRecord
    ) -> None:
        registry = BrainRegistry()
        await registry.start(event_bus=mock_event_bus)
        await registry.register(sample_record)
        mock_event_bus.publish.reset_mock()

        await registry.unregister(sample_record.id)
        mock_event_bus.publish.assert_called_once()
        call_args = mock_event_bus.publish.call_args[0][0]
        assert call_args.topic == Topic.BRAIN_REMOVED.value
        # Payload should reflect REMOVED status
        assert call_args.payload["status"] == BrainStatus.REMOVED.value

    async def test_unregister_twice_returns_false(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()
        await registry.register(sample_record)
        await registry.unregister(sample_record.id)
        result = await registry.unregister(sample_record.id)
        assert result is False


# ═══════════════════════════════════════════════════════════════════════
# Lookup / Query
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRegistryGet:
    """get() — single brain lookup."""

    async def test_get_existing_brain(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()
        await registry.register(sample_record)
        found = await registry.get(sample_record.id)
        assert found is not None
        assert found.id == sample_record.id

    async def test_get_nonexistent_brain(self) -> None:
        registry = BrainRegistry()
        await registry.start()
        found = await registry.get("does-not-exist")
        assert found is None

    async def test_get_returns_same_instance(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()
        await registry.register(sample_record)
        found = await registry.get(sample_record.id)
        assert found is sample_record  # same object reference


class TestBrainRegistryListAll:
    """list_all() — snapshot of all brains."""

    async def test_list_all_empty(self) -> None:
        registry = BrainRegistry()
        await registry.start()
        assert await registry.list_all() == []

    async def test_list_all_returns_all(
        self, sample_record: BrainRecord, sample_record_openai: BrainRecord
    ) -> None:
        registry = BrainRegistry()
        await registry.start()
        await registry.register(sample_record)
        await registry.register(sample_record_openai)
        all_brains = await registry.list_all()
        assert len(all_brains) == 2
        ids = {b.id for b in all_brains}
        assert ids == {"test-1", "openai-1"}


class TestBrainRegistrySearch:
    """search() — filtered queries."""

    @pytest.fixture
    async def registry_with_brains(self) -> BrainRegistry:
        reg = BrainRegistry()
        await reg.start()
        await reg.register(
            BrainRecord(
                id="b1",
                display_name="O1",
                brain_type=BrainType.CLOUD_API,
                vendor=BrainVendor.OPENAI,
                runtime=BrainRuntime.CLOUD,
                version="1",
                status=BrainStatus.CONNECTED,
                tags=("prod",),
            )
        )
        await reg.register(
            BrainRecord(
                id="b2",
                display_name="O2",
                brain_type=BrainType.LOCAL_CLI,
                vendor=BrainVendor.OLLAMA,
                runtime=BrainRuntime.PYTHON,
                version="2",
                status=BrainStatus.IDLE,
                tags=("dev", "local"),
            )
        )
        await reg.register(
            BrainRecord(
                id="b3",
                display_name="O3",
                brain_type=BrainType.CLOUD_API,
                vendor=BrainVendor.ANTHROPIC,
                runtime=BrainRuntime.CLOUD,
                version="3",
                status=BrainStatus.DISCONNECTED,
                tags=("prod",),
            )
        )
        return reg

    async def test_search_by_brain_type(self, registry_with_brains: BrainRegistry) -> None:
        results = await registry_with_brains.search(brain_type="cloud_api")
        assert len(results) == 2

    async def test_search_by_vendor(self, registry_with_brains: BrainRegistry) -> None:
        results = await registry_with_brains.search(vendor="openai")
        assert len(results) == 1
        assert results[0].id == "b1"

    async def test_search_by_status(self, registry_with_brains: BrainRegistry) -> None:
        results = await registry_with_brains.search(status="idle")
        assert len(results) == 1
        assert results[0].id == "b2"

    async def test_search_by_tag(self, registry_with_brains: BrainRegistry) -> None:
        results = await registry_with_brains.search(tag="prod")
        assert len(results) == 2
        ids = {r.id for r in results}
        assert ids == {"b1", "b3"}

    async def test_search_running_brains(self, registry_with_brains: BrainRegistry) -> None:
        results = await registry_with_brains.search(running=True)
        assert len(results) == 2  # b1 (CONNECTED) + b2 (IDLE)
        ids = {r.id for r in results}
        assert ids == {"b1", "b2"}

    async def test_search_not_running(self, registry_with_brains: BrainRegistry) -> None:
        results = await registry_with_brains.search(running=False)
        assert len(results) == 1  # b3 (DISCONNECTED)
        assert results[0].id == "b3"

    async def test_search_multiple_filters(self, registry_with_brains: BrainRegistry) -> None:
        results = await registry_with_brains.search(brain_type="cloud_api", tag="prod")
        assert len(results) == 2  # b1 and b3 are both cloud_api + prod

    async def test_search_limit(self, registry_with_brains: BrainRegistry) -> None:
        results = await registry_with_brains.search(limit=1)
        assert len(results) == 1

    async def test_search_no_match(self, registry_with_brains: BrainRegistry) -> None:
        results = await registry_with_brains.search(vendor="nonexistent")
        assert results == []

    async def test_search_no_filters_returns_all(self, registry_with_brains: BrainRegistry) -> None:
        results = await registry_with_brains.search()
        assert len(results) == 3


class TestBrainRegistryCount:
    """count() — total registered brains."""

    async def test_count_empty(self) -> None:
        registry = BrainRegistry()
        await registry.start()
        assert await registry.count() == 0

    async def test_count_after_register(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()
        assert await registry.count() == 0
        await registry.register(sample_record)
        assert await registry.count() == 1


# ═══════════════════════════════════════════════════════════════════════
# Update
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRegistryUpdate:
    """update() — partial field updates."""

    async def test_update_existing_fields(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()
        await registry.register(sample_record)
        updated = await registry.update(sample_record.id, display_name="Renamed", version="2.0.0")
        assert updated is not None
        assert updated.display_name == "Renamed"
        assert updated.version == "2.0.0"

    async def test_update_nonexistent_returns_none(self) -> None:
        registry = BrainRegistry()
        await registry.start()
        result = await registry.update("unknown", display_name="Nope")
        assert result is None

    async def test_update_publishes_event(
        self, mock_event_bus: AsyncMock, sample_record: BrainRecord
    ) -> None:
        registry = BrainRegistry()
        await registry.start(event_bus=mock_event_bus)
        await registry.register(sample_record)
        mock_event_bus.publish.reset_mock()

        await registry.update(sample_record.id, version="3.0.0")
        mock_event_bus.publish.assert_called_once()
        assert mock_event_bus.publish.call_args[0][0].topic == Topic.BRAIN_UPDATED.value

    async def test_update_preserves_other_fields(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()
        await registry.register(sample_record)
        updated = await registry.update(sample_record.id, priority=99)
        assert updated is not None
        assert updated.priority == 99
        assert updated.display_name == sample_record.display_name  # unchanged
        assert updated.version == sample_record.version  # unchanged


# ═══════════════════════════════════════════════════════════════════════
# Mark status
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRegistryMarkStatus:
    """mark_status() — convenience for status-only updates."""

    async def test_mark_status_updates_status(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()
        await registry.register(sample_record)
        updated = await registry.mark_status(sample_record.id, BrainStatus.CONNECTED)
        assert updated is not None
        assert updated.status == BrainStatus.CONNECTED

    async def test_mark_status_nonexistent(self) -> None:
        registry = BrainRegistry()
        await registry.start()
        result = await registry.mark_status("unknown", BrainStatus.FAILED)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════
# Event publishing edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRegistryEventPublishing:
    """Edge cases around event bus publishing."""

    async def test_no_event_bus_does_not_raise(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()  # no bus
        await registry.register(sample_record)  # should not raise
        await registry.unregister(sample_record.id)  # should not raise

    async def test_event_bus_exception_caught(
        self, mock_event_bus: AsyncMock, sample_record: BrainRecord
    ) -> None:
        """Publish errors should be logged, not propagated."""
        mock_event_bus.publish.side_effect = RuntimeError("bus down")
        registry = BrainRegistry()
        await registry.start(event_bus=mock_event_bus)
        await registry.register(sample_record)  # should not raise

    async def test_unregister_publishes_even_without_bus(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()
        await registry.register(sample_record)
        result = await registry.unregister(sample_record.id)
        assert result is True


# ═══════════════════════════════════════════════════════════════════════
# Concurrency
# ═══════════════════════════════════════════════════════════════════════


class TestBrainRegistryConcurrency:
    """Basic concurrency / lock behaviour."""

    async def test_concurrent_registrations(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()

        async def register_brain(brain_id: str) -> None:
            record = BrainRecord(
                id=brain_id,
                display_name=f"Brain {brain_id}",
                brain_type=BrainType.CUSTOM,
                vendor=BrainVendor.CUSTOM,
                runtime=BrainRuntime.UNKNOWN,
                version="1.0.0",
                status=BrainStatus.IDLE,
            )
            await registry.register(record)

        await asyncio.gather(
            register_brain("c1"),
            register_brain("c2"),
            register_brain("c3"),
        )
        assert await registry.count() == 3

    async def test_concurrent_register_and_get(self, sample_record: BrainRecord) -> None:
        registry = BrainRegistry()
        await registry.start()
        await registry.register(sample_record)

        async def read_brain() -> None:
            _ = await registry.get(sample_record.id)

        await asyncio.gather(
            registry.update(sample_record.id, version="x"),
            read_brain(),
            read_brain(),
        )
        assert await registry.count() == 1
