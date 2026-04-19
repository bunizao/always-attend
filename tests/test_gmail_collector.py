"""Tests for Gmail source collection backends."""

from __future__ import annotations

import base64
import json
import subprocess
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
        ), patch(
            "always_attend.source_collectors.gmail.find_codex_executable",
            return_value=None,
        ), patch(
            "always_attend.source_collectors.gmail.find_gmail_connector_id",
            return_value=None,
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

    def test_collect_gmail_candidates_uses_codex_connector_backend(self) -> None:
        def fake_run(command: list[str], capture_output: bool, text: bool, timeout: float):
            del capture_output, text, timeout
            output_path = command[command.index("--output-last-message") + 1]
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "status": "ok",
                        "messages": [
                            {
                                "id": "msg-1",
                                "thread_id": "thread-1",
                                "subject": "FIT2099 Week 7 Workshop A1",
                                "from": "teaching@example.test",
                                "date": "2026-03-17",
                                "snippet": "attendance code ABCDE",
                                "plain_text": "FIT2099 Week 7 Workshop Group A1 attendance code: ABCDE",
                                "html": "",
                                "labels": ["INBOX"],
                            }
                        ],
                        "notes": [],
                    },
                    handle,
                )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with patch("always_attend.source_collectors.gmail.find_executable", return_value=None), patch(
            "always_attend.source_collectors.gmail.find_codex_executable",
            return_value="/opt/homebrew/bin/codex",
        ), patch(
            "always_attend.source_collectors.gmail.find_gmail_connector_id",
            return_value="connector_123",
        ), patch(
            "always_attend.source_collectors.gmail.subprocess.run",
            side_effect=fake_run,
        ):
            candidates, trace, artifacts = collect_gmail_candidates(
                target_url="https://attendance.example.test/student/",
                courses={"FIT2099"},
                week=7,
                env={},
            )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].code, "ABCDE")
        self.assertEqual(artifacts[0].source, "gmail")
        self.assertIn("gmail_using_codex_connector", [item.code for item in trace])

    def test_collect_gmail_candidates_reports_missing_when_no_backend_exists(self) -> None:
        with patch("always_attend.source_collectors.gmail.find_executable", return_value=None), patch(
            "always_attend.source_collectors.gmail.find_codex_executable",
            return_value=None,
        ), patch(
            "always_attend.source_collectors.gmail.find_gmail_connector_id",
            return_value=None,
        ):
            candidates, trace, artifacts = collect_gmail_candidates(
                target_url="https://attendance.example.test/student/",
                courses={"FIT2099"},
                week=7,
                env={},
            )

        self.assertEqual(candidates, [])
        self.assertEqual(artifacts, [])
        self.assertEqual(trace[-1].code, "gmail_missing")
        self.assertIn("codex_gmail_connector", trace[-1].details["tried"])


if __name__ == "__main__":
    unittest.main()
