"""Submission plan normalization for agent-authored attendance runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from always_attend.paths import codes_db_path, ensure_parent


class SubmissionPlanError(RuntimeError):
    """Raised when a submission plan is invalid."""


@dataclass(frozen=True)
class SubmissionPlanEntry:
    """Single attendance code submission target."""

    course_code: str
    week: int
    slot: str
    code: str
    source: str | None = None


def _require_text(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SubmissionPlanError(f"Missing required field '{field_name}'.")
    return text


def _require_week(value: Any) -> int:
    try:
        week = int(value)
    except (TypeError, ValueError) as exc:
        raise SubmissionPlanError("Missing or invalid field 'week'.") from exc
    if week <= 0:
        raise SubmissionPlanError("Week must be a positive integer.")
    return week


def _entry_from_payload(payload: dict[str, Any], *, course_code: str | None = None, week: int | None = None) -> SubmissionPlanEntry:
    resolved_course = _require_text(payload.get("course_code") or course_code, field_name="course_code")
    resolved_week = _require_week(payload.get("week", week))
    slot = _require_text(payload.get("slot"), field_name="slot")
    code = _require_text(payload.get("code"), field_name="code")
    raw_source = payload.get("source")
    source = str(raw_source).strip() if raw_source is not None else None
    if not source:
        source = None
    return SubmissionPlanEntry(
        course_code=resolved_course,
        week=resolved_week,
        slot=slot,
        code=code,
        source=source,
    )


def _entries_from_course_block(payload: dict[str, Any]) -> list[SubmissionPlanEntry]:
    course_code = _require_text(payload.get("course_code"), field_name="course_code")
    week = _require_week(payload.get("week"))
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise SubmissionPlanError("Course block must include an 'entries' list.")
    return [_entry_from_payload(item, course_code=course_code, week=week) for item in entries if isinstance(item, dict)]


def normalize_submission_plan(payload: Any) -> list[SubmissionPlanEntry]:
    """Accept several agent-friendly shapes and normalize them into flat entries."""
    if isinstance(payload, list):
        return [_entry_from_payload(item) for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        raise SubmissionPlanError("Submission plan must be a JSON object or list.")

    if isinstance(payload.get("courses"), list):
        normalized: list[SubmissionPlanEntry] = []
        for block in payload["courses"]:
            if not isinstance(block, dict):
                continue
            normalized.extend(_entries_from_course_block(block))
        return normalized

    if isinstance(payload.get("entries"), list):
        course_code = payload.get("course_code")
        week = payload.get("week")
        return [
            _entry_from_payload(item, course_code=course_code, week=week)
            for item in payload["entries"]
            if isinstance(item, dict)
        ]

    raise SubmissionPlanError("Unsupported submission plan shape.")


def load_submission_plan(path: Path) -> list[SubmissionPlanEntry]:
    """Load and normalize a JSON submission plan from disk."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SubmissionPlanError(f"Submission plan file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SubmissionPlanError(f"Invalid submission plan JSON: {exc}") from exc
    return normalize_submission_plan(payload)


def plan_summary(entries: list[SubmissionPlanEntry]) -> dict[str, Any]:
    """Build a stable summary for JSON output."""
    grouped: dict[tuple[str, int], list[SubmissionPlanEntry]] = {}
    for entry in entries:
        grouped.setdefault((entry.course_code, entry.week), []).append(entry)

    courses = [
        {
            "course_code": course_code,
            "week": week,
            "entry_count": len(grouped_entries),
            "entries": [asdict(item) for item in grouped_entries],
        }
        for (course_code, week), grouped_entries in sorted(grouped.items())
    ]
    return {
        "entry_count": len(entries),
        "course_count": len(courses),
        "weeks": sorted({entry.week for entry in entries}),
        "courses": courses,
    }


def materialize_plan(entries: list[SubmissionPlanEntry]) -> list[str]:
    """Write a normalized plan into the existing per-course/week codes database."""
    grouped: dict[tuple[str, int], list[SubmissionPlanEntry]] = {}
    for entry in entries:
        grouped.setdefault((entry.course_code, entry.week), []).append(entry)

    written_files: list[str] = []
    for (course_code, week), grouped_entries in sorted(grouped.items()):
        course_dir = codes_db_path().expanduser().resolve() / "".join(ch for ch in course_code if ch.isalnum())
        target_path = course_dir / f"{week}.json"
        ensure_parent(target_path)
        payload = [{"slot": entry.slot, "code": entry.code} for entry in grouped_entries]
        target_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written_files.append(str(target_path))
    return written_files
