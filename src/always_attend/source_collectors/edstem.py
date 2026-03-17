"""Edstem source collector."""

from __future__ import annotations

from typing import Any

from always_attend.agent_protocol import CandidateRecord, SourceArtifact, TraceEvent
from always_attend.code_parser import parse_candidate_records
from always_attend.source_collectors.base import artifact_from_payload, collect_course_filters, extract_course_code, find_executable, run_json_command


def _match_edstem_course_ids(payload: Any, courses: set[str]) -> list[int]:
    matched: list[int] = []
    if not isinstance(payload, list):
        return matched
    for item in payload:
        if not isinstance(item, dict):
            continue
        haystack = " ".join(str(item.get(key, "")) for key in ("code", "name", "title"))
        course_code = extract_course_code(haystack)
        if course_code and course_code in courses:
            course_id = item.get("id") or item.get("courseId")
            if isinstance(course_id, int):
                matched.append(course_id)
    return sorted(set(matched))


def collect_edstem_candidates(
    *,
    target_url: str,
    courses: set[str],
    week: int | None,
    env: dict[str, str],
) -> tuple[list[CandidateRecord], list[TraceEvent], list[SourceArtifact]]:
    """Collect candidate records from the Ed CLI."""
    del target_url
    executable = find_executable(("edstem-cli", "edstem"))
    if executable is None:
        return [], [
            TraceEvent(
                stage="collect",
                code="edstem_missing",
                message="Edstem CLI was not available.",
                details={"tried": ["edstem-cli", "edstem"]},
            )
        ], []

    trace: list[TraceEvent] = []
    courses_payload, event = run_json_command([executable, "courses", "--json"], env=env)
    if event is not None:
        return [], [event], []

    matched_ids = _match_edstem_course_ids(courses_payload, collect_course_filters(courses))
    if not matched_ids:
        return [], [
            TraceEvent(
                stage="collect",
                code="edstem_courses_not_found",
                message="No Edstem course IDs matched the requested courses.",
                details={"courses": sorted(courses)},
            )
        ], []

    candidates: list[CandidateRecord] = []
    artifacts: list[SourceArtifact] = []
    for course_id in matched_ids:
        for command in (
            [executable, "threads", str(course_id), "--json", "-n", "50"],
            [executable, "lessons", str(course_id), "--json"],
        ):
            payload, command_event = run_json_command(command, env=env)
            if command_event is not None:
                trace.append(command_event)
                continue
            command_candidates, parse_trace = parse_candidate_records(
                source="edstem",
                payload=payload,
                courses=courses,
                week=week,
            )
            candidates.extend(command_candidates)
            trace.extend(parse_trace)
            artifacts.append(
                artifact_from_payload(
                    source="edstem",
                    command=command,
                    payload=payload,
                    requested_courses=courses,
                    requested_week=week,
                )
            )
    return candidates, trace, artifacts
