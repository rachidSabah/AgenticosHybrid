"""
Discovery Framework — Phase 4, Milestone 2 + Phase 6.1 Local Agent Discovery.

Automatic runtime discovery, validation, profiling, and binding subsystem.
Wraps the M1 DiscoveryEngine to add profiles, caching, scheduling, telemetry,
validation, profiling, and hot-reload.  Phase 6.1 adds local agent discovery
(:mod:`~.local`) for AI tools installed on the local workstation.
"""

from agentic_os.core.discovery.cache import DiscoveryCache
from agentic_os.core.discovery.config import DiscoveryConfiguration
from agentic_os.core.discovery.framework import DiscoveryFramework
from agentic_os.core.discovery.local import (
    AgentScanner,
    CapabilityDetector,
    EnvironmentDetector,
    ExecutableLocator,
    FilesystemScanner,
    HealthMonitor,
    LocalDiscoveryService,
    PathScanner,
    ProcessScanner,
    RegistryScanner,
    VersionDetector,
)
from agentic_os.core.discovery.profiling import ProfilingEngine
from agentic_os.core.discovery.publisher import DiscoveryEventPublisher
from agentic_os.core.discovery.registry import DiscoveryRegistry
from agentic_os.core.discovery.scheduler import DiscoveryScheduler
from agentic_os.core.discovery.telemetry import DiscoveryTelemetry
from agentic_os.core.discovery.validation import ValidationPipeline

__all__ = [
    "DiscoveryFramework",
    "DiscoveryRegistry",
    "DiscoveryCache",
    "DiscoveryTelemetry",
    "DiscoveryConfiguration",
    "DiscoveryScheduler",
    "DiscoveryEventPublisher",
    "ValidationPipeline",
    "ProfilingEngine",
    # Phase 6.1 — Local Agent Discovery
    "AgentScanner",
    "CapabilityDetector",
    "EnvironmentDetector",
    "ExecutableLocator",
    "FilesystemScanner",
    "HealthMonitor",
    "LocalDiscoveryService",
    "PathScanner",
    "ProcessScanner",
    "RegistryScanner",
    "VersionDetector",
]
