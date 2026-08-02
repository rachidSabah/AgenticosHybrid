"""Local agent discovery service — Phase 6.1.

Provides local workstation AI agent detection via path scanning,
Windows Registry scanning, process scanning, environment variable
detection, filesystem scanning, and periodic health monitoring.

All scanners feed into :class:`AgentScanner`, which is orchestrated
by :class:`LocalDiscoveryService`.
"""

from agentic_os.core.discovery.local.capability_detector import CapabilityDetector
from agentic_os.core.discovery.local.env_detector import EnvironmentDetector
from agentic_os.core.discovery.local.filesystem_scanner import FilesystemScanner
from agentic_os.core.discovery.local.health_monitor import HealthMonitor
from agentic_os.core.discovery.local.path_scanner import ExecutableLocator, PathScanner
from agentic_os.core.discovery.local.process_scanner import ProcessScanner
from agentic_os.core.discovery.local.registry_scanner import RegistryScanner
from agentic_os.core.discovery.local.scanner import AgentScanner
from agentic_os.core.discovery.local.service import LocalDiscoveryService
from agentic_os.core.discovery.local.version_detector import VersionDetector

__all__ = [
    "ExecutableLocator",
    "PathScanner",
    "RegistryScanner",
    "ProcessScanner",
    "EnvironmentDetector",
    "VersionDetector",
    "CapabilityDetector",
    "FilesystemScanner",
    "HealthMonitor",
    "AgentScanner",
    "LocalDiscoveryService",
]
