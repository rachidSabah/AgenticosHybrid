from __future__ import annotations

import json
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

_VSCODE_EXTENSION_DIRS: list[Path] = []

if platform.system() == "Windows":
    _VSCODE_EXTENSION_DIRS = [
        Path(os.environ.get("USERPROFILE", "")) / ".vscode" / "extensions",
        Path(os.environ.get("USERPROFILE", "")) / ".vscode-insiders" / "extensions",
    ]
else:
    _VSCODE_EXTENSION_DIRS = [
        Path.home() / ".vscode" / "extensions",
        Path.home() / ".vscode-insiders" / "extensions",
    ]

_AI_EXTENSIONS: dict[str, tuple[str, RuntimeType]] = {
    "continue.continue": ("continue", RuntimeType.CONTINUE),
    "github.copilot": ("copilot", RuntimeType.CUSTOM),
    "github.copilot-chat": ("copilot-chat", RuntimeType.CUSTOM),
    "tabnine.tabnine-vscode": ("tabnine", RuntimeType.CUSTOM),
}

_DISPLAY_NAMES: dict[RuntimeType, str] = {
    RuntimeType.CONTINUE: "Continue",
    RuntimeType.CUSTOM: "AI Extension",
}


class VSCodeDiscoveryProvider:
    provider_type = DiscoveryProviderType.VSCODE

    async def discover(
        self, runtime_type: RuntimeType | None = None
    ) -> list[RuntimeDiscoveryResult]:
        results: list[RuntimeDiscoveryResult] = []
        for ext_dir in _VSCODE_EXTENSION_DIRS:
            if not ext_dir.exists():
                continue
            for ext_folder in ext_dir.iterdir():
                if not ext_folder.is_dir():
                    continue
                ext_id = ext_folder.name
                ext_info = _AI_EXTENSIONS.get(ext_id)
                if ext_info is None:
                    continue
                binary_name, rt_type = ext_info
                if runtime_type is not None and rt_type != runtime_type:
                    continue
                version = await self._read_extension_version(ext_folder)
                results.append(
                    RuntimeDiscoveryResult(
                        runtime_type=rt_type,
                        name=binary_name,
                        display_name=_DISPLAY_NAMES.get(rt_type, ext_id),
                        version=version,
                        binary_path=str(ext_folder),
                        executable=str(ext_folder),
                        source=DiscoveryProviderType.VSCODE,
                        confidence=0.7,
                        found=True,
                        metadata={"extension_id": ext_id, "vscode_dir": str(ext_dir)},
                    )
                )
        _log.info("VSCodeDiscoveryProvider found %d runtimes", len(results))
        return results

    async def discover_all(self) -> list[RuntimeDiscoveryResult]:
        return await self.discover()

    async def get_provider_name(self) -> str:
        return "vscode"

    async def get_provider_type(self) -> DiscoveryProviderType:
        return DiscoveryProviderType.VSCODE

    async def _read_extension_version(self, ext_folder: Path) -> str | None:
        pkg_json = ext_folder / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
                return data.get("version")
            except Exception:
                pass
        return None
