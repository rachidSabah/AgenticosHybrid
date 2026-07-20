from __future__ import annotations

import json
import subprocess

from core.logging import get_logger
from services.runtime_discovery.models import (
    DiscoveryProviderType,
    RuntimeDiscoveryResult,
    RuntimeType,
)

_log = get_logger(__name__)

_MCP_IMAGE_PREFIXES = [
    "mcp-",
    "mcp/",
    "modelcontextprotocol/",
    "anthropic-mcp-",
]

_DEV_TOOL_IMAGES = {
    "ollama": RuntimeType.OLLAMA,
}


class DockerDiscoveryProvider:
    provider_type = DiscoveryProviderType.DOCKER

    async def discover(
        self, runtime_type: RuntimeType | None = None
    ) -> list[RuntimeDiscoveryResult]:
        results: list[RuntimeDiscoveryResult] = []
        try:
            info = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if info.returncode != 0:
                return results
        except Exception:
            return results

        images = await self._list_images()
        for image in images:
            if runtime_type is not None and runtime_type != RuntimeType.MCP_SERVER:
                continue
            if any(image.startswith(prefix) for prefix in _MCP_IMAGE_PREFIXES):
                results.append(
                    RuntimeDiscoveryResult(
                        runtime_type=RuntimeType.MCP_SERVER,
                        name=f"mcp-{image}",
                        display_name=f"MCP Server ({image})",
                        version=images[image],
                        binary_path=None,
                        executable=None,
                        source=DiscoveryProviderType.DOCKER,
                        confidence=0.7,
                        found=True,
                        metadata={"docker_image": image, "tag": images[image]},
                    )
                )

        for dev_tool, rt_type in _DEV_TOOL_IMAGES.items():
            if runtime_type is not None and rt_type != runtime_type:
                continue
            if dev_tool in images:
                results.append(
                    RuntimeDiscoveryResult(
                        runtime_type=rt_type,
                        name=dev_tool,
                        display_name=f"{dev_tool.capitalize()} (Docker)",
                        version=images[dev_tool],
                        binary_path="docker",
                        executable="docker",
                        source=DiscoveryProviderType.DOCKER,
                        confidence=0.8,
                        found=True,
                    )
                )

        containers = await self._list_containers()
        for container in containers:
            if runtime_type is not None and runtime_type != RuntimeType.MCP_SERVER:
                continue
            results.append(
                RuntimeDiscoveryResult(
                    runtime_type=RuntimeType.MCP_SERVER,
                    name=f"container-{container['name']}",
                    display_name=f"Container ({container['name']})",
                    version=container["image"],
                    binary_path=None,
                    executable=None,
                    source=DiscoveryProviderType.DOCKER,
                    confidence=0.5,
                    found=True,
                    metadata={"container_id": container["id"], "container_name": container["name"]},
                )
            )

        _log.info("DockerDiscoveryProvider found %d runtimes", len(results))
        return results

    async def discover_all(self) -> list[RuntimeDiscoveryResult]:
        return await self.discover()

    async def get_provider_name(self) -> str:
        return "docker"

    async def get_provider_type(self) -> DiscoveryProviderType:
        return DiscoveryProviderType.DOCKER

    async def _list_images(self) -> dict[str, str]:
        try:
            result = subprocess.run(
                ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return {}
            images: dict[str, str] = {}
            for line in result.stdout.splitlines():
                if ":" in line:
                    repo, tag = line.rsplit(":", 1)
                    repo_short = repo.split("/")[-1].lower()
                    images[repo_short] = tag
            return images
        except Exception:
            return {}

    async def _list_containers(self) -> list[dict[str, str]]:
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []
            containers: list[dict[str, str]] = []
            for line in result.stdout.splitlines():
                try:
                    data = json.loads(line)
                    containers.append(
                        {
                            "id": data.get("ID", ""),
                            "name": data.get("Names", ""),
                            "image": data.get("Image", ""),
                        }
                    )
                except json.JSONDecodeError:
                    continue
            return containers
        except Exception:
            return []
