"""Tests for multimodal AI handoff artifacts."""

from __future__ import annotations

import unittest

from always_attend.ai_handoff import build_source_artifact


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


if __name__ == "__main__":
    unittest.main()
