from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from services.runtime_discovery.models import (
    BindingStatus,
    DiscoveryProviderType,
    Runtime,
    RuntimeBinding,
    RuntimeBindingConfig,
    RuntimeConfiguration,
    RuntimeDiscoveryResult,
    RuntimeHealth,
    RuntimeProfile,
    RuntimeTelemetry,
    RuntimeType,
    RuntimeValidationResult,
)


@runtime_checkable
class RuntimeDiscoveryPort(Protocol):
    async def discover(
        self, runtime_type: RuntimeType | None = None
    ) -> list[RuntimeDiscoveryResult]: ...

    async def discover_all(self) -> list[RuntimeDiscoveryResult]: ...

    async def get_provider_name(self) -> str: ...

    async def get_provider_type(self) -> DiscoveryProviderType: ...


@runtime_checkable
class RuntimeBindingPort(Protocol):
    async def bind(
        self, runtime: Runtime, config: RuntimeBindingConfig | None = None
    ) -> RuntimeBinding: ...

    async def unbind(self, runtime_id: str) -> bool: ...

    async def get_binding(self, runtime_id: str) -> RuntimeBinding | None: ...

    async def list_bindings(self, status: BindingStatus | None = None) -> list[RuntimeBinding]: ...


@runtime_checkable
class RuntimeRegistryPort(Protocol):
    async def register(self, runtime: Runtime) -> Runtime: ...

    async def unregister(self, runtime_id: str) -> bool: ...

    async def get(self, runtime_id: str) -> Runtime | None: ...

    async def find_by_name(self, name: str) -> Runtime | None: ...

    async def find_by_type(self, runtime_type: RuntimeType) -> list[Runtime]: ...

    async def list(self, status: str | None = None) -> list[Runtime]: ...

    async def update(self, runtime: Runtime) -> Runtime: ...


@runtime_checkable
class RuntimeValidationPort(Protocol):
    async def validate(self, runtime: Runtime) -> RuntimeValidationResult: ...

    async def validate_all(self, runtimes: list[Runtime]) -> list[RuntimeValidationResult]: ...

    async def get_validator_name(self) -> str: ...


@runtime_checkable
class RuntimeProfilingPort(Protocol):
    async def profile(self, runtime: Runtime) -> RuntimeProfile: ...

    async def to_execution_profile(self, profile: RuntimeProfile) -> dict[str, Any]: ...


@runtime_checkable
class RuntimeConfigurationPort(Protocol):
    async def get_config(self, runtime_id: str) -> RuntimeConfiguration | None: ...

    async def set_config(self, runtime_id: str, config: RuntimeConfiguration) -> None: ...

    async def reset_config(self, runtime_id: str) -> None: ...

    async def list_configs(self) -> list[RuntimeConfiguration]: ...


@runtime_checkable
class RuntimeHealthPort(Protocol):
    async def check(self, runtime: Runtime) -> RuntimeHealth: ...

    async def check_all(self, runtimes: list[Runtime]) -> list[RuntimeHealth]: ...

    async def get_history(self, runtime_id: str, limit: int = 100) -> list[RuntimeHealth]: ...


@runtime_checkable
class RuntimeTelemetryPort(Protocol):
    async def record(self, runtime_id: str, telemetry: RuntimeTelemetry) -> None: ...

    async def get(self, runtime_id: str) -> RuntimeTelemetry | None: ...

    async def get_all(self) -> list[RuntimeTelemetry]: ...

    async def flush(self) -> None: ...
