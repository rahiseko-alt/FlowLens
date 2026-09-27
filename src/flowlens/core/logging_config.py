from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(
    log_path: str | Path | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """Configures the FlowLens diagnostic logger.

    Privacy Guarantee:
    This logger is strictly for service lifecycle, troubleshooting, and error diagnostics.
    It NEVER records window titles, keystrokes, URLs, clipboard data, or user content.
    """
    logger = logging.getLogger("flowlens")
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if log_path:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            str(path),
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    else:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger


def get_logger() -> logging.Logger:
    """Gets the existing FlowLens logger."""
    return logging.getLogger("flowlens")


def close_logging() -> None:
    """Closes and removes all handlers from the FlowLens logger."""
    logger = logging.getLogger("flowlens")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
