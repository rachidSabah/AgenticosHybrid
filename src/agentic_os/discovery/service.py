"""Runtime Discovery Engine — probes system binaries, local AI CLIs, and cloud APIs."""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from typing import Any

from agentic_os.discovery.models import BrainRecord, BrainRelationship, normalize_health_status
from agentic_os.infrastructure.logging import get_logger

log = get_logger("discovery.service")

# System binaries to probe dynamically
SYSTEM_BINARIES: list[dict[str, Any]] = [
    {
        "exe": "python",
        "aliases": ["python3", "py"],
        "display_name": "Python Runtime",
        "vendor": "python",
        "runtime": "python",
        "capabilities": ["code_generation", "testing", "script_execution"],
        "tags": ["python", "interpreter", "runtime"],
    },
    {
        "exe": "node",
        "aliases": ["nodejs"],
        "display_name": "Node.js Runtime",
        "vendor": "node",
        "runtime": "node",
        "capabilities": ["code_generation", "testing", "javascript_execution"],
        "tags": ["node", "javascript", "runtime"],
    },
    {
        "exe": "bun",
        "aliases": [],
        "display_name": "Bun Runtime",
        "vendor": "bun",
        "runtime": "bun",
        "capabilities": ["fast_execution", "bundling", "testing"],
        "tags": ["bun", "javascript", "runtime"],
    },
    {
        "exe": "deno",
        "aliases": [],
        "display_name": "Deno Runtime",
        "vendor": "deno",
        "runtime": "deno",
        "capabilities": ["secure_execution", "typescript", "testing"],
        "tags": ["deno", "typescript", "runtime"],
    },
    {
        "exe": "git",
        "aliases": [],
        "display_name": "Git VCS",
        "vendor": "git",
        "runtime": "native",
        "capabilities": ["vcs", "diff", "branching", "worktrees"],
        "tags": ["git", "vcs", "source_control"],
    },
    {
        "exe": "docker",
        "aliases": [],
        "display_name": "Docker Engine",
        "vendor": "docker",
        "runtime": "container",
        "capabilities": ["containerization", "isolation", "sandboxing"],
        "tags": ["docker", "container", "virtualization"],
    },
    {
        "exe": "cargo",
        "aliases": ["rustc"],
        "display_name": "Cargo (Rust)",
        "vendor": "rust",
        "runtime": "native",
        "capabilities": ["compilation", "native_build", "testing"],
        "tags": ["cargo", "rust", "native"],
    },
    {
        "exe": "go",
        "aliases": [],
        "display_name": "Go Toolchain",
        "vendor": "go",
        "runtime": "native",
        "capabilities": ["compilation", "concurrency", "testing"],
        "tags": ["go", "golang", "native"],
    },
]

# Local AI CLI Tools
LOCAL_AI_TOOLS: list[dict[str, Any]] = [
    {
        "exe": "ollama",
        "display_name": "Ollama Local Engine",
        "vendor": "ollama",
        "runtime": "native",
        "capabilities": ["local_inference", "chat", "embeddings"],
        "tags": ["ollama", "local", "privacy"],
        "models": ["llama3.2", "qwen2.5-coder", "deepseek-r1:8b"],
    },
    {
        "exe": "claude",
        "display_name": "Claude Code CLI",
        "vendor": "anthropic",
        "runtime": "native",
        "capabilities": ["chat", "code_generation", "file_editing", "terminal_access"],
        "tags": ["claude_code", "agent", "coding"],
        "models": ["claude-3-7-sonnet"],
    },
    {
        "exe": "gemini",
        "display_name": "Gemini CLI",
        "vendor": "google",
        "runtime": "node",
        "capabilities": ["chat", "multimodal", "code_generation"],
        "tags": ["gemini_cli", "google", "agent"],
        "models": ["gemini-2.5-flash"],
    },
    {
        "exe": "codex",
        "display_name": "OpenAI Codex CLI",
        "vendor": "openai",
        "runtime": "native",
        "capabilities": ["chat", "code_generation", "file_editing"],
        "tags": ["codex", "openai", "agent"],
        "models": ["codex-beta"],
    },
    {
        "exe": "aider",
        "display_name": "Aider Pair Programmer",
        "vendor": "aider",
        "runtime": "python",
        "capabilities": ["chat", "code_generation", "git_integration"],
        "tags": ["aider", "pair_programming", "git"],
        "models": [],
    },
    {
        "exe": "hermes",
        "display_name": "Hermes Agent",
        "vendor": "hermes",
        "runtime": "python",
        "capabilities": ["chat", "tool_use", "multi_agent"],
        "tags": ["hermes", "python", "agent"],
        "models": [],
    },
]

# Cloud Provider Credentials
CLOUD_PROVIDERS: list[dict[str, Any]] = [
    {
        "env_var": "OPENAI_API_KEY",
        "id": "cloud-openai",
        "display_name": "OpenAI Cloud API",
        "vendor": "openai",
        "runtime": "cloud",
        "models": ["gpt-4o", "gpt-4o-mini", "o1", "o3-mini"],
        "capabilities": ["chat", "code_generation", "reasoning", "embeddings"],
    },
    {
        "env_var": "ANTHROPIC_API_KEY",
        "id": "cloud-anthropic",
        "display_name": "Anthropic Claude API",
        "vendor": "anthropic",
        "runtime": "cloud",
        "models": ["claude-3-7-sonnet", "claude-3-5-sonnet", "claude-3-5-haiku"],
        "capabilities": ["chat", "deep_reasoning", "code_generation", "tool_use"],
    },
    {
        "env_var": "GEMINI_API_KEY",
        "id": "cloud-google",
        "display_name": "Google Gemini API",
        "vendor": "google",
        "runtime": "cloud",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
        "capabilities": ["chat", "long_context", "multimodal", "fast_inference"],
    },
    {
        "env_var": "GROQ_API_KEY",
        "id": "cloud-groq",
        "display_name": "Groq LPU Acceleration",
        "vendor": "groq",
        "runtime": "cloud",
        "models": [
            "llama-3.3-70b-versatile",
            "mixtral-8x7b-32768",
            "deepseek-r1-distill-llama-70b",
        ],
        "capabilities": ["ultra_fast_inference", "chat", "low_latency"],
    },
    {
        "env_var": "DEEPSEEK_API_KEY",
        "id": "cloud-deepseek",
        "display_name": "DeepSeek AI API",
        "vendor": "deepseek",
        "runtime": "cloud",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "capabilities": ["deep_reasoning", "math", "coding", "cost_efficient"],
    },
]


class RuntimeDiscoveryService:
    """Automated host discovery service for AgenticOS."""

    def __init__(self) -> None:
        self._brains: dict[str, BrainRecord] = {}
        self._relationships: list[BrainRelationship] = []
        self._lock: asyncio.Lock = asyncio.Lock()
        self._last_probe_time: float = 0.0

    async def _resolve_binary_path(self, exe: str, aliases: list[str] | None = None) -> str:
        """Find binary executable on PATH asynchronously without blocking."""
        names = [exe] + (aliases or [])
        for name in names:
            found = await asyncio.to_thread(shutil.which, name)
            if found:
                return str(found)
        return ""

    async def probe_all(self) -> list[BrainRecord]:
        """Inspect host binaries, AI CLIs, and cloud API keys."""
        discovered: list[BrainRecord] = []

        # 1. System Binaries Probe
        for spec in SYSTEM_BINARIES:
            path = await self._resolve_binary_path(spec["exe"], spec.get("aliases"))
            if path:
                record = BrainRecord(
                    id=f"sys-{spec['exe']}",
                    display_name=spec["display_name"],
                    brain_type="local_cli",
                    vendor=spec["vendor"],
                    runtime=spec["runtime"],
                    version="",
                    status="idle",
                    health=normalize_health_status(1.0),
                    capabilities=spec["capabilities"],
                    supported_models=[],
                    supported_tools=[spec["exe"]],
                    workspace=path,
                    tags=spec["tags"],
                )
                discovered.append(record)

        # 2. Local AI CLI Tools Probe
        for tool in LOCAL_AI_TOOLS:
            path = await self._resolve_binary_path(tool["exe"])
            if path:
                record = BrainRecord(
                    id=f"cli-{tool['exe']}",
                    display_name=tool["display_name"],
                    brain_type="local_cli",
                    vendor=tool["vendor"],
                    runtime=tool["runtime"],
                    version="",
                    status="idle",
                    health=normalize_health_status(1.0),
                    capabilities=tool["capabilities"],
                    supported_models=tool.get("models", []),
                    supported_tools=[tool["exe"]],
                    workspace=path,
                    tags=tool["tags"],
                )
                discovered.append(record)

        # 3. Cloud Provider API Credentials
        for cloud in CLOUD_PROVIDERS:
            has_key = bool(os.environ.get(cloud["env_var"]))
            if has_key:
                record = BrainRecord(
                    id=cloud["id"],
                    display_name=cloud["display_name"],
                    brain_type="cloud_api",
                    vendor=cloud["vendor"],
                    runtime="cloud",
                    version="API",
                    status="connected",
                    health=normalize_health_status(1.0),
                    capabilities=cloud["capabilities"],
                    supported_models=cloud["models"],
                    supported_tools=[],
                    workspace="cloud",
                    tags=[cloud["vendor"], "cloud_api", "remote"],
                )
                discovered.append(record)

        # 4. AgenticOS Core Orchestrator Record
        orchestrator_record = BrainRecord(
            id="agentic-orchestrator",
            display_name="AgenticOS Kernel Orchestrator",
            brain_type="orchestrator",
            vendor="agentic_os",
            runtime="python",
            version="1.0.0-rc10",
            status="executing",
            health="healthy",
            capabilities=["multi_agent_coordination", "dag_pipeline", "omniroute", "failover"],
            supported_models=[],
            supported_tools=["all"],
            workspace=os.getcwd(),
            tags=["orchestrator", "kernel", "core"],
        )
        discovered.insert(0, orchestrator_record)

        # Update cache and relationships
        async with self._lock:
            self._brains = {b.id: b for b in discovered}
            self._relationships = [
                BrainRelationship(
                    id=f"rel-orch-{b.id}",
                    source_id="agentic-orchestrator",
                    target_id=b.id,
                    relationship_type="executor" if b.brain_type != "orchestrator" else "self",
                    weight=1.0,
                    active=True,
                )
                for b in discovered
                if b.id != "agentic-orchestrator"
            ]
            self._last_probe_time = time.time()

        return discovered

    async def get_brains(self) -> list[BrainRecord]:
        """Return all discovered brains (trigger probe if cache empty)."""
        async with self._lock:
            if self._brains:
                return list(self._brains.values())
        return await self.probe_all()

    async def get_relationships(self) -> list[BrainRelationship]:
        """Return relationship edges."""
        async with self._lock:
            if self._relationships:
                return list(self._relationships)
        await self.probe_all()
        return list(self._relationships)

    async def rescan(self) -> dict[str, Any]:
        """Trigger background re-probing and return discovered count and duration."""
        t0 = time.perf_counter()
        brains = await self.probe_all()
        duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "discovered": len(brains),
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        }


# Singleton service instance
discovery_service = RuntimeDiscoveryService()
