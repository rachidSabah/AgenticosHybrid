"""Brain Registry & Constellation Management — Phase 6.2.

Every detected or registered AI capability — local CLI, cloud API, MCP server,
internal orchestrator — is managed as a :class:`BrainRecord` in the registry.
The package provides lifecycle management, health monitoring, capability
analysis, relationship graphing, and runtime bridges to external CLI brains.
"""

from __future__ import annotations

from agentic_os.core.brains.bridge import BrainDiscoveryBridge
from agentic_os.core.brains.capabilities import BrainCapabilityAnalyzer
from agentic_os.core.brains.catalog import BrainCatalog
from agentic_os.core.brains.graph import BrainRelationshipGraph
from agentic_os.core.brains.health import BrainHealthMonitor
from agentic_os.core.brains.lifecycle import BrainLifecycleManager
from agentic_os.core.brains.manager import BrainManager
from agentic_os.core.brains.registry import BrainRegistry
from agentic_os.core.brains.runtime_bridge import RuntimeBridge
from agentic_os.core.brains.stats import BrainStatistics
from agentic_os.core.brains.windows_detector import detect_local_windows, detect_remote_brains

__all__ = [
    "BrainRegistry",
    "BrainManager",
    "BrainCatalog",
    "BrainLifecycleManager",
    "BrainCapabilityAnalyzer",
    "BrainHealthMonitor",
    "BrainRelationshipGraph",
    "BrainStatistics",
    "BrainDiscoveryBridge",
    "RuntimeBridge",
    "detect_local_windows",
    "detect_remote_brains",
]
