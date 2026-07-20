from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.contracts.execution_engine import EngineConfig, EngineType
from core.logging import get_logger
from services.execution_engine.manager import ExecutionEngineManager
from services.runtime_discovery.models import (
    BindingStatus,
    Runtime,
    RuntimeBinding,
    RuntimeBindingConfig,
    RuntimeStatus,
    RuntimeType,
)

_log = get_logger(__name__)

__all__ = ["RuntimeBindingManager", "BindingNotFoundError"]

_ENGINE_TYPE_MAP: dict[RuntimeType, EngineType] = {
    RuntimeType.CLAUDE_CODE: EngineType.CLAUDE_CODE,
    RuntimeType.GEMINI_CLI: EngineType.GEMINI_CLI,
    RuntimeType.CODEX_CLI: EngineType.CODEX_CLI,
    RuntimeType.HERMES: EngineType.HERMES,
    RuntimeType.OPENHANDS: EngineType.OPENHANDS,
    RuntimeType.AIDER: EngineType.AIDER,
    RuntimeType.CONTINUE: EngineType.CONTINUE,
    RuntimeType.CLINE: EngineType.CLINE,
    RuntimeType.ROO_CODE: EngineType.ROO_CODE,
    RuntimeType.OLLAMA: EngineType.LOCAL,
    RuntimeType.PYTHON: EngineType.LOCAL,
    RuntimeType.NODEJS: EngineType.LOCAL,
    RuntimeType.DOCKER: EngineType.LOCAL,
    RuntimeType.GIT: EngineType.LOCAL,
    RuntimeType.GH_CLI: EngineType.LOCAL,
    RuntimeType.MCP_SERVER: EngineType.CUSTOM,
    RuntimeType.CUSTOM: EngineType.CUSTOM,
}


class BindingNotFoundError(Exception):
    """Raised when a binding is not found."""


class RuntimeBindingManager:
    def __init__(self, engine_manager: ExecutionEngineManager) -> None:
        self._engine_manager = engine_manager
        self._bindings: dict[str, RuntimeBinding] = {}

    async def bind(
        self, runtime: Runtime, config: RuntimeBindingConfig | None = None
    ) -> RuntimeBinding:
        binding_config = config or RuntimeBindingConfig()
        engine_type = _ENGINE_TYPE_MAP.get(runtime.runtime_type, EngineType.CUSTOM)

        binding = RuntimeBinding(
            runtime_id=runtime.runtime_id,
            engine_name=runtime.name,
            adapter_key=engine_type.value,
            status=BindingStatus.BINDING,
            binding_config=binding_config,
        )

        try:
            engine_config = EngineConfig(
                type=engine_type,
                name=runtime.name,
                binary_path=runtime.binary_path,
                version=runtime.version,
                enabled=binding_config.auto_start,
                environment=binding_config.environment_overrides
                if hasattr(binding_config, "environment_overrides")
                else {},
                extra={
                    "runtime_id": runtime.runtime_id,
                    "auto_register": binding_config.auto_register,
                    **binding_config.adapter_params,
                },
            )

            if binding_config.auto_register:
                await self._engine_manager.register_engine(engine_config)

            binding.status = BindingStatus.BOUND
            binding.bound_at = datetime.now(UTC)
            runtime.status = RuntimeStatus.BOUND
            _log.info("Runtime bound", name=runtime.name, engine=engine_type.value)

        except Exception as e:
            binding.status = BindingStatus.FAILED
            binding.error = str(e)
            _log.warning("Binding failed", name=runtime.name, error=str(e))

        self._bindings[runtime.runtime_id] = binding
        runtime.binding = binding
        return binding

    async def unbind(self, runtime_id: str) -> bool:
        binding = self._bindings.pop(runtime_id, None)
        if not binding:
            return False
        try:
            if binding.engine_name:
                await self._engine_manager.unregister_engine(binding.engine_name)
            binding.status = BindingStatus.UNBOUND
            _log.info("Runtime unbound", name=binding.engine_name)
            return True
        except Exception as e:
            _log.warning("Unbind error", name=binding.engine_name, error=str(e))
            return False

    def get_binding(self, runtime_id: str) -> RuntimeBinding | None:
        return self._bindings.get(runtime_id)

    def list_bindings(self, status: BindingStatus | None = None) -> list[RuntimeBinding]:
        bindings = list(self._bindings.values())
        if status:
            bindings = [b for b in bindings if b.status == status]
        return bindings
