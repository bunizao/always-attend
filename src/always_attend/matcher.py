"""Structured matching between open attendance items and source candidates."""

from __future__ import annotations

from dataclasses import dataclass

from always_attend.agent_protocol import AttendanceStateItem, CandidateRecord, MatchResult


@dataclass(frozen=True)
class _WeightedScore:
    total: float
    matched_fields: list[str]
    conflicting_fields: list[str]
    missing_fields: list[str]


WEIGHTS = {
    "course_code": 0.35,
    "class_type": 0.20,
    "date": 0.20,
    "time_range": 0.15,
    "group": 0.10,
}


def _compare_field(name: str, item_value: str | None, candidate_value: str | None) -> tuple[float, bool, bool, bool]:
    if not item_value and not candidate_value:
        return 0.0, False, False, False
    if item_value and not candidate_value:
        if name == "group":
            return -WEIGHTS[name] * 0.35, False, False, True
        return 0.0, False, False, True
    if candidate_value and not item_value:
        return 0.0, False, False, False
    if item_value.strip().lower() == candidate_value.strip().lower():
        return WEIGHTS[name], True, False, False
    return -WEIGHTS[name] * 0.75, False, True, False


def score_candidate(item: AttendanceStateItem, candidate: CandidateRecord) -> _WeightedScore:
    """Score a candidate against a single attendance item."""
    total = 0.0
    matched_fields: list[str] = []
    conflicting_fields: list[str] = []
    missing_fields: list[str] = []

    for field_name in WEIGHTS:
        points, matched, conflicting, missing = _compare_field(
            field_name,
            getattr(item, field_name),
            getattr(candidate, field_name),
        )
        total += points
        if matched:
            matched_fields.append(field_name)
        if conflicting:
            conflicting_fields.append(field_name)
        if missing:
            missing_fields.append(field_name)
            if field_name == "group":
                conflicting_fields.append(field_name)

    if not candidate.course_code or candidate.course_code != item.course_code:
        conflicting_fields.append("course_code")
        total = min(total, 0.0)

    normalized = max(0.0, min(1.0, total))
    return _WeightedScore(
        total=normalized,
        matched_fields=matched_fields,
        conflicting_fields=sorted(set(conflicting_fields)),
        missing_fields=sorted(set(missing_fields)),
    )


def choose_best_match(item: AttendanceStateItem, candidates: list[CandidateRecord]) -> MatchResult:
    """Return the best candidate for an open attendance item."""
    ranked: list[tuple[_WeightedScore, CandidateRecord]] = []
    for candidate in candidates:
        if candidate.course_code and candidate.course_code != item.course_code:
            continue
        ranked.append((score_candidate(item, candidate), candidate))

    if not ranked:
        return MatchResult(
            item_id=item.item_id,
            course_code=item.course_code,
            slot_label=item.slot_label,
            candidate_code=None,
            confidence=0.0,
            reason="No candidate matched the target course.",
            matched_fields=[],
            conflicting_fields=[],
            source=None,
            class_type=item.class_type,
            date=item.date,
            time_range=item.time_range,
            group=item.group,
            raw_slot=None,
        )

    ranked.sort(key=lambda item_pair: item_pair[0].total, reverse=True)
    top_score, top_candidate = ranked[0]
    ambiguous = len(ranked) > 1 and abs(top_score.total - ranked[1][0].total) <= 0.05
    hard_conflicts = [field for field in top_score.conflicting_fields if field not in top_score.missing_fields]
    if ambiguous:
        reason = "Candidate is ambiguous with another near-identical match."
    elif top_score.missing_fields and not hard_conflicts:
        reason = f"Candidate is missing fields: {', '.join(top_score.missing_fields)}."
    elif top_score.conflicting_fields:
        reason = f"Candidate has conflicting fields: {', '.join(top_score.conflicting_fields)}."
    else:
        reason = "Best structured candidate chosen by five-field match."
    return MatchResult(
        item_id=item.item_id,
        course_code=item.course_code,
        slot_label=item.slot_label,
        candidate_code=top_candidate.code,
        confidence=round(top_score.total, 3),
        reason=reason,
        matched_fields=top_score.matched_fields,
        conflicting_fields=top_score.conflicting_fields,
        source=top_candidate.source,
        class_type=top_candidate.class_type or item.class_type,
        date=top_candidate.date or item.date,
        time_range=top_candidate.time_range or item.time_range,
        group=top_candidate.group or item.group,
        raw_slot=top_candidate.raw_slot,
    )


def match_open_items(items: list[AttendanceStateItem], candidates: list[CandidateRecord]) -> list[MatchResult]:
    """Match all open items against the available candidates."""
    results: list[MatchResult] = []
    for item in items:
        if item.dom_state != "open":
            continue
        results.append(choose_best_match(item, candidates))
    return results
