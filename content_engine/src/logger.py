"""
Logging configuration using loguru.

Provides structured logging with rotation and contextual information.
"""

import sys
from pathlib import Path

from loguru import logger

from .config import get_settings


def setup_logging() -> None:
    """Configure loguru logging with file rotation and structured output."""
    settings = get_settings()

    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stderr,
        format=log_format,
        level=settings.log_level,
        colorize=True,
    )

    log_file = settings.log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_file),
        format=log_format,
        level=settings.log_level,
        rotation="10 MB",
        retention="7 days",
        compression="gz",
        backtrace=True,
        diagnose=True,
    )

    logger.info(f"Logging initialized | level={settings.log_level} | file={log_file}")


def get_logger(name: str) -> "logger":
    """Get a contextualized logger instance."""
    return logger.bind(module=name)
