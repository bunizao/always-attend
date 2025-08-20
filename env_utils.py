"""Utilities for loading environment variables from .env files."""

from __future__ import annotations

import os


def load_env(path: str = ".env") -> None:
    """Populate :data:`os.environ` with values from a ``.env`` file.

    Existing environment variables are not overridden. Lines beginning with
    ``#`` or without an ``=`` are ignored. Values wrapped in single or double
    quotes are unwrapped before assignment.
    """
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as file:
            for raw in file:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        # Environment loading should not be fatal; swallow errors intentionally.
        pass

__all__ = ["load_env"]

