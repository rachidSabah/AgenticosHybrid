"""
MCP Client Implementation

Handles stdio, SSE, and Streamable HTTP transport connections to MCP servers.
Provides capability negotiation, tool/resource/prompt management.
"""

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx

from agentic_os.domain.mcp import (
    MCPPrompt,
    MCPResource,
    MCPResourceTemplate,
    MCPServerConfig,
    MCPTool,
    MCPToolResult,
    MCPTransport,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("mcp.client")

# MCP Protocol constants
MCP_PROTOCOL_VERSION = "2024-11-05"
JSON_RPC_VERSION = "2.0"

# Reconnection defaults
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_BASE_DELAY = 1.0
_DEFAULT_MAX_DELAY = 30.0


@dataclass
class MCPClient:
    """
    MCP Client for communicating with MCP servers via stdio, SSE, or Streamable HTTP.

    Supports:
    - stdio transport (subprocess with stdin/stdout JSON-RPC)
    - SSE transport (HTTP with Server-Sent Events)
    - Streamable HTTP transport (HTTP POST with streaming responses)
    - Capability negotiation
    - Tool listing and invocation
    - Resource listing, reading, and subscription
    - Prompt listing and retrieval
    - Health checks
    - Automatic reconnection with exponential backoff
    """

    config: MCPServerConfig
    _process: subprocess.Popen | None = field(default=None, init=False, repr=False)
    _http_client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)
    _sse_task: asyncio.Task | None = field(default=None, init=False, repr=False)
    _request_id: int = field(default=0, init=False, repr=False)
    _pending_requests: dict[int, asyncio.Future] = field(
        default_factory=dict, init=False, repr=False
    )
    _tools: list[MCPTool] = field(default_factory=list, init=False, repr=False)
    _resources: list[MCPResource] = field(default_factory=list, init=False, repr=False)
    _resource_templates: list[MCPResourceTemplate] = field(
        default_factory=list, init=False, repr=False
    )
    _prompts: list[MCPPrompt] = field(default_factory=list, init=False, repr=False)
    _connected: bool = field(default=False, init=False, repr=False)
    _capabilities: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _server_capabilities: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    process_id: int | None = field(default=None, init=False, repr=False)
    _reconnect_task: asyncio.Task | None = field(default=None, init=False, repr=False)
    _retry_count: int = field(default=0, init=False, repr=False)
    _session_id: str | None = field(default=None, init=False, repr=False)

    # ── Connection ──────────────────────────────────────────────────────

    async def connect(self) -> dict[str, Any]:
        """Connect to the MCP server and perform initialization."""
        self._session_id = uuid4().hex
        if self.config.transport == MCPTransport.STDIO:
            return await self._connect_stdio()
        elif self.config.transport == MCPTransport.SSE:
            return await self._connect_sse()
        elif self.config.transport == MCPTransport.STREAMABLE_HTTP:
            return await self._connect_streamable_http()
        else:
            raise ValueError(f"Unknown transport: {self.config.transport}")

    async def _connect_stdio(self) -> dict[str, Any]:
        """Connect via stdio transport (subprocess)."""
        if not self.config.command:
            raise ValueError("No command configured for stdio transport")

        env = os.environ.copy()
        env.update(self.config.env)

        cmd = [self.config.command, *self.config.args]
        use_shell = sys.platform == "win32" and self.config.command.lower() in ("npx", "npm", "cmd", "npx.cmd")

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=0,
            shell=use_shell,
        )
        self.process_id = self._process.pid

        self._connected = True
        asyncio.create_task(self._read_stdout())

        init_result = await self._send_request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {},
                },
                "clientInfo": {"name": "agentic-os-mcp-client", "version": "0.4.0"},
            },
        )

        await self._send_notification("notifications/initialized", {})

        self._server_capabilities = init_result.get("capabilities", {})
        self._capabilities = self._server_capabilities
        return init_result

    async def _connect_sse(self) -> dict[str, Any]:
        """Connect via SSE transport."""
        if not self.config.url:
            raise ValueError("No URL configured for SSE transport")

        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers=self.config.headers,
        )
        self._connected = True

        self._sse_task = asyncio.create_task(self._sse_listener())

        init_result = await self._send_request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {},
                },
                "clientInfo": {"name": "agentic-os-mcp-client", "version": "0.4.0"},
            },
        )

        await self._send_notification("notifications/initialized", {})

        self._server_capabilities = init_result.get("capabilities", {})
        self._capabilities = self._server_capabilities
        return init_result

    async def _connect_streamable_http(self) -> dict[str, Any]:
        """Connect via Streamable HTTP transport.

        Uses HTTP POST with streaming response for bidirectional JSON-RPC.
        Each request/response pair is a separate HTTP exchange with the
        server streaming the response back as newline-delimited JSON.
        """
        if not self.config.url:
            raise ValueError("No URL configured for Streamable HTTP transport")

        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            headers=self.config.headers,
        )
        self._connected = True

        init_result = await self._send_request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {},
                },
                "clientInfo": {"name": "agentic-os-mcp-client", "version": "0.4.0"},
            },
        )

        await self._send_notification("notifications/initialized", {})

        self._server_capabilities = init_result.get("capabilities", {})
        self._capabilities = self._server_capabilities
        return init_result

    # ── Stream readers ──────────────────────────────────────────────────

    async def _read_stdout(self) -> None:
        """Read stdout from stdio subprocess."""
        if not self._process or not self._process.stdout:
            return

        loop = asyncio.get_running_loop()
        while self._connected and self._process.poll() is None:
            try:
                line = await loop.run_in_executor(None, self._process.stdout.readline)
                if not line:
                    break
                line = line.strip()
                if line:
                    await self._handle_message(line)
            except Exception as e:
                log.error(f"Error reading from MCP server stdout: {e}")
                break

        self._connected = False
        if not self._reconnect_task or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._auto_reconnect())

    async def _sse_listener(self) -> None:
        """Listen for SSE events from the server."""
        if not self._http_client or not self.config.url:
            return

        try:
            async with self._http_client.stream(
                "GET",
                f"{self.config.url}/sse",
                headers={"Accept": "text/event-stream"},
            ) as response:
                async for line in response.aiter_lines():
                    if not self._connected:
                        break
                    if line.startswith("data: "):
                        data = line[6:]
                        try:
                            await self._handle_message(data)
                        except Exception as e:
                            log.error(f"Error handling SSE message: {e}")
        except Exception as e:
            log.error(f"SSE listener error: {e}")
        finally:
            self._connected = False
            if not self._reconnect_task or self._reconnect_task.done():
                self._reconnect_task = asyncio.create_task(self._auto_reconnect())

    # ── Message handling ────────────────────────────────────────────────

    async def _handle_message(self, message: str) -> None:
        """Handle incoming JSON-RPC message."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            log.warning(f"Failed to parse JSON-RPC message: {message[:200]}")
            return

        if "id" in data and data["id"] is not None:
            request_id = data["id"]
            future = self._pending_requests.pop(request_id, None)
            if future:
                if "error" in data:
                    future.set_exception(Exception(data["error"].get("message", "Unknown error")))
                else:
                    future.set_result(data.get("result"))
            return

        if "method" in data and "id" not in data:
            method = data["method"]
            params = data.get("params", {})
            await self._handle_notification(method, params)
            return

        log.warning(f"Received message without ID: {data}")

    async def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle incoming notifications."""
        if method == "notifications/tools/list_changed":
            await self.list_tools()
        elif method == "notifications/resources/list_changed":
            await self.list_resources()
        elif method == "notifications/resources/subscription_change":
            resource_uri = params.get("uri", "")
            log.info(f"Resource changed: {resource_uri}")
        elif method == "notifications/roots/list_changed":
            pass
        else:
            log.debug(f"Unhandled notification: {method}")

    # ── Request IDs ─────────────────────────────────────────────────────

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    # ── Request dispatch ────────────────────────────────────────────────

    async def _send_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send a JSON-RPC request, dispatching to the active transport."""
        if self.config.transport == MCPTransport.STDIO:
            return await self._send_stdio_request(method, params)
        elif self.config.transport == MCPTransport.SSE:
            return await self._send_sse_request(method, params)
        elif self.config.transport == MCPTransport.STREAMABLE_HTTP:
            return await self._send_streamable_request(method, params)
        raise RuntimeError(f"Unsupported transport: {self.config.transport}")

    async def _send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC notification, dispatching to the active transport."""
        if self.config.transport == MCPTransport.STDIO:
            await self._send_stdio_notification(method, params)
        elif self.config.transport in (MCPTransport.SSE, MCPTransport.STREAMABLE_HTTP):
            await self._send_http_notification(method, params)
        else:
            raise RuntimeError(f"Unsupported transport: {self.config.transport}")

    # ── Stdio request/notification ──────────────────────────────────────

    async def _send_stdio_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send JSON-RPC request over stdio and wait for response."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("Not connected")

        request_id = self._next_request_id()
        request = {
            "jsonrpc": JSON_RPC_VERSION,
            "id": request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            message = json.dumps(request) + "\n"
            self._process.stdin.write(message)
            await asyncio.get_running_loop().run_in_executor(None, self._process.stdin.flush)
        except Exception:
            self._pending_requests.pop(request_id, None)
            raise

        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except TimeoutError as err:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(f"Request {method} timed out") from err

    async def _send_stdio_notification(
        self, method: str, params: dict[str, Any] | None = None
    ) -> None:
        """Send JSON-RPC notification over stdio (no response expected)."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("Not connected")

        notification = {
            "jsonrpc": JSON_RPC_VERSION,
            "method": method,
        }
        if params is not None:
            notification["params"] = params

        message = json.dumps(notification) + "\n"
        self._process.stdin.write(message)
        await asyncio.get_running_loop().run_in_executor(None, self._process.stdin.flush)

    # ── SSE request/notification ────────────────────────────────────────

    async def _send_sse_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send JSON-RPC request over SSE (via POST to the MCP endpoint)."""
        if not self._http_client or not self.config.url:
            raise RuntimeError("Not connected")

        request_id = self._next_request_id()
        request = {
            "jsonrpc": JSON_RPC_VERSION,
            "id": request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            response = await self._http_client.post(
                f"{self.config.url}/mcp",
                json=request,
                headers={"Content-Type": "application/json", **self.config.headers},
            )
            response.raise_for_status()
            data = response.json()
            if "id" in data and data["id"] is not None:
                self._pending_requests.pop(request_id, None)
                if "error" in data:
                    raise Exception(data["error"].get("message", "Unknown error"))
                return data.get("result", {})
        except Exception:
            self._pending_requests.pop(request_id, None)
            raise

        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except TimeoutError as err:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(f"SSE request {method} timed out") from err

    # ── Streamable HTTP request/notification ────────────────────────────

    async def _send_streamable_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send JSON-RPC request over Streamable HTTP and read streaming response.

        The server responds with newline-delimited JSON that may contain
        the response to this request or server-initiated notifications.
        """
        if not self._http_client or not self.config.url:
            raise RuntimeError("Not connected")

        request_id = self._next_request_id()
        request = {
            "jsonrpc": JSON_RPC_VERSION,
            "id": request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            async with self._http_client.stream(
                "POST",
                self.config.url,
                json=request,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        if not isinstance(data, dict):
                            continue
                        msg_id = data.get("id")
                        if msg_id == request_id:
                            self._pending_requests.pop(request_id, None)
                            if "error" in data:
                                raise Exception(data["error"].get("message", "Unknown error"))
                            return data.get("result", {})
                        elif msg_id is None and "method" in data:
                            await self._handle_notification(data["method"], data.get("params", {}))
                    except json.JSONDecodeError:
                        continue

                self._pending_requests.pop(request_id, None)
                raise TimeoutError(f"Streamable HTTP request {method} ended without response")
        except Exception:
            self._pending_requests.pop(request_id, None)
            raise
        finally:
            if request_id in self._pending_requests:
                self._pending_requests.pop(request_id, None)

    async def _send_http_notification(
        self, method: str, params: dict[str, Any] | None = None
    ) -> None:
        """Send JSON-RPC notification via HTTP (fire-and-forget)."""
        if not self._http_client or not self.config.url:
            raise RuntimeError("Not connected")

        notification = {
            "jsonrpc": JSON_RPC_VERSION,
            "method": method,
        }
        if params is not None:
            notification["params"] = params

        endpoint = self.config.url
        if self.config.transport == MCPTransport.SSE:
            endpoint = f"{self.config.url}/mcp"

        try:
            await self._http_client.post(endpoint, json=notification)
        except Exception as e:
            log.warning(f"Failed to send notification {method}: {e}")

    # ── Tool methods ────────────────────────────────────────────────────

    async def list_tools(self) -> list[MCPTool]:
        """List available tools from the MCP server."""
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")

        result = await self._send_request("tools/list", {})
        tools_data = result.get("tools", [])

        self._tools = [MCPTool.from_mcp(t) for t in tools_data]
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolResult:
        """Invoke an MCP tool."""
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")

        result = await self._send_request("tools/call", {"name": name, "arguments": arguments})

        content = result.get("content", [])
        is_error = result.get("isError", False)

        return MCPToolResult(content=content, is_error=is_error)

    async def health_check(self) -> dict[str, Any]:
        """Perform a health check on the MCP server."""
        if not self._connected:
            return {"healthy": False, "error": "Not connected"}

        try:
            start = asyncio.get_running_loop().time()
            await self._send_request("ping", {})
            latency = (asyncio.get_running_loop().time() - start) * 1000

            return {
                "healthy": True,
                "latency_ms": round(latency, 2),
                "tools": len(self._tools),
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    # ── Resource methods ────────────────────────────────────────────────

    async def list_resources(self) -> list[MCPResource]:
        """List available resources from the MCP server."""
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")

        result = await self._send_request("resources/list", {})
        resources_data = result.get("resources", [])

        self._resources = [MCPResource.from_mcp(r) for r in resources_data]
        return self._resources

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """Read a specific resource by URI."""
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")

        return await self._send_request("resources/read", {"uri": uri})

    async def list_resource_templates(self) -> list[MCPResourceTemplate]:
        """List available resource templates from the MCP server."""
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")

        result = await self._send_request("resources/templates/list", {})
        templates_data = result.get("resourceTemplates", [])

        self._resource_templates = [
            MCPResourceTemplate(
                uri_template=t.get("uriTemplate", ""),
                name=t.get("name", ""),
                description=t.get("description", ""),
                mime_type=t.get("mimeType"),
            )
            for t in templates_data
        ]
        return self._resource_templates

    async def subscribe_resource(self, uri: str) -> bool:
        """Subscribe to resource change notifications."""
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")

        result = await self._send_request("resources/subscribe", {"uri": uri})
        return result.get("success", True)

    async def unsubscribe_resource(self, uri: str) -> bool:
        """Unsubscribe from resource change notifications."""
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")

        result = await self._send_request("resources/unsubscribe", {"uri": uri})
        return result.get("success", True)

    # ── Prompt methods ──────────────────────────────────────────────────

    async def list_prompts(self) -> list[MCPPrompt]:
        """List available prompts from the MCP server."""
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")

        result = await self._send_request("prompts/list", {})
        prompts_data = result.get("prompts", [])

        self._prompts = [MCPPrompt.from_mcp(p) for p in prompts_data]
        return self._prompts

    async def get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Get a specific prompt by name."""
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")

        params: dict[str, Any] = {"name": name}
        if arguments:
            params["arguments"] = arguments

        return await self._send_request("prompts/get", params)

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        self._connected = False

        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        if self._process:
            try:
                if self._process.poll() is None:
                    self._process.terminate()
                    await asyncio.get_running_loop().run_in_executor(None, self._process.wait, 5.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                await asyncio.get_running_loop().run_in_executor(None, self._process.wait)
            except Exception as e:
                log.warning(f"Error terminating MCP process: {e}")
            finally:
                self._process = None
                self.process_id = None

        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
            self._sse_task = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        self._tools.clear()
        self._resources.clear()
        self._resource_templates.clear()
        self._prompts.clear()
        self._capabilities.clear()
        self._server_capabilities.clear()
        self._retry_count = 0
        self._session_id = None

    # ── Reconnection ────────────────────────────────────────────────────

    async def _auto_reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        if self._connected:
            return

        retries = 0
        while retries < _DEFAULT_MAX_RETRIES:
            delay = min(_DEFAULT_BASE_DELAY * (2**retries), _DEFAULT_MAX_DELAY)
            log.info(f"Reconnecting in {delay:.1f}s (attempt {retries + 1}/{_DEFAULT_MAX_RETRIES})")
            await asyncio.sleep(delay)

            try:
                await self.connect()

                try:
                    self._tools = await self.list_tools()
                except Exception as e:
                    log.warning(f"Failed to rediscover tools after reconnect: {e}")

                try:
                    self._resources = await self.list_resources()
                except Exception as e:
                    log.warning(f"Failed to rediscover resources after reconnect: {e}")

                try:
                    self._prompts = await self.list_prompts()
                except Exception as e:
                    log.warning(f"Failed to rediscover prompts after reconnect: {e}")

                self._retry_count = retries
                log.info("Reconnection successful")
                return

            except Exception as e:
                log.warning(f"Reconnection attempt {retries + 1} failed: {e}")
                retries += 1

        log.error(f"Failed to reconnect after {_DEFAULT_MAX_RETRIES} attempts")
        self._retry_count = _DEFAULT_MAX_RETRIES

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def tools(self) -> list[MCPTool]:
        return self._tools.copy()

    @property
    def resources(self) -> list[MCPResource]:
        return self._resources.copy()

    @property
    def resource_templates(self) -> list[MCPResourceTemplate]:
        return self._resource_templates.copy()

    @property
    def prompts(self) -> list[MCPPrompt]:
        return self._prompts.copy()

    @property
    def capabilities(self) -> dict[str, Any]:
        return self._capabilities.copy()

    @property
    def session_id(self) -> str | None:
        return self._session_id


__all__ = ["MCPClient"]
