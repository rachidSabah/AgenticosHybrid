"""
Docker MCP Adapter

Exposes Docker operations as MCP tools including:
- Container management
- Image operations
- System information
"""

import json
from typing import Any

from agentic_os.adapters.mcp.base import BaseMCPAdapter
from agentic_os.domain.mcp import MCPPrompt, MCPResource, MCPTool, MCPToolResult, MCPTransport


class DockerAdapter(BaseMCPAdapter):
    """
    MCP adapter for Docker container operations.

    Tools:
    - list_containers(all=False) -> list[dict]
    - get_container(container_id) -> dict
    - start_container(container_id) -> dict
    - stop_container(container_id) -> dict
    - restart_container(container_id) -> dict
    - logs(container_id, tail=100) -> str
    - list_images() -> list[dict]
    - pull_image(image_name) -> dict

    Config:
      docker_host (str): Docker socket path or host (default: unix:///var/run/docker.sock)
    """

    def __init__(
        self,
        name: str = "docker",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name, config)
        self._docker_host = (
            config.get("docker_host", "unix:///var/run/docker.sock")
            if config
            else "unix:///var/run/docker.sock"
        )
        self._client = None

    @property
    def transport_type(self) -> MCPTransport:
        return MCPTransport.STDIO

    def _get_client(self):
        """Get or create Docker client."""
        if self._client is None:
            try:
                import docker

                self._client = docker.DockerClient(base_url=self._docker_host)
            except ImportError:
                self._log.warning("docker-py not installed, using mock implementation")
                return None
        return self._client

    async def list_tools(self) -> list[MCPTool]:
        return list(self._build_tools().values())

    def _build_tools(self) -> dict[str, MCPTool]:
        return {
            "list_containers": MCPTool(
                name="list_containers",
                description="List running Docker containers",
                input_schema={
                    "type": "object",
                    "properties": {
                        "all": {"type": "boolean", "description": "Include stopped containers"},
                    },
                },
            ),
            "get_container": MCPTool(
                name="get_container",
                description="Get details of a specific container",
                input_schema={
                    "type": "object",
                    "properties": {
                        "container_id": {"type": "string", "description": "Container ID or name"},
                    },
                    "required": ["container_id"],
                },
            ),
            "start_container": MCPTool(
                name="start_container",
                description="Start a stopped container",
                input_schema={
                    "type": "object",
                    "properties": {
                        "container_id": {"type": "string", "description": "Container ID or name"},
                    },
                    "required": ["container_id"],
                },
            ),
            "stop_container": MCPTool(
                name="stop_container",
                description="Stop a running container",
                input_schema={
                    "type": "object",
                    "properties": {
                        "container_id": {
                            "type": "string",
                            "description": "Container ID or name",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Seconds to wait before killing",
                        },
                    },
                    "required": ["container_id"],
                },
            ),
            "restart_container": MCPTool(
                name="restart_container",
                description="Restart a container",
                input_schema={
                    "type": "object",
                    "properties": {
                        "container_id": {
                            "type": "string",
                            "description": "Container ID or name",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Seconds to wait before killing",
                        },
                    },
                    "required": ["container_id"],
                },
            ),
            "container_logs": MCPTool(
                name="container_logs",
                description="Get container logs",
                input_schema={
                    "type": "object",
                    "properties": {
                        "container_id": {"type": "string", "description": "Container ID or name"},
                        "tail": {"type": "integer", "description": "Number of lines to show"},
                        "timestamps": {"type": "boolean", "description": "Include timestamps"},
                    },
                    "required": ["container_id"],
                },
            ),
            "list_images": MCPTool(
                name="list_images",
                description="List Docker images",
                input_schema={
                    "type": "object",
                    "properties": {
                        "all": {"type": "boolean", "description": "Include intermediate images"},
                    },
                },
            ),
            "pull_image": MCPTool(
                name="pull_image",
                description="Pull a Docker image",
                input_schema={
                    "type": "object",
                    "properties": {
                        "image_name": {"type": "string", "description": "Image name to pull"},
                        "tag": {"type": "string", "description": "Image tag"},
                    },
                    "required": ["image_name"],
                },
            ),
        }

    async def invoke_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        tool_map = {
            "list_containers": self._list_containers,
            "get_container": self._get_container,
            "start_container": self._start_container,
            "stop_container": self._stop_container,
            "restart_container": self._restart_container,
            "container_logs": self._container_logs,
            "list_images": self._list_images,
            "pull_image": self._pull_image,
        }

        method = tool_map.get(tool)
        if method is None:
            return MCPToolResult(
                content=[{"type": "text", "text": f"Unknown tool: {tool}"}],
                is_error=True,
            )

        try:
            result = await method(arguments)
            return MCPToolResult(
                content=[{"type": "text", "text": json.dumps(result, default=str)}],
                is_error=False,
            )
        except Exception as e:
            self._log.error(f"Docker tool '{tool}' failed: {e}")
            return MCPToolResult(
                content=[{"type": "text", "text": f"Error: {e}"}],
                is_error=True,
            )

    async def _list_containers(self, args: dict[str, Any]) -> dict:
        """List Docker containers."""
        client = self._get_client()
        if not client:
            return {"containers": [], "error": "Docker client not available"}

        all_containers = args.get("all", False)
        containers = client.containers.list(all=all_containers)

        return {
            "containers": [
                {
                    "id": c.id[:12],
                    "name": c.name,
                    "image": c.image.tags[0] if c.image.tags else c.image.id[:12],
                    "status": c.status,
                    "created": c.attrs.get("Created"),
                }
                for c in containers
            ],
        }

    async def _get_container(self, args: dict[str, Any]) -> dict:
        """Get container details."""
        client = self._get_client()
        if not client:
            return {"error": "Docker client not available"}

        container_id = args["container_id"]
        container = client.containers.get(container_id)

        return {
            "id": container.id[:12],
            "name": container.name,
            "image": container.image.tags[0] if container.image.tags else container.image.id[:12],
            "status": container.status,
            "attrs": container.attrs,
        }

    async def _start_container(self, args: dict[str, Any]) -> dict:
        """Start a container."""
        client = self._get_client()
        if not client:
            return {"error": "Docker client not available"}

        container_id = args["container_id"]
        container = client.containers.get(container_id)
        container.start()

        return {
            "success": True,
            "container_id": container.id[:12],
            "status": container.status,
        }

    async def _stop_container(self, args: dict[str, Any]) -> dict:
        """Stop a container."""
        client = self._get_client()
        if not client:
            return {"error": "Docker client not available"}

        container_id = args["container_id"]
        timeout = args.get("timeout", 10)
        container = client.containers.get(container_id)
        container.stop(timeout=timeout)

        return {
            "success": True,
            "container_id": container.id[:12],
            "status": container.status,
        }

    async def _restart_container(self, args: dict[str, Any]) -> dict:
        """Restart a container."""
        client = self._get_client()
        if not client:
            return {"error": "Docker client not available"}

        container_id = args["container_id"]
        timeout = args.get("timeout", 10)
        container = client.containers.get(container_id)
        container.restart(timeout=timeout)

        return {
            "success": True,
            "container_id": container.id[:12],
            "status": container.status,
        }

    async def _container_logs(self, args: dict[str, Any]) -> dict:
        """Get container logs."""
        client = self._get_client()
        if not client:
            return {"logs": "", "error": "Docker client not available"}

        container_id = args["container_id"]
        tail = args.get("tail", 100)
        timestamps = args.get("timestamps", False)

        container = client.containers.get(container_id)
        logs = container.logs(tail=tail, timestamps=timestamps).decode("utf-8")

        return {
            "container_id": container.id[:12],
            "logs": logs,
        }

    async def _list_images(self, args: dict[str, Any]) -> dict:
        """List Docker images."""
        client = self._get_client()
        if not client:
            return {"images": [], "error": "Docker client not available"}

        all_images = args.get("all", False)
        images = client.images.list(all=all_images)

        return {
            "images": [
                {
                    "id": img.id.replace("sha256:", "")[:12],
                    "tags": img.tags,
                    "size": img.attrs.get("Size"),
                    "created": img.attrs.get("Created"),
                }
                for img in images
            ],
        }

    async def _pull_image(self, args: dict[str, Any]) -> dict:
        """Pull a Docker image."""
        client = self._get_client()
        if not client:
            return {"error": "Docker client not available"}

        image_name = args["image_name"]
        tag = args.get("tag", "latest")

        for line in client.images.pull(image_name, tag=tag, stream=True, decode=True):
            self._log.debug(f"Pull progress: {line}")

        return {
            "success": True,
            "image": f"{image_name}:{tag}",
        }

    async def list_resources(self) -> list[MCPResource]:
        from agentic_os.domain.mcp import MCPResource as MCPResourceModel

        return [
            MCPResourceModel(
                uri="docker://containers",
                name="Docker Containers",
                description="List of Docker containers",
                mime_type="application/json",
            ),
            MCPResourceModel(
                uri="docker://images",
                name="Docker Images",
                description="List of Docker images",
                mime_type="application/json",
            ),
        ]

    async def read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "docker://containers":
            return await self._list_containers({})
        if uri == "docker://images":
            return await self._list_images({})
        raise ValueError(f"Unknown resource URI: {uri}")

    async def list_prompts(self) -> list[MCPPrompt]:
        from agentic_os.domain.mcp import MCPPrompt as MCPPromptModel

        return [
            MCPPromptModel(
                name="docker_container_summary",
                description="Generate a summary of Docker containers",
                arguments=(
                    {"name": "all", "description": "Include stopped containers", "required": False},
                ),
            ),
        ]

    async def get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if name == "docker_container_summary":
            result = await self._list_containers({"all": args.get("all", True)})

            summary = "# Docker Container Summary\n\n"
            containers = result.get("containers", [])

            running = [c for c in containers if c["status"] == "running"]
            stopped = [c for c in containers if c["status"] != "running"]

            summary += f"**Total:** {len(containers)} containers\n"
            summary += f"**Running:** {len(running)}\n"
            summary += f"**Stopped:** {len(stopped)}\n\n"

            if running:
                summary += "## Running Containers\n\n"
                for c in running:
                    summary += f"- `{c['name']}` ({c['id']}): {c['image']}\n"

            return {
                "messages": [
                    {"role": "user", "content": summary},
                ],
            }

        raise ValueError(f"Unknown prompt: {name}")
