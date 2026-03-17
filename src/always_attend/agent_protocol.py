"""Structured protocol objects for the AI-native attendance workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


DomState = Literal["submitted", "open", "locked", "unresolved"]
SubmissionState = Literal[
    "ready",
    "submitted_ok",
    "incorrect_code",
    "dom_locked",
    "session_invalid",
    "wrong_week",
    "ambiguous",
    "post_submit_unverified",
]


@dataclass(frozen=True)
class TraceEvent:
    """Single structured event emitted by the agent pipeline."""

    stage: str
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly event payload."""
        return asdict(self)


@dataclass(frozen=True)
class AttendanceStateItem:
    """Normalized unit entry discovered from the attendance site."""

    item_id: str
    course_code: str
    class_type: str | None
    slot_label: str
    date: str | None
    time_range: str | None
    group: str | None
    anchor: str | None
    dom_state: DomState
    reason: str
    position: int
    raw_text: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly item payload."""
        return asdict(self)


@dataclass(frozen=True)
class CandidateRecord:
    """Potential attendance code candidate gathered from a source."""

    source: str
    course_code: str | None
    class_type: str | None
    date: str | None
    time_range: str | None
    group: str | None
    raw_slot: str | None
    code: str
    evidence: str
    extraction_mode: str
    confidence_hint: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly candidate payload."""
        return asdict(self)


@dataclass(frozen=True)
class SourceArtifact:
    """Structured source payload handed to an external AI model."""

    source: str
    command: list[str]
    course_codes: list[str]
    image_urls: list[str]
    text_snippets: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly artifact payload."""
        return asdict(self)


@dataclass(frozen=True)
class MatchResult:
    """Best candidate chosen for an open attendance item."""

    item_id: str
    course_code: str
    slot_label: str
    candidate_code: str | None
    confidence: float
    reason: str
    matched_fields: list[str]
    conflicting_fields: list[str]
    source: str | None
    class_type: str | None = None
    date: str | None = None
    time_range: str | None = None
    group: str | None = None
    raw_slot: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly match payload."""
        return asdict(self)


@dataclass(frozen=True)
class SubmissionAttempt:
    """Submitter outcome for a matched attendance item."""

    item_id: str
    course_code: str
    slot_label: str
    candidate_code: str | None
    confidence: float
    state: SubmissionState
    reason: str
    source: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly submission payload."""
        return asdict(self)
