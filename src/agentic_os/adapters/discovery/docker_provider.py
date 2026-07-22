"""Docker Discovery Provider.

Probes Docker for running containers that expose AI coding assistant
capabilities. Lists running containers, checks images and labels for
known AI execution tools.
"""

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.execution import EngineCapability, EngineType
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.docker")


@dataclass
class DockerDiscovery(DiscoveryProvider):
    """Probes Docker for AI execution containers.

    Runs ``docker ps`` to list running containers, then inspects their
    images and labels to detect well-known AI coding tools. Also checks
    for Docker Desktop or Docker Engine installation.
    """

    _known_images: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {
                "name": "claude-code",
                "image_pattern": "claude",
                "type": EngineType.CLAUDE_CODE,
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
            {
                "name": "aider",
                "image_pattern": "aider",
                "type": EngineType.AIDER,
                "capabilities": [EngineCapability.CODING, EngineCapability.PLANNING],
            },
            {
                "name": "openhands",
                "image_pattern": "openhands",
                "type": EngineType.OPENHANDS,
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.PLANNING,
                    EngineCapability.FILESYSTEM,
                ],
            },
        )
    )

    _engine_labels: tuple[dict[str, Any], ...] = field(
        default_factory=lambda: (
            {
                "name": "claude-code",
                "label": "com.anthropic.claude.version",
                "type": EngineType.CLAUDE_CODE,
                "capabilities": [
                    EngineCapability.CODING,
                    EngineCapability.REASONING,
                    EngineCapability.TERMINAL,
                ],
            },
        )
    )

    async def discover(self) -> list[EngineRegistration]:
        """Probe Docker for running containers and detect AI engines."""
        results: list[EngineRegistration] = []

        if not self._docker_available():
            log.info("Docker discovery skipped — docker not available")
            return results

        # Find Docker Engine itself
        docker_version = await self._get_docker_version()
        if docker_version:
            results.append(
                EngineRegistration(
                    name="docker-engine",
                    engine_type=EngineType.DOCKER,
                    endpoint="local:docker",
                    transport="local",
                    capabilities=[EngineCapability.DOCKER],
                    description=f"Docker Engine v{docker_version} (discovered)",
                    version=docker_version,
                    tags=["discovered", "docker", "engine"],
                    metadata={"discovery_method": "docker", "binary": "docker"},
                )
            )

        # Scan running containers
        containers = await self._list_containers()
        for container in containers:
            container_result = self._classify_container(container)
            if container_result is not None:
                results.append(container_result)

        return results

    def get_provider_name(self) -> str:
        return "docker-discovery"

    def get_provider_type(self) -> str:
        return "docker"

    # ── Internal ──

    @staticmethod
    def _docker_available() -> bool:
        """Check if docker CLI is available."""
        return shutil.which("docker") is not None

    @staticmethod
    async def _get_docker_version() -> str | None:
        """Get Docker Engine version."""
        try:
            result = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            if result.returncode == 0:
                return result.stdout.strip()[:50]
            return None
        except FileNotFoundError, subprocess.TimeoutExpired, OSError:
            return None

    @staticmethod
    async def _list_containers() -> list[dict]:
        """List running Docker containers with their metadata."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
                timeout=15.0,
            )
            if result.returncode != 0:
                return []

            containers: list[dict] = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    container = json.loads(line)
                    containers.append(container)
                except json.JSONDecodeError:
                    continue
            return containers
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            log.warning("Failed to list Docker containers", error=str(exc))
            return []

    def _classify_container(self, container: dict) -> EngineRegistration | None:
        """Classify a container by image name and labels."""
        image = container.get("Image", "")
        names = container.get("Names", "")
        container_id = container.get("ID", "")[:12]
        labels_str = container.get("Labels", "")
        status = container.get("Status", "")

        # Check labels first (most specific)
        for label_entry in self._engine_labels:
            if label_entry["label"] in labels_str:
                return self._make_registration(
                    name=label_entry["name"],
                    engine_type=label_entry["type"],
                    capabilities=label_entry["capabilities"],
                    container_id=container_id,
                    image=image,
                    names=names,
                    status=status,
                )

        # Check image name patterns
        for image_entry in self._known_images:
            if image_entry["image_pattern"].lower() in image.lower():
                return self._make_registration(
                    name=image_entry["name"],
                    engine_type=image_entry["type"],
                    capabilities=image_entry["capabilities"],
                    container_id=container_id,
                    image=image,
                    names=names,
                    status=status,
                )

        return None

    @staticmethod
    def _make_registration(
        name: str,
        engine_type: EngineType,
        capabilities: list,
        container_id: str,
        image: str,
        names: str,
        status: str,
    ) -> EngineRegistration:
        """Build an EngineRegistration for a Docker container."""
        return EngineRegistration(
            name=f"{name}-docker-{container_id}",
            engine_type=engine_type,
            endpoint=f"docker:{container_id}",
            transport="docker",
            capabilities=capabilities,
            description=f"{name} (Docker container {container_id}: {image})",
            version="",
            tags=["discovered", "docker", container_id],
            metadata={
                "container_id": container_id,
                "image": image,
                "names": names,
                "status": status,
                "discovery_method": "docker",
            },
        )
