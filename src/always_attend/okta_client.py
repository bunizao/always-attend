"""Okta CLI integration for agent-oriented workflows."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from always_attend.paths import ensure_parent


class OktaCliError(RuntimeError):
    """Raised when the external Okta CLI fails."""


@dataclass(frozen=True)
class OktaCommandResult:
    """Parsed result from an Okta CLI invocation."""

    command: list[str]
    payload: Any


def _run_okta_json(command: list[str]) -> OktaCommandResult:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "okta command failed").strip()
        raise OktaCliError(message)

    stdout = (result.stdout or "").strip()
    if not stdout:
        return OktaCommandResult(command=command, payload={})

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise OktaCliError(f"Invalid JSON from okta CLI: {exc}") from exc
    return OktaCommandResult(command=command, payload=payload)


class OktaClient:
    """Thin wrapper over the installed `okta` CLI."""

    def login(
        self,
        *,
        url: str,
        username: str | None = None,
        password: str | None = None,
        totp_secret: str | None = None,
        headed: bool = False,
        timeout_ms: int | None = None,
    ) -> OktaCommandResult:
        command = ["okta", "login", "--json"]
        if username:
            command.extend(["--username", username])
        if password:
            command.extend(["--password", password])
        if totp_secret:
            command.extend(["--totp-secret", totp_secret])
        if headed:
            command.append("--headed")
        if timeout_ms is not None:
            command.extend(["--timeout-ms", str(timeout_ms)])
        command.append(url)
        return _run_okta_json(command)

    def check(self, *, url: str, timeout_ms: int | None = None) -> OktaCommandResult:
        command = ["okta", "check", "--json"]
        if timeout_ms is not None:
            command.extend(["--timeout-ms", str(timeout_ms)])
        command.append(url)
        return _run_okta_json(command)

    def cookies(self, *, url: str, domain: str | None = None) -> OktaCommandResult:
        command = ["okta", "cookies", "--json"]
        if domain:
            command.extend(["--domain", domain])
        command.append(url)
        return _run_okta_json(command)

    def list_sessions(self) -> OktaCommandResult:
        return _run_okta_json(["okta", "list", "--json"])


def _parse_cookie_header(header: str) -> list[dict[str, Any]]:
    cookies: list[dict[str, Any]] = []
    for part in header.split(";"):
        name, separator, value = part.strip().partition("=")
        if not separator or not name:
            continue
        cookies.append({"name": name.strip(), "value": value.strip()})
    return cookies


def _extract_cookie_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("cookies", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, str):
            return _parse_cookie_header(value)

    session_payload = payload.get("session")
    if isinstance(session_payload, dict):
        nested = session_payload.get("cookies")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if isinstance(nested, str):
            return _parse_cookie_header(nested)

    header = payload.get("cookie_header")
    if isinstance(header, str):
        return _parse_cookie_header(header)

    return []


def extract_cookie_items(payload: Any) -> list[dict[str, Any]]:
    """Return normalized cookie items from an Okta CLI payload."""
    return _extract_cookie_items(payload)


def build_cookie_header(payload: Any) -> str:
    """Serialize cookie payloads into a Cookie request header."""
    parts = []
    for item in _extract_cookie_items(payload):
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        parts.append(f"{name}={item.get('value', '')}")
    return "; ".join(parts)


def _normalize_cookie(cookie: dict[str, Any], host: str, secure_default: bool) -> dict[str, Any]:
    normalized = {
        "name": str(cookie.get("name", "")).strip(),
        "value": str(cookie.get("value", "")),
        "domain": str(cookie.get("domain") or host),
        "path": str(cookie.get("path") or "/"),
        "expires": float(cookie.get("expires", -1)),
        "httpOnly": bool(cookie.get("httpOnly", False)),
        "secure": bool(cookie.get("secure", secure_default)),
    }
    same_site = cookie.get("sameSite")
    if same_site in {"Strict", "Lax", "None"}:
        normalized["sameSite"] = same_site
    return normalized


def build_playwright_storage_state(payload: Any, *, url: str) -> dict[str, Any]:
    """Convert Okta cookie payloads to Playwright storage_state."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    secure_default = parsed.scheme == "https"
    cookies = [
        _normalize_cookie(item, host=host, secure_default=secure_default)
        for item in _extract_cookie_items(payload)
        if str(item.get("name", "")).strip()
    ]
    return {"cookies": cookies, "origins": []}


def write_storage_state_from_okta(payload: Any, *, url: str, output_path: Path) -> dict[str, Any]:
    """Persist Okta cookies in Playwright storage_state format."""
    storage_state = build_playwright_storage_state(payload, url=url)
    ensure_parent(output_path)
    output_path.write_text(json.dumps(storage_state, indent=2), encoding="utf-8")
    return {
        "path": str(output_path),
        "cookie_count": len(storage_state["cookies"]),
    }
