import os
import sys
import re
from datetime import datetime

# Configuration via environment
LOG_LEVEL_NAME = (os.getenv("LOG_LEVEL") or "INFO").upper()
NO_COLOR = os.getenv("NO_COLOR") is not None
LOG_FILE = os.getenv("LOG_FILE")

_LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARN": 30,
    "ERROR": 40,
}

_level = _LEVELS.get(LOG_LEVEL_NAME, 20)


class _C:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"


def _now_hms() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _colorize(s: str, color: str) -> str:
    if NO_COLOR:
        return s
    return f"{color}{s}{_C.RESET}"


def _strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


_fh = None
if LOG_FILE:
    try:
        _fh = open(LOG_FILE, "a", encoding="utf-8")
    except Exception:
        _fh = None


def _emit(line: str) -> None:
    print(line)
    if _fh is not None:
        try:
            _fh.write(_strip_ansi(line) + "\n")
            _fh.flush()
        except Exception:
            pass


def set_level(name: str) -> None:
    global _level
    _level = _LEVELS.get((name or "").upper(), _level)


def is_debug() -> bool:
    return _level <= _LEVELS["DEBUG"]


def log_debug(msg: str) -> None:
    if _level <= _LEVELS["DEBUG"]:
        _emit(f"[{_now_hms()}] " + _colorize(msg, _C.DIM))


def log_info(msg: str) -> None:
    if _level <= _LEVELS["INFO"]:
        _emit(f"[{_now_hms()}] " + _colorize(msg, _C.DIM))


def log_step(msg: str) -> None:
    if _level <= _LEVELS["INFO"]:
        _emit(f"[{_now_hms()}] " + _colorize(msg, _C.BLUE))


def log_ok(msg: str) -> None:
    if _level <= _LEVELS["INFO"]:
        _emit(f"[{_now_hms()}] " + _colorize(msg, _C.GREEN))


def log_warn(msg: str) -> None:
    if _level <= _LEVELS["WARN"]:
        _emit(f"[{_now_hms()}] " + _colorize(msg, _C.YELLOW))


def log_err(msg: str) -> None:
    if _level <= _LEVELS["ERROR"]:
        _emit(f"[{_now_hms()}] " + _colorize(msg, _C.RED))

