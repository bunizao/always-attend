"""Structured candidate extraction from source payloads."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any

from always_attend.agent_protocol import CandidateRecord, TraceEvent


COURSE_RE = re.compile(r"\b[A-Z]{3}\d{4}\b")
CODE_RE = re.compile(r"\b[A-Z0-9]{4,12}\b")
CLASS_PATTERNS = {
    "workshop": re.compile(r"\bworkshop\b", re.I),
    "applied": re.compile(r"\bapplied\b", re.I),
    "lab": re.compile(r"\b(?:lab|laboratory)\b", re.I),
    "tutorial": re.compile(r"\b(?:tutorial|tut)\b", re.I),
    "lecture": re.compile(r"\blecture\b", re.I),
}
DATE_PATTERNS = [
    re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b"),
    re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2})\b"),
]
TIME_RE = re.compile(
    r"\b(\d{1,2}:\d{2}\s*(?:am|pm)?\s*(?:-|–|to)\s*\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm)\s*(?:-|–|to)\s*\d{1,2}\s*(?:am|pm))\b",
    re.I,
)
GROUP_RE = re.compile(r"\b(?:group|grp)\s*([A-Za-z0-9_-]+)\b", re.I)
WEEK_RE = re.compile(r"\bweek\s*(\d{1,2})\b", re.I)
EXPLICIT_CODE_RE = re.compile(r"\b(?:attendance\s+code|code|passcode)\b\s*[:=-]?\s*([A-Z0-9]{4,12})\b", re.I)
COMMON_NON_CODES = {
    "WORKSHOP",
    "APPLIED",
    "LECTURE",
    "TUTORIAL",
    "GENERAL",
    "CONTENT",
    "LESSON",
    "WEEK",
    "GROUP",
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
}


class _TableExtractor(HTMLParser):
    """Minimal HTML table extractor for Moodle/Ed rich text."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        del attrs
        if tag in {"td", "th"}:
            self._in_cell = True
            self._current_cell = []
        elif tag == "tr":
            self._current_row = []

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag in {"td", "th"} and self._in_cell:
            self._current_row.append(" ".join(self._current_cell).strip())
            self._in_cell = False
        elif tag == "tr" and self._current_row:
            self.rows.append(self._current_row)
            self._current_row = []

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._in_cell:
            self._current_cell.append(data.strip())


def _looks_like_html(text: str) -> bool:
    return "<" in text and ">" in text and "</" in text


def _extract_course_code(text: str, courses: set[str]) -> str | None:
    if not text:
        return None
    if courses:
        for course in sorted(courses):
            if course in text.upper():
                return course
    match = COURSE_RE.search(text.upper())
    if match:
        return match.group(0)
    return None


def _looks_like_attendance_code(value: str) -> bool:
    if not value:
        return False
    token = value.strip().upper()
    if COURSE_RE.fullmatch(token):
        return False
    if len(token) < 5 or len(token) > 8:
        return False
    if token.isdigit():
        return False
    if not re.search(r"[A-Z]", token):
        return False
    if token in COMMON_NON_CODES:
        return False
    return True


def _extract_class_type(text: str) -> str | None:
    for value, pattern in CLASS_PATTERNS.items():
        if pattern.search(text):
            return value
    return None


def _extract_date(text: str) -> str | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _extract_time_range(text: str) -> str | None:
    match = TIME_RE.search(text)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return None


def _extract_group(text: str) -> str | None:
    match = GROUP_RE.search(text)
    if match:
        return match.group(1)
    if "separate group" in text.lower():
        return "separate-groups"
    return None


def _extract_week(text: str) -> int | None:
    match = WEEK_RE.search(text)
    if match:
        return int(match.group(1))
    return None


def _candidate_from_text(
    *,
    source: str,
    text: str,
    evidence: str,
    courses: set[str],
    week: int | None,
    extraction_mode: str,
) -> list[CandidateRecord]:
    upper_text = text.upper()
    if week is not None:
        extracted_week = _extract_week(text)
        if extracted_week is not None and extracted_week != week:
            return []

    course_code = _extract_course_code(upper_text, courses)
    class_type = _extract_class_type(text)
    date = _extract_date(text)
    time_range = _extract_time_range(text)
    group = _extract_group(text)

    candidates: list[CandidateRecord] = []
    explicit_codes = [match.group(1).upper() for match in EXPLICIT_CODE_RE.finditer(upper_text)]
    code_values = explicit_codes if explicit_codes else [match.group(0) for match in CODE_RE.finditer(upper_text)]
    for code in code_values:
        if not _looks_like_attendance_code(code):
            continue
        candidates.append(
            CandidateRecord(
                source=source,
                course_code=course_code,
                class_type=class_type,
                date=date,
                time_range=time_range,
                group=group,
                raw_slot=text.strip()[:240] or None,
                code=code,
                evidence=evidence,
                extraction_mode=extraction_mode,
                confidence_hint=0.85 if class_type or course_code else 0.6,
            )
        )
    return candidates


def _extract_text_nodes(payload: Any, *, path: str = "$") -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            values.extend(_extract_text_nodes(value, path=f"{path}.{key}"))
    elif isinstance(payload, list):
        for idx, value in enumerate(payload):
            values.extend(_extract_text_nodes(value, path=f"{path}[{idx}]"))
    elif isinstance(payload, str):
        values.append((path, payload))
    return values


def parse_html_table_candidates(
    source: str,
    html_text: str,
    *,
    courses: set[str],
    week: int | None,
    evidence: str,
) -> list[CandidateRecord]:
    """Extract code candidates from HTML tables."""
    parser = _TableExtractor()
    parser.feed(html_text)

    candidates: list[CandidateRecord] = []
    for row in parser.rows:
        if len(row) < 2:
            continue
        slot_text = " | ".join(cell for cell in row[:-1] if cell).strip()
        code_text = row[-1].strip().upper()
        if not _looks_like_attendance_code(code_text):
            continue
        if week is not None:
            extracted_week = _extract_week(slot_text)
            if extracted_week is not None and extracted_week != week:
                continue
        candidates.append(
            CandidateRecord(
                source=source,
                course_code=_extract_course_code(slot_text.upper(), courses),
                class_type=_extract_class_type(slot_text),
                date=_extract_date(slot_text),
                time_range=_extract_time_range(slot_text),
                group=_extract_group(slot_text),
                raw_slot=slot_text or None,
                code=code_text,
                evidence=evidence,
                extraction_mode="html_table",
                confidence_hint=0.92,
            )
        )
    return candidates


def parse_candidate_records(
    *,
    source: str,
    payload: Any,
    courses: set[str] | None = None,
    week: int | None = None,
) -> tuple[list[CandidateRecord], list[TraceEvent]]:
    """Extract normalized candidate records from a source payload."""
    course_set = {item.upper() for item in (courses or set()) if item}
    candidates: list[CandidateRecord] = []
    trace: list[TraceEvent] = []

    for path, text in _extract_text_nodes(payload):
        if not text.strip():
            continue

        if _looks_like_html(text):
            html_candidates = parse_html_table_candidates(
                source,
                text,
                courses=course_set,
                week=week,
                evidence=path,
            )
            candidates.extend(html_candidates)

        text_candidates = _candidate_from_text(
            source=source,
            text=text,
            evidence=path,
            courses=course_set,
            week=week,
            extraction_mode="plain_text",
        )
        candidates.extend(text_candidates)

        if re.search(r"\.(?:png|jpg|jpeg|webp|gif)\b", text, re.I):
            trace.append(
                TraceEvent(
                    stage="collect",
                    code="image_reference_detected",
                    message="Image evidence was detected and should be handed to a multimodal model.",
                    details={
                        "source": source,
                        "evidence": path,
                    },
                )
            )

    deduped: list[CandidateRecord] = []
    seen: set[str] = set()
    for item in candidates:
        key = json.dumps(item.to_dict(), sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped, trace
