"""Engine profiling — auto-generates ExecutionProfile from discovered engine metadata.

After discovery and validation, the ProfilingEngine generates a ProfileResult
with estimated capabilities, latency, resource footprint, and configuration
defaults. These profiles can be converted into domain ExecutionProfile objects
for registration with the RuntimeManager.
"""

import platform as platform_mod
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime

from agentic_os.domain.discovery import ProfileResult, ValidationResult
from agentic_os.domain.execution import (
    EngineCapability,
    EngineType,
    ExecutionCapability,
    ExecutionProfile,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import EngineRegistration

log = get_logger("discovery.profiling")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class ProfilingEngine:
    """Auto-generates ExecutionProfile from discovered engine metadata.

    Uses validation results (if provided) to enrich the profile with actual
    version, capability, and latency data. Falls back to estimation when
    validation results are not available.
    """

    async def profile(
        self,
        registration: EngineRegistration,
        validation_results: list[ValidationResult] | None = None,
    ) -> ProfileResult:
        """Generate a profile from discovery metadata + optional validation results.

        Args:
            registration: The engine registration discovered by a provider.
            validation_results: Optional results from the validation pipeline
                to enrich the profile with actual detected values.

        Returns:
            A ProfileResult with estimated and actual engine characteristics.
        """
        engine_id = registration.name  # placeholder; RuntimeManager assigns real ID
        name = registration.name
        version = registration.version
        executable = self._resolve_executable(registration)

        # Merge capability info from registration
        capabilities = [str(c) for c in registration.capabilities]

        # Merge validation data if provided
        if validation_results:
            for vr in validation_results:
                if vr.version_detected and vr.valid:
                    version = vr.version_detected

        # Detect platform
        platform_name = platform_mod.system().lower()

        # Estimate capabilities
        supports_streaming = await self._detect_streaming(registration)
        supports_mcp = self._estimate_mcp_support(registration)

        # Estimate latency
        latency = await self._estimate_latency(executable, registration)

        # Estimate resource footprint (default heuristic)
        resource_mb = self._estimate_resource_footprint(registration)

        # Provide config defaults
        config_defaults = self._generate_config_defaults(registration)

        return ProfileResult(
            engine_id=engine_id,
            engine_name=name,
            version=version,
            executable_path=executable or registration.endpoint or "",
            platform=platform_name,
            capabilities=tuple(capabilities),
            supports_streaming=supports_streaming,
            supports_mcp=supports_mcp,
            latency_estimate_ms=latency,
            cost_estimate=0.0,
            resource_footprint_mb=resource_mb,
            config_defaults=config_defaults,
            profiled_at=_utcnow(),
        )

    async def to_execution_profile(self, profile_result: ProfileResult) -> ExecutionProfile:
        """Convert a ProfileResult to an ExecutionProfile domain model.

        The ExecutionProfile can be associated with an engine during registration.
        """
        caps = tuple(
            ExecutionCapability(type=EngineCapability(c)) for c in profile_result.capabilities
        )
        return ExecutionProfile(
            name=profile_result.engine_name,
            engine_type=EngineType.GENERIC,
            capabilities=caps,
            config=None,
            description=f"Auto-profiled: {profile_result.engine_name} v{profile_result.version}",
            tags=("auto-profiled",),
        )

    # ── Estimation helpers ──

    @staticmethod
    def _resolve_executable(registration: EngineRegistration) -> str | None:
        """Resolve the executable path from a registration."""
        if registration.endpoint and registration.endpoint.startswith("local:"):
            binary = registration.endpoint.replace("local:", "", 1)
            found = shutil.which(binary)
            return found
        return None

    async def _detect_streaming(self, registration: EngineRegistration) -> bool:
        """Check if the engine likely supports streaming output."""
        # Streaming is implied by certain engine types
        streaming_types = {"claude_code", "mcp", "docker", "wsl"}
        if registration.engine_type.value in streaming_types:
            return True
        # Check metadata for streaming flag
        return bool(registration.metadata.get("supports_streaming", False))

    @staticmethod
    def _estimate_mcp_support(registration: EngineRegistration) -> bool:
        """Check if the engine likely supports MCP."""
        if registration.engine_type.value == "mcp":
            return True
        return bool(registration.metadata.get("supports_mcp", False))

    async def _estimate_latency(
        self, executable: str | None, registration: EngineRegistration
    ) -> float:
        """Run a quick probe and measure approximate response time."""
        if executable is None:
            return 50.0  # default estimate for remote engines

        try:
            import time

            start = time.perf_counter()
            result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            elapsed = (time.perf_counter() - start) * 1000  # ms
            if result.returncode == 0:
                return round(elapsed, 2)
            return round(elapsed * 2, 2)  # penalty for non-zero exit
        except FileNotFoundError, subprocess.TimeoutExpired, OSError:
            return 100.0  # conservative estimate on error

    @staticmethod
    def _estimate_resource_footprint(registration: EngineRegistration) -> float:
        """Estimate memory footprint based on engine type."""
        footprints: dict[str, float] = {
            "claude_code": 512.0,
            "docker": 256.0,
            "wsl": 512.0,
            "mcp": 128.0,
            "generic": 64.0,
            "aider": 256.0,
            "custom": 128.0,
        }
        return footprints.get(registration.engine_type.value, 128.0)

    @staticmethod
    def _generate_config_defaults(registration: EngineRegistration) -> dict:
        """Provide sensible configuration defaults for the engine type."""
        base: dict = {
            "timeout_seconds": 60,
            "max_retries": 3,
        }

        type_defaults: dict[str, dict] = {
            "claude_code": {"model": "sonnet", "max_tokens": 4096},
            "docker": {"network": "host", "memory_limit": "4g"},
            "wsl": {"distribution": "Ubuntu", "memory_limit": "2g"},
            "mcp": {"protocol_version": "2024-11-05"},
        }

        base.update(type_defaults.get(registration.engine_type.value, {}))
        return base
