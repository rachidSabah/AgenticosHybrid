"""Validation Pipeline — deep validation of every discovered AI runtime.

Validation goes beyond simple executable existence to probe capabilities,
measure performance, detect features, and ensure the runtime is usable.
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass, field

from agentic_os.infrastructure.logging import get_logger
from services.installer.provider_catalog import ProviderDef

log = get_logger("installer.validator")


@dataclass
class ValidationResult:
    """Result of validating a single runtime."""

    provider_id: str
    executable_path: str | None = None
    version: str | None = None
    version_raw: str | None = None

    # Binary validation
    executable_exists: bool = False
    executable_is_file: bool = False
    executable_executable: bool = False

    # Runtime validation
    launches_success: bool = False
    version_command_success: bool = False
    help_command_success: bool = False
    health_command_success: bool = False
    exit_code: int | None = None

    # Performance
    launch_time_ms: float = 0.0
    version_response_time_ms: float = 0.0

    # Capabilities (detected at runtime)
    detected_capabilities: set[str] = field(default_factory=set)

    # Feature detection
    supports_streaming: bool = False
    supports_vision: bool = False
    supports_attachments: bool = False
    supports_code_execution: bool = False
    supports_shell: bool = False
    supports_web_browsing: bool = False

    # Models (if applicable)
    detected_models: list[str] = field(default_factory=list)

    # Overall
    passed: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Raw output
    raw_version_output: str = ""
    raw_help_output: str = ""


@dataclass
class ValidationReport:
    """Aggregate validation report for all discovered providers."""

    results: list[ValidationResult] = field(default_factory=list)
    total_found: int = 0
    total_validated: int = 0
    total_passed: int = 0
    total_failed: int = 0
    duration_seconds: float = 0.0

    @property
    def passed(self) -> list[ValidationResult]:
        return [r for r in self.results if r.passed]

    @property
    def failed(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.passed and r.executable_path]

    @property
    def not_found(self) -> list[str]:
        return [r.provider_id for r in self.results if not r.executable_path]


class ValidationPipeline:
    """Validates discovered AI runtimes through a multi-step pipeline.

    Stages:
        1. Binary validation — does the executable exist?
        2. Runtime validation — does it launch and respond?
        3. Capability detection — what can it do?
        4. Feature detection — streaming, vision, code execution?
    """

    def __init__(self, timeout: float = 15.0):
        self._timeout = timeout

    async def validate(
        self,
        provider: ProviderDef,
        executable_path: str | None = None,
    ) -> ValidationResult:
        """Run the full validation pipeline for a single provider."""
        result = ValidationResult(provider_id=provider.id)

        # Stage 1: Find executable if not provided
        exe = executable_path or self._find_executable(provider)
        result.executable_path = exe

        if not exe:
            result.errors.append("Executable not found")
            return result

        # Stage 1b: Binary checks
        result.executable_exists = os.path.exists(exe)
        result.executable_is_file = os.path.isfile(exe)
        result.executable_executable = (
            os.access(exe, os.X_OK) if platform.system() != "Windows" else True
        )

        if not result.executable_exists:
            result.errors.append(f"Path does not exist: {exe}")
            return result

        # Stage 2: Runtime validation
        await self._run_validation(provider, exe, result)

        # Stage 3: Capability detection from output
        self._detect_capabilities(provider, result)

        # Stage 4: Feature detection from output
        self._detect_features(result)

        # Overall pass/fail
        result.passed = result.executable_exists and result.version_command_success

        return result

    def _find_executable(self, provider: ProviderDef) -> str | None:
        """Search for a provider's executable."""
        # Check PATH first
        for name in provider.exe_names:
            exe = shutil.which(name)
            if exe:
                return exe

        # Check well-known install paths
        for path in provider.install_paths:
            for name in provider.exe_names:
                full = os.path.join(path, name)
                if os.path.isfile(full):
                    return full

        # Check environment variables
        for var in provider.env_vars:
            val = os.environ.get(var)
            if val and os.path.isfile(val):
                return val
            if val:
                # Could be a directory — check for exe inside
                for name in provider.exe_names:
                    full = os.path.join(val, name)
                    if os.path.isfile(full):
                        return full

        return None

    async def _run_command(
        self, cmd: list[str], timeout: float | None = None
    ) -> tuple[str, str, int | None, float]:
        """Run a command and return (stdout, stderr, exit_code, elapsed_ms).

        The subprocess runs inside an executor thread (``asyncio.to_thread``)
        so validation works under SelectorEventLoop on Windows, which does
        not support ``asyncio`` subprocesses (``create_subprocess_exec``
        raises ``NotImplementedError`` there).
        """
        t0 = time.perf_counter()
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=timeout or self._timeout,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            return (
                result.stdout.decode("utf-8", errors="replace"),
                result.stderr.decode("utf-8", errors="replace"),
                result.returncode,
                elapsed,
            )
        except subprocess.TimeoutExpired:
            elapsed = (time.perf_counter() - t0) * 1000
            return "", "TIMEOUT", None, elapsed
        except FileNotFoundError:
            return "", "NOT_FOUND", None, 0.0
        except PermissionError:
            return "", "PERMISSION_DENIED", None, 0.0

    async def _run_validation(
        self, provider: ProviderDef, exe: str, result: ValidationResult
    ) -> None:
        """Run version, help, and health commands."""
        # Version command
        if provider.version_flags:
            cmd = [exe, *provider.version_flags]
            stdout, stderr, code, elapsed = await self._run_command(cmd)
            result.raw_version_output = stdout
            result.version_response_time_ms = elapsed
            if code == 0 and stdout.strip():
                result.version_command_success = True
                result.version = stdout.strip().split("\n")[0].strip()
                result.version_raw = stdout.strip()
                result.launch_time_ms = elapsed
            else:
                result.errors.append(f"Version command failed (exit={code}): {stderr[:200]}")

        # Help command
        if provider.help_flags:
            cmd = [exe, *provider.help_flags]
            stdout, stderr, code, elapsed = await self._run_command(cmd, timeout=5.0)
            result.raw_help_output = stdout
            if code == 0:
                result.help_command_success = True

        # Health command (provider-specific)
        if provider.health_flags:
            cmd = [exe, *provider.health_flags]
            stdout, stderr, code, elapsed = await self._run_command(cmd)
            result.health_command_success = code == 0

    def _detect_capabilities(self, provider: ProviderDef, result: ValidationResult) -> None:
        """Detect capabilities from known capabilities + output analysis."""
        # Start with known capabilities
        result.detected_capabilities = set(provider.known_capabilities)

        # Augment from version output analysis
        output = (result.raw_version_output + result.raw_help_output).lower()

        capability_signals: dict[str, list[str]] = {
            "vision": ["vision", "image", "visual", "ocr", "screenshot"],
            "streaming": ["stream", "sse", "websocket"],
            "code_execution": ["sandbox", "execute", "python", "node", "runtime"],
            "web_browsing": ["browser", "web", "search", "fetch", "curl"],
            "terminal": ["terminal", "shell", "bash", "zsh", "cmd"],
            "filesystem": ["file", "read", "write", "ls", "mkdir"],
            "git": ["git", "commit", "branch", "pr", "clone"],
            "docker": ["docker", "container", "compose"],
            "memory": ["memory", "context", "history", "remember"],
            "mcp": ["mcp", "tool", "function call", "plugin"],
        }

        for capability, signals in capability_signals.items():
            if any(s in output for s in signals):
                result.detected_capabilities.add(capability)

    def _detect_features(self, result: ValidationResult) -> None:
        """Detect specific features from output."""
        output = (result.raw_version_output + result.raw_help_output).lower()

        result.supports_streaming = any(
            s in output for s in ["stream", "sse", "--stream", "websocket"]
        )
        result.supports_vision = any(
            s in output for s in ["vision", "image", "visual", "screenshot"]
        )
        result.supports_attachments = any(s in output for s in ["attach", "upload", "file"])
        result.supports_code_execution = any(s in output for s in ["execute", "sandbox", "run"])
        result.supports_shell = any(s in output for s in ["shell", "bash", "terminal"])
        result.supports_web_browsing = any(
            s in output for s in ["browser", "web", "search", "fetch"]
        )

    async def validate_many(
        self,
        providers: list[ProviderDef],
        found_paths: dict[str, str] | None = None,
    ) -> ValidationReport:
        """Validate multiple providers and return an aggregate report."""
        t0 = time.perf_counter()
        report = ValidationReport()

        tasks = []
        for p in providers:
            exe = found_paths.get(p.id) if found_paths else None
            tasks.append(self.validate(p, exe))

        results = await asyncio.gather(*tasks)
        report.results = list(results)
        report.total_found = sum(1 for r in results if r.executable_path)
        report.total_validated = sum(1 for r in results if r.executable_exists)
        report.total_passed = sum(1 for r in results if r.passed)
        report.total_failed = sum(1 for r in results if r.executable_path and not r.passed)
        report.duration_seconds = time.perf_counter() - t0

        return report
