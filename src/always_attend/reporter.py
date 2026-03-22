"""Final report generation for AI-native attendance runs."""

from __future__ import annotations

from typing import Any

from always_attend.agent_protocol import AttendanceStateItem, MatchResult, SubmissionAttempt, TraceEvent


def _item_payload(item: AttendanceStateItem) -> dict[str, Any]:
    return item.to_dict()


def _match_payload(result: MatchResult) -> dict[str, Any]:
    return result.to_dict()


def _attempt_payload(attempt: SubmissionAttempt) -> dict[str, Any]:
    return attempt.to_dict()


def _recommended_sources(match: MatchResult | None, attempt: SubmissionAttempt | None) -> list[str]:
    values: list[str] = []
    if match is not None and match.source:
        values.append(match.source)
    if attempt is not None and attempt.source and attempt.source not in values:
        values.append(attempt.source)
    return values


def _next_action_for_unresolved(
    item: AttendanceStateItem,
    match: MatchResult | None,
    attempt: SubmissionAttempt | None,
) -> tuple[str, str]:
    if attempt is not None:
        if attempt.state == "incorrect_code":
            return "find_alternate_candidate", "The submitted code was rejected by the portal."
        if attempt.state == "dom_locked":
            return "recheck_dom_state", "The DOM became locked before submission could complete."
        if attempt.state == "post_submit_unverified":
            return "verify_submission_state", "The portal accepted input but did not confirm submission."
    if match is None:
        return "collect_more_evidence", "No structured candidate was available for this open item."
    if match.confidence < 0.8:
        return "review_source_evidence", "The best candidate was below the submission confidence threshold."
    if match.conflicting_fields:
        return "resolve_conflicts", "Structured evidence conflicted on important matching fields."
    if item.dom_state == "unresolved":
        return "reinspect_attendance_site", "The attendance DOM did not expose a stable state."
    return "review_source_evidence", "More evidence is needed before the item can be safely submitted."


def _next_action_for_rejected(attempt: SubmissionAttempt) -> tuple[str, str]:
    if attempt.state == "incorrect_code":
        return "find_alternate_candidate", "The submitted code was rejected by the portal."
    return "review_submission_trace", attempt.reason


def build_report(
    *,
    items: list[AttendanceStateItem],
    matches: list[MatchResult],
    attempts: list[SubmissionAttempt],
    trace: list[TraceEvent],
) -> dict[str, Any]:
    """Build the stable report shape consumed by agents."""
    matches_by_id = {item.item_id: item for item in matches}
    attempts_by_id = {item.item_id: item for item in attempts}

    submitted = [_attempt_payload(item) for item in attempts if item.state == "submitted_ok"]
    rejected = [_attempt_payload(item) for item in attempts if item.state == "incorrect_code"]
    skipped_low_confidence = [
        _match_payload(item)
        for item in matches
        if item.candidate_code and item.confidence < 0.8
    ]
    locked = [_item_payload(item) for item in items if item.dom_state == "locked"]
    known_locked_codes = []
    for item in items:
        if item.dom_state != "locked":
            continue
        match = matches_by_id.get(item.item_id)
        if match and match.candidate_code:
            known_locked_codes.append(
                {
                    "item": _item_payload(item),
                    "candidate": _match_payload(match),
                }
            )

    unresolved: list[dict[str, Any]] = []
    for item in items:
        if item.dom_state not in {"open", "unresolved"}:
            continue
        attempt = attempts_by_id.get(item.item_id)
        if attempt is not None and attempt.state == "submitted_ok":
            continue
        payload: dict[str, Any] = {"item": _item_payload(item)}
        match = matches_by_id.get(item.item_id)
        if match is not None:
            payload["match"] = _match_payload(match)
        if attempt is not None:
            payload["attempt"] = _attempt_payload(attempt)
        next_action, explanation = _next_action_for_unresolved(item, match, attempt)
        payload["next_action"] = next_action
        payload["explanation"] = explanation
        payload["recommended_sources"] = _recommended_sources(match, attempt)
        unresolved.append(payload)

    actionable_rejected: list[dict[str, Any]] = []
    for attempt in attempts:
        if attempt.state != "incorrect_code":
            continue
        payload = _attempt_payload(attempt)
        next_action, explanation = _next_action_for_rejected(attempt)
        payload["next_action"] = next_action
        payload["explanation"] = explanation
        actionable_rejected.append(payload)

    summary = {
        "submitted": submitted,
        "open_unresolved": unresolved,
        "locked": locked,
        "known_locked_codes": known_locked_codes,
        "rejected_attempts": actionable_rejected,
        "skipped_low_confidence": skipped_low_confidence,
    }
    metrics = {
        "open_count": sum(1 for item in items if item.dom_state == "open"),
        "submitted_count": len(submitted),
        "rejected_count": len(rejected),
        "unresolved_count": len(unresolved),
    }
    return {
        "status": "ok",
        "summary": summary,
        "trace": [item.to_dict() for item in trace],
        "metrics": metrics,
    }


def exit_code_for_report(report: dict[str, Any]) -> int:
    """Map report outcomes to stable exit codes."""
    if report.get("status") != "ok":
        return 1
    metrics = report.get("metrics", {})
    open_count = int(metrics.get("open_count", 0))
    unresolved_count = int(metrics.get("unresolved_count", 0))
    if open_count == 0:
        return 4
    if unresolved_count > 0:
        return 5
    return 0
