"""Provider Manager + Model Manager implementation.

Implements :class:`ProviderManager` and :class:`ModelManager`. The manager owns
the provider adapters (replacing the thin Phase-1 ``ProviderRegistry`` role for
management concerns) and the catalog of models with their economics. It is the
single source of truth for "what providers/models exist and how to reach them".
"""

from __future__ import annotations

from agentic_os.domain.agent import ProviderInfo
from agentic_os.domain.provider_mgmt import ProviderConfig
from agentic_os.ports.provider import ProviderAdapter as _PA
from agentic_os.ports.provider_management import (
    ModelInfo,
    ProviderAdapter,
)


class ProviderManagerImpl:
    def __init__(self) -> None:
        self._providers: dict[str, _PA] = {}
        self._models: dict[str, ModelInfo] = {}  # key: provider::model
        self._configs: dict[str, ProviderConfig] = {}

    # ── providers ──
    def register(self, adapter: ProviderAdapter) -> None:
        self._providers[adapter.info.name] = adapter

    def get(self, name: str) -> _PA | None:
        return self._providers.get(name)

    def list_providers(self) -> list[ProviderInfo]:
        return [a.info for a in self._providers.values()]

    def set_config(self, config: ProviderConfig) -> None:
        self._configs[config.name] = config

    def get_config(self, name: str) -> ProviderConfig | None:
        return self._configs.get(name)

    def list_configs(self) -> list[ProviderConfig]:
        return list(self._configs.values())

    # ── models ──
    def register_model(self, model: ModelInfo) -> None:
        self._models[f"{model.provider}::{model.id}"] = model

    def list_models(self, provider: str | None = None) -> list[ModelInfo]:
        if provider is None:
            return list(self._models.values())
        return [m for m in self._models.values() if m.provider == provider]

    def get_model(self, provider: str, model_id: str) -> ModelInfo | None:
        return self._models.get(f"{provider}::{model_id}")


class ModelManagerImpl:
    def __init__(self, manager: ProviderManagerImpl) -> None:
        self._manager = manager

    def models_for(self, provider: str) -> list[ModelInfo]:
        return self._manager.list_models(provider)

    def get_model(self, provider: str, model_id: str) -> ModelInfo | None:
        return self._manager.get_model(provider, model_id)

    def cheapest(self, capability: str) -> ModelInfo | None:
        matches = [m for m in self._manager.list_models() if capability in m.capabilities]
        if not matches:
            return None
        return min(matches, key=lambda m: m.input_cost_per_1k + m.output_cost_per_1k)

    def by_latency(self, capability: str) -> list[ModelInfo]:
        # Latency is not known statically; return capability matches ordered by
        # cost as a stable proxy until the health monitor supplies live data.
        matches = [m for m in self._manager.list_models() if capability in m.capabilities]
        return sorted(matches, key=lambda m: m.input_cost_per_1k + m.output_cost_per_1k)
