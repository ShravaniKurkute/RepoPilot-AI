"""Structured logging configuration for RepoPilot AI."""

import logging
import sys


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configures structured stream logging for the application."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Root logger format
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    logger = logging.getLogger("repopilot")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False

    return logger


logger = setup_logging()

