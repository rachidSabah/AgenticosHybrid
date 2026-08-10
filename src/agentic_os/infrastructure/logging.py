"""Structured logging via structlog.

Centralized so every module emits consistent, machine-readable logs with
correlation ids (task/agent) when available.

Design note (Windows + pytest): wrapping ``sys.stdout`` in a
``TextIOWrapper`` at configure time leaks a captured stream handle. When
pytest rotates or closes the fd at teardown, structlog's cached
``PrintLogger`` writes to the closed wrapper and raises
``ValueError: I/O operation on closed file``, cascading into thousands of
teardown errors. We therefore write through the *current* ``sys.stdout``
on every call (no cached wrapper), which stays valid regardless of
test-runner stream rotation.
"""

from __future__ import annotations

import logging
import sys

import structlog

_CONFIGURED = False


class _LiveStream:
    """Adapter that always resolves to the *current* sys.stdout.

    Avoids caching a stream object that pytest may close/rotate during
    test teardown (the root cause of "I/O operation on closed file"
    cascades in full-suite runs).
    """

    def write(self, data: str) -> int:
        stream = sys.stdout
        # If stdout is gone/closed, fall back to stderr or skip silently.
        try:
            if stream is None:
                return 0
            try:
                return stream.write(data)
            except (ValueError, OSError):
                # stream was closed underneath us — retry via current sys.stderr if usable
                err = sys.stderr
                if err is not None:
                    try:
                        return err.write(data)
                    except (ValueError, OSError):
                        return 0
                return 0
        except Exception:
            return 0

    def flush(self) -> None:
        try:
            stream = sys.stdout
            if stream is not None:
                stream.flush()
        except Exception:
            pass


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(format="%(message)s", stream=_LiveStream(), level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=_LiveStream()),
    )
    _CONFIGURED = True


def get_logger(name: str = "agentic-os"):
    return structlog.get_logger(name)