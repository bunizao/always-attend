"""Tests for Gmail source collection backends."""

from __future__ import annotations

import base64
import unittest
from unittest.mock import patch

from always_attend.source_collectors.gmail import collect_gmail_candidates


def _encode_gws_body(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


class GmailCollectorTests(unittest.TestCase):
    def test_collect_gmail_candidates_falls_back_to_gws_and_decodes_message_body(self) -> None:
        def fake_find_executable(candidates: tuple[str, ...]) -> str | None:
            if candidates == ("gmail-cli", "gmail"):
                return None
            if candidates == ("gws",):
                return "/opt/homebrew/bin/gws"
            return None

        def fake_run_json_command(command: list[str], *, env: dict[str, str] | None = None):
            del env
            if command[:5] == ["/opt/homebrew/bin/gws", "gmail", "users", "messages", "list"]:
                return {"messages": [{"id": "msg-1"}]}, None
            if command[:5] == ["/opt/homebrew/bin/gws", "gmail", "users", "messages", "get"]:
                return {
                    "id": "msg-1",
                    "snippet": "FIT2099 Week 7 workshop",
                    "payload": {
                        "mimeType": "multipart/alternative",
                        "headers": [
                            {"name": "Subject", "value": "FIT2099 Week 7 Workshop A1"},
                        ],
                        "parts": [
                            {
                                "mimeType": "text/plain",
                                "body": {
                                    "data": _encode_gws_body(
                                        "FIT2099 Week 7 Workshop Group A1 attendance code: ABCDE"
                                    )
                                },
                            }
                        ],
                    },
                }, None
            self.fail(f"Unexpected command: {command}")

        with patch("always_attend.source_collectors.gmail.find_executable", side_effect=fake_find_executable), patch(
            "always_attend.source_collectors.gmail.run_json_command",
            side_effect=fake_run_json_command,
        ):
            candidates, trace, artifacts = collect_gmail_candidates(
                target_url="https://attendance.example.test/student/",
                courses={"FIT2099"},
                week=7,
                env={},
            )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source, "gmail")
        self.assertEqual(candidates[0].code, "ABCDE")
        self.assertEqual(candidates[0].course_code, "FIT2099")
        self.assertEqual(artifacts[0].source, "gmail")
        self.assertIn("gmail_using_gws", [item.code for item in trace])

    def test_collect_gmail_candidates_reports_missing_when_no_backend_exists(self) -> None:
        with patch("always_attend.source_collectors.gmail.find_executable", return_value=None):
            candidates, trace, artifacts = collect_gmail_candidates(
                target_url="https://attendance.example.test/student/",
                courses={"FIT2099"},
                week=7,
                env={},
            )

        self.assertEqual(candidates, [])
        self.assertEqual(artifacts, [])
        self.assertEqual(trace[0].code, "gmail_missing")
        self.assertIn("gws", trace[0].details["tried"])


if __name__ == "__main__":
    unittest.main()
