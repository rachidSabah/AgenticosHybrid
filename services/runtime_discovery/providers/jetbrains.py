from __future__ import annotations

import os
import platform
from pathlib import Path

from core.logging import get_logger
from services.runtime_discovery.models import (
    DiscoveryProviderType,
    RuntimeDiscoveryResult,
    RuntimeType,
)

_log = get_logger(__name__)

_JETBRAINS_CONFIG_DIRS: list[Path] = []

if platform.system() == "Windows":
    _JETBRAINS_CONFIG_DIRS = [
        Path(os.environ.get("APPDATA", "")) / "JetBrains",
    ]
elif platform.system() == "Darwin":
    _JETBRAINS_CONFIG_DIRS = [
        Path.home() / "Library" / "Application Support" / "JetBrains",
    ]
else:
    _JETBRAINS_CONFIG_DIRS = [
        Path.home() / ".config" / "JetBrains",
    ]

_AI_PLUGIN_PATTERNS: list[str] = [
    "ai-assistant",
    "continue",
    "github-copilot",
]

_PLUGIN_TO_TYPE: dict[str, RuntimeType] = {
    "continue": RuntimeType.CONTINUE,
}

_PLUGIN_DISPLAY: dict[str, str] = {
    "continue": "Continue",
    "ai-assistant": "JetBrains AI Assistant",
    "github-copilot": "GitHub Copilot",
}


class JetBrainsDiscoveryProvider:
    provider_type = DiscoveryProviderType.JETBRAINS

    async def discover(  # noqa: E501
        self, runtime_type: RuntimeType | None = None
    ) -> list[RuntimeDiscoveryResult]:
        results: list[RuntimeDiscoveryResult] = []
        for config_dir in _JETBRAINS_CONFIG_DIRS:
            if not config_dir.exists():
                continue
            for child in config_dir.iterdir():
                if not child.is_dir():
                    continue
                plugins_dir = child / "plugins"
                if not plugins_dir.exists():
                    continue
                for plugin_pattern in _AI_PLUGIN_PATTERNS:
                    if (
                        runtime_type is not None
                        and _PLUGIN_TO_TYPE.get(plugin_pattern, RuntimeType.CUSTOM) != runtime_type
                    ):  # noqa: E501
                        continue
                    plugin_path = plugins_dir / plugin_pattern
                    if plugin_path.exists():
                        rt_type = _PLUGIN_TO_TYPE.get(plugin_pattern, RuntimeType.CUSTOM)
                        results.append(
                            RuntimeDiscoveryResult(
                                runtime_type=rt_type,
                                name=plugin_pattern,
                                display_name=_PLUGIN_DISPLAY.get(plugin_pattern, plugin_pattern),
                                binary_path=str(plugin_path),
                                executable=str(plugin_path),
                                source=DiscoveryProviderType.JETBRAINS,
                                confidence=0.6,
                                found=True,
                                metadata={
                                    "ide_config_dir": str(child),
                                    "plugin_path": str(plugin_path),
                                    "ide_name": child.name,
                                },
                            )
                        )
        _log.info("JetBrainsDiscoveryProvider found %d runtimes", len(results))
        return results

    async def discover_all(self) -> list[RuntimeDiscoveryResult]:
        return await self.discover()

    async def get_provider_name(self) -> str:
        return "jetbrains"

    async def get_provider_type(self) -> DiscoveryProviderType:
        return DiscoveryProviderType.JETBRAINS
