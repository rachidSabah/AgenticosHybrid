"""Runtime Execution Engine Core Package — unified runtime orchestration.

This package provides the complete runtime management system:

- **Runtime**: The universal domain model for all executable runtimes
- **RuntimeRegistry**: In-memory thread-safe CRUD for Runtime objects
- **RuntimeController**: Lifecycle orchestration (start/stop/restart/kill)
- **RuntimeBridge**: Maps desktop discovery results to the Runtime model
- **RuntimeManager**: Top-level facade that ties everything together
- **RuntimeEvent**: Typed event payloads with publish helpers
"""

from agentic_os.core.runtime.coordinator import RuntimeCoordinator
from agentic_os.core.runtime.runtime import (
    RestartPolicy,
    Runtime,
    RuntimeCapability,
    RuntimeHealth,
    RuntimeLog,
    RuntimeMetrics,
    RuntimeSession,
    RuntimeStatus,
    RuntimeType,
)
from agentic_os.core.runtime.runtime_bridge import RuntimeBridge
from agentic_os.core.runtime.runtime_controller import RuntimeController
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
from agentic_os.core.runtime.runtime_manager import RuntimeManager
from agentic_os.core.runtime.runtime_registry import RuntimeRegistry

__all__ = [
    "RuntimeCoordinator",
    # Domain model
    "Runtime",
    "RuntimeType",
    "RuntimeStatus",
    "RuntimeHealth",
    "RestartPolicy",
    "RuntimeCapability",
    "RuntimeMetrics",
    "RuntimeSession",
    "RuntimeLog",
    # Registry
    "RuntimeRegistry",
    # Controller
    "RuntimeController",
    # Bridge
    "RuntimeBridge",
    # Top-level facade
    "RuntimeManager",
    # Events
    "RuntimeEvent",
    "RUNTIME_EVENTS",
    "make_runtime_event",
    "publish_runtime_event",
    "publish_runtime_discovered",
    "publish_runtime_registered",
    "publish_runtime_started",
    "publish_runtime_ready",
    "publish_runtime_stopped",
    "publish_runtime_crashed",
    "publish_runtime_restarted",
    "publish_runtime_recovered",
    "publish_runtime_health_changed",
    "publish_runtime_session_created",
    "publish_runtime_session_closed",
    "publish_runtime_heartbeat",
    "publish_runtime_command",
    "publish_runtime_command_failed",
    "publish_runtime_removed",
]
