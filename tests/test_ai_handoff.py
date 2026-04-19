"""Tests for multimodal AI handoff artifacts."""

from __future__ import annotations

import unittest

from always_attend.ai_handoff import build_decision_packet, build_source_artifact
from always_attend.agent_protocol import AttendanceStateItem, CandidateRecord, MatchResult, TraceEvent


class AiHandoffTests(unittest.TestCase):
    def test_build_source_artifact_extracts_image_urls_and_text(self) -> None:
        payload = {
            "document": "FIT2099 Week 7 applied session code is in the attached image https://example.test/code.png",
            "html": '<p>See this screenshot:</p><img src="https://example.test/inline.jpg" />',
        }

        artifact = build_source_artifact(
            source="edstem",
            command=["edstem", "threads", "30595", "--json"],
            payload=payload,
            requested_courses={"FIT2099"},
        )

        self.assertEqual(artifact.source, "edstem")
        self.assertIn("FIT2099", artifact.course_codes)
        self.assertIn("https://example.test/code.png", artifact.image_urls)
        self.assertIn("https://example.test/inline.jpg", artifact.image_urls)
        self.assertTrue(artifact.text_snippets)
        self.assertIn(7, artifact.week_hints)
        self.assertEqual(artifact.artifact_kind, "mixed")

    def test_build_source_artifact_extracts_group_hints(self) -> None:
        payload = {
            "document": "FIT2099 Workshop Group A1 Week 7 code ABCDE",
        }

        artifact = build_source_artifact(
            source="gmail",
            command=["gmail", "messages", "--json"],
            payload=payload,
            requested_courses={"FIT2099"},
        )

        self.assertIn("A1", artifact.group_hints)

    def test_build_source_artifact_filters_text_by_requested_week(self) -> None:
        payload = {
            "week7": "FIT2099 Week 7 workshop details code ABCDE",
            "week8": "FIT2099 Week 8 workshop details code FGHIJ",
        }

        artifact = build_source_artifact(
            source="edstem",
            command=["edstem", "threads", "30595", "--json"],
            payload=payload,
            requested_courses={"FIT2099"},
            requested_week=7,
        )

        joined = "\n".join(artifact.text_snippets)
        self.assertIn("Week 7", joined)
        self.assertNotIn("Week 8", joined)

    def test_build_decision_packet_keeps_plan_contract_and_evidence_refs(self) -> None:
        item = AttendanceStateItem(
            item_id="FIT2099:visible:0:Workshop 01",
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
            group="A1",
            raw_slot="Workshop 01",
            code="ABCDE",
            evidence="$.threads[0].body",
            extraction_mode="plain_text",
            confidence_hint=0.95,
        )
        match = MatchResult(
            item_id=item.item_id,
            course_code=item.course_code,
            slot_label=item.slot_label,
            candidate_code="ABCDE",
            confidence=0.98,
            reason="Strong five-field match.",
            matched_fields=["course_code", "class_type", "date", "time_range", "group"],
            conflicting_fields=[],
            source="edstem",
            evidence_refs=["$.threads[0].body"],
            class_type="workshop",
            date="2026-03-17",
            time_range="10:00-12:00",
            group="A1",
            raw_slot="Workshop 01",
        )

        packet = build_decision_packet(
            target="https://attendance.example.test/student/",
            source_priority=["gmail", "edstem"],
            open_items=[item],
            candidate_hints=[candidate],
            artifacts=[],
            matches=[match],
            trace=[TraceEvent(stage="match", code="ok", message="ready", details={})],
            requested_week=7,
        ).to_dict()

        self.assertEqual(packet["schema_version"], "1")
        self.assertEqual(packet["matches"][0]["evidence_refs"], ["$.threads[0].body"])
        self.assertIn("evidence_refs", packet["plan_contract"]["recommended_fields"])
        self.assertEqual(packet["plan_contract"]["sample_entry"]["item_id"], item.item_id)
        self.assertEqual(packet["plan_contract"]["sample_entry"]["week"], 7)


if __name__ == "__main__":
    unittest.main()
