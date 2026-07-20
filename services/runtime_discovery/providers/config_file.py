from __future__ import annotations

import json
from pathlib import Path

from core.logging import get_logger
from services.runtime_discovery.models import (
    DiscoveryProviderType,
    RuntimeDiscoveryResult,
    RuntimeType,
)

_log = get_logger(__name__)

_CONFIG_FILES: dict[RuntimeType, list[Path]] = {
    RuntimeType.CLAUDE_CODE: [
        Path.home() / ".claude" / "config.json",
        Path.home() / "AppData" / "Local" / "Claude" / "config.json",
    ],
    RuntimeType.CONTINUE: [
        Path.home() / ".continue" / "config.json",
    ],
    RuntimeType.CODEX_CLI: [
        Path.home() / ".codex" / "config.json",
    ],
    RuntimeType.AIDER: [
        Path.home() / ".aider" / "config.yml",
        Path.home() / ".aider.conf.yml",
    ],
    RuntimeType.CLINE: [
        Path.home() / ".cline" / "config.json",
    ],
    RuntimeType.ROO_CODE: [
        Path.home() / ".roo" / "config.json",
    ],
}

_DISPLAY_NAMES: dict[RuntimeType, str] = {
    RuntimeType.CLAUDE_CODE: "Claude Code",
    RuntimeType.CONTINUE: "Continue",
    RuntimeType.CODEX_CLI: "Codex CLI",
    RuntimeType.AIDER: "Aider",
    RuntimeType.CLINE: "Cline",
    RuntimeType.ROO_CODE: "Roo Code",
}

_BINARY_NAMES: dict[RuntimeType, str] = {
    RuntimeType.CLAUDE_CODE: "claude",
    RuntimeType.CONTINUE: "continue",
    RuntimeType.CODEX_CLI: "codex",
    RuntimeType.AIDER: "aider",
    RuntimeType.CLINE: "cline",
    RuntimeType.ROO_CODE: "roo",
}


class ConfigFileProvider:
    provider_type = DiscoveryProviderType.CONFIG_FILE

    async def discover(
        self, runtime_type: RuntimeType | None = None
    ) -> list[RuntimeDiscoveryResult]:
        results: list[RuntimeDiscoveryResult] = []
        types_to_check = [runtime_type] if runtime_type else list(_CONFIG_FILES.keys())
        for rt_type in types_to_check:
            config_paths = _CONFIG_FILES.get(rt_type, [])
            for config_path in config_paths:
                if config_path.exists():
                    version = await self._read_version(config_path, rt_type)
                    results.append(
                        RuntimeDiscoveryResult(
                            runtime_type=rt_type,
                            name=_BINARY_NAMES.get(rt_type, rt_type.value),
                            display_name=_DISPLAY_NAMES.get(rt_type, rt_type.value),
                            version=version,
                            binary_path=str(config_path),
                            executable=str(config_path),
                            source=DiscoveryProviderType.CONFIG_FILE,
                            confidence=0.6,
                            found=True,
                            metadata={"config_path": str(config_path)},
                        )
                    )
                    break
        _log.info("ConfigFileProvider found %d runtimes", len(results))
        return results

    async def discover_all(self) -> list[RuntimeDiscoveryResult]:
        return await self.discover()

    async def get_provider_name(self) -> str:
        return "config_file"

    async def get_provider_type(self) -> DiscoveryProviderType:
        return DiscoveryProviderType.CONFIG_FILE

    async def _read_version(self, config_path: Path, rt_type: RuntimeType) -> str | None:
        try:
            if config_path.suffix == ".json":
                data = json.loads(config_path.read_text(encoding="utf-8"))
                return data.get("version") or data.get("schemaVersion") or None
            elif config_path.suffix in (".yml", ".yaml"):
                try:
                    import yaml

                    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                    return data.get("version") if isinstance(data, dict) else None
                except ImportError:
                    return None
        except Exception:
            return None
        return None
