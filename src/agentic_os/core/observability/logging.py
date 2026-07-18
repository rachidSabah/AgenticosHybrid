"""Structured Logging Implementation

Core implementation of LoggingPort using structlog with correlation context.
"""

from __future__ import annotations

import contextvars
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from agentic_os.domain.observability import CorrelationContext, LogEntry
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.observability import LoggingPort

log = get_logger("observability.logging")


class StructuredLogging(LoggingPort):
    """Structured logging with correlation context support."""

    def __init__(self, logger_name: str = "agentic-os"):
        self.logger_name = logger_name
        self._base_logger = structlog.get_logger(logger_name)
        self._correlation_context: contextvars.ContextVar[CorrelationContext | None] = (
            contextvars.ContextVar("correlation_context", default=None)
        )

    def _get_logger(self) -> structlog.BoundLogger:
        """Get logger with current correlation context bound."""
        context = self._correlation_context.get()
        if context:
            return self._base_logger.bind(
                trace_id=context.trace_id,
                span_id=context.span_id,
                **context.baggage,
            )
        return self._base_logger

    def log(self, entry: LogEntry) -> None:
        """Log a structured entry."""
        logger = self._get_logger()

        # Add entry attributes
        bound_logger = logger.bind(**entry.attributes)

        # Log at appropriate level
        level = entry.level.upper()
        if level == "DEBUG":
            bound_logger.debug(entry.message)
        elif level == "INFO":
            bound_logger.info(entry.message)
        elif level == "WARNING":
            bound_logger.warning(entry.message)
        elif level == "ERROR":
            bound_logger.error(entry.message)
        elif level == "CRITICAL":
            bound_logger.critical(entry.message)
        else:
            bound_logger.info(entry.message)

    def debug(self, message: str, **attributes: Any) -> None:
        """Log debug message."""
        self.log(LogEntry(level="DEBUG", message=message, attributes=attributes))

    def info(self, message: str, **attributes: Any) -> None:
        """Log info message."""
        self.log(LogEntry(level="INFO", message=message, attributes=attributes))

    def warning(self, message: str, **attributes: Any) -> None:
        """Log warning message."""
        self.log(LogEntry(level="WARNING", message=message, attributes=attributes))

    def error(self, message: str, **attributes: Any) -> None:
        """Log error message."""
        self.log(LogEntry(level="ERROR", message=message, attributes=attributes))

    def critical(self, message: str, **attributes: Any) -> None:
        """Log critical message."""
        self.log(LogEntry(level="CRITICAL", message=message, attributes=attributes))

    def with_context(self, context: CorrelationContext) -> LoggingPort:
        """Return a logger with correlation context bound."""
        # Create a new logger instance with context
        new_logger = StructuredLogging(self.logger_name)
        new_logger._correlation_context.set(context)
        return new_logger

    def bind_context(self, context: CorrelationContext) -> None:
        """Bind correlation context to current contextvars."""
        bind_contextvars(
            trace_id=context.trace_id,
            span_id=context.span_id,
            **context.baggage,
        )
        self._correlation_context.set(context)

    def clear_context(self) -> None:
        """Clear correlation context."""
        clear_contextvars()
        self._correlation_context.set(None)

    def get_current_context(self) -> CorrelationContext | None:
        """Get current correlation context."""
        return self._correlation_context.get()


# Global logging instance
_logging_instance: StructuredLogging | None = None


def get_logging() -> StructuredLogging:
    """Get or create the global logging instance."""
    global _logging_instance
    if _logging_instance is None:
        _logging_instance = StructuredLogging()
    return _logging_instance


def configure_logging(
    logger_name: str = "agentic-os",
    level: str = "INFO",
    json_output: bool = False,
) -> StructuredLogging:
    """Configure and return the global logging instance."""
    global _logging_instance

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            (
                structlog.processors.JSONRenderer()
                if json_output
                else structlog.dev.ConsoleRenderer(colors=True)
            ),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Set log level
    import logging

    logging.basicConfig(level=getattr(logging, level.upper()))

    _logging_instance = StructuredLogging(logger_name)
    return _logging_instance