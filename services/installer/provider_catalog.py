"""Provider Catalog — definitive registry of all supported AI runtimes.

Every agent the installer can discover, validate, and bind is defined here.
Search paths cover Windows, macOS, Linux. Add new providers here.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderDef:
    """Definition of a single discoverable AI runtime."""

    # Identity
    id: str  # e.g. "claude-code"
    display_name: str  # e.g. "Claude Code"
    engine_type: str  # maps to EngineType enum value

    # Executable names (in priority order)
    exe_names: tuple[str, ...] = ()

    # Well-known install paths (per-platform)
    install_paths: tuple[str, ...] = ()

    # Registry keys (Windows only)
    registry_keys: tuple[str, ...] = ()

    # Environment variables that might point to the executable
    env_vars: tuple[str, ...] = ()

    # Package manager package names
    pkg_npm: tuple[str, ...] = ()
    pkg_pip: tuple[str, ...] = ()
    pkg_cargo: tuple[str, ...] = ()
    pkg_go: tuple[str, ...] = ()
    pkg_winget: tuple[str, ...] = ()
    pkg_choco: tuple[str, ...] = ()
    pkg_scoop: tuple[str, ...] = ()
    pkg_brew: tuple[str, ...] = ()

    # Validation
    version_flags: tuple[str, ...] = ("--version",)
    help_flags: tuple[str, ...] = ("--help",)
    health_flags: tuple[str, ...] = ()
    capabilities_check: tuple[str, ...] = ()  # args to probe capabilities

    # Known capabilities (static, augmented by validation)
    known_capabilities: tuple[str, ...] = ()

    # Whether this is a local CLI tool vs remote API
    is_local_cli: bool = True

    # Metadata
    vendor: str = ""
    homepage: str = ""
    description: str = ""


# ── Platform helpers ──

def _is_windows() -> bool:
    return sys.platform == "win32"


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _localappdata() -> str:
    return os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.local/share"))


def _roaming() -> str:
    return os.environ.get("APPDATA", os.path.expanduser("~/.config"))


def _programfiles() -> str:
    return os.environ.get("ProgramFiles", r"C:\Program Files")


def _programfiles_x86() -> str:
    return os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")


def _home() -> str:
    return os.path.expanduser("~")


# ── The Catalog ──

PROVIDER_CATALOG: tuple[ProviderDef, ...] = (
    # ── Claude Code ──
    ProviderDef(
        id="claude-code",
        display_name="Claude Code",
        engine_type="CLAUDE_CODE",
        exe_names=("claude", "claude.exe"),
        install_paths=(
            os.path.join(_home(), ".npm-global"),
            os.path.join(_home(), "node_modules", ".bin"),
            os.path.join(_home(), ".local", "bin"),
            os.path.join(_home(), ".nvm", "current", "bin"),
        ),
        env_vars=("CLAUDE_PATH", "CLAUDE_CODE_PATH"),
        pkg_npm=("@anthropic-ai/claude-code",),
        version_flags=("--version",),
        health_flags=("--version",),
        known_capabilities=("coding", "reasoning", "terminal", "git", "filesystem"),
        vendor="Anthropic",
        description="Claude Code — AI coding assistant by Anthropic",
    ),
    # ── Claude CLI ──
    ProviderDef(
        id="claude-cli",
        display_name="Claude CLI",
        engine_type="CLAUDE_CODE",
        exe_names=("claude-cli", "claude-cli.exe"),
        env_vars=("CLAUDE_CLI_PATH",),
        pkg_npm=("@anthropic-ai/claude-cli",),
        version_flags=("--version",),
        known_capabilities=("coding", "reasoning", "terminal"),
        vendor="Anthropic",
        description="Claude CLI — command-line Claude client",
    ),
    # ── Hermes ──
    ProviderDef(
        id="hermes",
        display_name="Hermes",
        engine_type="HERMES",
        exe_names=("hermes", "hermes.exe"),
        install_paths=(
            os.path.join(_localappdata(), "hermes"),
            os.path.join(_home(), ".local", "bin"),
        ),
        env_vars=("HERMES_PATH", "HERMES_BIN"),
        pkg_npm=("@nousresearch/hermes",),
        pkg_pip=("hermes-agent",),
        pkg_cargo=("hermes",),
        version_flags=("--version",),
        health_flags=("version",),
        known_capabilities=("coding", "reasoning", "terminal", "filesystem", "git"),
        vendor="Nous Research",
        description="Hermes — general-purpose AI coding agent",
    ),
    # ── OpenCode ──
    ProviderDef(
        id="opencode",
        display_name="OpenCode",
        engine_type="OPENCODE",
        exe_names=("opencode", "opencode.exe"),
        install_paths=(
            os.path.join(_home(), ".opencode"),
            os.path.join(_home(), ".npm-global"),
            os.path.join(_home(), ".local", "bin"),
        ),
        env_vars=("OPENCODE_PATH",),
        pkg_npm=("opencode",),
        pkg_cargo=("opencode",),
        version_flags=("--version",),
        known_capabilities=("coding", "reasoning", "terminal", "git"),
        vendor="OpenCode AI",
        description="OpenCode — open-source AI coding agent",
    ),
    # ── AGY CLI (Antigravity) ──
    ProviderDef(
        id="agy",
        display_name="Antigravity CLI",
        engine_type="AGY_CLI",
        exe_names=("agy", "agy.exe"),
        install_paths=(
            os.path.join(_home(), ".agy"),
            os.path.join(_home(), ".npm-global"),
            os.path.join(_localappdata(), "antigravity"),
        ),
        env_vars=("AGY_PATH", "ANTIGRAVITY_PATH"),
        pkg_npm=("@antigravity/agy",),
        pkg_cargo=("antigravity-cli",),
        version_flags=("--version",),
        known_capabilities=("coding", "reasoning", "planning", "terminal", "git", "vision"),
        vendor="Antigravity",
        description="Antigravity CLI — AI agent framework by Antigravity",
    ),
    # ── Gemini CLI ──
    ProviderDef(
        id="gemini-cli",
        display_name="Gemini CLI",
        engine_type="GEMINI_CLI",
        exe_names=("gemini", "gemini.exe", "gemini-cli", "gemini-cli.exe"),
        install_paths=(
            os.path.join(_home(), ".npm-global"),
            os.path.join(_home(), ".gemini"),
        ),
        env_vars=("GEMINI_PATH", "GEMINI_CLI_PATH"),
        pkg_npm=("@google/gemini-cli",),
        version_flags=("--version",),
        known_capabilities=("coding", "reasoning", "vision", "planning"),
        vendor="Google",
        description="Gemini CLI — Google's AI coding assistant",
    ),
    # ── Codex CLI ──
    ProviderDef(
        id="codex",
        display_name="Codex CLI",
        engine_type="CODEX",
        exe_names=("codex", "codex.exe", "codex-cli", "codex-cli.exe"),
        install_paths=(
            os.path.join(_home(), ".npm-global"),
            os.path.join(_home(), ".codex"),
        ),
        env_vars=("CODEX_PATH",),
        pkg_npm=("@openai/codex",),
        version_flags=("--version",),
        known_capabilities=("coding", "reasoning", "terminal", "filesystem"),
        vendor="OpenAI",
        description="Codex CLI — OpenAI's coding agent",
    ),
    # ── Cursor CLI ──
    ProviderDef(
        id="cursor",
        display_name="Cursor CLI",
        engine_type="CURSOR",
        exe_names=("cursor", "cursor.exe"),
        install_paths=(
            os.path.join(_localappdata(), "cursor"),
            os.path.join(_programfiles(), "Cursor"),
            os.path.join(_home(), ".npm-global"),
        ),
        env_vars=("CURSOR_PATH",),
        version_flags=("--version",),
        known_capabilities=("coding", "terminal", "git"),
        vendor="Cursor",
        description="Cursor CLI — AI-first code editor",
    ),
    # ── Continue CLI ──
    ProviderDef(
        id="continue",
        display_name="Continue CLI",
        engine_type="CONTINUE",
        exe_names=("continue", "continue.exe"),
        env_vars=("CONTINUE_PATH",),
        pkg_npm=("continue",),
        version_flags=("--version",),
        known_capabilities=("coding", "reasoning", "terminal"),
        vendor="Continue",
        description="Continue — open-source AI code assistant",
    ),
    # ── Goose ──
    ProviderDef(
        id="goose",
        display_name="Goose",
        engine_type="GOOSE",
        exe_names=("goose", "goose.exe"),
        install_paths=(
            os.path.join(_home(), ".npm-global"),
            os.path.join(_home(), ".goose"),
        ),
        env_vars=("GOOSE_PATH",),
        pkg_npm=("goose",),
        pkg_cargo=("goose-cli",),
        version_flags=("--version",),
        known_capabilities=("coding", "terminal", "filesystem", "git"),
        vendor="Block",
        description="Goose — AI coding agent by Block",
    ),
    # ── Aider ──
    ProviderDef(
        id="aider",
        display_name="Aider",
        engine_type="AIDER",
        exe_names=("aider", "aider.exe"),
        install_paths=(
            os.path.join(_home(), ".local", "bin"),
            os.path.join(_home(), ".aider"),
        ),
        env_vars=("AIDER_PATH",),
        pkg_pip=("aider-chat",),
        version_flags=("--version",),
        known_capabilities=("coding", "planning", "git", "vision"),
        vendor="Paul Gauthier",
        description="Aider — AI pair programming in the terminal",
    ),
    # ── Open Interpreter ──
    ProviderDef(
        id="open-interpreter",
        display_name="Open Interpreter",
        engine_type="OPEN_INTERPRETER",
        exe_names=("interpreter", "interpreter.exe"),
        env_vars=("INTERPRETER_PATH",),
        pkg_pip=("open-interpreter",),
        version_flags=("--version",),
        known_capabilities=("coding", "terminal", "filesystem", "shell"),
        vendor="Open Interpreter",
        description="Open Interpreter — natural-language computer interface",
    ),
    # ── OpenHands ──
    ProviderDef(
        id="openhands",
        display_name="OpenHands",
        engine_type="OPENHANDS",
        exe_names=("openhands", "openhands.exe"),
        install_paths=(
            os.path.join(_home(), ".npm-global"),
            os.path.join(_home(), ".openhands"),
        ),
        env_vars=("OPENHANDS_PATH",),
        pkg_npm=("@openhands/openhands",),
        version_flags=("--version",),
        known_capabilities=("coding", "reasoning", "terminal", "web_browsing"),
        vendor="All Hands AI",
        description="OpenHands — AI software development platform",
    ),
    # ── Ollama ──
    ProviderDef(
        id="ollama",
        display_name="Ollama",
        engine_type="OLLAMA",
        exe_names=("ollama", "ollama.exe"),
        install_paths=(
            os.path.join(_home(), ".ollama"),
            os.path.join(_localappdata(), "ollama"),
            os.path.join(_programfiles(), "Ollama"),
        ),
        env_vars=("OLLAMA_HOST", "OLLAMA_PATH"),
        pkg_brew=("ollama",),
        pkg_scoop=("ollama",),
        version_flags=("--version",),
        health_flags=("--version",),
        known_capabilities=("local_llm", "model_serving", "embedding"),
        vendor="Ollama",
        description="Ollama — local LLM runner",
    ),
    # ── LM Studio ──
    ProviderDef(
        id="lm-studio",
        display_name="LM Studio",
        engine_type="CUSTOM",
        exe_names=("lm-studio", "lm-studio.exe", "lms", "lms.exe"),
        install_paths=(
            os.path.join(_localappdata(), "LM Studio"),
            os.path.join(_programfiles(), "LM Studio"),
        ),
        env_vars=("LM_STUDIO_PATH",),
        version_flags=("--version",),
        known_capabilities=("local_llm", "model_serving"),
        vendor="LM Studio",
        description="LM Studio — local LLM playground and server",
    ),
    # ── Qwen CLI ──
    ProviderDef(
        id="qwen",
        display_name="Qwen CLI",
        engine_type="QWEN",
        exe_names=("qwen", "qwen.exe", "qwen-cli", "qwen-cli.exe"),
        env_vars=("QWEN_PATH",),
        pkg_npm=("@qwen/qwen-cli",),
        pkg_pip=("qwen-cli",),
        version_flags=("--version",),
        known_capabilities=("coding", "reasoning", "vision"),
        vendor="Alibaba Cloud",
        description="Qwen CLI — Alibaba's Qwen coding assistant",
    ),
    # ── DeepSeek CLI ──
    ProviderDef(
        id="deepseek",
        display_name="DeepSeek CLI",
        engine_type="DEEPSEEK",
        exe_names=("deepseek", "deepseek.exe", "deepseek-cli", "deepseek-cli.exe"),
        env_vars=("DEEPSEEK_PATH",),
        pkg_npm=("@deepseek/cli",),
        version_flags=("--version",),
        known_capabilities=("coding", "reasoning", "vision"),
        vendor="DeepSeek",
        description="DeepSeek CLI — DeepSeek AI coding assistant",
    ),
    # ── vLLM ──
    ProviderDef(
        id="vllm",
        display_name="vLLM",
        engine_type="CUSTOM",
        exe_names=("vllm", "vllm.exe"),
        env_vars=("VLLM_PATH",),
        pkg_pip=("vllm",),
        version_flags=("--version",),
        known_capabilities=("model_serving", "local_llm"),
        vendor="vLLM",
        description="vLLM — high-throughput LLM serving",
    ),
    # ── Docker ──
    ProviderDef(
        id="docker",
        display_name="Docker",
        engine_type="DOCKER",
        exe_names=("docker", "docker.exe"),
        install_paths=(
            os.path.join(_programfiles(), "Docker", "Docker", "resources", "bin"),
            os.path.join(_programfiles(), "Docker"),
        ),
        env_vars=("DOCKER_HOST",),
        pkg_brew=("docker",),
        pkg_scoop=("docker",),
        version_flags=("--version",),
        known_capabilities=("container", "sandbox", "docker"),
        vendor="Docker Inc.",
        description="Docker — container runtime",
    ),
    # ── WSL ──
    ProviderDef(
        id="wsl",
        display_name="WSL",
        engine_type="WSL",
        exe_names=("wsl", "wsl.exe"),
        install_paths=(
            os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"),
        ),
        version_flags=("--version",),
        known_capabilities=("linux", "subsystem"),
        vendor="Microsoft",
        description="Windows Subsystem for Linux",
    ),
    # ── Cline ──
    ProviderDef(
        id="cline",
        display_name="Cline",
        engine_type="CLINE",
        exe_names=("cline", "cline.exe"),
        env_vars=("CLINE_PATH",),
        pkg_npm=("@cline/cline",),
        version_flags=("--version",),
        known_capabilities=("coding", "reasoning", "terminal", "filesystem"),
        vendor="Cline",
        description="Cline — autonomous coding agent",
    ),
    # ── Roo Code ──
    ProviderDef(
        id="roo-code",
        display_name="Roo Code",
        engine_type="ROO_CODE",
        exe_names=("roo", "roo.exe", "roo-code", "roo-code.exe"),
        env_vars=("ROO_PATH",),
        pkg_npm=("roo-code",),
        version_flags=("--version",),
        known_capabilities=("coding", "reasoning", "terminal"),
        vendor="Roo Code",
        description="Roo Code — AI coding agent",
    ),
    # ── AutoGen ──
    ProviderDef(
        id="autogen",
        display_name="AutoGen",
        engine_type="CUSTOM",
        exe_names=(),
        env_vars=("AUTOGEN_PATH",),
        pkg_pip=("pyautogen",),
        known_capabilities=("multi_agent", "orchestration", "coding", "reasoning"),
        is_local_cli=False,
        vendor="Microsoft",
        description="AutoGen — multi-agent conversation framework",
    ),
    # ── CrewAI ──
    ProviderDef(
        id="crewai",
        display_name="CrewAI",
        engine_type="CUSTOM",
        exe_names=("crewai", "crewai.exe"),
        env_vars=("CREWAI_PATH",),
        pkg_pip=("crewai",),
        pkg_npm=("crewai",),
        version_flags=("--version",),
        known_capabilities=("multi_agent", "orchestration", "coding"),
        vendor="CrewAI",
        description="CrewAI — multi-agent orchestration framework",
    ),
    # ── LangGraph CLI ──
    ProviderDef(
        id="langgraph",
        display_name="LangGraph CLI",
        engine_type="CUSTOM",
        exe_names=("langgraph", "langgraph.exe", "lg", "lg.exe"),
        env_vars=("LANGGRAPH_PATH",),
        pkg_pip=("langgraph-cli",),
        pkg_npm=("@langgraph/cli",),
        version_flags=("--version",),
        known_capabilities=("agent_framework", "state_machine", "orchestration"),
        vendor="LangChain",
        description="LangGraph CLI — agent orchestration framework",
    ),
)


def find_provider(provider_id: str) -> ProviderDef | None:
    """Look up a provider by its id."""
    for p in PROVIDER_CATALOG:
        if p.id == provider_id:
            return p
    return None


def providers_by_engine(engine_type: str) -> tuple[ProviderDef, ...]:
    """Get all providers matching an engine type."""
    return tuple(p for p in PROVIDER_CATALOG if p.engine_type == engine_type)


def all_provider_ids() -> list[str]:
    """Get all provider IDs for iteration."""
    return [p.id for p in PROVIDER_CATALOG]
