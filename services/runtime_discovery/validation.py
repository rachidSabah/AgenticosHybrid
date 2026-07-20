from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core.logging import get_logger
from services.runtime_discovery.models import (
    Runtime,
    RuntimeCapability,
    RuntimeType,
    RuntimeValidationResult,
    ValidationStatus,
)

_log = get_logger(__name__)

__all__ = [
    "ValidationPipeline",
    "ExecutableExistsValidator",
    "VersionDetectValidator",
    "CapabilityMatchValidator",
    "PermissionValidator",
    "IntegrityValidator",
    "HealthProbeValidator",
]


class ValidationPipeline:
    def __init__(self) -> None:
        self._validators: list[dict[str, Any]] = []

    def add_validator(
        self, name: str, validator: Callable[[Runtime], Any], required: bool = True
    ) -> None:
        self._validators.append({"name": name, "validator": validator, "required": required})

    def remove_validator(self, name: str) -> None:
        self._validators = [v for v in self._validators if v["name"] != name]

    def list_validators(self) -> list[str]:
        return [v["name"] for v in self._validators]

    async def validate(self, runtime: Runtime) -> RuntimeValidationResult:
        result = RuntimeValidationResult(
            runtime_id=runtime.runtime_id,
            runtime_type=runtime.runtime_type,
            name=runtime.name,
            status=ValidationStatus.PASSED,
        )
        errors = []
        warnings = []

        for validator_def in self._validators:
            name = validator_def["name"]
            validator_fn = validator_def["validator"]
            required = validator_def["required"]
            try:
                if asyncio.iscoroutinefunction(validator_fn):
                    check_result = await validator_fn(runtime)
                else:
                    check_result = validator_fn(runtime)
                if isinstance(check_result, bool):
                    result.checks[name] = check_result
                    if not check_result and required:
                        errors.append(f"{name}: failed")
                elif isinstance(check_result, dict):
                    passed = check_result.get("passed", False)
                    result.checks[name] = passed
                    if not passed and required:
                        errors.append(f"{name}: {check_result.get('error', 'failed')}")
                    if check_result.get("warning"):
                        warnings.append(f"{name}: {check_result['warning']}")
                else:
                    result.checks[name] = bool(check_result)
            except Exception as e:
                result.checks[name] = False
                if required:
                    errors.append(f"{name}: {e}")

        if errors:
            result.status = ValidationStatus.FAILED
        result.errors = errors
        result.warnings = warnings
        result.validated_at = datetime.now(UTC)
        return result

    async def validate_all(self, runtimes: list[Runtime]) -> list[RuntimeValidationResult]:
        import asyncio

        tasks = [self.validate(r) for r in runtimes]
        return await asyncio.gather(*tasks)


class ExecutableExistsValidator:
    @staticmethod
    async def validate(runtime: Runtime) -> bool:
        if runtime.binary_path:
            return os.path.isfile(runtime.binary_path) and os.access(runtime.binary_path, os.X_OK)
        if runtime.name:
            found = shutil.which(runtime.name)
            if found:
                runtime.binary_path = found
                return True
        return False


class VersionDetectValidator:
    _VERSION_FLAGS: dict[RuntimeType, list[str]] = {
        RuntimeType.CLAUDE_CODE: ["--version"],
        RuntimeType.GEMINI_CLI: ["--version"],
        RuntimeType.CODEX_CLI: ["--version"],
        RuntimeType.HERMES: ["--version"],
        RuntimeType.AIDER: ["--version"],
        RuntimeType.PYTHON: ["--version"],
        RuntimeType.NODEJS: ["--version"],
        RuntimeType.GIT: ["--version"],
        RuntimeType.GH_CLI: ["--version"],
        RuntimeType.DOCKER: ["--version"],
        RuntimeType.OLLAMA: ["--version"],
    }

    @staticmethod
    async def validate(runtime: Runtime) -> dict[str, Any]:
        binary = runtime.binary_path or runtime.name
        if not binary:
            return {"passed": False, "error": "no binary path"}

        flags = VersionDetectValidator._VERSION_FLAGS.get(runtime.runtime_type, ["--version"])
        try:
            result = subprocess.run([binary, *flags], capture_output=True, text=True, timeout=10)
            output = (result.stdout or result.stderr).strip()
            if output:
                runtime.version = output.split("\n")[0].strip()
                return {"passed": True, "version": runtime.version}
            return {"passed": False, "error": "empty version output"}
        except FileNotFoundError:
            return {"passed": False, "error": "binary not found"}
        except subprocess.TimeoutExpired:
            return {"passed": False, "error": "version check timed out"}
        except Exception as e:
            return {"passed": False, "error": str(e)}


class CapabilityMatchValidator:
    _KNOWN_CAPABILITIES: dict[RuntimeType, list[str]] = {
        RuntimeType.CLAUDE_CODE: [
            "code.read",
            "code.write",
            "code.refactor",
            "code.review",
            "test.run",
            "shell.execute",
        ],
        RuntimeType.GEMINI_CLI: [
            "code.read",
            "code.write",
            "code.review",
            "test.run",
            "shell.execute",
        ],
        RuntimeType.CODEX_CLI: [
            "code.read",
            "code.write",
            "code.refactor",
            "code.review",
            "test.run",
            "shell.execute",
        ],
        RuntimeType.HERMES: [
            "desktop.ui.click",
            "desktop.screen.screenshot",
            "desktop.app.open",
            "browser.navigate",
        ],
        RuntimeType.PYTHON: ["script.execute", "package.install"],
        RuntimeType.NODEJS: ["script.execute", "package.install"],
        RuntimeType.GIT: ["git.clone", "git.commit", "git.push", "git.pull"],
        RuntimeType.DOCKER: ["container.run", "container.build", "image.pull"],
        RuntimeType.GH_CLI: ["pr.create", "pr.review", "issue.list"],
    }

    @staticmethod
    async def validate(runtime: Runtime) -> dict[str, Any]:
        expected = CapabilityMatchValidator._KNOWN_CAPABILITIES.get(runtime.runtime_type, [])
        if not expected:
            return {"passed": True, "warning": "no known capabilities for type"}

        actual = {c.namespace for c in runtime.capabilities}
        missing = [c for c in expected if c not in actual]
        if missing:
            runtime.capabilities = [RuntimeCapability(namespace=c) for c in expected]
            return {"passed": True, "warning": f"auto-populated {len(missing)} capabilities"}
        return {"passed": True}


class PermissionValidator:
    @staticmethod
    async def validate(runtime: Runtime) -> dict[str, Any]:
        binary = runtime.binary_path
        if not binary:
            return {"passed": False, "error": "no binary path"}

        if not os.path.exists(binary):
            return {"passed": False, "error": "binary does not exist"}

        readable = os.access(binary, os.R_OK)
        executable = os.access(binary, os.X_OK)
        if not readable:
            return {"passed": False, "error": "binary not readable"}
        if not executable:
            return {"passed": False, "error": "binary not executable"}
        return {"passed": True}


class IntegrityValidator:
    @staticmethod
    async def validate(runtime: Runtime, known_hash: str | None = None) -> dict[str, Any]:
        binary = runtime.binary_path
        if not binary:
            return {"passed": False, "error": "no binary path"}
        if not os.path.exists(binary):
            return {"passed": False, "error": "binary does not exist"}

        if known_hash:
            try:
                sha256 = hashlib.sha256()
                with open(binary, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        sha256.update(chunk)
                actual = sha256.hexdigest()
                if actual != known_hash:
                    return {"passed": False, "error": "hash mismatch"}
            except Exception as e:
                return {"passed": False, "error": str(e)}
        return {"passed": True, "warning": "no known hash to verify"}


class HealthProbeValidator:
    @staticmethod
    async def validate(runtime: Runtime) -> dict[str, Any]:
        binary = runtime.binary_path or runtime.name
        if not binary:
            return {"passed": False, "error": "no binary path"}

        try:
            result = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return {"passed": True}
            return {
                "passed": False,
                "error": f"exit code {result.returncode}: {result.stderr.strip()}",
            }
        except FileNotFoundError:
            return {"passed": False, "error": "binary not found"}
        except subprocess.TimeoutExpired:
            return {"passed": False, "error": "health probe timed out"}
        except Exception as e:
            return {"passed": False, "error": str(e)}
