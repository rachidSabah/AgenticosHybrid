"""Automatic Runtime Discovery & Binding Framework — v0.5.1

AgenticOS automatically discovers every compatible runtime, provider,
execution engine, SDK, MCP server and development tool installed on the
machine. Discovery is continuous, event-driven and self-healing. The
platform automatically binds discovered runtimes into the Execution
Engine Framework without requiring manual configuration.

Core subsystems:
  - RuntimeDiscoveryManager: top-level facade orchestrating the full
    discover → validate → profile → bind → register pipeline
  - RuntimeRegistry: CRUD registry for discovered runtimes
  - RuntimeBindingManager: binds discovered runtimes into the Execution
    Engine Framework (ExecutionEngineManager)
  - ValidationPipeline: validates executable integrity, version,
    capabilities, permissions, health
  - ProfilingEngine: auto-generates runtime profiles (capabilities,
    performance, resource footprint, latency estimates)
  - RuntimeHealthMonitor: periodic health checks, status tracking,
    degradation detection
  - RuntimeConfigurationManager: persistent per-runtime configuration
  - RuntimeCache: TTL-based discovery result cache
  - RuntimeDiscoveryScheduler: periodic auto-discovery scheduling
  - RuntimeTelemetryCollector: execution telemetry tracking

Discovery providers (via services/execution_engine/discovery.py):
  PATH, Filesystem, Environment Variables, Windows Registry, WSL, Docker,
  Known Installation Directories, Configuration Files, VS Code, JetBrains

Supported discoverable runtimes (17 types):
  Claude Code, Gemini CLI, Codex CLI, Hermes, OpenHands, Aider, Continue,
  Cline, Roo Code, Ollama, Python, Node.js, Docker, Git, GitHub CLI,
  MCP Servers, Custom

EventBus integration (32 runtime.* events):
  runtime.discovery.*, runtime.binding.*, runtime.validation.*,
  runtime.health.*, runtime.profile.*, runtime.configuration.*,
  runtime.telemetry.*, runtime.registry.*
"""

from __future__ import annotations

from services.runtime_discovery.binding import RuntimeBindingManager
from services.runtime_discovery.cache import RuntimeCache
from services.runtime_discovery.configuration import RuntimeConfigurationManager
from services.runtime_discovery.events import RuntimeEventPublisher
from services.runtime_discovery.health_monitor import RuntimeHealthMonitor
from services.runtime_discovery.manager import RuntimeDiscoveryManager
from services.runtime_discovery.models import (
    BindingStatus,
    DiscoveryProviderType,
    HealthStatus,
    Runtime,
    RuntimeBinding,
    RuntimeBindingConfig,
    RuntimeCacheEntry,
    RuntimeCapability,
    RuntimeConfiguration,
    RuntimeDiscoveryResult,
    RuntimeEvent,
    RuntimeHealth,
    RuntimeMetadata,
    RuntimeProfile,
    RuntimeStatus,
    RuntimeTelemetry,
    RuntimeType,
    RuntimeValidation,
    RuntimeValidationResult,
    ValidationStatus,
)
from services.runtime_discovery.ports import (
    RuntimeBindingPort,
    RuntimeConfigurationPort,
    RuntimeDiscoveryPort,
    RuntimeHealthPort,
    RuntimeProfilingPort,
    RuntimeRegistryPort,
    RuntimeTelemetryPort,
    RuntimeValidationPort,
)
from services.runtime_discovery.profiling import ProfilingEngine
from services.runtime_discovery.registry import RuntimeRegistry
from services.runtime_discovery.scheduler import RuntimeDiscoveryScheduler
from services.runtime_discovery.telemetry import RuntimeTelemetryCollector
from services.runtime_discovery.validation import ValidationPipeline

__all__ = [
    "BindingStatus",
    "DiscoveryProviderType",
    "HealthStatus",
    "ProfilingEngine",
    "Runtime",
    "RuntimeBinding",
    "RuntimeBindingConfig",
    "RuntimeBindingManager",
    "RuntimeBindingPort",
    "RuntimeCache",
    "RuntimeCacheEntry",
    "RuntimeCapability",
    "RuntimeConfiguration",
    "RuntimeConfigurationManager",
    "RuntimeConfigurationPort",
    "RuntimeDiscoveryManager",
    "RuntimeDiscoveryPort",
    "RuntimeDiscoveryResult",
    "RuntimeDiscoveryScheduler",
    "RuntimeEvent",
    "RuntimeEventPublisher",
    "RuntimeHealth",
    "RuntimeHealthMonitor",
    "RuntimeHealthPort",
    "RuntimeMetadata",
    "RuntimeProfile",
    "RuntimeProfilingPort",
    "RuntimeRegistry",
    "RuntimeRegistryPort",
    "RuntimeStatus",
    "RuntimeTelemetry",
    "RuntimeTelemetryCollector",
    "RuntimeTelemetryPort",
    "RuntimeType",
    "RuntimeValidation",
    "RuntimeValidationPort",
    "RuntimeValidationResult",
    "RuntimeConfiguration",
    "ValidationPipeline",
    "ValidationStatus",
]
