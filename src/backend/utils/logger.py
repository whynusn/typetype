import os
import sys
from pathlib import Path

_LEVELS = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
    "none": 50,
}

_LOG_FILE = Path.home() / ".typetype" / "app.log"
_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _get_log_level() -> str:
    debug_flag = os.getenv("TYPETYPE_DEBUG", "").strip().lower()
    if debug_flag in {"1", "true", "yes", "on"}:
        return "debug"
    return os.getenv("TYPETYPE_LOG_LEVEL", "warning").strip().lower()


_LOG_LEVEL = _get_log_level()


def _should_log(level: str) -> bool:
    current = _LEVELS.get(_LOG_LEVEL, _LEVELS["warning"])
    target = _LEVELS.get(level, _LEVELS["warning"])
    return target >= current


def _log(level: str, message: str) -> None:
    if not _should_log(level):
        return
    stream = sys.stderr if level in {"warning", "error"} else sys.stdout
    if stream is None:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(message + "\n")
        return
    print(message, file=stream)


def log_debug(message: str) -> None:
    _log("debug", message)


def log_info(message: str) -> None:
    _log("info", message)


def log_warning(message: str) -> None:
    _log("warning", message)


def log_error(message: str) -> None:
    _log("error", message)


def get_log_level() -> str:
    return _LOG_LEVEL


def is_debug_enabled() -> bool:
    return _should_log("debug")
