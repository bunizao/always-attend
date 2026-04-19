"""Helpers for using the Codex Gmail connector as a Gmail backend."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


DEFAULT_GMAIL_PLUGIN_APP_CONFIG = Path.home() / ".codex" / ".tmp" / "plugins" / "plugins" / "gmail" / ".app.json"


def find_codex_executable() -> str | None:
    """Return the configured Codex executable if it is available."""
    configured = (os.getenv("ATTEND_CODEX_EXECUTABLE") or "").strip()
    if configured:
        expanded = Path(configured).expanduser()
        if expanded.exists():
            return str(expanded)
        resolved = shutil.which(configured)
        if resolved:
            return resolved
        return None
    return shutil.which("codex")


def find_gmail_connector_id() -> str | None:
    """Return the configured Gmail connector id when one is available."""
    configured = (os.getenv("ATTEND_GMAIL_CONNECTOR_ID") or "").strip()
    if configured:
        return configured

    app_config = _gmail_plugin_app_config_path()
    if app_config is None or not app_config.exists():
        return None

    try:
        payload = json.loads(app_config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    apps = payload.get("apps", {}) if isinstance(payload, dict) else {}
    gmail = apps.get("gmail", {}) if isinstance(apps, dict) else {}
    connector_id = gmail.get("id") if isinstance(gmail, dict) else None
    if isinstance(connector_id, str) and connector_id.strip():
        return connector_id.strip()
    return None


def codex_gmail_backend_details() -> str | None:
    """Return a short doctor-friendly description for the Codex Gmail backend."""
    codex_executable = find_codex_executable()
    connector_id = find_gmail_connector_id()
    if not codex_executable or not connector_id:
        return None
    return f"{codex_executable} + app://{connector_id}"


def _gmail_plugin_app_config_path() -> Path | None:
    configured = (os.getenv("ATTEND_GMAIL_PLUGIN_APP_CONFIG") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_GMAIL_PLUGIN_APP_CONFIG
