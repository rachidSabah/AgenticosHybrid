"""Shared pytest fixtures for brain registry tests.

Provides sample BrainRecord instances, mock event buses, and pre-configured
registry/graph instances for the test suite.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agentic_os.domain.brains import BrainRecord, BrainRuntime, BrainStatus, BrainType, BrainVendor
from agentic_os.ports.event_bus import EventBus

# ═══════════════════════════════════════════════════════════════════════
# Sample BrainRecord fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_record() -> BrainRecord:
    """A minimal BrainRecord with default field values."""
    return BrainRecord(
        id="test-1",
        display_name="Test Brain",
        brain_type=BrainType.LOCAL_CLI,
        vendor=BrainVendor.CUSTOM,
        runtime=BrainRuntime.UNKNOWN,
        version="1.0.0",
        status=BrainStatus.DISCOVERED,
    )


@pytest.fixture
def sample_record_openai() -> BrainRecord:
    """A BrainRecord with OpenAI vendor metadata."""
    return BrainRecord(
        id="openai-1",
        display_name="GPT-4o",
        brain_type=BrainType.CLOUD_API,
        vendor=BrainVendor.OPENAI,
        runtime=BrainRuntime.CLOUD,
        version="4.0",
        health=98.5,
        status=BrainStatus.CONNECTED,
        capabilities=("chat", "vision"),
        supported_models=("gpt-4o", "gpt-4o-mini"),
        supported_tools=("function_calling", "structured_output"),
        tags=("production", "primary"),
        priority=10,
    )


@pytest.fixture
def sample_record_ollama() -> BrainRecord:
    """A BrainRecord with Ollama vendor metadata."""
    return BrainRecord(
        id="ollama-1",
        display_name="Llama 3.1",
        brain_type=BrainType.LOCAL_CLI,
        vendor=BrainVendor.OLLAMA,
        runtime=BrainRuntime.PYTHON,
        version="0.1.0",
        status=BrainStatus.IDLE,
        capabilities=("chat", "local_inference"),
        supported_models=("llama3.1", "mistral"),
        tags=("local", "test"),
        priority=5,
    )


@pytest.fixture
def sample_record_anthropic() -> BrainRecord:
    """A BrainRecord with Anthropic vendor metadata (used for graph tests)."""
    return BrainRecord(
        id="anthropic-1",
        display_name="Claude 3.5 Sonnet",
        brain_type=BrainType.CLOUD_API,
        vendor=BrainVendor.ANTHROPIC,
        runtime=BrainRuntime.CLOUD,
        version="3.5",
        status=BrainStatus.CONNECTED,
        capabilities=("chat", "tool_use"),
    )


@pytest.fixture
def sample_record_failed() -> BrainRecord:
    """A BrainRecord in FAILED status (used for lifecycle tests)."""
    return BrainRecord(
        id="failed-1",
        display_name="Failed Brain",
        brain_type=BrainType.CUSTOM,
        vendor=BrainVendor.CUSTOM,
        runtime=BrainRuntime.UNKNOWN,
        version="0.0.1",
        status=BrainStatus.FAILED,
        health=15.0,
        error_count=5,
        last_error="Memory overflow",
    )


@pytest.fixture
def sample_record_unhealthy() -> BrainRecord:
    """A BrainRecord in UNHEALTHY status."""
    return BrainRecord(
        id="unhealthy-1",
        display_name="Unhealthy Brain",
        brain_type=BrainType.CUSTOM,
        vendor=BrainVendor.CUSTOM,
        runtime=BrainRuntime.UNKNOWN,
        version="0.0.1",
        status=BrainStatus.UNHEALTHY,
        health=30.0,
    )


@pytest.fixture
def sample_record_disconnected() -> BrainRecord:
    """A BrainRecord in DISCONNECTED status."""
    return BrainRecord(
        id="disconnected-1",
        display_name="Disconnected Brain",
        brain_type=BrainType.CUSTOM,
        vendor=BrainVendor.CUSTOM,
        runtime=BrainRuntime.UNKNOWN,
        version="0.0.1",
        status=BrainStatus.DISCONNECTED,
    )


@pytest.fixture
def sample_record_paused() -> BrainRecord:
    """A BrainRecord in PAUSED status."""
    return BrainRecord(
        id="paused-1",
        display_name="Paused Brain",
        brain_type=BrainType.CUSTOM,
        vendor=BrainVendor.CUSTOM,
        runtime=BrainRuntime.UNKNOWN,
        version="0.0.1",
        status=BrainStatus.PAUSED,
    )


# ═══════════════════════════════════════════════════════════════════════
# Mock EventBus fixture
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    """An AutoSpecced AsyncMock that satisfies the EventBus protocol."""
    bus = AsyncMock(spec=EventBus)
    bus.start = AsyncMock()
    bus.stop = AsyncMock()
    bus.publish = AsyncMock()
    bus.subscribe = AsyncMock(return_value="sub-1")
    bus.unsubscribe = AsyncMock()
    return bus
