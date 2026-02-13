import logging
import os
import sys

_LOGGER_NAME = "citation_checker"
_DEFAULT_LEVEL = os.getenv("CITATION_CHECKER_LOG_LEVEL", "INFO").upper()


def _build_handler():
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    return handler


def get_logger(name: str | None = None) -> logging.Logger:
    logger_name = _LOGGER_NAME if not name else f"{_LOGGER_NAME}.{name}"
    logger = logging.getLogger(logger_name)
    if not logger.handlers:
        logger.addHandler(_build_handler())
    logger.setLevel(_DEFAULT_LEVEL)
    logger.propagate = False
    return logger


def set_log_level(level: str):
    normalized = (level or "INFO").upper()
    logging.getLogger(_LOGGER_NAME).setLevel(normalized)


def log_exception(context: str, exc: Exception, logger: logging.Logger | None = None):
    active_logger = logger or get_logger()
    has_active_exc = sys.exc_info()[0] is not None
    detail = getattr(exc, "detail", None)
    if has_active_exc:
        active_logger.exception(
            "%s | %s: %s | detail=%s",
            context,
            exc.__class__.__name__,
            exc,
            detail,
        )
    else:
        active_logger.error(
            "%s | %s: %s | detail=%s",
            context,
            exc.__class__.__name__,
            exc,
            detail,
        )
