"""Logging configuration for Typetype.

Supports:
- Environment variable TYPETYPE_DEBUG=1 enables debug output
- Environment variable TYPETYPE_LOG_LEVEL overrides log level
- Simultaneous output to console and rotating log file
- Automatic log rotation (10MB per file, keep 5 backups)
- Backward compatible with existing log_* API
"""

import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

# ANSI color codes for console output
COLORS = {
    "DEBUG": "\033[36m",  # Cyan
    "INFO": "\033[32m",  # Green
    "WARNING": "\033[33m",  # Yellow
    "ERROR": "\033[31m",  # Red
    "RESET": "\033[0m",
}

_LOG_FILE = Path.home() / ".typetype" / "app.log"
try:
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
except OSError:
    # Can't create log directory - we'll just skip file logging
    logging.warning("Could not create log directory %s, file logging disabled", _LOG_FILE.parent)
    _LOG_FILE = None

_MAX_SIZE = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5  # Keep 5 rotated files


class ColoredFormatter(logging.Formatter):
    """Console formatter with ANSI color by log level."""

    def format(self, record):
        levelname = record.levelname
        if levelname in COLORS:
            record.levelname = f"{COLORS[levelname]}{levelname}{COLORS['RESET']}"
        return super().format(record)


def _get_log_level() -> int:
    """Get log level from environment variables."""
    debug_flag = os.getenv("TYPETYPE_DEBUG", "").strip().lower()
    if debug_flag in {"1", "true", "yes", "on"}:
        return logging.DEBUG

    level_name = os.getenv("TYPETYPE_LOG_LEVEL", "warning").strip().lower()
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    return level_map.get(level_name, logging.WARNING)


def _setup_logging() -> None:
    """Setup root logger with console and rotating file handlers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(_get_log_level())

    # Remove any existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Console handler with colored output
    console_handler = logging.StreamHandler()
    console_formatter = ColoredFormatter(
        "%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Rotating file handler (only if log directory is writable)
    if _LOG_FILE is not None:
        file_handler = RotatingFileHandler(
            _LOG_FILE,
            maxBytes=_MAX_SIZE,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(message)s", "%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)


# Initialize logging on module import
_setup_logging()

# Get the module-level logger for our functions
_logger = logging.getLogger(__name__)


# Backward compatible API - preserve all existing function signatures
def log_debug(message: str) -> None:
    _logger.debug(message)


def log_info(message: str) -> None:
    _logger.info(message)


def log_warning(message: str) -> None:
    _logger.warning(message)


def log_error(message: str) -> None:
    _logger.error(message)


def get_log_level() -> str:
    """Get current log level name for backward compatibility."""
    level = _logger.getEffectiveLevel()
    name_map = {
        logging.DEBUG: "debug",
        logging.INFO: "info",
        logging.WARNING: "warning",
        logging.ERROR: "error",
    }
    return name_map.get(level, "warning")


def is_debug_enabled() -> bool:
    """Check if debug logging is enabled."""
    return _logger.isEnabledFor(logging.DEBUG)
