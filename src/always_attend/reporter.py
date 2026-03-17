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
        unresolved.append(payload)

    summary = {
        "submitted": submitted,
        "open_unresolved": unresolved,
        "locked": locked,
        "known_locked_codes": known_locked_codes,
        "rejected_attempts": rejected,
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
