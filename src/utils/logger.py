"""Structured logging helpers for Always Attend."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "apply_env_configuration",
    "logger",
    "step",
    "progress",
    "success",
    "debug_detail",
    "get_logger",
    "spinner",
    "set_log_profile",
]

_PALETTE: Dict[str, str] = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "blue": "\033[34m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
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


class LayeredFormatter(logging.Formatter):
    """Formatter that decorates output based on the record.layer attribute."""

    LAYER_MAPPINGS: Dict[str, Dict[str, Any]] = {
        "step": {"icon": ">", "style": ("blue", "bold")},
        "progress": {"icon": "-", "style": ("blue",)},
        "success": {"icon": "+", "style": ("green", "bold")},
        "warning": {"icon": "!", "style": ("yellow", "bold")},
        "error": {"icon": "x", "style": ("red", "bold")},
        "debug": {"icon": ".", "style": ("magenta",)},
        "user": {"icon": "*", "style": ()},
    }

    def format(self, record: logging.LogRecord) -> str:
        layer = getattr(record, "layer", "user")
        mapping = self.LAYER_MAPPINGS.get(layer, self.LAYER_MAPPINGS["user"])
        message = super().format(record)
        if layer == "debug":
            return "{} {}".format(_apply_color("[debug]", "dim"), message)
        prefix = _apply_color(mapping["icon"], *mapping["style"])
        return f"{prefix} {message}"


class LayeredAdapter(logging.LoggerAdapter):
    """Logger adapter that injects a ``layer`` extra value."""

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


def step(message: str, *, animated: bool = True) -> None:
    """Log a major step in the workflow."""
    _ = animated
    logger.log(logging.INFO, message, layer="step")


def progress(message: str, *, animated: bool = True) -> None:
    """Log a short-lived progress update."""
    _ = animated
    logger.log(logging.INFO, message, layer="progress")


def success(message: str, *, animated: bool = True) -> None:
    """Log successful completion of an action."""
    _ = animated
    logger.log(logging.INFO, message, layer="success")


def debug_detail(message: str) -> None:
    """Log detailed debug information."""
    logger.log(logging.DEBUG, message, layer="debug")


def get_logger(name: str, *, layer: str = "user") -> LayeredAdapter:
    """Return a child logger using the layered formatting."""
    child = logging.getLogger(f"always_attend.{name}")
    return LayeredAdapter(child, default_layer=layer)


class _Spinner:
    """Compatibility wrapper for code paths that expect a spinner context."""

    def __init__(self, message: str):
        self.message = message
        self._status: Optional[str] = None
        self._failure_logged = False

    async def __aenter__(self) -> "_Spinner":
        progress(self.message)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.fail(str(exc) if exc else None)
            return False

        if self._status == "failure":
            if not self._failure_logged:
                logger.error(self.message)
        else:
            success(self.message)
        return False

    def succeed(self) -> None:
        self._status = "success"

    def fail(self, reason: Optional[str] = None) -> None:
        self._status = "failure"
        if reason:
            logger.error(f"{self.message}: {reason}")
            self._failure_logged = True

    def update(self, message: str) -> None:
        self.message = message

    def note(self, message: str, *, level: str = "info") -> None:
        log_fn = getattr(logger, level, logger.info)
        log_fn(message)


def spinner(message: str) -> _Spinner:
    """Return a compatibility context manager for progress logging."""
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

    LOG_PROFILE = profile
    os.environ["LOG_PROFILE"] = profile


def apply_env_configuration() -> None:
    """Apply LOG_PROFILE and LOG_FILE after environment loading."""
    profile = (os.getenv("LOG_PROFILE") or LOG_PROFILE or "user").lower()
    set_log_profile(profile)

    desired_log = os.getenv("LOG_FILE", "").strip()
    base_logger = logging.getLogger("always_attend")
    existing_file_handlers = [
        handler
        for handler in base_logger.handlers
        if isinstance(handler, logging.FileHandler)
    ]

    if not desired_log:
        for handler in existing_file_handlers:
            base_logger.removeHandler(handler)
            handler.close()
        return

    target_path = Path(desired_log).expanduser()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    for handler in existing_file_handlers:
        current_path = getattr(handler, "baseFilename", "")
        if current_path == str(target_path):
            return
        base_logger.removeHandler(handler)
        handler.close()

    file_handler = logging.FileHandler(target_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    file_handler.setLevel(logging.DEBUG)
    base_logger.addHandler(file_handler)
