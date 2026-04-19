"""Gmail source collector."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from always_attend.agent_protocol import CandidateRecord, SourceArtifact, TraceEvent
from always_attend.code_parser import parse_candidate_records
from always_attend.gmail_codex import find_codex_executable, find_gmail_connector_id
from always_attend.source_collectors.base import artifact_from_payload, find_executable, run_json_command


def collect_gmail_candidates(
    *,
    target_url: str,
    courses: set[str],
    week: int | None,
    env: dict[str, str],
) -> tuple[list[CandidateRecord], list[TraceEvent], list[SourceArtifact]]:
    """Collect candidate records from a Gmail CLI if available."""
    del target_url
    trace: list[TraceEvent] = []
    backend = _requested_backend()

    cli_executable = find_executable(("gmail-cli", "gmail"))
    if backend in {"auto", "gmail-cli"} and cli_executable is not None:
        return _collect_with_gmail_cli(executable=cli_executable, courses=courses, week=week, env=env)

    if backend == "gmail-cli":
        return [], [
            TraceEvent(
                stage="collect",
                code="gmail_cli_missing",
                message="Requested gmail-cli backend was not available.",
                details={"tried": ["gmail-cli", "gmail"]},
            )
        ], []

    gws_executable = find_executable(("gws",))
    if backend in {"auto", "gws"} and gws_executable is not None:
        return _collect_with_gws(executable=gws_executable, courses=courses, week=week, env=env)

    if backend == "gws":
        return [], [
            TraceEvent(
                stage="collect",
                code="gmail_gws_missing",
                message="Requested gws backend was not available.",
                details={"tried": ["gws"]},
            )
        ], []

    if backend in {"auto", "codex"}:
        candidates, codex_trace, artifacts = _collect_with_codex(
            courses=courses,
            week=week,
            env=env,
        )
        trace.extend(codex_trace)
        if candidates or artifacts or backend == "codex":
            return candidates, trace, artifacts

    return [], trace + [
        TraceEvent(
            stage="collect",
            code="gmail_missing",
            message="No Gmail backend was available.",
            details={"tried": ["gmail-cli", "gmail", "gws", "codex_gmail_connector"]},
        )
    ], []


def _collect_with_gmail_cli(
    *,
    executable: str,
    courses: set[str],
    week: int | None,
    env: dict[str, str],
) -> tuple[list[CandidateRecord], list[TraceEvent], list[SourceArtifact]]:
    """Collect Gmail candidates with the dedicated Gmail CLI."""
    command_options = [
        [executable, "messages", "--json"],
        [executable, "threads", "--json"],
        [executable, "--json"],
    ]
    payload: Any | None = None
    trace: list[TraceEvent] = []
    for command in command_options:
        payload, event = run_json_command(command, env=env)
        if event is None:
            break
        trace.append(event)
        payload = None
    if payload is None:
        return [], trace, []

    candidates, parse_trace = parse_candidate_records(
        source="gmail",
        payload=payload,
        courses=courses,
        week=week,
    )
    artifact = artifact_from_payload(
        source="gmail",
        command=command,
        payload=payload,
        requested_courses=courses,
        requested_week=week,
    )
    return candidates, trace + parse_trace, [artifact]


def _collect_with_codex(
    *,
    courses: set[str],
    week: int | None,
    env: dict[str, str],
) -> tuple[list[CandidateRecord], list[TraceEvent], list[SourceArtifact]]:
    """Collect Gmail candidates through the Codex Gmail connector."""
    del env
    codex_executable = find_codex_executable()
    connector_id = find_gmail_connector_id()
    if codex_executable is None or connector_id is None:
        return [], [
            TraceEvent(
                stage="collect",
                code="gmail_codex_unavailable",
                message="Codex Gmail connector backend was not available.",
                details={
                    "codex_found": bool(codex_executable),
                    "connector_found": bool(connector_id),
                },
            )
        ], []

    query = _codex_gmail_query(courses=courses, week=week)
    trace = [
        TraceEvent(
            stage="collect",
            code="gmail_using_codex_connector",
            message="Using the Codex Gmail connector as the Gmail source backend.",
            details={
                "command": codex_executable,
                "connector_id": connector_id,
                "query": query,
            },
        )
    ]
    payload, command, event = _run_codex_gmail_query(
        codex_executable=codex_executable,
        connector_id=connector_id,
        query=query,
    )
    if event is not None or payload is None:
        if event is not None:
            trace.append(event)
        return [], trace, []

    messages = payload.get("messages", []) if isinstance(payload, dict) else []
    if not isinstance(messages, list) or not messages:
        trace.append(
            TraceEvent(
                stage="collect",
                code="gmail_codex_messages_not_found",
                message="Codex Gmail connector returned no candidate messages.",
                details={
                    "query": query,
                    "course_filters": sorted(courses),
                    "week": week,
                },
            )
        )
        return [], trace, []

    candidates: list[CandidateRecord] = []
    artifacts: list[SourceArtifact] = []
    for message in messages:
        normalized_payload = _normalize_codex_message_payload(message)
        parse_payload = _codex_candidate_payload(message)
        command_candidates, parse_trace = parse_candidate_records(
            source="gmail",
            payload=parse_payload,
            courses=courses,
            week=week,
        )
        candidates.extend(command_candidates)
        trace.extend(parse_trace)
        artifacts.append(
            artifact_from_payload(
                source="gmail",
                command=command,
                payload=normalized_payload,
                requested_courses=courses,
                requested_week=week,
            )
        )
    return candidates, trace, artifacts


def _collect_with_gws(
    *,
    executable: str,
    courses: set[str],
    week: int | None,
    env: dict[str, str],
) -> tuple[list[CandidateRecord], list[TraceEvent], list[SourceArtifact]]:
    """Collect Gmail candidates through the Google Workspace CLI."""
    trace = [
        TraceEvent(
            stage="collect",
            code="gmail_using_gws",
            message="Using gws CLI as the Gmail source backend.",
            details={"command": executable},
        )
    ]
    list_command = [
        executable,
        "gmail",
        "users",
        "messages",
        "list",
        "--params",
        _gws_list_params(courses=courses),
    ]
    listing_payload, list_event = run_json_command(list_command, env=env)
    if list_event is not None:
        return [], trace + [list_event], []

    messages = listing_payload.get("messages", []) if isinstance(listing_payload, dict) else []
    if not isinstance(messages, list) or not messages:
        trace.append(
            TraceEvent(
                stage="collect",
                code="gmail_messages_not_found",
                message="GWS Gmail listing returned no candidate messages.",
                details={
                    "course_filters": sorted(courses),
                    "week": week,
                },
            )
        )
        return [], trace, []

    candidates: list[CandidateRecord] = []
    artifacts: list[SourceArtifact] = []
    for message in messages[:20]:
        message_id = str(message.get("id", "")).strip() if isinstance(message, dict) else ""
        if not message_id:
            continue
        command = [
            executable,
            "gmail",
            "users",
            "messages",
            "get",
            "--params",
            json.dumps(
                {
                    "userId": "me",
                    "id": message_id,
                    "format": "full",
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
        ]
        payload, event = run_json_command(command, env=env)
        if event is not None:
            trace.append(event)
            continue
        normalized_payload = _normalize_gws_message_payload(payload)
        command_candidates, parse_trace = parse_candidate_records(
            source="gmail",
            payload=normalized_payload,
            courses=courses,
            week=week,
        )
        candidates.extend(command_candidates)
        trace.extend(parse_trace)
        artifacts.append(
            artifact_from_payload(
                source="gmail",
                command=command,
                payload=normalized_payload,
                requested_courses=courses,
                requested_week=week,
            )
        )
    return candidates, trace, artifacts


def _requested_backend() -> str:
    value = (os.getenv("ATTEND_GMAIL_BACKEND") or "auto").strip().lower()
    aliases = {
        "cli": "gmail-cli",
        "gmail": "gmail-cli",
        "plugin": "codex",
        "mcp": "codex",
        "codex-plugin": "codex",
    }
    normalized = aliases.get(value, value)
    if normalized in {"auto", "gmail-cli", "gws", "codex"}:
        return normalized
    return "auto"


def _codex_gmail_query(*, courses: set[str], week: int | None) -> str:
    query_parts = ["in:anywhere", "newer_than:120d"]
    if courses:
        query_parts.append("(" + " OR ".join(sorted(courses)) + ")")
    if week is not None:
        query_parts.append(f"(\"Week {week}\" OR \"week {week}\" OR \"wk {week}\")")
    return " ".join(query_parts)


def _run_codex_gmail_query(
    *,
    codex_executable: str,
    connector_id: str,
    query: str,
) -> tuple[dict[str, Any] | None, list[str], TraceEvent | None]:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "thread_id": {"type": "string"},
                        "subject": {"type": "string"},
                        "from": {"type": "string"},
                        "date": {"type": "string"},
                        "snippet": {"type": "string"},
                        "plain_text": {"type": "string"},
                        "html": {"type": "string"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "id",
                        "thread_id",
                        "subject",
                        "from",
                        "date",
                        "snippet",
                        "plain_text",
                        "html",
                        "labels",
                    ],
                    "additionalProperties": False,
                },
            },
            "notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["status", "messages", "notes"],
        "additionalProperties": False,
    }

    prompt = (
        f'Use [$gmail](app://{connector_id}) to collect Gmail messages relevant to attendance codes. '
        f'First search Gmail with query syntax "{query}" and keep the result set small. '
        "Prefer search_emails for the shortlist, then read full bodies only when the snippet is insufficient. "
        "Return only JSON matching the schema. "
        "If Gmail access is unavailable, return status unavailable, an empty messages list, and a brief note. "
        "Each message must include id, thread_id, subject, from, date, snippet, plain_text, html, and labels."
    )
    timeout_ms = _codex_timeout_ms()

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as schema_file:
        json.dump(schema, schema_file)
        schema_path = schema_file.name
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".json", delete=False) as output_file:
        output_path = output_file.name

    command = [
        codex_executable,
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--output-schema",
        schema_path,
        "--output-last-message",
        output_path,
        prompt,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
        )
    except subprocess.TimeoutExpired as exc:
        return None, command, TraceEvent(
            stage="collect",
            code="gmail_codex_timeout",
            message="Codex Gmail connector query timed out.",
            details={
                "command": command,
                "timeout_ms": timeout_ms,
                "stderr": (exc.stderr or "").strip(),
            },
        )
    finally:
        _safe_unlink(schema_path)

    try:
        raw_output = Path(output_path).read_text(encoding="utf-8").strip()
    except OSError:
        raw_output = ""
    finally:
        _safe_unlink(output_path)

    if result.returncode != 0:
        return None, command, TraceEvent(
            stage="collect",
            code="gmail_codex_failed",
            message="Codex Gmail connector query failed.",
            details={
                "command": command,
                "returncode": result.returncode,
                "stderr": (result.stderr or "").strip(),
                "stdout": (result.stdout or "").strip(),
            },
        )

    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        return None, command, TraceEvent(
            stage="collect",
            code="gmail_codex_invalid_json",
            message="Codex Gmail connector did not return valid JSON.",
            details={
                "command": command,
                "error": str(exc),
                "raw_output": raw_output[:1000],
            },
        )

    status = str(payload.get("status", "")).strip().lower()
    if status in {"unavailable", "error"}:
        return None, command, TraceEvent(
            stage="collect",
            code="gmail_codex_unavailable",
            message="Codex Gmail connector reported that Gmail access was unavailable.",
            details={
                "command": command,
                "notes": payload.get("notes", []),
            },
        )
    return payload, command, None


def _normalize_codex_message_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    headers: dict[str, str] = {}
    for source_key, target_key in (("subject", "subject"), ("from", "from"), ("date", "date")):
        value = str(payload.get(source_key, "")).strip()
        if value:
            headers[target_key] = value
    normalized: dict[str, Any] = {
        "id": payload.get("id"),
        "threadId": payload.get("thread_id"),
        "snippet": payload.get("snippet"),
        "labelIds": payload.get("labels", []),
    }
    if headers:
        normalized["headers"] = headers
    plain_text = str(payload.get("plain_text", "")).strip()
    if plain_text:
        normalized["decoded_plain_text"] = [plain_text]
    html = str(payload.get("html", "")).strip()
    if html:
        normalized["decoded_html"] = [html]
    return normalized


def _codex_candidate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    sections: list[str] = []
    for key in ("subject", "snippet", "plain_text"):
        value = str(payload.get(key, "")).strip()
        if value:
            sections.append(value)
    combined_text = "\n\n".join(sections)
    candidate_payload: dict[str, Any] = {"document": combined_text}
    html = str(payload.get("html", "")).strip()
    if html:
        candidate_payload["html"] = html
    return candidate_payload


def _codex_timeout_ms() -> int:
    raw_value = (os.getenv("ATTEND_CODEX_TIMEOUT_MS") or "90000").strip()
    try:
        return max(1000, int(raw_value))
    except ValueError:
        return 90000


def _safe_unlink(path: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


def _gws_list_params(*, courses: set[str]) -> str:
    query_parts: list[str] = []
    if courses:
        query_parts.append("{" + " ".join(sorted(courses)) + "}")
    params = {
        "userId": "me",
        "maxResults": 20,
    }
    if query_parts:
        params["q"] = " ".join(query_parts)
    return json.dumps(params, separators=(",", ":"), sort_keys=True)


def _normalize_gws_message_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    normalized: dict[str, Any] = {}
    for key in ("id", "threadId", "labelIds", "snippet", "internalDate"):
        if key in payload:
            normalized[key] = payload[key]
    plain_parts, html_parts = _extract_gws_message_bodies(payload.get("payload"))
    header_values = _extract_gws_header_values(payload.get("payload"))
    if header_values:
        normalized["headers"] = header_values
    if plain_parts:
        normalized["decoded_plain_text"] = plain_parts
    if html_parts:
        normalized["decoded_html"] = html_parts
    return normalized


def _extract_gws_message_bodies(payload: Any) -> tuple[list[str], list[str]]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in _walk_gws_message_parts(payload):
        mime_type = str(part.get("mimeType", "")).lower()
        body = part.get("body", {})
        body_data = body.get("data") if isinstance(body, dict) else None
        decoded = _decode_gws_body(body_data)
        if not decoded:
            continue
        if mime_type.startswith("text/plain"):
            plain_parts.append(decoded)
        elif mime_type.startswith("text/html"):
            html_parts.append(decoded)
    return plain_parts, html_parts


def _extract_gws_header_values(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    selected = {"subject", "from", "to", "date"}
    values: dict[str, str] = {}
    for item in payload.get("headers", []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("name", "")).strip().lower()
        value = str(item.get("value", "")).strip()
        if key in selected and value:
            values[key] = value
    return values


def _walk_gws_message_parts(part: Any) -> list[dict[str, Any]]:
    if not isinstance(part, dict):
        return []
    parts = [part]
    for child in part.get("parts", []):
        parts.extend(_walk_gws_message_parts(child))
    return parts


def _decode_gws_body(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding).decode("utf-8", errors="replace")
    except (ValueError, UnicodeDecodeError):
        return None
