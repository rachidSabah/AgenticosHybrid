"""Strategy manager — manages optimization strategies."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("learning.strategy")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Strategy:
    """An optimization strategy with a name, description, and score function."""

    def __init__(
        self,
        name: str,
        description: str,
        score_fn: Callable[[dict[str, Any]], float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.score_fn = score_fn
        self.metadata = metadata or {}
        self.created_at: datetime = _utcnow()

    def score(self, context: dict[str, Any]) -> float:
        """Evaluate the strategy against a context and return a score."""
        return self.score_fn(context)


class StrategyManager:
    """Manages a registry of optimization strategies.

    Strategies are registered with a name, description, and score function.
    The ``select_best_strategy`` method evaluates all registered strategies
    against a given context and returns the highest-scoring one.
    """

    def __init__(self) -> None:
        self._strategies: dict[str, Strategy] = {}

    def register_strategy(
        self,
        name: str,
        description: str,
        score_fn: Callable[[dict[str, Any]], float],
        metadata: dict[str, Any] | None = None,
    ) -> Strategy:
        """Register a new strategy.

        Args:
            name: Unique strategy name.
            description: Human-readable description.
            score_fn: Function that takes a context dict and returns a float score.
            metadata: Optional additional metadata.

        Returns:
            The registered Strategy instance.

        Raises:
            ValueError: If a strategy with the same name already exists.
        """
        if name in self._strategies:
            raise ValueError(f"Strategy '{name}' is already registered")

        strategy = Strategy(
            name=name,
            description=description,
            score_fn=score_fn,
            metadata=metadata,
        )
        self._strategies[name] = strategy
        log.info("Strategy registered", name=name)
        return strategy

    def unregister_strategy(self, name: str) -> None:
        """Unregister a strategy by name.

        Raises:
            KeyError: If the strategy is not found.
        """
        if name not in self._strategies:
            raise KeyError(f"Strategy '{name}' not found")
        del self._strategies[name]
        log.info("Strategy unregistered", name=name)

    def get_strategy(self, name: str) -> Strategy | None:
        """Get a registered strategy by name."""
        return self._strategies.get(name)

    def list_strategies(self) -> Sequence[Strategy]:
        """List all registered strategies."""
        return list(self._strategies.values())

    def select_best_strategy(
        self,
        context: dict[str, Any],
    ) -> Strategy | None:
        """Evaluate all strategies against context and return the highest scorer.

        Args:
            context: A dictionary of context information used by score functions.

        Returns:
            The highest-scoring strategy, or None if no strategies are registered.
        """
        if not self._strategies:
            return None

        best: tuple[str, float] | None = None
        for name, strategy in self._strategies.items():
            try:
                s = strategy.score(context)
                if best is None or s > best[1]:
                    best = (name, s)
            except Exception as exc:
                log.warning("Strategy score function failed", name=name, error=str(exc))

        if best is None:
            return None
        return self._strategies[best[0]]
