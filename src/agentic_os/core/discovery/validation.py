"""Engine validation pipeline — chain-of-responsibility for validating discovered engines.

Each validator checks one aspect of an engine: executable existence, version,
health, capabilities, permissions, integrity. The pipeline runs all validators
and aggregates results.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from agentic_os.domain.discovery import ValidationResult
from agentic_os.domain.execution import ExecutionEngine
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import EngineRegistration

log = get_logger("discovery.validation")


@runtime_checkable
class EngineValidator(Protocol):
    """Interface for a single engine validation step."""

    async def validate(
        self,
        registration: EngineRegistration,
        executable_path: str | None = None,
        engine: ExecutionEngine | None = None,
    ) -> ValidationResult:
        """Validate the engine and return a result."""
        ...

    def get_validator_name(self) -> str:
        """Return a human-readable name for this validator."""
        ...


# ── Concrete Validators ──


@dataclass
class ExecutableExistsValidator:
    """Verifies that the engine's executable binary exists and is executable.

    For local endpoints (``local:<binary>``), checks PATH and common dirs.
    For remote endpoints, passes automatically.
    """

    async def validate(
        self,
        registration: EngineRegistration,
        executable_path: str | None = None,
        engine: ExecutionEngine | None = None,
    ) -> ValidationResult:
        engine_id = engine.id if engine else registration.name
        engine_name = registration.name

        if executable_path:
            exists = os.path.isfile(executable_path) and os.access(executable_path, os.X_OK)
            if exists:
                return ValidationResult.passed(
                    engine_id=engine_id,
                    engine_name=engine_name,
                    executable_exists=True,
                )
            return ValidationResult.failed(
                engine_id,
                engine_name,
                f"Executable not found or not executable: {executable_path}",
                executable_exists=False,
            )

        # Check by endpoint
        if registration.endpoint and registration.endpoint.startswith("local:"):
            binary = registration.endpoint.replace("local:", "", 1)
            found = shutil.which(binary)
            if found:
                return ValidationResult.passed(
                    engine_id=engine_id,
                    engine_name=engine_name,
                    executable_exists=True,
                )
            return ValidationResult.failed(
                engine_id,
                engine_name,
                f"Binary not found on PATH: {binary}",
                executable_exists=False,
            )

        # Remote endpoint — skip local check
        return ValidationResult.passed(
            engine_id=engine_id,
            engine_name=engine_name,
            executable_exists=True,
            warnings=("Remote endpoint — skipping local executable check",),
        )

    @staticmethod
    def get_validator_name() -> str:
        return "executable-exists"


@dataclass
class VersionDetectValidator:
    """Runs ``--version`` (or a configurable flag) on the executable and parses output."""

    version_flag: str = "--version"
    timeout_seconds: float = 5.0

    async def validate(
        self,
        registration: EngineRegistration,
        executable_path: str | None = None,
        engine: ExecutionEngine | None = None,
    ) -> ValidationResult:
        engine_id = engine.id if engine else registration.name
        engine_name = registration.name

        # Determine the binary to run
        binary: str | None = executable_path
        if binary is None and registration.endpoint:
            if registration.endpoint.startswith("local:"):
                binary = registration.endpoint.replace("local:", "", 1)
                found = shutil.which(binary)
                if not found:
                    return ValidationResult.failed(
                        engine_id,
                        engine_name,
                        f"Cannot detect version: binary not found: {binary}",
                    )
                binary = found

        if binary is None:
            return ValidationResult.passed(
                engine_id=engine_id,
                engine_name=engine_name,
                version_detected=registration.version,
                warnings=("Remote endpoint — using registration version",),
            )

        try:
            result = subprocess.run(
                [binary, self.version_flag],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            if result.returncode == 0:
                first_line = result.stdout.strip().split("\n")[0]
                version = first_line[:100] if first_line else "unknown"
                return ValidationResult.passed(
                    engine_id=engine_id,
                    engine_name=engine_name,
                    version_detected=version,
                )
            return ValidationResult.failed(
                engine_id,
                engine_name,
                f"Version command failed (exit {result.returncode}): {result.stderr.strip()[:200]}",
                version_detected=registration.version,
            )
        except FileNotFoundError:
            return ValidationResult.failed(
                engine_id,
                engine_name,
                f"Binary not found: {binary}",
            )
        except subprocess.TimeoutExpired:
            return ValidationResult.failed(
                engine_id,
                engine_name,
                f"Version check timed out after {self.timeout_seconds}s",
                version_detected=registration.version,
            )
        except OSError as exc:
            return ValidationResult.failed(
                engine_id,
                engine_name,
                f"OS error running version check: {exc}",
            )

    @staticmethod
    def get_validator_name() -> str:
        return "version-detect"


@dataclass
class HealthCheckValidator:
    """Performs a quick health check using the engine's adapter.

    Requires an initialized ``ExecutionEngine`` instance — skipped if none provided.
    """

    requires_adapter: bool = True

    async def validate(
        self,
        registration: EngineRegistration,
        executable_path: str | None = None,
        engine: ExecutionEngine | None = None,
    ) -> ValidationResult:
        engine_id = engine.id if engine else registration.name
        engine_name = registration.name

        if engine is None:
            return ValidationResult.passed(
                engine_id=engine_id,
                engine_name=engine_name,
                health_check_passed=True,
                warnings=("No engine instance — skipping health check",),
            )

        # Status-based health: if the engine is RUNNING/IDLE, consider healthy
        from agentic_os.domain.execution import EngineStatus

        healthy_statuses = {EngineStatus.RUNNING, EngineStatus.IDLE}
        if engine.status in healthy_statuses:
            return ValidationResult.passed(
                engine_id=engine_id,
                engine_name=engine_name,
                health_check_passed=True,
            )

        return ValidationResult.failed(
            engine_id,
            engine_name,
            f"Engine status is {engine.status.value} — not healthy",
            health_check_passed=False,
        )

    @staticmethod
    def get_validator_name() -> str:
        return "health-check"


@dataclass
class CapabilityMatchValidator:
    """Verifies that advertised capabilities are consistent with the engine metadata."""

    async def validate(
        self,
        registration: EngineRegistration,
        executable_path: str | None = None,
        engine: ExecutionEngine | None = None,
    ) -> ValidationResult:
        engine_id = engine.id if engine else registration.name
        engine_name = registration.name

        # Check that the registration's capabilities are valid enum values
        if not registration.capabilities:
            return ValidationResult.passed(
                engine_id=engine_id,
                engine_name=engine_name,
                capability_match=True,
                warnings=("No capabilities advertised",),
            )

        from agentic_os.domain.execution import EngineCapability

        for cap in registration.capabilities:
            if not isinstance(cap, EngineCapability):
                try:
                    EngineCapability(cap.value if hasattr(cap, "value") else str(cap))
                except (ValueError, TypeError):
                    return ValidationResult.failed(
                        engine_id,
                        engine_name,
                        f"Invalid capability: {cap}",
                        capability_match=False,
                    )

        return ValidationResult.passed(
            engine_id=engine_id,
            engine_name=engine_name,
            capability_match=True,
        )

    @staticmethod
    def get_validator_name() -> str:
        return "capability-match"


@dataclass
class PermissionValidator:
    """Checks file permissions on the executable and required resources."""

    async def validate(
        self,
        registration: EngineRegistration,
        executable_path: str | None = None,
        engine: ExecutionEngine | None = None,
    ) -> ValidationResult:
        engine_id = engine.id if engine else registration.name
        engine_name = registration.name

        path_to_check: str | None = executable_path
        if path_to_check is None and registration.endpoint:
            if registration.endpoint.startswith("local:"):
                binary = registration.endpoint.replace("local:", "", 1)
                path_to_check = shutil.which(binary)

        if path_to_check is None:
            return ValidationResult.passed(
                engine_id=engine_id,
                engine_name=engine_name,
                permission_ok=True,
                warnings=("Remote endpoint — skipping permission check",),
            )

        if not os.path.exists(path_to_check):
            return ValidationResult.failed(
                engine_id,
                engine_name,
                f"Path does not exist: {path_to_check}",
                permission_ok=False,
            )

        if not os.access(path_to_check, os.R_OK):
            return ValidationResult.failed(
                engine_id,
                engine_name,
                f"Executable is not readable: {path_to_check}",
                permission_ok=False,
            )

        return ValidationResult.passed(
            engine_id=engine_id,
            engine_name=engine_name,
            permission_ok=True,
        )

    @staticmethod
    def get_validator_name() -> str:
        return "permission"


@dataclass
class IntegrityValidator:
    """Basic integrity check — compares file hash against a known value if available.

    Uses metadata ``sha256`` or ``md5`` fields if present in the registration.
    """

    async def validate(
        self,
        registration: EngineRegistration,
        executable_path: str | None = None,
        engine: ExecutionEngine | None = None,
    ) -> ValidationResult:
        engine_id = engine.id if engine else registration.name
        engine_name = registration.name

        known_hash = registration.metadata.get("sha256") or registration.metadata.get("md5")
        if known_hash is None:
            return ValidationResult.passed(
                engine_id=engine_id,
                engine_name=engine_name,
                integrity_ok=True,
                warnings=("No known hash — skipping integrity check",),
            )

        path_to_check: str | None = executable_path
        if path_to_check is None and registration.endpoint:
            if registration.endpoint.startswith("local:"):
                binary = registration.endpoint.replace("local:", "", 1)
                path_to_check = shutil.which(binary)

        if path_to_check is None or not os.path.isfile(path_to_check):
            return ValidationResult.failed(
                engine_id,
                engine_name,
                "Cannot check integrity: file not found",
                integrity_ok=False,
            )

        try:
            import hashlib

            hash_type = "sha256" if "sha256" in registration.metadata else "md5"
            h = hashlib.new(hash_type)
            with open(path_to_check, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            actual = h.hexdigest()

            if actual == known_hash:
                return ValidationResult.passed(
                    engine_id=engine_id,
                    engine_name=engine_name,
                    integrity_ok=True,
                )
            return ValidationResult.failed(
                engine_id,
                engine_name,
                f"{hash_type.upper()} mismatch: expected {known_hash}, got {actual}",
                integrity_ok=False,
            )
        except Exception as exc:
            return ValidationResult.failed(
                engine_id,
                engine_name,
                f"Integrity check error: {exc}",
                integrity_ok=False,
            )

    @staticmethod
    def get_validator_name() -> str:
        return "integrity"


# ── Pipeline ──


@dataclass
class ValidationPipeline:
    """Chain-of-responsibility pipeline for engine validation.

    Runs all registered validators against each discovered engine and
    aggregates their results. Provides both full result sets and a
    pass/fail summary.
    """

    _validators: list[EngineValidator] = field(default_factory=list)

    # ── Validator management ──

    def add_validator(self, validator: EngineValidator) -> None:
        """Register a validator in the pipeline."""
        self._validators.append(validator)
        log.info("Validator added", name=validator.get_validator_name())

    def remove_validator(self, name: str) -> bool:
        """Remove a validator by name. Returns True if removed."""
        before = len(self._validators)
        self._validators = [v for v in self._validators if v.get_validator_name() != name]
        return len(self._validators) < before

    def list_validators(self) -> list[str]:
        """Return names of registered validators."""
        return [v.get_validator_name() for v in self._validators]

    def clear_validators(self) -> None:
        """Remove all validators."""
        self._validators.clear()

    # ── Validation ──

    async def validate(
        self,
        registration: EngineRegistration,
        executable_path: str | None = None,
        engine: ExecutionEngine | None = None,
    ) -> list[ValidationResult]:
        """Run all validators and return their results."""
        results: list[ValidationResult] = []
        for validator in self._validators:
            try:
                result = await validator.validate(
                    registration=registration,
                    executable_path=executable_path,
                    engine=engine,
                )
                results.append(result)
            except Exception as exc:
                log.warning(
                    "Validator failed",
                    validator=validator.get_validator_name(),
                    error=str(exc),
                )
                engine_id = engine.id if engine else registration.name
                results.append(
                    ValidationResult.failed(
                        engine_id,
                        registration.name,
                        f"Validator error: {exc}",
                    )
                )
        return results

    async def validate_and_report(
        self,
        registration: EngineRegistration,
        executable_path: str | None = None,
        engine: ExecutionEngine | None = None,
    ) -> tuple[bool, list[ValidationResult]]:
        """Run all validators and return (all_pass, results)."""
        results = await self.validate(
            registration=registration,
            executable_path=executable_path,
            engine=engine,
        )
        all_pass = all(r.valid for r in results)
        return all_pass, results
