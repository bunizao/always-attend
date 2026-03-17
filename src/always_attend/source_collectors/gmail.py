"""Gmail source collector."""

from __future__ import annotations

from typing import Any

from always_attend.agent_protocol import CandidateRecord, TraceEvent
from always_attend.code_parser import parse_candidate_records
from always_attend.source_collectors.base import find_executable, run_json_command


def collect_gmail_candidates(
    *,
    target_url: str,
    courses: set[str],
    week: int | None,
    env: dict[str, str],
) -> tuple[list[CandidateRecord], list[TraceEvent]]:
    """Collect candidate records from a Gmail CLI if available."""
    del target_url
    executable = find_executable(("gmail-cli", "gmail"))
    if executable is None:
        return [], [
            TraceEvent(
                stage="collect",
                code="gmail_missing",
                message="Gmail CLI was not available.",
                details={"tried": ["gmail-cli", "gmail"]},
            )
        ]

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
        return [], trace

    candidates, parse_trace = parse_candidate_records(
        source="gmail",
        payload=payload,
        courses=courses,
        week=week,
    )
    return candidates, trace + parse_trace
