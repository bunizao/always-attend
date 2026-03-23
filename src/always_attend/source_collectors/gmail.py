"""Gmail source collector."""

from __future__ import annotations

import base64
import json
from typing import Any

from always_attend.agent_protocol import CandidateRecord, SourceArtifact, TraceEvent
from always_attend.code_parser import parse_candidate_records
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
    executable = find_executable(("gmail-cli", "gmail"))
    if executable is not None:
        return _collect_with_gmail_cli(executable=executable, courses=courses, week=week, env=env)
    gws_executable = find_executable(("gws",))
    if gws_executable is not None:
        return _collect_with_gws(executable=gws_executable, courses=courses, week=week, env=env)
    return [], [
        TraceEvent(
            stage="collect",
            code="gmail_missing",
            message="Gmail CLI was not available.",
            details={"tried": ["gmail-cli", "gmail", "gws"]},
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
