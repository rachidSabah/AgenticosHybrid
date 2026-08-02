"""Desktop Configuration Manager — manages desktop preferences."""

from __future__ import annotations

from typing import Any

from agentic_os.domain.desktop import DesktopConfig, ThemeMode
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.config")


class DesktopConfigurationManager:
    """In-memory desktop configuration manager. Persists via local database."""

    def __init__(self) -> None:
        self._config = DesktopConfig()

    async def get_config(self) -> DesktopConfig:
        return self._config

    async def update_config(self, config: DesktopConfig) -> DesktopConfig:
        self._config = config
        log.info("Desktop config updated")
        return self._config

    async def reset_config(self) -> DesktopConfig:
        self._config = DesktopConfig()
        return self._config

    async def set_theme(self, theme: ThemeMode) -> None:
        self._config.theme = theme

    async def get_theme(self) -> ThemeMode:
        return self._config.theme

    async def get_setting(self, key: str) -> Any:
        return getattr(self._config, key, None)

    async def set_setting(self, key: str, value: Any) -> None:
        if hasattr(self._config, key):
            setattr(self._config, key, value)
