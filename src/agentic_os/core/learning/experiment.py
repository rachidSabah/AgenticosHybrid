"""Experiment manager — A/B testing, canary, and controlled rollout experiments."""

from collections.abc import Sequence
from datetime import UTC, datetime

from agentic_os.domain.learning import Experiment, ExperimentStatus
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.learning import ExperimentPort

log = get_logger("learning.experiment")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ExperimentManager(ExperimentPort):
    """In-memory experiment manager implementing ``ExperimentPort``.

    Manages the full lifecycle of ``Experiment`` instances including
    creation, starting, completion, and rollback. Automatically selects
    a winner based on metric comparisons when an experiment completes.
    """

    def __init__(self) -> None:
        self._experiments: dict[str, Experiment] = {}

    # ── CRUD ──

    async def create_experiment(self, experiment: Experiment) -> Experiment:
        if experiment.id in self._experiments:
            raise ValueError(f"Experiment '{experiment.id}' already exists")
        self._experiments[experiment.id] = experiment
        log.info("Experiment created", experiment_id=experiment.id, name=experiment.name)
        return experiment

    async def get_experiment(self, experiment_id: str) -> Experiment | None:
        return self._experiments.get(experiment_id)

    async def list_experiments(self) -> Sequence[Experiment]:
        return sorted(
            self._experiments.values(),
            key=lambda e: e.created_at,
            reverse=True,
        )

    async def update_experiment(self, experiment: Experiment) -> Experiment:
        if experiment.id not in self._experiments:
            raise ValueError(f"Experiment '{experiment.id}' not found")
        self._experiments[experiment.id] = experiment
        log.info("Experiment updated", experiment_id=experiment.id)
        return experiment

    async def delete_experiment(self, experiment_id: str) -> None:
        if experiment_id not in self._experiments:
            raise ValueError(f"Experiment '{experiment_id}' not found")
        del self._experiments[experiment_id]
        log.info("Experiment deleted", experiment_id=experiment_id)

    # ── Lifecycle ──

    async def start_experiment(self, experiment_id: str) -> Experiment:
        """Start an experiment, transitioning it from DRAFT to RUNNING."""
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            raise ValueError(f"Experiment '{experiment_id}' not found")
        if experiment.status != ExperimentStatus.DRAFT:
            raise ValueError(f"Cannot start experiment in status '{experiment.status.value}'")

        updated = Experiment(
            id=experiment.id,
            name=experiment.name,
            description=experiment.description,
            experiment_type=experiment.experiment_type,
            control_config=experiment.control_config,
            treatment_config=experiment.treatment_config,
            status=ExperimentStatus.RUNNING,
            winner=experiment.winner,
            metrics=experiment.metrics,
            confidence=experiment.confidence,
            rollback_on_regression=experiment.rollback_on_regression,
            created_at=experiment.created_at,
        )
        self._experiments[experiment_id] = updated
        log.info("Experiment started", experiment_id=experiment_id)
        return updated

    async def complete_experiment(self, experiment_id: str) -> Experiment:
        """Complete an experiment and automatically select a winner."""
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            raise ValueError(f"Experiment '{experiment_id}' not found")
        if experiment.status != ExperimentStatus.RUNNING:
            raise ValueError(f"Cannot complete experiment in status '{experiment.status.value}'")

        winner = self._select_winner(experiment)
        should_rollback = (
            winner is None and experiment.rollback_on_regression and bool(experiment.metrics)
        )

        status = ExperimentStatus.ROLLED_BACK if should_rollback else ExperimentStatus.COMPLETED

        updated = Experiment(
            id=experiment.id,
            name=experiment.name,
            description=experiment.description,
            experiment_type=experiment.experiment_type,
            control_config=experiment.control_config,
            treatment_config=experiment.treatment_config,
            status=status,
            winner=winner,
            metrics=experiment.metrics,
            confidence=experiment.confidence,
            rollback_on_regression=experiment.rollback_on_regression,
            created_at=experiment.created_at,
            completed_at=_utcnow(),
        )
        self._experiments[experiment_id] = updated

        if winner:
            log.info(
                "Experiment completed with winner",
                experiment_id=experiment_id,
                winner=winner,
            )
        elif should_rollback:
            log.info("Experiment completed with rollback", experiment_id=experiment_id)
        else:
            log.info("Experiment completed without clear winner", experiment_id=experiment_id)

        return updated

    async def rollback_experiment(self, experiment_id: str) -> Experiment:
        """Roll back an experiment, restoring the control configuration."""
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            raise ValueError(f"Experiment '{experiment_id}' not found")
        if experiment.status not in (ExperimentStatus.RUNNING, ExperimentStatus.COMPLETED):
            raise ValueError(f"Cannot rollback experiment in status '{experiment.status.value}'")

        updated = Experiment(
            id=experiment.id,
            name=experiment.name,
            description=experiment.description,
            experiment_type=experiment.experiment_type,
            control_config=experiment.control_config,
            treatment_config=experiment.treatment_config,
            status=ExperimentStatus.ROLLED_BACK,
            winner=None,
            metrics=experiment.metrics,
            confidence=experiment.confidence,
            rollback_on_regression=experiment.rollback_on_regression,
            created_at=experiment.created_at,
            completed_at=_utcnow(),
        )
        self._experiments[experiment_id] = updated
        log.info("Experiment rolled back", experiment_id=experiment_id)
        return updated

    # ── Winner Selection ──

    def _select_winner(self, experiment: Experiment) -> str | None:
        """Select the winner based on metric comparisons.

        Compares control vs treatment metrics. If treatment metrics
        are consistently better, treatment wins. If control is better
        or metrics are equal/inconclusive, None is returned (which
        may trigger a rollback if ``rollback_on_regression`` is set).
        """
        if not experiment.metrics:
            return None

        control_metrics = experiment.metrics.get("control", {})
        treatment_metrics = experiment.metrics.get("treatment", {})

        if not control_metrics or not treatment_metrics:
            return None

        treatment_wins = 0
        control_wins = 0
        total_metrics = 0

        for metric, control_val in control_metrics.items():
            treatment_val = treatment_metrics.get(metric)
            if treatment_val is None:
                continue
            total_metrics += 1
            # For most metrics (latency, cost), lower is better.
            # success_rate, quality_score: higher is better.
            lower_is_better = metric in (
                "latency_ms",
                "avg_latency_ms",
                "cost",
                "avg_cost",
                "retry_count",
                "p50_latency_ms",
                "p95_latency_ms",
                "p99_latency_ms",
            )
            if lower_is_better:
                if treatment_val < control_val:
                    treatment_wins += 1
                elif control_val < treatment_val:
                    control_wins += 1
            else:
                if treatment_val > control_val:
                    treatment_wins += 1
                elif control_val > treatment_val:
                    control_wins += 1

        if total_metrics == 0:
            return None

        if treatment_wins > control_wins:
            return "treatment"
        if control_wins > treatment_wins:
            return "control"
        return None

    # ── Utility ──

    async def record_metrics(
        self,
        experiment_id: str,
        arm: str,
        metrics: dict[str, float],
    ) -> Experiment:
        """Record metrics for an experiment arm (control or treatment)."""
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            raise ValueError(f"Experiment '{experiment_id}' not found")

        updated_metrics = dict(experiment.metrics)
        updated_metrics[arm] = dict(metrics)

        updated = Experiment(
            id=experiment.id,
            name=experiment.name,
            description=experiment.description,
            experiment_type=experiment.experiment_type,
            control_config=experiment.control_config,
            treatment_config=experiment.treatment_config,
            status=experiment.status,
            winner=experiment.winner,
            metrics=updated_metrics,
            confidence=experiment.confidence,
            rollback_on_regression=experiment.rollback_on_regression,
            created_at=experiment.created_at,
            completed_at=experiment.completed_at,
        )
        self._experiments[experiment_id] = updated
        return updated
