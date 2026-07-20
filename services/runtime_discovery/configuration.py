from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logging import get_logger
from services.runtime_discovery.models import RuntimeConfiguration

_log = get_logger(__name__)

__all__ = ["RuntimeConfigurationManager"]

_CONFIG_DIR = Path.home() / ".config" / "aaios" / "runtimes"
_CONFIG_EXT = ".json"


class RuntimeConfigurationManager:
    def __init__(self, config_dir: str | Path | None = None) -> None:
        self._config_dir = Path(config_dir) if config_dir else _CONFIG_DIR
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._in_memory: dict[str, RuntimeConfiguration] = {}

    async def get_config(self, runtime_id: str) -> RuntimeConfiguration | None:
        if runtime_id in self._in_memory:
            return self._in_memory[runtime_id]
        config_file = self._config_dir / f"{runtime_id}{_CONFIG_EXT}"
        if config_file.exists():
            try:
                data = json.loads(config_file.read_text(encoding="utf-8"))
                config = RuntimeConfiguration(**data)
                self._in_memory[runtime_id] = config
                return config
            except Exception as e:
                _log.warning("Failed to load config for %s: %s", runtime_id, e)
        return None

    async def set_config(self, runtime_id: str, config: RuntimeConfiguration) -> None:
        config.updated_at = datetime.now(UTC)
        self._in_memory[runtime_id] = config
        config_file = self._config_dir / f"{runtime_id}{_CONFIG_EXT}"
        try:
            config_file.write_text(
                json.dumps(config.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            _log.warning("Failed to save config for %s: %s", runtime_id, e)

    async def reset_config(self, runtime_id: str) -> None:
        self._in_memory.pop(runtime_id, None)
        config_file = self._config_dir / f"{runtime_id}{_CONFIG_EXT}"
        if config_file.exists():
            config_file.unlink()

    async def list_configs(self) -> list[RuntimeConfiguration]:
        configs = list(self._in_memory.values())
        if self._config_dir.exists():
            for f in self._config_dir.glob(f"*{_CONFIG_EXT}"):
                runtime_id = f.stem
                if runtime_id not in self._in_memory:
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        config = RuntimeConfiguration(**data)
                        configs.append(config)
                        self._in_memory[runtime_id] = config
                    except Exception:
                        pass
        return configs

    async def update_config(
        self, runtime_id: str, updates: dict[str, Any]
    ) -> RuntimeConfiguration | None:
        config = await self.get_config(runtime_id)
        if not config:
            config = RuntimeConfiguration(runtime_id=runtime_id)
        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)
        await self.set_config(runtime_id, config)
        return config
