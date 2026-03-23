"""Shared session management and dependency checks for agent workflows."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from always_attend.okta_client import (
    OktaCliError,
    OktaClient,
    build_playwright_storage_state,
    build_cookie_header,
    extract_cookie_items,
    write_storage_state_from_okta,
)
from always_attend.paths import storage_state_file
from utils.browser_session import resolve_browser_session_source
from utils.session import is_storage_state_effective


@dataclass(frozen=True)
class DependencyStatus:
    """Single dependency health check result."""

    name: str
    status: str
    details: str
    install_hint: str | None = None
    optional: bool = False

    def to_dict(self) -> dict[str, str | None]:
        """Return a JSON-friendly dependency status."""
        return {
            "name": self.name,
            "status": self.status,
            "details": self.details,
            "install_hint": self.install_hint,
            "optional": self.optional,
        }


class SessionManager:
    """Manage Okta-backed session state for the attendance pipeline."""

    def __init__(self, okta_client: OktaClient | None = None) -> None:
        self._okta = okta_client or OktaClient()

    def ensure_storage_state(self, target_url: str) -> dict[str, Any]:
        """Persist a Playwright storage_state file for the target URL."""
        if not self.requires_okta_session(target_url):
            return {
                "path": str(storage_state_file()),
                "cookie_count": 0,
                "skipped": True,
            }
        try:
            payload = self._okta.cookies(url=target_url).payload
        except OktaCliError:
            existing_state = storage_state_file()
            if is_storage_state_effective(str(existing_state)):
                return {
                    "path": str(existing_state),
                    "cookie_count": 0,
                    "reused": True,
                }
            raise
        return write_storage_state_from_okta(payload, url=target_url, output_path=storage_state_file())

    def check_okta_session(self, target_url: str, timeout_ms: int = 30000) -> dict[str, Any]:
        """Verify that an Okta-backed session is available for the target."""
        if not self.requires_okta_session(target_url):
            return {"ok": True, "skipped": True}
        return self._okta.check(url=target_url, timeout_ms=timeout_ms).payload

    async def import_browser_session(self, target_url: str, timeout_ms: int = 60000) -> dict[str, Any]:
        """Import cookies from a local browser profile into Playwright storage_state."""
        try:
            cookie_items = _browser_cookie_items_for_target(target_url)
        except Exception as exc:
            return {
                "status": "failed",
                "mode": "browser_cookie_import",
                "reason": str(exc),
            }
        if cookie_items:
            storage_state = build_playwright_storage_state(cookie_items, url=target_url)
            output_path = storage_state_file()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(storage_state, indent=2), encoding="utf-8")
            return {
                "status": "ok",
                "mode": "browser_cookie_import",
                "storage_state": str(output_path),
                "cookie_count": len(storage_state.get("cookies", [])),
            }
        return {
            "status": "failed",
            "mode": "browser_cookie_import",
            "reason": "No reusable browser session was found.",
        }

    def build_source_environment(self, source: str, target_url: str) -> dict[str, str]:
        """Build a source-specific environment with shared Okta session data."""
        env = os.environ.copy()
        session_url = self._source_session_url(source, target_url)
        if not session_url:
            return env
        if not self.requires_okta_session(session_url):
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
        ]

    def doctor_payload(self) -> dict[str, Any]:
        """Return machine-readable dependency health with aggregate status."""
        checks = [item.to_dict() for item in self.doctor()]
        all_ok = all(
            item["status"] == "ok" or bool(item.get("optional"))
            for item in checks
        )
        return {
            "checks": checks,
            "ready": all_ok,
        }

    @staticmethod
    def requires_okta_session(target_url: str) -> bool:
        """Return whether a target should use Okta-backed session bootstrapping."""
        parsed = urlparse((target_url or "").strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme == "file":
            return False
        if host in {"127.0.0.1", "localhost"}:
            return False
        if host.endswith(".local"):
            return False
        return True

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
            optional=(name == "gogcli"),
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


def _browsercookie_loader_name(channel: str) -> str:
    normalized = (channel or "chrome").strip().lower()
    mapping = {
        "chrome": "chrome",
        "chrome-beta": "chrome",
        "chrome-canary": "chrome",
        "msedge": "edge",
        "msedge-beta": "edge",
    }
    return mapping.get(normalized, "chrome")


def _browser_cookie_items_for_target(target_url: str) -> list[dict[str, Any]]:
    source = resolve_browser_session_source()
    channel = source.channel if source is not None else (os.getenv("BROWSER_CHANNEL") or "chrome")
    loader_name = _browsercookie_loader_name(channel)
    browsercookie = _load_browsercookie_module()
    loader = getattr(browsercookie, loader_name)

    cookie_files = None
    if source is not None:
        cookie_path = source.user_data_dir / source.profile_name / "Cookies"
        cookie_files = [str(cookie_path)] if cookie_path.exists() else None

    cookie_jar = loader(cookie_files=cookie_files)
    target_host = (urlparse(target_url).hostname or "").lower()
    if not target_host:
        return []

    items: list[dict[str, Any]] = []
    for cookie in cookie_jar:
        domain = str(getattr(cookie, "domain", "") or "")
        if not _cookie_matches_target(domain, target_host):
            continue
        expires = getattr(cookie, "expires", None)
        expires_value = float(expires) if expires else -1
        if expires_value <= 0:
            expires_value = -1
        item = {
            "name": cookie.name,
            "value": cookie.value,
            "domain": domain.lstrip(".") or target_host,
            "path": getattr(cookie, "path", "/") or "/",
            "expires": expires_value,
            "httpOnly": _cookie_is_http_only(cookie),
            "secure": bool(getattr(cookie, "secure", False)),
        }
        items.append(item)
    return items


def _cookie_matches_target(domain: str, target_host: str) -> bool:
    normalized = domain.lstrip(".").lower()
    return bool(normalized) and (normalized == target_host or target_host.endswith(f".{normalized}"))


def _cookie_is_http_only(cookie: Any) -> bool:
    rest = getattr(cookie, "_rest", {}) or {}
    for key in ("HttpOnly", "httponly"):
        if key in rest:
            return str(rest[key]).lower() not in {"", "false", "0", "none"}
    return False


def _load_browsercookie_module():
    import browsercookie

    return browsercookie
