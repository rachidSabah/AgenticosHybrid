from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from core.contracts.execution_engine import EngineDiscoveryResult, EngineType
from core.logging import get_logger

_log = get_logger(__name__)

__all__ = [
    "EngineDiscovery",
    "discovery_result_from_dict",
]

# Mapping of EngineType to known binary names to search for
_ENGINE_BINARIES: dict[EngineType, list[str]] = {
    EngineType.CLAUDE_CODE: ["claude"],
    EngineType.GEMINI_CLI: ["gemini", "gemini-cli"],
    EngineType.CODEX_CLI: ["codex", "openai-codex"],
    EngineType.HERMES: ["hermes", "hermes-daemon"],
    EngineType.OPENHANDS: ["openhands", "openhands-cli"],
    EngineType.AIDER: ["aider"],
    EngineType.CONTINUE: ["continue", "continue-cli"],
    EngineType.CLINE: ["cline"],
    EngineType.ROO_CODE: ["roo", "roo-cli", "roo-code"],
}

# Common install directories (per-platform)
_COMMON_INSTALL_DIRS_WIN = [
    Path(os.environ.get("ProgramFiles", "C:\\Program Files")),
    Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")),
    Path(os.environ.get("LocalAppData", Path.home() / "AppData" / "Local")),
    Path(os.environ.get("AppData", Path.home() / "AppData" / "Roaming")),
    Path(os.environ.get("USERPROFILE", "C:\\Users\\Default")) / ".local" / "bin",
    Path(os.environ.get("USERPROFILE", "C:\\Users\\Default")) / "bin",
    Path("C:\\ProgramData\\chocolatey\\bin"),
    Path("C:\\tools"),
]

_COMMON_INSTALL_DIRS_NIX = [
    Path("/usr/local/bin"),
    Path("/usr/bin"),
    Path("/opt"),
    Path.home() / ".local" / "bin",
    Path.home() / "bin",
]

# Windows Registry paths to check for tool installations
_WIN_REGISTRY_PATHS: list[tuple[str, str, str]] = [
    (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
        "claude.exe",
        EngineType.CLAUDE_CODE.value,
    ),
    (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
        "codex.exe",
        EngineType.CODEX_CLI.value,
    ),
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths", "aider.exe", EngineType.AIDER.value),
]


def _is_executable(path: Path) -> bool:
    return path.is_file() and (
        path.suffix.lower() in (".exe", ".cmd", ".bat", ".ps1") or os.name != "nt"
    )


def _check_path(engine_type: EngineType, binary_names: list[str]) -> EngineDiscoveryResult | None:
    path_env = os.environ.get("PATH", "")
    for directory in path_env.split(os.pathsep):
        if not directory:
            continue
        for name in binary_names:
            full = Path(directory) / name
            if full.is_file():
                version = _get_version(full, engine_type)
                return EngineDiscoveryResult(
                    engine_type=engine_type,
                    name=engine_type.value,
                    binary_path=str(full),
                    version=version,
                    found=True,
                    healthy=version is not None,
                    source="path",
                )
            if os.name == "nt":
                for ext in (".exe", ".cmd", ".bat", ".ps1"):
                    full_ext = Path(directory) / f"{name}{ext}"
                    if full_ext.is_file():
                        version = _get_version(full_ext, engine_type)
                        return EngineDiscoveryResult(
                            engine_type=engine_type,
                            name=engine_type.value,
                            binary_path=str(full_ext),
                            version=version,
                            found=True,
                            healthy=version is not None,
                            source="path",
                        )
    return None


def _check_common_dirs(
    engine_type: EngineType, binary_names: list[str]
) -> EngineDiscoveryResult | None:
    dirs = _COMMON_INSTALL_DIRS_WIN if os.name == "nt" else _COMMON_INSTALL_DIRS_NIX
    for directory in dirs:
        for name in binary_names:
            for entry in directory.iterdir() if directory.is_dir() else []:
                if entry.name.startswith(name) and (entry.is_file() or _is_executable(entry)):
                    version = _get_version(entry, engine_type)
                    return EngineDiscoveryResult(
                        engine_type=engine_type,
                        name=engine_type.value,
                        binary_path=str(entry),
                        version=version,
                        found=True,
                        healthy=version is not None,
                        source="install_dir",
                    )
    return None


def _get_version(binary_path: Path, engine_type: EngineType) -> str | None:
    try:
        version_flags = {
            EngineType.CLAUDE_CODE: ["--version"],
            EngineType.GEMINI_CLI: ["--version"],
            EngineType.CODEX_CLI: ["--version"],
            EngineType.HERMES: ["--version"],
            EngineType.AIDER: ["--version"],
        }
        flags = version_flags.get(engine_type, ["--version"])
        result = subprocess.run(
            [str(binary_path), *flags],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (result.stdout or result.stderr).strip()
        return output if output else None
    except Exception:
        return None


class EngineDiscovery:
    def __init__(self) -> None:
        self._discovered: dict[str, EngineDiscoveryResult] = {}

    async def discover_all(self) -> list[EngineDiscoveryResult]:
        results: list[EngineDiscoveryResult] = []
        for engine_type, binary_names in _ENGINE_BINARIES.items():
            result = await self.discover(engine_type, binary_names)
            if result and result.found:
                results.append(result)
        return results

    async def discover(
        self, engine_type: EngineType, binary_names: list[str] | None = None
    ) -> EngineDiscoveryResult:
        names = binary_names or _ENGINE_BINARIES.get(engine_type, [])
        result = _check_path(engine_type, names)
        if result and result.found:
            self._discovered[engine_type.value] = result
            return result

        result = _check_common_dirs(engine_type, names)
        if result and result.found:
            self._discovered[engine_type.value] = result
            return result

        result = await self._check_wsl(engine_type, names)
        if result and result.found:
            self._discovered[engine_type.value] = result
            return result

        result = await self._check_docker(engine_type, names)
        if result and result.found:
            self._discovered[engine_type.value] = result
            return result

        result = self._check_registry(engine_type)
        if result and result.found:
            self._discovered[engine_type.value] = result
            return result

        result = self._check_env_vars(engine_type)
        if result and result.found:
            self._discovered[engine_type.value] = result
            return result

        not_found = EngineDiscoveryResult(
            engine_type=engine_type,
            name=engine_type.value,
            found=False,
            error=f"{engine_type.value} not found on system",
        )
        self._discovered[engine_type.value] = not_found
        return not_found

    async def _check_wsl(
        self, engine_type: EngineType, binary_names: list[str]
    ) -> EngineDiscoveryResult | None:
        try:
            for name in binary_names:
                result = subprocess.run(
                    ["wsl", "which", name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    wsl_path = result.stdout.strip()
                    version = None
                    try:
                        v = subprocess.run(
                            ["wsl", wsl_path, "--version"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        version = (v.stdout or v.stderr).strip()
                    except Exception:
                        pass
                    return EngineDiscoveryResult(
                        engine_type=engine_type,
                        name=engine_type.value,
                        binary_path=wsl_path,
                        version=version,
                        found=True,
                        healthy=True,
                        source="wsl",
                    )
        except FileNotFoundError:
            pass
        except Exception as e:
            _log.debug("WSL check failed for %s: %s", engine_type, e)
        return None

    async def _check_docker(
        self, engine_type: EngineType, binary_names: list[str]
    ) -> EngineDiscoveryResult | None:
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None
            containers = result.stdout.strip().splitlines()
            for name in binary_names:
                matching = [c for c in containers if name.lower() in c.lower()]
                if matching:
                    return EngineDiscoveryResult(
                        engine_type=engine_type,
                        name=engine_type.value,
                        found=True,
                        healthy=True,
                        source="docker",
                        extra={"container": matching[0]},
                    )
        except FileNotFoundError:
            pass
        except Exception as e:
            _log.debug("Docker check failed for %s: %s", engine_type, e)
        return None

    def _check_registry(self, engine_type: EngineType) -> EngineDiscoveryResult | None:
        if os.name != "nt":
            return None
        try:
            import winreg
        except ImportError:
            return None
        for key_path, value_name, _ in _WIN_REGISTRY_PATHS:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                    for i in range(winreg.QueryInfoKey(key)[1]):
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                            if name.lower() == value_name.lower():
                                return EngineDiscoveryResult(
                                    engine_type=engine_type,
                                    name=engine_type.value,
                                    binary_path=str(value),
                                    found=True,
                                    healthy=True,
                                    source="registry",
                                )
                        except OSError:
                            continue
            except OSError:
                continue
        return None

    def _check_env_vars(self, engine_type: EngineType) -> EngineDiscoveryResult | None:
        env_keys = {
            EngineType.CLAUDE_CODE: ["CLAUDE_BINARY_PATH", "CLAUDE_CLI_PATH"],
            EngineType.GEMINI_CLI: ["GEMINI_BINARY_PATH", "GEMINI_CLI_PATH"],
            EngineType.CODEX_CLI: ["CODEX_BINARY_PATH"],
            EngineType.HERMES: ["HERMES_DAEMON_PATH"],
            EngineType.AIDER: ["AIDER_BINARY_PATH"],
        }
        keys = env_keys.get(engine_type, [])
        for key in keys:
            value = os.environ.get(key)
            if value:
                path = Path(value)
                if path.is_file():
                    return EngineDiscoveryResult(
                        engine_type=engine_type,
                        name=engine_type.value,
                        binary_path=str(path),
                        found=True,
                        healthy=True,
                        source="env",
                    )
        return None

    @property
    def discovered(self) -> dict[str, EngineDiscoveryResult]:
        return dict(self._discovered)


def discovery_result_from_dict(data: dict[str, Any]) -> EngineDiscoveryResult:
    return EngineDiscoveryResult(
        engine_type=EngineType(data.get("engine_type", "")),
        name=data.get("name", ""),
        binary_path=data.get("binary_path"),
        version=data.get("version"),
        found=data.get("found", False),
        healthy=data.get("healthy", False),
        error=data.get("error"),
        source=data.get("source", ""),
    )
