"""Tests for LocalDiscoveryService (Phase 6.1)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_os.core.discovery.local.service import LocalDiscoveryService
from agentic_os.domain.discovery import AgentDiscoveryConfig, AgentStatus
from agentic_os.domain.events import Topic


class TestLocalDiscoveryServiceLifecycle:
    @pytest.fixture
    async def service(self) -> LocalDiscoveryService:
        cfg = AgentDiscoveryConfig(auto_register=False)
        svc = LocalDiscoveryService(config=cfg)
        yield svc

    async def test_initial_state(self, service: LocalDiscoveryService) -> None:
        assert service.is_started is False

    async def test_start_sets_started(self, service: LocalDiscoveryService) -> None:
        await service.start()
        assert service.is_started is True
        await service.stop()

    async def test_stop_clears_started(self, service: LocalDiscoveryService) -> None:
        await service.start()
        await service.stop()
        assert service.is_started is False

    async def test_stop_when_not_started_is_safe(self, service: LocalDiscoveryService) -> None:
        await service.stop()  # should not raise

    async def test_start_twice_is_idempotent(self, service: LocalDiscoveryService) -> None:
        await service.start()
        await service.start()  # second call should be no-op
        assert service.is_started is True
        await service.stop()


class TestLocalDiscoveryServiceDiscovery:
    async def test_run_discovery_returns_result(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(
                return_value=[
                    ("hermes", "/usr/bin/hermes", "1.0.0"),
                    ("ollama", "/usr/bin/ollama", "0.1.0"),
                ]
            )
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            result = await service.run_discovery()
            assert result.agents_found == 2

    async def test_run_discovery_with_scanner_error(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(side_effect=RuntimeError("scan failed"))
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            result = await service.run_discovery()
            assert result.agents_found == 0
            assert len(result.errors) >= 1

    async def test_run_discovery_deduplicates(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(
                return_value=[
                    ("hermes", "/usr/bin/hermes", "1.0.0"),
                    ("hermes", "/usr/bin/hermes", "1.0.0"),  # duplicate
                ]
            )
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            result = await service.run_discovery()
            # Should detect 2 agents (both scanned), but only 1 new (deduped)
            assert result.agents_found == 2
            assert result.agents_new == 1


class TestLocalDiscoveryServiceAgentAccess:
    @pytest.fixture
    async def service_with_agents(self) -> LocalDiscoveryService:
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(
                return_value=[
                    ("hermes", "/usr/bin/hermes", "1.0.0"),
                    ("ollama", "/usr/bin/ollama", "0.1.0"),
                ]
            )
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            await service.run_discovery()
            yield service

    async def test_get_agents_returns_list(
        self, service_with_agents: LocalDiscoveryService
    ) -> None:
        agents = await service_with_agents.get_agents()
        assert len(agents) == 2

    async def test_get_agent_by_id(self, service_with_agents: LocalDiscoveryService) -> None:
        agents = await service_with_agents.get_agents()
        first = agents[0]
        found = await service_with_agents.get_agent(first.id)
        assert found is not None
        assert found.id == first.id

    async def test_get_agent_not_found(self, service_with_agents: LocalDiscoveryService) -> None:
        found = await service_with_agents.get_agent("nonexistent-id")
        assert found is None

    async def test_get_agent_types(self, service_with_agents: LocalDiscoveryService) -> None:
        agents = await service_with_agents.get_agents()
        tool_types = {a.tool_type for a in agents}
        assert "hermes" in tool_types
        assert "ollama" in tool_types


class TestLocalDiscoveryServiceUpdate:
    async def test_update_agent_returns_updated(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(return_value=[("hermes", "/usr/bin/hermes", "1.0.0")])
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            await service.run_discovery()
            agent = (await service.get_agents())[0]
            updated = await service.update_agent(agent.id, version="2.0.0")
            assert updated is not None
            assert updated.version == "2.0.0"

    async def test_update_agent_unknown_id(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(return_value=[])
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            result = await service.update_agent("nonexistent", version="2.0")
            assert result is None

    async def test_update_agent_publishes_event(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        event_bus = AsyncMock()
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(return_value=[("hermes", "/usr/bin/hermes", "1.0.0")])
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            service._event_bus = event_bus
            await service.run_discovery()
            agent = (await service.get_agents())[0]
            await service.update_agent(agent.id, version="2.0.0")
            event_bus.publish.assert_called()


class TestLocalDiscoveryServiceRemove:
    async def test_remove_agent_returns_true(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(return_value=[("hermes", "/usr/bin/hermes", "1.0.0")])
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            await service.run_discovery()
            agent = (await service.get_agents())[0]
            removed = await service.remove_agent(agent.id)
            assert removed is True

    async def test_remove_agent_unknown(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(return_value=[])
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            result = await service.remove_agent("nonexistent")
            assert result is False


class TestLocalDiscoveryServiceAutoRegister:
    async def test_auto_register_publishes_events(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        event_bus = AsyncMock()
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(return_value=[("hermes", "/usr/bin/hermes", "1.0.0")])
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            await service.run_discovery()
            agents = await service.auto_register(event_bus=event_bus)
            assert len(agents) == 1
            assert event_bus.publish.call_count >= 2  # AGENT_DISCOVERED + AGENT_REGISTERED

    async def test_auto_register_no_bus_returns_empty(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(return_value=[])
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            agents = await service.auto_register()
            assert agents == []


class TestLocalDiscoveryServiceStartStopIntegration:
    async def test_start_with_event_bus(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        event_bus = AsyncMock()
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(return_value=[("hermes", "/usr/bin/hermes", "1.0.0")])
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            await service.start(event_bus=event_bus)
            assert service.is_started is True
            assert mock_scanner.scan.called
            assert mock_hm.start.called

            await service.stop()
            assert service.is_started is False
            assert mock_hm.stop.called

    async def test_start_with_auto_register(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=True)
        event_bus = AsyncMock()
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(return_value=[("hermes", "/usr/bin/hermes", "1.0.0")])
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            await service.start(event_bus=event_bus)
            assert event_bus.publish.called  # auto_register publishes

            await service.stop()

    async def test_multiple_agents_registration(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(
                return_value=[
                    ("hermes", "/usr/bin/hermes", "1.0.0"),
                    ("ollama", "/usr/bin/ollama", "0.1.0"),
                    ("docker", "/usr/bin/docker", "24.0.0"),
                    ("python", "/usr/bin/python3", "3.12.0"),
                    ("git", "/usr/bin/git", "2.40.0"),
                ]
            )
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            result = await service.run_discovery()
            assert result.agents_found == 5
            assert result.agents_new == 5

            agents = await service.get_agents()
            assert len(agents) == 5

    async def test_events_published_on_each_operation(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        event_bus = AsyncMock()
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(return_value=[("hermes", "/usr/bin/hermes", "1.0.0")])
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            service._event_bus = event_bus
            await service.run_discovery()

            agent = (await service.get_agents())[0]

            # Update
            await service.update_agent(agent.id, status=AgentStatus.BUSY)
            update_topics = [
                call.kwargs["topic"]
                for call in event_bus.publish.call_args_list
                if call.kwargs["topic"] == Topic.AGENT_UPDATED.value
            ]
            assert update_topics

            # Remove
            await service.remove_agent(agent.id)
            remove_topics = [
                call.kwargs["topic"]
                for call in event_bus.publish.call_args_list
                if call.kwargs["topic"] == Topic.AGENT_REMOVED.value
            ]
            assert remove_topics

    async def test_concurrent_access_safety(self) -> None:
        """Multiple concurrent calls to get_agents should not corrupt state."""
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(
                return_value=[
                    ("hermes", "/usr/bin/hermes", "1.0.0"),
                    ("ollama", "/usr/bin/ollama", "0.1.0"),
                ]
            )
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            await service.run_discovery()

            # Fire concurrent reads
            async def read() -> int:
                agents = await service.get_agents()
                return len(agents)

            results = await asyncio.gather(*[read() for _ in range(10)])
            assert all(r == 2 for r in results)

    async def test_discovery_result_counters(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(
                return_value=[
                    ("hermes", "/usr/bin/hermes", "1.0.0"),
                    ("ollama", "/usr/bin/ollama", "0.1.0"),
                ]
            )
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            result = await service.run_discovery()
            assert result.agents_found == 2
            assert result.agents_new == 2
            assert result.agents_updated == 0
            assert len(result.errors) == 0
            assert result.duration_ms > 0
            assert "hermes" in result.tools_detected

    async def test_scanner_failure_does_not_crash_service(self) -> None:
        cfg = AgentDiscoveryConfig(auto_register=False)
        with (
            patch("agentic_os.core.discovery.local.service.AgentScanner") as mock_scanner_cls,
            patch("agentic_os.core.discovery.local.service.HealthMonitor") as mock_hm_cls,
            patch("agentic_os.core.discovery.local.service.CapabilityDetector") as mock_cap_cls,
        ):
            mock_scanner = MagicMock()
            mock_scanner.scan = AsyncMock(side_effect=RuntimeError("catastrophic failure"))
            mock_scanner_cls.return_value = mock_scanner

            mock_hm = MagicMock()
            mock_hm.start = AsyncMock()
            mock_hm.stop = AsyncMock()
            mock_hm.track_agent = AsyncMock()
            mock_hm_cls.return_value = mock_hm

            mock_cap = MagicMock()
            mock_cap.detect = MagicMock(return_value=())
            mock_cap_cls.return_value = mock_cap

            service = LocalDiscoveryService(
                config=cfg, scanner=mock_scanner, capability_detector=mock_cap
            )
            result = await service.run_discovery()
            assert result.errors
            # Service should still be usable
            agents = await service.get_agents()
            assert agents == []
