"""Cargo Install Discovery Provider.

Scans Cargo-installed binaries for AI coding assistants.
"""
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.cargo")


@dataclass
class CargoDiscovery(DiscoveryProvider):
    """Discovers AI coding assistants installed via cargo install."""

    _known_binaries: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {"name": "goose", "binary": "goose", "engine": EngineType.GOOSE,
             "caps": [EngineCapability.CODING, EngineCapability.PLANNING, EngineCapability.TERMINAL]},
            {"name": "glm", "binary": "glm", "engine": EngineType.GLM,
             "caps": [EngineCapability.CODING, EngineCapability.REASONING]},
            {"name": "qwen", "binary": "qwen", "engine": EngineType.QWEN,
             "caps": [EngineCapability.CODING, EngineCapability.REASONING]},
            {"name": "deepseek", "binary": "deepseek", "engine": EngineType.DEEPSEEK,
             "caps": [EngineCapability.CODING, EngineCapability.REASONING]},
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        results: list[EngineRegistration] = []
        cargo_dir = os.path.join(os.path.expanduser("~"), ".cargo", "bin")
        if not os.path.isdir(cargo_dir):
            return results

        for entry in self._known_binaries:
            binary = entry["binary"]
            path = os.path.join(cargo_dir, binary)
            ext = ".exe" if os.name == "nt" else ""
            if not os.path.isfile(path + ext):
                continue
            path += ext
            version = await self._get_version(path)
            results.append(EngineRegistration(
                name=f"{entry['name']}-cargo",
                engine_type=entry["engine"],
                endpoint=f"local:{binary}",
                transport="local",
                capabilities=entry["caps"],
                description=f"{entry['name'].title()} (cargo install)" + (f" v{version}" if version else ""),
                version=version or "unknown",
                tags=["discovered", "cargo", binary],
                metadata={"path": path, "discovery_method": "cargo", "binary": binary},
            ))
        return results

    def get_provider_name(self) -> str: return "cargo-discovery"
    def get_provider_type(self) -> str: return "cargo"

    @staticmethod
    async def _get_version(path: str) -> str | None:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, timeout=5.0)
            return result.stdout.decode("utf-8", errors="replace").strip().split("\n")[0][:100] if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            return None
