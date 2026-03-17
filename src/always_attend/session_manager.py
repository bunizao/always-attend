"""Shared session management and dependency checks for agent workflows."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from always_attend.okta_client import (
    OktaCliError,
    OktaClient,
    build_cookie_header,
    extract_cookie_items,
    write_storage_state_from_okta,
)
from always_attend.paths import storage_state_file


@dataclass(frozen=True)
class DependencyStatus:
    """Single dependency health check result."""

    name: str
    status: str
    details: str
    install_hint: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Return a JSON-friendly dependency status."""
        return {
            "name": self.name,
            "status": self.status,
            "details": self.details,
            "install_hint": self.install_hint,
        }


class SessionManager:
    """Manage Okta-backed session state for the attendance pipeline."""

    def __init__(self, okta_client: OktaClient | None = None) -> None:
        self._okta = okta_client or OktaClient()

    def ensure_storage_state(self, target_url: str) -> dict[str, Any]:
        """Persist a Playwright storage_state file for the target URL."""
        payload = self._okta.cookies(url=target_url).payload
        return write_storage_state_from_okta(payload, url=target_url, output_path=storage_state_file())

    def check_okta_session(self, target_url: str, timeout_ms: int = 30000) -> dict[str, Any]:
        """Verify that an Okta-backed session is available for the target."""
        return self._okta.check(url=target_url, timeout_ms=timeout_ms).payload

    def build_source_environment(self, source: str, target_url: str) -> dict[str, str]:
        """Build a source-specific environment with shared Okta session data."""
        env = os.environ.copy()
        session_url = self._source_session_url(source, target_url)
        if not session_url:
            return env

        try:
            payload = self._okta.cookies(url=session_url).payload
        except OktaCliError:
            return env

        cookie_items = extract_cookie_items(payload)
        if not cookie_items:
            return env

        env["ALWAYS_ATTEND_OKTA_URL"] = session_url
        env["ALWAYS_ATTEND_OKTA_COOKIES_JSON"] = json.dumps(cookie_items)
        env["OKTA_COOKIES_JSON"] = env["ALWAYS_ATTEND_OKTA_COOKIES_JSON"]

        cookie_header = build_cookie_header(payload)
        if cookie_header:
            env["ALWAYS_ATTEND_OKTA_COOKIE_HEADER"] = cookie_header
            env["OKTA_COOKIE_HEADER"] = cookie_header

        if source == "moodle":
            moodle_session = next(
                (
                    item.get("value", "")
                    for item in cookie_items
                    if str(item.get("name", "")).lower() == "moodlesession"
                ),
                "",
            )
            if moodle_session:
                env["MOODLE_SESSION"] = moodle_session

        return env

    def doctor(self) -> list[DependencyStatus]:
        """Return the current toolchain health summary."""
        return [
            self._command_status("okta", ("okta",)),
            self._python_module_status("playwright", "playwright"),
            self._command_status("moodle-cli", ("moodle-cli", "moodle")),
            self._command_status("edstem", ("edstem-cli", "edstem")),
            self._command_status("gogcli", ("gogcli", "gog")),
            self._python_module_status("pyyaml", "yaml"),
        ]

    def doctor_payload(self) -> dict[str, Any]:
        """Return machine-readable dependency health with aggregate status."""
        checks = [item.to_dict() for item in self.doctor()]
        all_ok = all(item["status"] == "ok" for item in checks)
        return {
            "checks": checks,
            "ready": all_ok,
        }

    @staticmethod
    def _source_session_url(source: str, target_url: str) -> str:
        source = source.lower()
        if source == "moodle":
            return os.getenv("MOODLE_TARGET_URL", "https://learning.monash.edu")
        return target_url

    @staticmethod
    def _command_status(name: str, commands: tuple[str, ...]) -> DependencyStatus:
        for command in commands:
            resolved = shutil.which(command)
            if resolved:
                return DependencyStatus(name=name, status="ok", details=resolved)
        return DependencyStatus(
            name=name,
            status="missing",
            details=f"Tried: {', '.join(commands)}",
            install_hint=_install_hint_for(name),
        )

    @staticmethod
    def _python_module_status(name: str, module_name: str) -> DependencyStatus:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            return DependencyStatus(
                name=name,
                status="missing",
                details=f"Python module '{module_name}' not found",
                install_hint=_install_hint_for(name),
            )
        origin = spec.origin or "namespace"
        return DependencyStatus(name=name, status="ok", details=origin)


def _install_hint_for(name: str) -> str | None:
    hints = {
        "okta": "uv tool install okta-auth-cli",
        "moodle-cli": "uv tool install moodle-cli",
        "edstem": "uv tool install edstem-cli",
        "gogcli": "Install the required GOG CLI plugin or add it to PATH before rerunning attend.",
        "pyyaml": "python -m pip install PyYAML",
    }
    return hints.get(name)
