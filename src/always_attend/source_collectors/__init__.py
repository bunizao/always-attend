"""Source collection orchestration with fixed priority order."""

from __future__ import annotations

from typing import Iterable

from always_attend.agent_protocol import AttendanceStateItem, CandidateRecord, SourceArtifact, TraceEvent
from always_attend.session_manager import SessionManager
from always_attend.source_collectors.edstem import collect_edstem_candidates
from always_attend.source_collectors.gmail import collect_gmail_candidates
from always_attend.source_collectors.gog import collect_gog_candidates
from always_attend.source_collectors.moodle import collect_moodle_candidates


SOURCE_ORDER = ("gmail", "moodle", "edstem", "gog")


def collect_candidates_for_sources(
    *,
    items: list[AttendanceStateItem],
    sources: Iterable[str],
    session_manager: SessionManager,
    target_url: str,
    week: int | None,
    explicit_courses: list[str] | None = None,
) -> tuple[list[CandidateRecord], list[TraceEvent], list[SourceArtifact]]:
    """Collect candidates in a fixed source priority order."""
    requested = [item.lower() for item in sources]
    prioritized = [item for item in SOURCE_ORDER if item in requested]
    open_items = [item for item in items if item.dom_state == "open"]
    courses = {item.course_code for item in open_items}
    if explicit_courses:
        courses = {item.upper() for item in explicit_courses if item}

    trace: list[TraceEvent] = []

    collectors = {
        "gmail": collect_gmail_candidates,
        "moodle": collect_moodle_candidates,
        "edstem": collect_edstem_candidates,
        "gog": collect_gog_candidates,
    }

    all_candidates: list[CandidateRecord] = []
    all_artifacts: list[SourceArtifact] = []
    for source in prioritized:
        if not open_items:
            break
        env = session_manager.build_source_environment(source, target_url)
        candidates, source_trace, artifacts = collectors[source](
            target_url=target_url,
            courses=courses,
            week=week,
            env=env,
        )
        all_candidates.extend(candidates)
        all_artifacts.extend(artifacts)
        trace.extend(source_trace)
        trace.append(
            TraceEvent(
                stage="collect",
                code="source_completed",
                message="Source collection completed.",
                details={
                    "source": source,
                    "candidate_count": len(candidates),
                },
            )
        )

    return all_candidates, trace, all_artifacts
