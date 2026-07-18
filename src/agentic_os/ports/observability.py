"""Ports: Observability.

Ports for tracing, metrics, and logging - enabling pluggable observability backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from agentic_os.domain.observability import (
    CorrelationContext,
    LogEntry,
    Metric,
    Span,
    SpanContext,
    Trace,
)


@runtime_checkable
class TracingPort(Protocol):
    """Port for distributed tracing operations."""

    def start_span(
        self,
        name: str,
        kind: str = "internal",
        parent: SpanContext | None = None,
        attributes: dict[str, Any] | None = None,
        links: list[tuple[SpanContext, dict[str, Any]]] | None = None,
    ) -> Span: ...

    def end_span(self, span: Span, status: str = "ok", message: str | None = None) -> None: ...

    def get_current_span(self) -> Span | None: ...

    def set_current_span(self, span: Span | None) -> None: ...

    def get_trace(self, trace_id: str) -> Trace | None: ...

    def inject_context(self, context: SpanContext, carrier: dict[str, str]) -> None: ...

    def extract_context(self, carrier: dict[str, str]) -> SpanContext | None: ...

    def shutdown(self) -> None: ...


@runtime_checkable
class MetricsPort(Protocol):
    """Port for metrics collection."""

    def counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None: ...

    def gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None: ...

    def histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None: ...

    def summary(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None: ...

    def record_metric(self, metric: Metric) -> None: ...

    def get_metric(self, name: str, labels: dict[str, str] | None = None) -> Metric | None: ...

    def list_metrics(self, prefix: str = "") -> list[Metric]: ...

    def export_prometheus(self) -> bytes: ...

    def get_content_type(self) -> str: ...


@runtime_checkable
class LoggingPort(Protocol):
    """Port for structured logging."""

    def log(self, entry: LogEntry) -> None: ...

    def debug(self, message: str, **attributes: Any) -> None: ...

    def info(self, message: str, **attributes: Any) -> None: ...

    def warning(self, message: str, **attributes: Any) -> None: ...

    def error(self, message: str, **attributes: Any) -> None: ...

    def critical(self, message: str, **attributes: Any) -> None: ...

    def with_context(self, context: CorrelationContext) -> LoggingPort: ...

    def bind_context(self, context: CorrelationContext) -> None: ...

    def clear_context(self) -> None: ...

    def get_current_context(self) -> CorrelationContext | None: ...


# Abstract base classes for concrete implementations
class TracingPortBase(ABC):
    """Abstract base for tracing implementations."""

    @abstractmethod
    def start_span(
        self,
        name: str,
        kind: str = "internal",
        parent: SpanContext | None = None,
        attributes: dict[str, Any] | None = None,
        links: list[tuple[SpanContext, dict[str, Any]]] | None = None,
    ) -> Span:
        pass

    @abstractmethod
    def end_span(self, span: Span, status: str = "ok", message: str | None = None) -> None:
        pass

    @abstractmethod
    def get_current_span(self) -> Span | None:
        pass

    @abstractmethod
    def set_current_span(self, span: Span | None) -> None:
        pass

    @abstractmethod
    def get_trace(self, trace_id: str) -> Trace | None:
        pass

    @abstractmethod
    def inject_context(self, context: SpanContext, carrier: dict[str, str]) -> None:
        pass

    @abstractmethod
    def extract_context(self, carrier: dict[str, str]) -> SpanContext | None:
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass


class MetricsPortBase(ABC):
    """Abstract base for metrics implementations."""

    @abstractmethod
    def counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        pass

    @abstractmethod
    def gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        pass

    @abstractmethod
    def histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        pass

    @abstractmethod
    def summary(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        pass

    @abstractmethod
    def record_metric(self, metric: Metric) -> None:
        pass

    @abstractmethod
    def get_metric(self, name: str, labels: dict[str, str] | None = None) -> Metric | None:
        pass

    @abstractmethod
    def list_metrics(self, prefix: str = "") -> list[Metric]:
        pass

    @abstractmethod
    def export_prometheus(self) -> bytes:
        pass

    @abstractmethod
    def get_content_type(self) -> str:
        pass


class LoggingPortBase(ABC):
    """Abstract base for logging implementations."""

    @abstractmethod
    def log(self, entry: LogEntry) -> None:
        pass

    @abstractmethod
    def debug(self, message: str, **attributes: Any) -> None:
        pass

    @abstractmethod
    def info(self, message: str, **attributes: Any) -> None:
        pass

    @abstractmethod
    def warning(self, message: str, **attributes: Any) -> None:
        pass

    @abstractmethod
    def error(self, message: str, **attributes: Any) -> None:
        pass

    @abstractmethod
    def critical(self, message: str, **attributes: Any) -> None:
        pass

    @abstractmethod
    def with_context(self, context: CorrelationContext) -> LoggingPort:
        pass

    @abstractmethod
    def bind_context(self, context: CorrelationContext) -> None:
        pass

    @abstractmethod
    def clear_context(self) -> None:
        pass

    @abstractmethod
    def get_current_context(self) -> CorrelationContext | None:
        pass


__all__ = [
    "TracingPort",
    "MetricsPort",
    "LoggingPort",
    "TracingPortBase",
    "MetricsPortBase",
    "LoggingPortBase",
]
