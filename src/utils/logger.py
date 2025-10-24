"""
 █████╗ ██╗     ██╗    ██╗ █████╗ ██╗   ██╗███████╗
██╔══██╗██║     ██║    ██║██╔══██╗╚██╗ ██╔╝██╔════╝
███████║██║     ██║ █╗ ██║███████║ ╚████╔╝ ███████╗
██╔══██║██║     ██║███╗██║██╔══██║  ╚██╔╝  ╚════██║
██║  ██║███████╗╚███╔███╔╝██║  ██║   ██║   ███████║
╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝

 █████╗ ████████╗████████╗███████╗███╗   ██╗██████╗ 
██╔══██╗╚══██╔══╝╚══██╔══╝██╔════╝████╗  ██║██╔══██╗
███████║   ██║      ██║   █████╗  ██╔██╗ ██║██║  ██║
██╔══██║   ██║      ██║   ██╔══╝  ██║╚██╗██║██║  ██║
██║  ██║   ██║      ██║   ███████╗██║ ╚████║██████╔╝
╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═══╝╚═════╝ 
src/utils/logger.py
Structured logging helpers for Always Attend.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import os
import sys
from typing import Any, Dict, Optional

__all__ = [
    "logger",
    "step",
    "progress",
    "success",
    "debug_detail",
    "get_logger",
    "spinner",
    "set_log_profile",
]

# ---------------------------------------------------------------------------
# Palette and helpers

_PALETTE: Dict[str, str] = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "blue": "\033[34m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "magenta": "\033[35m",
}

LOG_PROFILE = (os.getenv("LOG_PROFILE") or "user").lower()
LOG_FILE = os.getenv("LOG_FILE")
NO_COLOR = os.getenv("NO_COLOR") is not None
LOG_LEVEL_OVERRIDE = os.getenv("LOG_LEVEL")


def _apply_color(text: str, *styles: str) -> str:
    if NO_COLOR or not styles:
        return text
    colors = "".join(_PALETTE.get(style, "") for style in styles)
    return f"{colors}{text}{_PALETTE['reset']}"


# ---------------------------------------------------------------------------
# Formatter and adapter


class LayeredFormatter(logging.Formatter):
    """Formatter that decorates output based on the record.layer attribute."""

    LAYER_MAPPINGS: Dict[str, Dict[str, Any]] = {
        "step": {"icon": "▶", "style": ("blue", "bold")},
        "progress": {"icon": "…", "style": ("cyan",)},
        "success": {"icon": "✓", "style": ("green", "bold")},
        "warning": {"icon": "!", "style": ("yellow", "bold")},
        "error": {"icon": "✗", "style": ("red", "bold")},
        "debug": {"icon": "·", "style": ("magenta",)},
        "user": {"icon": "•", "style": ()},
    }

    def format(self, record: logging.LogRecord) -> str:
        layer = getattr(record, "layer", "user")
        mapping = self.LAYER_MAPPINGS.get(layer, self.LAYER_MAPPINGS["user"])
        icon = mapping["icon"]
        style = mapping["style"]
        message = super().format(record)
        if layer == "debug":
            return f"{_apply_color('[debug]', 'dim')} {message}"
        prefix = _apply_color(icon, *style)
        return f"{prefix} {message}"


class LayeredAdapter(logging.LoggerAdapter):
    """Logger adapter that injects a 'layer' extra value."""

    def __init__(self, logger: logging.Logger, default_layer: str = "user"):
        super().__init__(logger, {"layer": default_layer})

    def log(self, level: int, msg: Any, *args, layer: Optional[str] = None, **kwargs) -> None:
        if not self.isEnabledFor(level):
            return
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("layer", layer or self.extra.get("layer", "user"))
        self.logger.log(level, msg, *args, **kwargs)

    def warning(self, msg: Any, *args, **kwargs) -> None:  # type: ignore[override]
        kwargs.setdefault("layer", "warning")
        super().warning(msg, *args, **kwargs)

    def error(self, msg: Any, *args, **kwargs) -> None:  # type: ignore[override]
        kwargs.setdefault("layer", "error")
        super().error(msg, *args, **kwargs)

    def exception(self, msg: Any, *args, **kwargs) -> None:  # type: ignore[override]
        kwargs.setdefault("layer", "error")
        super().exception(msg, *args, **kwargs)

    def critical(self, msg: Any, *args, **kwargs) -> None:  # type: ignore[override]
        kwargs.setdefault("layer", "error")
        super().critical(msg, *args, **kwargs)


# ---------------------------------------------------------------------------
# Configuration


def _configure_base_logger() -> LayeredAdapter:
    base_logger = logging.getLogger("always_attend")
    if base_logger.handlers:
        return LayeredAdapter(base_logger)

    base_logger.setLevel(logging.DEBUG)
    base_logger.propagate = False

    console_level = logging.INFO
    if LOG_PROFILE == "quiet":
        console_level = logging.WARNING
    elif LOG_PROFILE in {"debug", "verbose"}:
        console_level = logging.DEBUG

    if LOG_LEVEL_OVERRIDE:
        level = getattr(logging, LOG_LEVEL_OVERRIDE.upper(), None)
        if isinstance(level, int):
            console_level = level

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(LayeredFormatter("%(message)s"))
    base_logger.addHandler(console_handler)

    if LOG_FILE:
        try:
            file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            file_formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(logging.DEBUG)
            base_logger.addHandler(file_handler)
        except Exception as exc:
            base_logger.warning("Failed to configure logfile '%s': %s", LOG_FILE, exc)

    return LayeredAdapter(base_logger)


logger = _configure_base_logger()


# ---------------------------------------------------------------------------
# Public helpers


def step(message: str) -> None:
    """Log a major step in the workflow."""
    logger.log(logging.INFO, message, layer="step")


def progress(message: str) -> None:
    """Log a short-lived progress update."""
    logger.log(logging.INFO, message, layer="progress")


def success(message: str) -> None:
    """Log successful completion of an action."""
    logger.log(logging.INFO, message, layer="success")


def debug_detail(message: str) -> None:
    """Log detailed debug information (hidden unless LOG_PROFILE=debug)."""
    logger.log(logging.DEBUG, message, layer="debug")


def get_logger(name: str, *, layer: str = "user") -> LayeredAdapter:
    """Return a child logger using the layered formatting."""
    child = logging.getLogger(f"always_attend.{name}")
    return LayeredAdapter(child, default_layer=layer)


# ---------------------------------------------------------------------------
# Spinner support


class _Spinner:
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str):
        self.message = message
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._status: Optional[str] = None
        self._failure_logged = False

    async def __aenter__(self) -> "_Spinner":
        await _SPINNER_LOCK.acquire()
        self._running = True
        self._task = asyncio.create_task(self._animate())
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self._running = False
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _clear_current_line()
        _SPINNER_LOCK.release()

        if exc_type is not None:
            self.fail(str(exc) if exc else None)
            return False

        if self._status == "failure":
            if not self._failure_logged:
                logger.error(self.message)
        else:
            success(self.message)
        return False

    async def _animate(self) -> None:
        for frame in itertools.cycle(self.FRAMES):
            if not self._running:
                break
            sys.stdout.write(f"\r{_apply_color(frame, 'cyan')} {self.message}")
            sys.stdout.flush()
            await asyncio.sleep(0.12)
        _clear_current_line()

    def succeed(self) -> None:
        self._status = "success"

    def fail(self, reason: Optional[str] = None) -> None:
        self._status = "failure"
        if reason:
            logger.error(f"{self.message} – {reason}")
            self._failure_logged = True

    def update(self, message: str) -> None:
        self.message = message

    def note(self, message: str, *, level: str = "info") -> None:
        _clear_current_line()
        log_fn = getattr(logger, level, logger.info)
        log_fn(message)


_SPINNER_LOCK = asyncio.Lock()


def _clear_current_line() -> None:
    sys.stdout.write("\r")
    sys.stdout.write(" " * 120)
    sys.stdout.write("\r")
    sys.stdout.flush()


def spinner(message: str) -> _Spinner:
    """Return an async spinner context manager."""
    return _Spinner(message)


def set_log_profile(profile: str) -> None:
    """Adjust console logging verbosity at runtime."""
    global LOG_PROFILE
    profile = (profile or "user").lower()
    level_map = {
        "quiet": logging.WARNING,
        "debug": logging.DEBUG,
        "verbose": logging.DEBUG,
        "user": logging.INFO,
    }
    level = level_map.get(profile, logging.INFO)

    base_logger = logging.getLogger("always_attend")
    base_logger.setLevel(logging.DEBUG)
    for handler in base_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(level)

    global LOG_PROFILE
    LOG_PROFILE = profile
    os.environ["LOG_PROFILE"] = profile
