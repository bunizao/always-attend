"""Generic GOG source collector."""

from __future__ import annotations

from always_attend.agent_protocol import CandidateRecord, SourceArtifact, TraceEvent
from always_attend.code_parser import parse_candidate_records
from always_attend.source_collectors.base import artifact_from_payload, find_executable, run_json_command


def collect_gog_candidates(
    *,
    target_url: str,
    courses: set[str],
    week: int | None,
    env: dict[str, str],
) -> tuple[list[CandidateRecord], list[TraceEvent], list[SourceArtifact]]:
    """Collect candidate records from gogcli if installed."""
    del target_url
    executable = find_executable(("gogcli", "gog"))
    if executable is None:
        return [], [
            TraceEvent(
                stage="collect",
                code="gog_missing",
                message="GOG CLI was not available.",
                details={"tried": ["gogcli", "gog"]},
            )
        ], []

    payload, event = run_json_command([executable, "--json"], env=env)
    if event is not None:
        return [], [event], []
    candidates, parse_trace = parse_candidate_records(
        source="gog",
        payload=payload,
        courses=courses,
        week=week,
    )
    artifact = artifact_from_payload(
        source="gog",
        command=[executable, "--json"],
        payload=payload,
        requested_courses=courses,
        requested_week=week,
    )
    return candidates, parse_trace, [artifact]
