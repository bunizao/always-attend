"""Tests for candidate parsing and structured matching."""

from __future__ import annotations

import unittest

from always_attend.agent_protocol import AttendanceStateItem, CandidateRecord
from always_attend.code_parser import parse_candidate_records, parse_html_table_candidates
from always_attend.matcher import choose_best_match


class ParserAndMatcherTests(unittest.TestCase):
    def test_parse_html_table_candidates(self) -> None:
        html = """
        <table>
          <tr><th>Slot</th><th>Code</th></tr>
          <tr><td>FIT2099 Workshop 01 Week 7</td><td>ABCDE</td></tr>
        </table>
        """
        candidates = parse_html_table_candidates(
            "moodle",
            html,
            courses={"FIT2099"},
            week=7,
            evidence="$.body",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].course_code, "FIT2099")
        self.assertEqual(candidates[0].code, "ABCDE")

    def test_parse_candidate_records_from_text(self) -> None:
        payload = {
            "document": "FIT2099 Workshop 01 Week 7 code ABCDE on 2026-03-17 10:00-12:00"
        }
        candidates, trace = parse_candidate_records(
            source="edstem",
            payload=payload,
            courses={"FIT2099"},
            week=7,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].class_type, "workshop")
        self.assertEqual(candidates[0].code, "ABCDE")
        self.assertEqual(trace, [])

    def test_choose_best_match_scores_five_tuple(self) -> None:
        item = AttendanceStateItem(
            item_id="FIT2099:7:0",
            course_code="FIT2099",
            class_type="workshop",
            slot_label="Workshop 01",
            date="2026-03-17",
            time_range="10:00-12:00",
            group="A1",
            anchor="17_Mar_26",
            dom_state="open",
            reason="Entry link is available.",
            position=0,
            raw_text="FIT2099 Workshop 01 Group A1 10:00-12:00",
        )
        candidate = CandidateRecord(
            source="gmail",
            course_code="FIT2099",
            class_type="workshop",
            date="2026-03-17",
            time_range="10:00-12:00",
            group="A1",
            raw_slot="Workshop 01",
            code="ABCDE",
            evidence="$.messages[0]",
            extraction_mode="plain_text",
            confidence_hint=0.9,
        )

        result = choose_best_match(item, [candidate])

        self.assertEqual(result.candidate_code, "ABCDE")
        self.assertGreaterEqual(result.confidence, 0.95)
        self.assertIn("course_code", result.matched_fields)
        self.assertIn("group", result.matched_fields)

    def test_choose_best_match_penalizes_missing_group(self) -> None:
        item = AttendanceStateItem(
            item_id="FIT2099:7:0",
            course_code="FIT2099",
            class_type="workshop",
            slot_label="Workshop 01",
            date="2026-03-17",
            time_range="10:00-12:00",
            group="A1",
            anchor="17_Mar_26",
            dom_state="open",
            reason="Entry link is available.",
            position=0,
            raw_text="FIT2099 Workshop 01 Group A1 10:00-12:00",
        )
        candidate = CandidateRecord(
            source="gmail",
            course_code="FIT2099",
            class_type="workshop",
            date="2026-03-17",
            time_range="10:00-12:00",
            group=None,
            raw_slot="Workshop 01",
            code="ABCDE",
            evidence="$.messages[0]",
            extraction_mode="plain_text",
            confidence_hint=0.9,
        )

        result = choose_best_match(item, [candidate])

        self.assertLess(result.confidence, 0.95)
        self.assertIn("group", result.conflicting_fields)
        self.assertIn("missing", result.reason.lower())

    def test_choose_best_match_marks_group_conflict(self) -> None:
        item = AttendanceStateItem(
            item_id="FIT2099:7:0",
            course_code="FIT2099",
            class_type="workshop",
            slot_label="Workshop 01",
            date="2026-03-17",
            time_range="10:00-12:00",
            group="A1",
            anchor="17_Mar_26",
            dom_state="open",
            reason="Entry link is available.",
            position=0,
            raw_text="FIT2099 Workshop 01 Group A1 10:00-12:00",
        )
        candidate = CandidateRecord(
            source="edstem",
            course_code="FIT2099",
            class_type="workshop",
            date="2026-03-17",
            time_range="10:00-12:00",
            group="B2",
            raw_slot="Workshop 01",
            code="ABCDE",
            evidence="$.threads[0]",
            extraction_mode="plain_text",
            confidence_hint=0.9,
        )

        result = choose_best_match(item, [candidate])

        self.assertIn("group", result.conflicting_fields)
        self.assertLess(result.confidence, 0.9)

    def test_choose_best_match_reports_ambiguity(self) -> None:
        item = AttendanceStateItem(
            item_id="FIT2099:7:0",
            course_code="FIT2099",
            class_type="workshop",
            slot_label="Workshop 01",
            date="2026-03-17",
            time_range="10:00-12:00",
            group=None,
            anchor="17_Mar_26",
            dom_state="open",
            reason="Entry link is available.",
            position=0,
            raw_text="FIT2099 Workshop 01 10:00-12:00",
        )
        candidates = [
            CandidateRecord(
                source="gmail",
                course_code="FIT2099",
                class_type="workshop",
                date="2026-03-17",
                time_range="10:00-12:00",
                group=None,
                raw_slot="Workshop 01",
                code="ABCDE",
                evidence="$.messages[0]",
                extraction_mode="plain_text",
                confidence_hint=0.9,
            ),
            CandidateRecord(
                source="edstem",
                course_code="FIT2099",
                class_type="workshop",
                date="2026-03-17",
                time_range="10:00-12:00",
                group=None,
                raw_slot="Workshop 01",
                code="FGHIJ",
                evidence="$.threads[0]",
                extraction_mode="plain_text",
                confidence_hint=0.9,
            ),
        ]

        result = choose_best_match(item, candidates)

        self.assertIn("ambiguous", result.reason.lower())


if __name__ == "__main__":
    unittest.main()
