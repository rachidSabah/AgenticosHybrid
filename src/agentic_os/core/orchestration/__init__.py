"""Core orchestration package — multi-agent orchestration and swarm intelligence."""

from agentic_os.core.orchestration.communication import CommunicationBus
from agentic_os.core.orchestration.config import OrchestrationConfiguration
from agentic_os.core.orchestration.coordination import CoordinationEngine
from agentic_os.core.orchestration.framework import OrchestrationFramework
from agentic_os.core.orchestration.intelligence import SwarmIntelligenceEngine
from agentic_os.core.orchestration.publisher import OrchestrationEventPublisher
from agentic_os.core.orchestration.registry import OrchestrationAgentRegistry
from agentic_os.core.orchestration.strategies.decomposition import (
    LLMDecomposition,
    RuleBasedDecomposition,
    TemplateBasedDecomposition,
)
from agentic_os.core.orchestration.swarm import SwarmManager
from agentic_os.core.orchestration.task_orchestrator import TaskOrchestrator
from agentic_os.core.orchestration.telemetry import OrchestrationTelemetry

__all__ = [
    "OrchestrationFramework",
    "OrchestrationAgentRegistry",
    "SwarmManager",
    "TaskOrchestrator",
    "CoordinationEngine",
    "SwarmIntelligenceEngine",
    "CommunicationBus",
    "OrchestrationTelemetry",
    "OrchestrationEventPublisher",
    "OrchestrationConfiguration",
    "RuleBasedDecomposition",
    "TemplateBasedDecomposition",
    "LLMDecomposition",
]
