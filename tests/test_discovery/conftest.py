"""Shared fixtures for Phase 6.1 Local Agent Discovery tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_os.domain.discovery import (
    AgentDiscoveryConfig,
)

# ── Path / Executable fixtures ─────────────────────────────────────────────


@pytest.fixture
def mock_executable() -> str:
    """Create a temporary executable script and return its path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".bat", delete=False) as f:
        f.write("@echo off\necho test\n")
        tmp = f.name
    yield tmp
    try:
        os.unlink(tmp)
    except OSError:
        pass


@pytest.fixture
def mock_path_env(tmp_path: Path) -> Path:
    """Create a temporary bin directory with a mock executable and return the dir.

    Modifies ``PATH`` for the duration of the test to include *tmp_dir*.
    """
    tmp_dir = tmp_path / "mock_bin"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fake_exe = tmp_dir / "mock-tool"
    fake_exe.write_text("#!/bin/bash\necho mock\n")
    fake_exe.chmod(0o755)

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = str(tmp_dir) + os.pathsep + old_path
    yield tmp_dir
    os.environ["PATH"] = old_path


# ── Event Bus fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    """Return an ``AsyncMock`` event bus with an async ``publish`` method."""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


# ── Sample agent data ──────────────────────────────────────────────────────


@pytest.fixture
def sample_agent_data() -> dict[str, Any]:
    """Return a dict matching the shape of ``LocalAgent.to_dict()``."""
    return {
        "id": "test-agent-001",
        "name": "Hermes",
        "tool_type": "hermes",
        "version": "2.0.0",
        "status": "running",
        "executable_path": "/usr/local/bin/hermes",
        "working_directory": "/home/user",
        "pid": 12345,
        "capabilities": ["code_generation", "chat"],
        "supported_models": ["gpt-4", "claude-3"],
        "supported_providers": ["openai", "anthropic"],
        "health_score": 0.95,
        "last_seen": "2025-01-01T00:00:00",
        "discovered_at": "2025-01-01T00:00:00",
        "latency_ms": 10.0,
        "memory_mb": 256.0,
        "cpu_percent": 5.0,
        "threads": 4,
        "uptime_seconds": 3600.0,
        "restart_count": 0,
        "configuration": {"config_key": "config_value"},
        "tags": ["test", "local"],
        "error": "",
    }


# ── LocalDiscoveryService fixture ──────────────────────────────────────────


@pytest.fixture
def local_discovery_service() -> tuple["LocalDiscoveryService", MagicMock, MagicMock, MagicMock]:  # noqa: F821
    """Create a ``LocalDiscoveryService`` with all scanners mocked.

    Returns ``(service, mock_scanner, mock_health_monitor, mock_event_bus)``.
    """
    from unittest.mock import AsyncMock, MagicMock

    from agentic_os.core.discovery.local.service import LocalDiscoveryService

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
        mock_hm.untrack_agent = AsyncMock()
        mock_hm_cls.return_value = mock_hm

        mock_cap = MagicMock()
        mock_cap.detect = MagicMock(return_value=())
        mock_cap_cls.return_value = mock_cap

        config = AgentDiscoveryConfig(auto_register=False)
        service = LocalDiscoveryService(
            config=config, scanner=mock_scanner, capability_detector=mock_cap
        )
        yield service, mock_scanner, mock_hm, AsyncMock()
