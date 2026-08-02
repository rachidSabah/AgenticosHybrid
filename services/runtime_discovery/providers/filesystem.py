from __future__ import annotations

import os

from core.logging import get_logger
from services.runtime_discovery.models import (
    DiscoveryProviderType,
    RuntimeDiscoveryResult,
    RuntimeType,
)

_log = get_logger(__name__)

_KNOWN_PATHS: dict[str, list[str]] = {
    "python": [
        r"C:\Python*",
        r"C:\Program Files\Python*",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
    ],
    "node": [
        r"C:\Program Files\nodejs",
        "/usr/local/bin/node",
        "/usr/bin/node",
    ],
    "docker": [
        r"C:\Program Files\Docker\Docker",
        "/usr/bin/docker",
        "/usr/local/bin/docker",
    ],
    "git": [
        r"C:\Program Files\Git\bin",
        "/usr/bin/git",
        "/usr/local/bin/git",
    ],
}

_BINARY_TO_TYPE: dict[str, RuntimeType] = {
    "python": RuntimeType.PYTHON,
    "node": RuntimeType.NODEJS,
    "docker": RuntimeType.DOCKER,
    "git": RuntimeType.GIT,
}


class FilesystemDiscoveryProvider:
    provider_type = DiscoveryProviderType.FILESYSTEM

    async def discover(
        self, runtime_type: RuntimeType | None = None
    ) -> list[RuntimeDiscoveryResult]:
        results: list[RuntimeDiscoveryResult] = []
        for binary_name, paths in _KNOWN_PATHS.items():
            rt_type = _BINARY_TO_TYPE.get(binary_name)
            if rt_type is None or (runtime_type is not None and rt_type != runtime_type):
                continue
            for pattern in paths:
                expanded = pattern.replace("*", "")
                if os.path.exists(expanded):
                    results.append(
                        RuntimeDiscoveryResult(
                            runtime_type=rt_type,
                            name=binary_name,
                            display_name=binary_name.capitalize(),
                            binary_path=expanded,
                            executable=expanded,
                            source=DiscoveryProviderType.FILESYSTEM,
                            confidence=0.6,
                            found=True,
                        )
                    )
                    break
        _log.info("FilesystemDiscoveryProvider found %d runtimes", len(results))
        return results

    async def discover_all(self) -> list[RuntimeDiscoveryResult]:
        return await self.discover()

    async def get_provider_name(self) -> str:
        return "filesystem"

    async def get_provider_type(self) -> DiscoveryProviderType:
        return DiscoveryProviderType.FILESYSTEM
