"""
HTTP MCP Adapter

Exposes HTTP client operations as MCP tools with domain sandboxing,
timeout control, and response size limits.
"""

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from agentic_os.adapters.mcp.base import BaseMCPAdapter
from agentic_os.domain.mcp import MCPTool, MCPToolResult, MCPTransport


class HTTPAdapter(BaseMCPAdapter):
    """
    MCP adapter for HTTP client operations.

    Tools:
    - http_get(url, headers=None, params=None) -> dict
    - http_post(url, body=None, headers=None) -> dict
    - http_put(url, body=None, headers=None) -> dict
    - http_delete(url, headers=None) -> dict

    Config:
      allowed_domains (list[str] | None): if set, only requests to these domains
          (exact host match) are allowed.
      default_timeout (int): default request timeout in seconds (default: 30).
      max_response_size (int): maximum response body size in bytes
          (default: 1_000_000).
    """

    def __init__(
        self,
        name: str = "http",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name, config)
        cfg = config or {}
        self._allowed_domains: list[str] | None = cfg.get("allowed_domains")
        self._default_timeout: int = cfg.get("default_timeout", 30)
        self._max_response_size: int = cfg.get("max_response_size", 1_000_000)
        self._client: httpx.AsyncClient | None = None

    # ── Transport ─────────────────────────────────────────────────────────────

    @property
    def transport_type(self) -> MCPTransport:
        return MCPTransport.STDIO

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Create the shared httpx async client."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._default_timeout),
            follow_redirects=True,
        )
        self._log.info(
            "HTTP adapter initialized",
            allowed_domains=self._allowed_domains,
            default_timeout=self._default_timeout,
            max_response_size=self._max_response_size,
        )

    async def shutdown(self) -> None:
        """Close the shared httpx async client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._log.info("HTTP adapter shut down")

    # ── URL validation ────────────────────────────────────────────────────────

    def _validate_url(self, url: str) -> str:
        """Validate the URL against allowed domains and basic constraints."""
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

        host = parsed.hostname
        if host is None:
            raise ValueError(f"Could not extract hostname from URL: {url}")

        if self._allowed_domains is not None:
            if host not in self._allowed_domains:
                raise PermissionError(
                    f"Domain '{host}' is not in allowed domains: {self._allowed_domains}"
                )

        return url

    def _response_to_dict(self, response: httpx.Response) -> dict[str, Any]:
        """Convert an httpx Response to a serializable dict, respecting size limit."""
        body_bytes = response.content[: self._max_response_size]
        truncated = len(response.content) > self._max_response_size

        # Try to decode as JSON, fall back to text
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                data = json.loads(body_bytes)
            except json.JSONDecodeError, ValueError:
                data = body_bytes.decode("utf-8", errors="replace")
        else:
            data = body_bytes.decode("utf-8", errors="replace")

        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "data": data,
            "truncated": truncated,
            "elapsed_ms": int(response.elapsed.total_seconds() * 1000),
        }

    # ── Tool definitions ──────────────────────────────────────────────────────

    def _build_tools(self) -> dict[str, MCPTool]:
        return {
            "http_get": MCPTool(
                name="http_get",
                description="Execute an HTTP GET request",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Request URL"},
                        "headers": {
                            "type": "object",
                            "description": "Request headers (optional)",
                        },
                        "params": {
                            "type": "object",
                            "description": "Query parameters (optional)",
                        },
                    },
                    "required": ["url"],
                },
            ),
            "http_post": MCPTool(
                name="http_post",
                description="Execute an HTTP POST request",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Request URL"},
                        "body": {
                            "description": "Request body (dict for JSON, str for text)",
                        },
                        "headers": {
                            "type": "object",
                            "description": "Request headers (optional)",
                        },
                    },
                    "required": ["url"],
                },
            ),
            "http_put": MCPTool(
                name="http_put",
                description="Execute an HTTP PUT request",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Request URL"},
                        "body": {
                            "description": "Request body (dict for JSON, str for text)",
                        },
                        "headers": {
                            "type": "object",
                            "description": "Request headers (optional)",
                        },
                    },
                    "required": ["url"],
                },
            ),
            "http_delete": MCPTool(
                name="http_delete",
                description="Execute an HTTP DELETE request",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Request URL"},
                        "headers": {
                            "type": "object",
                            "description": "Request headers (optional)",
                        },
                    },
                    "required": ["url"],
                },
            ),
        }

    async def list_tools(self) -> list[MCPTool]:
        return list(self._build_tools().values())

    # ── Tool invocation ───────────────────────────────────────────────────────

    async def invoke_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        tool_map: dict[str, Any] = {
            "http_get": self._http_get,
            "http_post": self._http_post,
            "http_put": self._http_put,
            "http_delete": self._http_delete,
        }

        method = tool_map.get(tool)
        if method is None:
            return MCPToolResult(
                content=[{"type": "text", "text": f"Unknown tool: {tool}"}],
                is_error=True,
            )

        try:
            result = await method(arguments)
            text = json.dumps(result, default=str, indent=2)
            return MCPToolResult(
                content=[{"type": "text", "text": text}],
                is_error=False,
            )
        except PermissionError as e:
            self._log.warning("Permission denied for tool '%s': %s", tool, e)
            return MCPToolResult(
                content=[{"type": "text", "text": str(e)}],
                is_error=True,
            )
        except httpx.HTTPError as e:
            self._log.error("HTTP error for tool '%s': %s", tool, e)
            return MCPToolResult(
                content=[
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"error": str(e), "type": type(e).__name__},
                            indent=2,
                        ),
                    }
                ],
                is_error=True,
            )
        except Exception as e:
            self._log.error("Tool '%s' failed: %s", tool, e)
            return MCPToolResult(
                content=[{"type": "text", "text": f"Error: {e}"}],
                is_error=True,
            )

    # ── Tool implementations ──────────────────────────────────────────────────

    async def _http_get(self, args: dict[str, Any]) -> dict[str, Any]:
        url = self._validate_url(args["url"])
        headers = args.get("headers")
        params = args.get("params")

        client = self._client
        if client is None:
            raise RuntimeError("HTTP adapter not initialized. Call initialize() first.")

        response = await client.get(url, headers=headers, params=params)
        return self._response_to_dict(response)

    async def _http_post(self, args: dict[str, Any]) -> dict[str, Any]:
        url = self._validate_url(args["url"])
        headers = args.get("headers")
        body = args.get("body")

        client = self._client
        if client is None:
            raise RuntimeError("HTTP adapter not initialized. Call initialize() first.")

        if isinstance(body, dict):
            response = await client.post(url, json=body, headers=headers)
        else:
            response = await client.post(url, content=body, headers=headers)

        return self._response_to_dict(response)

    async def _http_put(self, args: dict[str, Any]) -> dict[str, Any]:
        url = self._validate_url(args["url"])
        headers = args.get("headers")
        body = args.get("body")

        client = self._client
        if client is None:
            raise RuntimeError("HTTP adapter not initialized. Call initialize() first.")

        if isinstance(body, dict):
            response = await client.put(url, json=body, headers=headers)
        else:
            response = await client.put(url, content=body, headers=headers)

        return self._response_to_dict(response)

    async def _http_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        url = self._validate_url(args["url"])
        headers = args.get("headers")

        client = self._client
        if client is None:
            raise RuntimeError("HTTP adapter not initialized. Call initialize() first.")

        response = await client.delete(url, headers=headers)
        return self._response_to_dict(response)
