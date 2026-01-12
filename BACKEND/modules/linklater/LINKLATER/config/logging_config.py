"""
LINKLATER Centralized Logging Configuration

Usage in any LINKLATER module:
    from modules.LINKLATER.config.logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("Message")
    logger.debug("Debug details")
    logger.warning("Warning message")
    logger.error("Error occurred", exc_info=True)

Log Levels:
    DEBUG   - Detailed debugging (usually off in production)
    INFO    - Normal operation messages
    WARNING - Something unexpected, but recoverable
    ERROR   - Something failed
    CRITICAL- System is unusable

Environment Variables:
    LINKLATER_LOG_LEVEL  - Set log level (DEBUG, INFO, WARNING, ERROR)
    LINKLATER_LOG_FILE   - Path to log file (optional)
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

# LINKLATER module prefix for consistent log formatting
MODULE_PREFIX = "LINKLATER"

# Default log level (can be overridden by environment)
DEFAULT_LOG_LEVEL = logging.INFO

# Log format with module name for easy filtering
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Track configured loggers to avoid duplicate handlers
_configured_loggers: set = set()


def get_log_level() -> int:
    """Get log level from environment or default."""
    level_str = os.environ.get("LINKLATER_LOG_LEVEL", "INFO").upper()
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_str, DEFAULT_LOG_LEVEL)


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Get a configured logger for a LINKLATER module.

    Args:
        name: Module name (usually __name__)
        level: Optional specific log level

    Returns:
        Configured logger instance
    """
    # Normalize the logger name
    if not name.startswith(MODULE_PREFIX):
        # Extract just the module name if it's a full path
        parts = name.split(".")
        # Take last 2-3 parts to keep context
        short_name = ".".join(parts[-3:]) if len(parts) > 3 else name
        logger_name = f"{MODULE_PREFIX}.{short_name}"
    else:
        logger_name = name

    logger = logging.getLogger(logger_name)

    # Only configure once per logger
    if logger_name in _configured_loggers:
        return logger

    _configured_loggers.add(logger_name)

    # Set level
    effective_level = level if level is not None else get_log_level()
    logger.setLevel(effective_level)

    # Prevent propagation to root logger (avoid duplicate logs)
    logger.propagate = False

    # Console handler
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(effective_level)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        logger.addHandler(console_handler)

    # Optional file handler
    log_file = os.environ.get("LINKLATER_LOG_FILE")
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(effective_level)
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
            logger.addHandler(file_handler)

    return logger


def configure_all_loggers(level: int = None):
    """
    Configure all LINKLATER loggers to use consistent formatting.
    Call this at application startup if needed.
    """
    effective_level = level if level is not None else get_log_level()

    # Configure the root LINKLATER logger
    root_logger = get_logger(MODULE_PREFIX, effective_level)

    # Find and configure any existing LINKLATER loggers
    for name in logging.Logger.manager.loggerDict:
        if name.startswith(MODULE_PREFIX):
            logger = logging.getLogger(name)
            logger.setLevel(effective_level)


# Convenience functions for quick logging without creating a logger
def log_info(message: str, module: str = "LINKLATER"):
    """Quick info log."""
    get_logger(module).info(message)


def log_debug(message: str, module: str = "LINKLATER"):
    """Quick debug log."""
    get_logger(module).debug(message)


def log_warning(message: str, module: str = "LINKLATER"):
    """Quick warning log."""
    get_logger(module).warning(message)


def log_error(message: str, module: str = "LINKLATER", exc_info: bool = False):
    """Quick error log."""
    get_logger(module).error(message, exc_info=exc_info)


# Module-level logger for this config module
logger = get_logger(__name__)
