import logging
import sys

_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str | None = None) -> logging.Logger:
    if name is None:
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "root")
        else:
            name = "root"
    if name not in _LOGGERS:
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter(
                '{"event": "%(message)s", "level": "%(levelname)s", "logger": "%(name)s"}'
            ))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        _LOGGERS[name] = logger
    return _LOGGERS[name]


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        stream=sys.stdout,
    )
