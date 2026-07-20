"""
GitHub MCP Adapter

Exposes GitHub operations as MCP tools including:
- Repository management
- Issues and pull requests
- File operations
- Search
"""

import json
from typing import Any

from agentic_os.adapters.mcp.base import BaseMCPAdapter
from agentic_os.domain.mcp import MCPPrompt, MCPResource, MCPTool, MCPToolResult, MCPTransport


class GitHubAdapter(BaseMCPAdapter):
    """
    MCP adapter for GitHub operations.

    Tools:
    - list_repositories() -> list[dict]
    - get_repository(owner, repo) -> dict
    - list_issues(owner, repo, state="open") -> list[dict]
    - get_issue(owner, repo, issue_number) -> dict
    - create_issue(owner, repo, title, body) -> dict
    - list_pull_requests(owner, repo) -> list[dict]
    - get_file_contents(owner, repo, path, ref) -> dict

    Config:
      token (str): GitHub personal access token
      api_url (str): GitHub API URL (default: https://api.github.com)
    """

    def __init__(
        self,
        name: str = "github",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name, config)
        self._token = config.get("token", "") if config else ""
        self._api_url = (
            config.get("api_url", "https://api.github.com") if config else "https://api.github.com"
        )
        self._headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AgenticOS-MCP-GitHub",
        }
        if self._token:
            self._headers["Authorization"] = f"token {self._token}"

    @property
    def transport_type(self) -> MCPTransport:
        return MCPTransport.SSE

    async def list_tools(self) -> list[MCPTool]:
        return list(self._build_tools().values())

    def _build_tools(self) -> dict[str, MCPTool]:
        return {
            "list_repositories": MCPTool(
                name="list_repositories",
                description="List repositories for the authenticated user",
                input_schema={"type": "object", "properties": {}},
            ),
            "get_repository": MCPTool(
                name="get_repository",
                description="Get details of a specific repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                    },
                    "required": ["owner", "repo"],
                },
            ),
            "list_issues": MCPTool(
                name="list_issues",
                description="List issues in a repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner",
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name",
                        },
                        "state": {
                            "type": "string",
                            "description": "Filter by state (open, closed, all)",
                        },
                    },
                    "required": ["owner", "repo"],
                },
            ),
            "get_issue": MCPTool(
                name="get_issue",
                description="Get a specific issue",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                        "issue_number": {"type": "integer", "description": "Issue number"},
                    },
                    "required": ["owner", "repo", "issue_number"],
                },
            ),
            "create_issue": MCPTool(
                name="create_issue",
                description="Create a new issue",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                        "title": {"type": "string", "description": "Issue title"},
                        "body": {"type": "string", "description": "Issue body"},
                        "labels": {"type": "array", "description": "Labels to add"},
                    },
                    "required": ["owner", "repo", "title"],
                },
            ),
            "list_pull_requests": MCPTool(
                name="list_pull_requests",
                description="List pull requests in a repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner",
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name",
                        },
                        "state": {
                            "type": "string",
                            "description": "Filter by state (open, closed, all)",
                        },
                    },
                    "required": ["owner", "repo"],
                },
            ),
            "get_file_contents": MCPTool(
                name="get_file_contents",
                description="Get file contents from a repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                        "path": {"type": "string", "description": "File path"},
                        "ref": {"type": "string", "description": "Branch or commit ref"},
                    },
                    "required": ["owner", "repo", "path"],
                },
            ),
        }

    async def invoke_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        tool_map = {
            "list_repositories": self._list_repositories,
            "get_repository": self._get_repository,
            "list_issues": self._list_issues,
            "get_issue": self._get_issue,
            "create_issue": self._create_issue,
            "list_pull_requests": self._list_pull_requests,
            "get_file_contents": self._get_file_contents,
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
            self._log.error(f"GitHub tool '{tool}' failed: {e}")
            return MCPToolResult(
                content=[{"type": "text", "text": f"Error: {e}"}],
                is_error=True,
            )

    async def _list_repositories(self, args: dict[str, Any]) -> dict:
        """List repositories for authenticated user."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._api_url}/user/repos",
                headers=self._headers,
                params={"per_page": 100},
            )
            response.raise_for_status()
            return {"repositories": response.json()}

    async def _get_repository(self, args: dict[str, Any]) -> dict:
        """Get repository details."""
        import httpx

        owner = args["owner"]
        repo = args["repo"]

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._api_url}/repos/{owner}/{repo}",
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    async def _list_issues(self, args: dict[str, Any]) -> dict:
        """List issues in a repository."""
        import httpx

        owner = args["owner"]
        repo = args["repo"]
        state = args.get("state", "open")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._api_url}/repos/{owner}/{repo}/issues",
                headers=self._headers,
                params={"state": state, "per_page": 100},
            )
            response.raise_for_status()
            return {"issues": response.json()}

    async def _get_issue(self, args: dict[str, Any]) -> dict:
        """Get a specific issue."""
        import httpx

        owner = args["owner"]
        repo = args["repo"]
        issue_number = args["issue_number"]

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._api_url}/repos/{owner}/{repo}/issues/{issue_number}",
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    async def _create_issue(self, args: dict[str, Any]) -> dict:
        """Create a new issue."""
        import httpx

        owner = args["owner"]
        repo = args["repo"]
        title = args["title"]
        body = args.get("body", "")
        labels = args.get("labels", [])

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._api_url}/repos/{owner}/{repo}/issues",
                headers=self._headers,
                json={"title": title, "body": body, "labels": labels},
            )
            response.raise_for_status()
            return response.json()

    async def _list_pull_requests(self, args: dict[str, Any]) -> dict:
        """List pull requests in a repository."""
        import httpx

        owner = args["owner"]
        repo = args["repo"]
        state = args.get("state", "open")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._api_url}/repos/{owner}/{repo}/pulls",
                headers=self._headers,
                params={"state": state, "per_page": 100},
            )
            response.raise_for_status()
            return {"pull_requests": response.json()}

    async def _get_file_contents(self, args: dict[str, Any]) -> dict:
        """Get file contents from a repository."""
        import httpx

        owner = args["owner"]
        repo = args["repo"]
        path = args["path"]
        ref = args.get("ref", "main")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._api_url}/repos/{owner}/{repo}/contents/{path}",
                headers=self._headers,
                params={"ref": ref},
            )
            response.raise_for_status()
            return response.json()

    async def list_resources(self) -> list[MCPResource]:
        from agentic_os.domain.mcp import MCPResource as MCPToolResource

        return [
            MCPToolResource(
                uri="github://repositories",
                name="GitHub Repositories",
                description="List of GitHub repositories",
                mime_type="application/json",
            ),
        ]

    async def read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "github://repositories":
            return await self._list_repositories({})
        raise ValueError(f"Unknown resource URI: {uri}")

    async def list_prompts(self) -> list[MCPPrompt]:
        from agentic_os.domain.mcp import MCPPrompt as MCPToolPrompt

        return [
            MCPToolPrompt(
                name="github_issue_summary",
                description="Generate a summary of GitHub issues",
                arguments=(
                    {
                        "name": "owner",
                        "description": "Repository owner",
                        "required": True,
                    },
                    {
                        "name": "repo",
                        "description": "Repository name",
                        "required": True,
                    },
                    {
                        "name": "state",
                        "description": "Issue state (open, closed)",
                        "required": False,
                    },
                ),
            ),
        ]

    async def get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if name == "github_issue_summary":
            owner = args.get("owner")
            repo = args.get("repo")
            state = args.get("state", "open")

            issues = await self._list_issues({"owner": owner, "repo": repo, "state": state})
            issue_list = issues.get("issues", [])

            summary = f"# GitHub Issue Summary for {owner}/{repo}\n\n"
            summary += f"State: {state}\n"
            summary += f"Total: {len(issue_list)}\n\n"

            for issue in issue_list[:10]:
                summary += f"- #{issue['number']}: {issue['title']} ({issue['state']})\n"

            return {
                "messages": [
                    {"role": "user", "content": summary},
                ],
            }

        raise ValueError(f"Unknown prompt: {name}")
