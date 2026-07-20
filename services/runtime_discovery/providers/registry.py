from __future__ import annotations

import platform

from core.logging import get_logger
from services.runtime_discovery.models import (
    DiscoveryProviderType,
    RuntimeDiscoveryResult,
    RuntimeType,
)

_log = get_logger(__name__)

_REGISTRY_PATHS: dict[RuntimeType, list[str]] = {
    RuntimeType.PYTHON: [
        r"SOFTWARE\Python\PythonCore",
        r"SOFTWARE\Wow6432Node\Python\PythonCore",
    ],
    RuntimeType.NODEJS: [
        r"SOFTWARE\Node.js",
    ],
    RuntimeType.DOCKER: [
        r"SOFTWARE\Docker Inc.",
    ],
    RuntimeType.GIT: [
        r"SOFTWARE\GitForWindows",
    ],
}

_DISPLAY_NAMES: dict[RuntimeType, str] = {
    RuntimeType.PYTHON: "Python",
    RuntimeType.NODEJS: "Node.js",
    RuntimeType.DOCKER: "Docker",
    RuntimeType.GIT: "Git",
}

_BINARY_NAMES: dict[RuntimeType, str] = {
    RuntimeType.PYTHON: "python",
    RuntimeType.NODEJS: "node",
    RuntimeType.DOCKER: "docker",
    RuntimeType.GIT: "git",
}


class RegistryDiscoveryProvider:
    provider_type = DiscoveryProviderType.REGISTRY

    async def discover(  # noqa: E501
        self, runtime_type: RuntimeType | None = None
    ) -> list[RuntimeDiscoveryResult]:
        results: list[RuntimeDiscoveryResult] = []
        if platform.system() != "Windows":
            _log.info("RegistryDiscoveryProvider: not on Windows, skipping")
            return results

        try:
            import winreg
        except ImportError:
            _log.info("RegistryDiscoveryProvider: winreg not available")
            return results

        types_to_check = [runtime_type] if runtime_type else list(_REGISTRY_PATHS.keys())
        for rt_type in types_to_check:
            paths = _REGISTRY_PATHS.get(rt_type, [])
            for reg_path in paths:
                try:
                    hkey = winreg.HKEY_LOCAL_MACHINE
                    with winreg.OpenKey(hkey, reg_path) as key:
                        subkey_count = winreg.QueryInfoKey(key)[0]
                        if subkey_count > 0:
                            name, _ = winreg.EnumKey(key, 0)
                            install_path = None
                            try:
                                with winreg.OpenKey(key, f"{name}\\InstallPath") as ip_key:
                                    install_path, _ = winreg.QueryValueEx(ip_key, "")
                            except Exception:
                                pass
                            results.append(
                                RuntimeDiscoveryResult(
                                    runtime_type=rt_type,
                                    name=_BINARY_NAMES.get(rt_type, rt_type.value),
                                    display_name=_DISPLAY_NAMES.get(rt_type, rt_type.value),
                                    version=name,
                                    binary_path=install_path,
                                    executable=install_path,
                                    source=DiscoveryProviderType.REGISTRY,
                                    confidence=0.7,
                                    found=True,
                                    metadata={"registry_path": reg_path, "version_key": name},
                                )
                            )
                except Exception:
                    continue

        _log.info("RegistryDiscoveryProvider found %d runtimes", len(results))
        return results

    async def discover_all(self) -> list[RuntimeDiscoveryResult]:
        return await self.discover()

    async def get_provider_name(self) -> str:
        return "registry"

    async def get_provider_type(self) -> DiscoveryProviderType:
        return DiscoveryProviderType.REGISTRY
