"""Provider execution strategy framework.

Each AI CLI has a different invocation model — different argument flags,
different prompt delivery methods (stdin vs arg vs file), different output
formats. This module defines a strategy interface and concrete strategies
for every supported CLI agent.

The ProviderFactory creates the correct strategy + adapter for a given
provider kind. auto_bind calls the factory instead of manually
instantiating adapter classes.

Architecture:
  ProviderExecutionStrategy (interface)
    ├── build_command(prompt) → list[str]   (CLI argv)
    ├── build_stdin(prompt) → bytes | None  (stdin data, or None)
    ├── parse_output(stdout, stderr) → str  (extract result)
    ├── health_command() → list[str] | None (fastest non-interactive check)
    └── timeout_s → float                   (per-strategy timeout)

  Concrete strategies (one per CLI):
    ClaudeExecutionStrategy      — claude -p "{prompt}" --output-format text
    HermesExecutionStrategy      — hermes -p "{prompt}" --output-format text
    OpenCodeExecutionStrategy    — opencode run "{prompt}"
    CodexExecutionStrategy       — codex --prompt "{prompt}"
    AiderExecutionStrategy       — aider --message "{prompt}" --no-auto-commits
    GeminiExecutionStrategy      — gemini -p "{prompt}"
    AGYExecutionStrategy         — agy run "{prompt}"
    OllamaExecutionStrategy      — ollama run llama3 (stdin: prompt)
    GenericExecutionStrategy     — {binary} (stdin: prompt) [fallback]
"""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from agentic_os.domain.agent import Agent, ProviderInfo, Task
from agentic_os.infrastructure.logging import get_logger

log = get_logger("provider.strategy")


# ── Strategy Interface ─────────────────────────────────────────────────


class ProviderExecutionStrategy(ABC):
    """Interface for CLI-specific execution strategies.

    Each strategy knows how to:
      - Build the correct CLI command (argv) for a given prompt
      - Build stdin data if the CLI reads from stdin
      - Parse stdout/stderr into a result string
      - Build a fast health-check command
      - Report the appropriate timeout
    """

    @property
    @abstractmethod
    def kind(self) -> str:
        """Provider kind identifier (e.g. 'claude_code', 'hermes')."""

    @property
    def timeout_s(self) -> float:
        """Execution timeout in seconds. Default 120s."""
        return 120.0

    @property
    def supports_streaming(self) -> bool:
        """Whether this strategy supports incremental stdout streaming."""
        return True

    @abstractmethod
    def build_command(self, task: Task, bin_path: str) -> list[str]:
        """Build the CLI argv list. Does NOT include the prompt (use build_stdin)."""

    def build_stdin(self, task: Task) -> bytes | None:
        """Build stdin input for CLIs that read from stdin. None = pass prompt as arg."""
        return None

    def parse_output(self, stdout: bytes, stderr: bytes, task: Task) -> str:
        """Parse stdout/stderr into a result string. Default: decode stdout."""
        return stdout.decode("utf-8", errors="replace").strip()

    def health_command(self, bin_path: str) -> list[str] | None:
        """Build a fast non-interactive health-check command. None = use shutil.which only."""
        return None

    def build_prompt(self, task: Task) -> str:
        """Compose the final CLI prompt from the task.

        Preserves BOTH the original user request (task.user_prompt) AND
        the planner-generated task description (task.description).
        """
        user_prompt = (task.user_prompt or "").strip()
        description = (task.description or "").strip()
        title = (task.title or "").strip()

        if not user_prompt:
            return f"{title}\n\n{description}".strip()

        sections = [
            "=" * 50,
            "Mission Request",
            user_prompt,
            "",
            "=" * 50,
            "Assigned Task",
            description,
            "",
            "=" * 50,
            "Task Title",
            title,
            "=" * 50,
        ]
        return "\n".join(sections)

    def build_env(self, api_key: str = "") -> dict[str, str]:
        """Build the environment for the subprocess."""
        env = dict(os.environ)
        if api_key:
            env[self._api_key_env_name()] = api_key
        return env

    def _api_key_env_name(self) -> str:
        """Override to set the API key env var name for this provider."""
        return ""


# ── Concrete Strategies ────────────────────────────────────────────────


class ClaudeExecutionStrategy(ProviderExecutionStrategy):
    """Claude Code CLI: `claude -p "{prompt}" --output-format text`"""

    @property
    def kind(self) -> str:
        return "claude_code"

    def build_command(self, task: Task, bin_path: str) -> list[str]:
        return [bin_path, "-p", self.build_prompt(task), "--output-format", "text"]

    def health_command(self, bin_path: str) -> list[str] | None:
        return [bin_path, "--version"]

    def _api_key_env_name(self) -> str:
        return "ANTHROPIC_API_KEY"


class HermesExecutionStrategy(ProviderExecutionStrategy):
    """Hermes CLI: `hermes -p "{prompt}" --output-format text`"""

    @property
    def kind(self) -> str:
        return "hermes"

    def build_command(self, task: Task, bin_path: str) -> list[str]:
        return [bin_path, "-p", self.build_prompt(task), "--output-format", "text"]

    def health_command(self, bin_path: str) -> list[str] | None:
        # Use --help instead of --version: hermes --version performs a network
        # update check that can take 2-75s depending on connectivity, causing
        # healthcheck timeouts. --help exits immediately with no network I/O.
        return [bin_path, "--help"]

    def _api_key_env_name(self) -> str:
        return "HERMES_CONFIG"


class OpenCodeExecutionStrategy(ProviderExecutionStrategy):
    """OpenCode CLI: `opencode run "{prompt}"`"""

    @property
    def kind(self) -> str:
        return "opencode"

    def build_command(self, task: Task, bin_path: str) -> list[str]:
        return [bin_path, "run", self.build_prompt(task)]

    def health_command(self, bin_path: str) -> list[str] | None:
        return [bin_path, "--version"]


class CodexExecutionStrategy(ProviderExecutionStrategy):
    """Codex CLI: `codex --prompt "{prompt}"`"""

    @property
    def kind(self) -> str:
        return "codex"

    def build_command(self, task: Task, bin_path: str) -> list[str]:
        return [bin_path, "--prompt", self.build_prompt(task)]

    def health_command(self, bin_path: str) -> list[str] | None:
        return [bin_path, "--version"]


class AiderExecutionStrategy(ProviderExecutionStrategy):
    """Aider: `aider --message "{prompt}" --no-auto-commits`"""

    @property
    def kind(self) -> str:
        return "aider"

    @property
    def timeout_s(self) -> float:
        return 180.0  # Aider can be slow (starts a model)

    def build_command(self, task: Task, bin_path: str) -> list[str]:
        return [bin_path, "--message", self.build_prompt(task), "--no-auto-commits"]

    def health_command(self, bin_path: str) -> list[str] | None:
        return [bin_path, "--version"]


class GeminiExecutionStrategy(ProviderExecutionStrategy):
    """Gemini CLI: `gemini -p "{prompt}"`"""

    @property
    def kind(self) -> str:
        return "gemini_cli"

    @property
    def timeout_s(self) -> float:
        return 180.0  # Gemini CLI can be slow to initialize

    def build_command(self, task: Task, bin_path: str) -> list[str]:
        return [bin_path, "-p", self.build_prompt(task)]

    def health_command(self, bin_path: str) -> list[str] | None:
        # Use --version (exits in ~6s on Windows). --help triggers interactive
        # auth/OAuth flow on first run and can hang indefinitely in a subprocess.
        return [bin_path, "--version"]


class AGYExecutionStrategy(ProviderExecutionStrategy):
    """AGY CLI: `agy run "{prompt}"`"""

    @property
    def kind(self) -> str:
        return "antigravity"

    def build_command(self, task: Task, bin_path: str) -> list[str]:
        return [bin_path, "run", self.build_prompt(task)]

    def health_command(self, bin_path: str) -> list[str] | None:
        return [bin_path, "--version"]


class OllamaExecutionStrategy(ProviderExecutionStrategy):
    """Ollama: `ollama run {model}` (prompt via stdin)"""

    @property
    def kind(self) -> str:
        return "ollama"

    @property
    def timeout_s(self) -> float:
        return 300.0  # Local models can be slow

    def build_command(self, task: Task, bin_path: str) -> list[str]:
        # Ollama reads prompt from stdin when running a model
        return [bin_path, "run", "llama3"]

    def build_stdin(self, task: Task) -> bytes | None:
        return self.build_prompt(task).encode("utf-8")

    def health_command(self, bin_path: str) -> list[str] | None:
        return [bin_path, "list"]

    def parse_output(self, stdout: bytes, stderr: bytes, task: Task) -> str:
        # Ollama prints the prompt back via stderr — extract stdout only
        return stdout.decode("utf-8", errors="replace").strip()


class GenericExecutionStrategy(ProviderExecutionStrategy):
    """Fallback strategy: `{binary}` (prompt via stdin).

    Used for unknown/auto-detected agents. Works with CLIs that accept
    a prompt on stdin. If the CLI doesn't read stdin, the process will
    timeout and the error will be reported clearly.
    """

    def __init__(self, kind: str = "generic") -> None:
        self._kind = kind

    @property
    def kind(self) -> str:
        return self._kind

    def build_command(self, task: Task, bin_path: str) -> list[str]:
        return [bin_path]

    def build_stdin(self, task: Task) -> bytes | None:
        return self.build_prompt(task).encode("utf-8")


# ── Strategy Registry ──────────────────────────────────────────────────


# Maps provider kind → strategy class
_STRATEGY_REGISTRY: dict[str, type[ProviderExecutionStrategy]] = {
    "claude_code": ClaudeExecutionStrategy,
    "hermes": HermesExecutionStrategy,
    "opencode": OpenCodeExecutionStrategy,
    "codex": CodexExecutionStrategy,
    "aider": AiderExecutionStrategy,
    "gemini_cli": GeminiExecutionStrategy,
    "antigravity": AGYExecutionStrategy,
    "ollama": OllamaExecutionStrategy,
    "nvidia_nim": GenericExecutionStrategy,
}


def get_strategy(kind: str) -> ProviderExecutionStrategy:
    """Get the execution strategy for a provider kind.

    Falls back to GenericExecutionStrategy for unknown kinds.
    """
    cls = _STRATEGY_REGISTRY.get(kind)
    if cls is not None:
        return cls()
    return GenericExecutionStrategy(kind=kind)


def register_strategy(kind: str, strategy_cls: type[ProviderExecutionStrategy]) -> None:
    """Register a custom strategy for a provider kind."""
    _STRATEGY_REGISTRY[kind] = strategy_cls


# ── Strategy-Based Provider Adapter ────────────────────────────────────


@dataclass
class ProviderAdapterConfig:
    """Configuration for a strategy-based provider adapter."""

    bin_path: str = ""
    name: str = ""
    kind: str = "generic"
    display_name: str = ""
    capabilities: list[str] = field(default_factory=list)
    api_key: str = ""


class StrategyBasedProvider:
    """Provider adapter that delegates to an execution strategy.

    This replaces the individual provider classes (ClaudeCodeProvider,
    HermesProvider, GenericCLIProvider) with a single adapter that uses
    a strategy object for CLI-specific behavior.

    The strategy determines:
      - How to build the CLI command
      - Whether to use stdin or args for the prompt
      - How to parse the output
      - What health-check command to use
      - What timeout to apply
    """

    def __init__(self, config: ProviderAdapterConfig) -> None:
        self._config = config
        self._strategy = get_strategy(config.kind)
        self.info = ProviderInfo(
            name=config.name or f"auto:{config.bin_path}",
            kind=config.kind,
            supports_streaming=self._strategy.supports_streaming,
            supports_tools=True,
            capabilities=config.capabilities,
        )

    @property
    def strategy(self) -> ProviderExecutionStrategy:
        return self._strategy

    @property
    def bin_path(self) -> str:
        return self._config.bin_path

    async def execute(
        self, agent: Agent, task: Task, on_output=None, cwd: str | None = None
    ) -> str:
        """Execute a task using the strategy's CLI invocation.

        If ``on_output`` is provided, it's called for each line of
        stdout/stderr as it arrives (real-time streaming). The callback
        receives (line: str, stream: str) where stream is "stdout" or
        "stderr".

        If ``cwd`` is provided, the CLI subprocess runs in that directory
        (used for git worktree isolation).
        """
        import asyncio

        resolved_bin = shutil.which(self._config.bin_path) or self._config.bin_path
        if not shutil.which(resolved_bin):
            raise RuntimeError(
                f"CLI binary '{self._config.bin_path}' not found on PATH. Kind: {self._config.kind}"
            )

        cmd = self._strategy.build_command(task, resolved_bin)
        stdin_data = self._strategy.build_stdin(task)
        env = self._strategy.build_env(self._config.api_key)
        timeout = self._strategy.timeout_s

        log.info(
            "provider.execute",
            kind=self._config.kind,
            binary=self._config.bin_path,
            agent=agent.id,
            task=task.id,
            cmd_len=len(cmd),
            has_stdin=stdin_data is not None,
            timeout=timeout,
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else asyncio.subprocess.DEVNULL,
            env=env,
            cwd=cwd,
        )

        # If no streaming callback, use the original communicate() path
        if on_output is None:
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=stdin_data),
                    timeout=timeout,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                raise RuntimeError(
                    f"{self._config.bin_path} ({self._config.kind}) timed out after {timeout}s"
                ) from None

            if proc.returncode != 0:
                stderr_text = stderr.decode("utf-8", errors="replace").strip()[:200]
                raise RuntimeError(
                    f"{self._config.bin_path} ({self._config.kind}) "
                    f"exited {proc.returncode}: {stderr_text}"
                )

            result = self._strategy.parse_output(stdout, stderr, task)
            return result or f"[{self._config.kind}] completed '{task.title}'"

        # Streaming path: read stdout/stderr line-by-line
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        async def _read_stream(stream, stream_name: str, store: list[str]):
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip("\n\r")
                store.append(decoded)
                try:
                    on_output(decoded, stream_name)
                except Exception:
                    pass  # don't let callback errors crash execution

        try:
            # Write stdin if needed, then read streams concurrently
            async def _feed_stdin():
                if stdin_data is not None and proc.stdin:
                    proc.stdin.write(stdin_data)
                    await proc.stdin.drain()
                    proc.stdin.close()

            await asyncio.wait_for(
                asyncio.gather(
                    _feed_stdin(),
                    _read_stream(proc.stdout, "stdout", stdout_lines),
                    _read_stream(proc.stderr, "stderr", stderr_lines),
                    proc.wait(),
                ),
                timeout=timeout,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(
                f"{self._config.bin_path} ({self._config.kind}) timed out after {timeout}s"
            ) from None

        stdout_bytes = "\n".join(stdout_lines).encode()
        stderr_bytes = "\n".join(stderr_lines).encode()

        if proc.returncode != 0:
            stderr_text = "\n".join(stderr_lines).strip()[:200]
            raise RuntimeError(
                f"{self._config.bin_path} ({self._config.kind}) "
                f"exited {proc.returncode}: {stderr_text}"
            )

        result = self._strategy.parse_output(stdout_bytes, stderr_bytes, task)
        return result or f"[{self._config.kind}] completed '{task.title}'"

    async def healthcheck(self) -> bool:
        """Check if the CLI binary is available and healthy."""
        if not shutil.which(self._config.bin_path):
            return False

        health_cmd = self._strategy.health_command(self._config.bin_path)
        if health_cmd is None:
            return True  # Binary exists, that's sufficient

        import asyncio
        import subprocess

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                health_cmd,
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False


# ── Provider Factory ───────────────────────────────────────────────────


class ProviderFactory:
    """Factory for creating provider adapters from a kind string.

    Replaces the manual if/elif/else adapter instantiation in auto_bind.py.
    """

    @staticmethod
    def create(
        kind: str,
        bin_path: str,
        name: str = "",
        display_name: str = "",
        capabilities: list[str] | None = None,
        api_key: str = "",
    ) -> StrategyBasedProvider:
        """Create a provider adapter for the given kind.

        Args:
            kind: Provider kind (e.g. 'claude_code', 'hermes', 'opencode')
            bin_path: CLI binary name or path
            name: Provider registry name
            display_name: Human-readable name
            capabilities: List of capability strings
            api_key: Optional API key

        Returns:
            A StrategyBasedProvider configured with the correct strategy.
        """
        config = ProviderAdapterConfig(
            bin_path=bin_path,
            name=name or f"auto:{bin_path}",
            kind=kind,
            display_name=display_name or bin_path,
            capabilities=capabilities or ["coding", "reasoning"],
            api_key=api_key,
        )
        return StrategyBasedProvider(config)

    @staticmethod
    def supported_kinds() -> list[str]:
        """Return all supported provider kinds."""
        return list(_STRATEGY_REGISTRY.keys()) + ["generic"]

    @staticmethod
    def is_supported(kind: str) -> bool:
        """Check if a provider kind is supported."""
        return kind in _STRATEGY_REGISTRY or kind == "generic"
