"""Moodle source collector."""

from __future__ import annotations

from typing import Any

from always_attend.agent_protocol import CandidateRecord, TraceEvent
from always_attend.code_parser import parse_candidate_records
from always_attend.source_collectors.base import collect_course_filters, extract_course_code, find_executable, run_json_command


def _match_moodle_course_ids(payload: Any, courses: set[str]) -> list[int]:
    matched: list[int] = []
    if not isinstance(payload, list):
        return matched
    for item in payload:
        if not isinstance(item, dict):
            continue
        haystack = " ".join(str(item.get(key, "")) for key in ("code", "shortname", "fullname", "displayname", "name"))
        course_code = extract_course_code(haystack)
        if course_code and course_code in courses:
            course_id = item.get("id") or item.get("courseId")
            if isinstance(course_id, int):
                matched.append(course_id)
    return sorted(set(matched))


def collect_moodle_candidates(
    *,
    target_url: str,
    courses: set[str],
    week: int | None,
    env: dict[str, str],
) -> tuple[list[CandidateRecord], list[TraceEvent]]:
    """Collect candidate records from moodle-cli."""
    del target_url
    executable = find_executable(("moodle-cli", "moodle"))
    if executable is None:
        return [], [
            TraceEvent(
                stage="collect",
                code="moodle_missing",
                message="Moodle CLI was not available.",
                details={"tried": ["moodle-cli", "moodle"]},
            )
        ]

    trace: list[TraceEvent] = []
    courses_payload, event = run_json_command([executable, "courses", "--json"], env=env)
    if event is not None:
        return [], [event]

    matched_ids = _match_moodle_course_ids(courses_payload, collect_course_filters(courses))
    if not matched_ids:
        return [], [
            TraceEvent(
                stage="collect",
                code="moodle_courses_not_found",
                message="No Moodle course IDs matched the requested courses.",
                details={"courses": sorted(courses)},
            )
        ]

    candidates: list[CandidateRecord] = []
    for course_id in matched_ids:
        for command in (
            [executable, "course", str(course_id), "--json"],
            [executable, "activities", str(course_id), "--json"],
        ):
            payload, command_event = run_json_command(command, env=env)
            if command_event is not None:
                trace.append(command_event)
                continue
            command_candidates, parse_trace = parse_candidate_records(
                source="moodle",
                payload=payload,
                courses=courses,
                week=week,
            )
            candidates.extend(command_candidates)
            trace.extend(parse_trace)

    overview_payload, overview_event = run_json_command([executable, "overview", "--json"], env=env)
    if overview_event is None:
        overview_candidates, parse_trace = parse_candidate_records(
            source="moodle",
            payload=overview_payload,
            courses=courses,
            week=week,
        )
        candidates.extend(overview_candidates)
        trace.extend(parse_trace)
    else:
        trace.append(overview_event)

    return candidates, trace
