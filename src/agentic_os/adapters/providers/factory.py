"""Provider factory — builds a runtime adapter from a ProviderConfig.

Used by the provider management UI/API so that saving a config also yields a
working adapter registered in the manager + registry. Secrets are pulled from
the ApiKeyVault rather than the config payload.

Auto-registration bridge: the factory now recognises agent CLI kinds
(claude_code, hermes, aider, codex, ollama) so discovery findings can be
converted into live providers.
"""

from __future__ import annotations

import shutil

from agentic_os.adapters.providers.claude_code import ClaudeCodeProvider
from agentic_os.adapters.providers.hermes import HermesProvider
from agentic_os.adapters.providers.mock import MockProvider
from agentic_os.adapters.providers.openai_compatible import OpenAICompatibleProvider
from agentic_os.domain.provider_mgmt import ProviderConfig
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.provider import ProviderAdapter

log = get_logger("factory")


async def build_adapter(config: ProviderConfig, get_key) -> ProviderAdapter:
    """Construct a concrete adapter for a config. ``get_key`` resolves secrets."""
    kind = config.kind
    name = config.name

    if kind == "mock":
        return MockProvider(name=name, kind=kind)

    if kind == "claude_code":
        bin_path = config.base_url or "claude"
        api_key = await get_key(name) or ""
        log.info("factory.build_claude_code", name=name, bin_path=bin_path)
        return ClaudeCodeProvider(bin_path=bin_path, api_key=api_key)

    if kind == "hermes":
        bin_path = config.base_url or "hermes"
        api_key = await get_key(name) or ""
        log.info("factory.build_hermes", name=name, bin_path=bin_path)
        return HermesProvider(bin_path=bin_path, api_key=api_key)

    if kind == "openai_compatible":
        api_key = await get_key(name) or ""
        return OpenAICompatibleProvider(
            name=name,
            base_url=config.base_url,
            model=config.default_model,
            api_key=api_key,
        )

    # Strategy-based CLI agents (codex, opencode, aider, antigravity/agy,
    # gemini_cli, ollama, ...). Each has its own correct invocation flags and
    # API-key env var — handled by the per-kind execution strategy. This is the
    # real path for auto-bound agents; previously they were forced through
    # ClaudeCodeProvider (wrong `claude -p` flags + only ANTHROPIC key), which
    # made every non-claude agent fail auth / mis-invoke its CLI.
    from agentic_os.adapters.providers.strategies import (
        ProviderAdapterConfig,
        StrategyBasedProvider,
    )

    cli_kinds = {
        "codex",
        "opencode",
        "aider",
        "antigravity",
        "gemini_cli",
        "ollama",
        "nvidia_nim",
    }
    binary_name = kind.replace("_", "-")  # e.g. aider, codex, ollama, agy
    if kind in cli_kinds or shutil.which(binary_name) or shutil.which(kind):
        resolved_bin = binary_name if shutil.which(binary_name) else (kind if shutil.which(kind) else binary_name)
        api_key = await get_key(name) or ""
        log.info("factory.strategy_bind_cli", name=name, kind=kind, binary=resolved_bin)
        return StrategyBasedProvider(
            ProviderAdapterConfig(
                bin_path=resolved_bin,
                name=name,
                kind=kind,
                capabilities=list(config.capabilities) if hasattr(config, "capabilities") else [],
                api_key=api_key,
            )
        )

    # Unknown kinds fall back to a mock so the system stays operable.
    log.warning("factory.unknown_kind_fallback", name=name, kind=kind)
    return MockProvider(name=name, kind=kind)
