"""Provider factory — builds a runtime adapter from a ProviderConfig.

Used by the provider management UI/API so that saving a config also yields a
working adapter registered in the manager + registry. Secrets are pulled from
the ApiKeyVault rather than the config payload.
"""

from __future__ import annotations

from agentic_os.adapters.providers.mock import MockProvider
from agentic_os.adapters.providers.openai_compatible import OpenAICompatibleProvider
from agentic_os.domain.provider_mgmt import ProviderConfig
from agentic_os.ports.provider import ProviderAdapter


async def build_adapter(config: ProviderConfig, get_key) -> ProviderAdapter:
    """Construct a concrete adapter for a config. ``get_key`` resolves secrets."""
    kind = config.kind
    if kind == "mock":
        return MockProvider(name=config.name, kind=config.kind)
    if kind == "openai_compatible":
        api_key = await get_key(config.name) or ""
        return OpenAICompatibleProvider(
            name=config.name,
            base_url=config.base_url,
            model=config.default_model,
            api_key=api_key,
        )
    # Unknown kinds fall back to a mock so the system stays operable.
    return MockProvider(name=config.name, kind=config.kind)
