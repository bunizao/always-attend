"""Tests for actionable reporting."""

from __future__ import annotations

import unittest

from always_attend.agent_protocol import AttendanceStateItem, MatchResult, SubmissionAttempt, TraceEvent
from always_attend.reporter import build_report


class ReporterTests(unittest.TestCase):
    def test_unresolved_items_include_next_action(self) -> None:
        item = AttendanceStateItem(
            item_id="FIT2099:visible:1:Workshop 01",
            course_code="FIT2099",
            class_type="workshop",
            slot_label="Workshop 01",
            date="2026-03-17",
            time_range="10:00-12:00",
            group="A1",
            anchor="17_Mar_26",
            dom_state="open",
            reason="Entry link is available.",
            position=1,
            raw_text="FIT2099 Workshop 01",
        )
        match = MatchResult(
            item_id=item.item_id,
            course_code=item.course_code,
            slot_label=item.slot_label,
            candidate_code="ABCDE",
            confidence=0.62,
            reason="Candidate matched course and class type only.",
            matched_fields=["course_code", "class_type"],
            conflicting_fields=["group"],
            source="edstem",
            class_type="workshop",
            date=None,
            time_range=None,
            group=None,
            raw_slot="Workshop 01",
        )
        report = build_report(
            items=[item],
            matches=[match],
            attempts=[],
            trace=[TraceEvent(stage="match", code="low_confidence", message="Low confidence.", details={})],
        )

        unresolved = report["summary"]["open_unresolved"][0]
        self.assertEqual(unresolved["next_action"], "review_source_evidence")
        self.assertIn("edstem", unresolved["recommended_sources"])

    def test_rejected_attempts_preserve_actionable_reason(self) -> None:
        item = AttendanceStateItem(
            item_id="FIT2099:visible:1:Workshop 01",
            course_code="FIT2099",
            class_type="workshop",
            slot_label="Workshop 01",
            date="2026-03-17",
            time_range="10:00-12:00",
            group="A1",
            anchor="17_Mar_26",
            dom_state="open",
            reason="Entry link is available.",
            position=1,
            raw_text="FIT2099 Workshop 01",
        )
        attempt = SubmissionAttempt(
            item_id=item.item_id,
            course_code=item.course_code,
            slot_label=item.slot_label,
            candidate_code="ABCDE",
            confidence=0.9,
            state="incorrect_code",
            reason="Incorrect code returned by the portal.",
            source="moodle",
        )
        report = build_report(items=[item], matches=[], attempts=[attempt], trace=[])
        rejected = report["summary"]["rejected_attempts"][0]
        self.assertEqual(rejected["next_action"], "find_alternate_candidate")
        self.assertEqual(rejected["source"], "moodle")


if __name__ == "__main__":
    unittest.main()
