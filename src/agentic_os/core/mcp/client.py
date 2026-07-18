"""
MCP Client Implementation

Handles stdio and SSE transport connections to MCP servers.
Provides capability negotiation, tool listing, and tool invocation.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

import httpx

from agentic_os.domain.mcp import (
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


@dataclass
class MCPClient:
    """
    MCP Client for communicating with MCP servers via stdio or SSE.

    Supports:
    - stdio transport (subprocess with stdin/stdout JSON-RPC)
    - SSE transport (HTTP with Server-Sent Events)
    - Capability negotiation
    - Tool listing and invocation
    - Health checks
    """

    config: MCPServerConfig
    _process: subprocess.Popen | None = field(default=None, init=False, repr=False)
    _sse_client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)
    _sse_task: asyncio.Task | None = field(default=None, init=False, repr=False)
    _request_id: int = field(default=0, init=False, repr=False)
    _pending_requests: dict[int, asyncio.Future] = field(
        default_factory=dict, init=False, repr=False
    )
    _tools: list[MCPTool] = field(default_factory=list, init=False, repr=False)
    _connected: bool = field(default=False, init=False, repr=False)
    _capabilities: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    process_id: int | None = field(default=None, init=False, repr=False)

    async def connect(self) -> dict[str, Any]:
        """Connect to the MCP server and perform initialization."""
        if self.config.transport == MCPTransport.STDIO:
            return await self._connect_stdio()
        elif self.config.transport == MCPTransport.SSE:
            return await self._connect_sse()
        else:
            raise ValueError(f"Unknown transport: {self.config.transport}")

    async def _connect_stdio(self) -> dict[str, Any]:
        """Connect via stdio transport (subprocess)."""
        if not self.config.command:
            raise ValueError("No command configured for stdio transport")

        # Prepare environment
        env = os.environ.copy()
        env.update(self.config.env)

        # Start subprocess
        self._process = subprocess.Popen(
            [self.config.command, *self.config.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=0,
        )
        self.process_id = self._process.pid

        # Start reader task
        self._connected = True
        asyncio.create_task(self._read_stdout())

        # Send initialize request
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

        # Send initialized notification
        await self._send_notification("notifications/initialized", {})

        self._capabilities = init_result.get("capabilities", {})
        return init_result

    async def _connect_sse(self) -> dict[str, Any]:
        """Connect via SSE transport."""
        if not self.config.url:
            raise ValueError("No URL configured for SSE transport")

        self._sse_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        self._connected = True

        # Start SSE listener
        self._sse_task = asyncio.create_task(self._sse_listener())

        # Send initialize via POST to /mcp
        init_result = await self._send_sse_request(
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

        self._capabilities = init_result.get("capabilities", {})
        return init_result

    async def _read_stdout(self) -> None:
        """Read stdout from stdio subprocess."""
        if not self._process or not self._process.stdout:
            return

        loop = asyncio.get_event_loop()
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

        # Process ended
        self._connected = False

    async def _sse_listener(self) -> None:
        """Listen for SSE events from the server."""
        if not self._sse_client or not self.config.url:
            return

        try:
            async with self._sse_client.stream(
                "GET", f"{self.config.url}/sse", headers={"Accept": "text/event-stream"}
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

    async def _handle_message(self, message: str) -> None:
        """Handle incoming JSON-RPC message."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            log.warning(f"Failed to parse JSON-RPC message: {message[:200]}")
            return

        # Response to a request
        if "id" in data and data["id"] is not None:
            request_id = data["id"]
            future = self._pending_requests.pop(request_id, None)
            if future:
                if "error" in data:
                    future.set_exception(Exception(data["error"].get("message", "Unknown error")))
                else:
                    future.set_result(data.get("result"))
            return

        # Notification
        if "method" in data and "id" not in data:
            method = data["method"]
            params = data.get("params", {})
            await self._handle_notification(method, params)
            return

        # Response without ID (shouldn't happen)
        log.warning(f"Received message without ID: {data}")

    async def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle incoming notifications."""
        if method == "notifications/tools/list_changed":
            # Refresh tools
            await self.list_tools()
        elif method == "notifications/roots/list_changed":
            pass  # Handle roots change if needed
        else:
            log.debug(f"Unhandled notification: {method}")

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(
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

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            message = json.dumps(request) + "\n"
            self._process.stdin.write(message)
            await asyncio.get_event_loop().run_in_executor(None, self._process.stdin.flush)
        except Exception:
            self._pending_requests.pop(request_id, None)
            raise

        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except TimeoutError as err:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(f"Request {method} timed out") from err

    async def _send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send JSON-RPC notification (no response expected)."""
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
        await asyncio.get_event_loop().run_in_executor(None, self._process.stdin.flush)

    async def _send_sse_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send JSON-RPC request over SSE (via POST to /mcp endpoint)."""
        if not self._sse_client or not self.config.url:
            raise RuntimeError("Not connected")

        request_id = self._next_request_id()
        request = {
            "jsonrpc": JSON_RPC_VERSION,
            "id": request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            response = await self._sse_client.post(
                f"{self.config.url}/mcp",
                json=request,
                headers={"Content-Type": "application/json", **self.config.headers},
            )
            response.raise_for_status()
            # For SSE, responses come via the SSE stream, not the POST response
            # But some implementations may return immediate response
            data = response.json()
            if "id" in data and data["id"] is not None:
                # Immediate response
                self._pending_requests.pop(request_id, None)
                if "error" in data:
                    raise Exception(data["error"].get("message", "Unknown error"))
                return data.get("result", {})
        except Exception:
            self._pending_requests.pop(request_id, None)
            raise

        # Wait for response via SSE
        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except TimeoutError as err:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(f"SSE request {method} timed out") from err

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
            # Ping the server
            start = asyncio.get_event_loop().time()
            await self._send_request("ping", {})
            latency = (asyncio.get_event_loop().time() - start) * 1000

            return {
                "healthy": True,
                "latency_ms": round(latency, 2),
                "tools": len(self._tools),
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        self._connected = False

        # Cancel pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

        if self._process:
            try:
                if self._process.poll() is None:
                    self._process.terminate()
                    await asyncio.get_event_loop().run_in_executor(None, self._process.wait, 5.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                await asyncio.get_event_loop().run_in_executor(None, self._process.wait)
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

        if self._sse_client:
            await self._sse_client.aclose()
            self._sse_client = None

        self._tools.clear()
        self._capabilities.clear()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def tools(self) -> list[MCPTool]:
        return self._tools.copy()

    @property
    def capabilities(self) -> dict[str, Any]:
        return self._capabilities.copy()
