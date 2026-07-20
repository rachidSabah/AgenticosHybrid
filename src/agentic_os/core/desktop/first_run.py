"""First Run Wizard — guides users through initial setup."""

from __future__ import annotations

from datetime import UTC, datetime

from agentic_os.domain.desktop import FirstRunState, FirstRunStep
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.first_run")


class FirstRunWizard:
    """Guides users through the first-run setup experience."""

    def __init__(self) -> None:
        self._state = FirstRunState()

    async def get_state(self) -> FirstRunState:
        return self._state

    async def is_completed(self) -> bool:
        return self._state.completed

    async def run_step(self, step: str) -> dict[str, object]:
        try:
            step_enum = FirstRunStep(step)
        except ValueError:
            return {"success": False, "error": f"Unknown step: {step}"}

        self._state.current_step = step_enum
        log.info("Running first-run step", step=step)

        if step_enum == FirstRunStep.WELCOME:
            pass
        elif step_enum == FirstRunStep.WORKSPACE:
            self._state.workspace_created = True
        elif step_enum == FirstRunStep.CONFIG:
            self._state.config_saved = True
        elif step_enum == FirstRunStep.RUNTIME_DISCOVERY:
            self._state.runtimes_discovered = True
        elif step_enum == FirstRunStep.PROVIDER:
            self._state.provider_configured = True
        elif step_enum == FirstRunStep.PLUGIN:
            self._state.plugins_initialized = True
        elif step_enum == FirstRunStep.DATABASE:
            self._state.database_initialized = True
        elif step_enum == FirstRunStep.HEALTH:
            self._state.health_verified = True
        elif step_enum == FirstRunStep.COMPLETE:
            self._state.completed = True
            self._state.completed_at = datetime.now(UTC)

        return {"success": True, "step": step, "state": self._state.to_dict()}

    async def skip_step(self, step: str) -> None:
        if step not in self._state.skipped_steps:
            self._state.skipped_steps.append(step)
        log.info("Skipped first-run step", step=step)

    async def complete(self) -> None:
        self._state.completed = True
        self._state.completed_at = datetime.now(UTC)
        log.info("First run completed")

    async def reset(self) -> None:
        self._state = FirstRunState()
        log.info("First run state reset")
