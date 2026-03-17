"""Tests for the AI-native agent CLI workflow."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch

from always_attend.agent_cli import main as agent_main
from always_attend.okta_client import build_playwright_storage_state


class AgentCliTests(unittest.TestCase):
    def run_agent_command(self, argv: list[str]) -> tuple[int, dict]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = agent_main(argv)
        payload = json.loads(buffer.getvalue())
        return exit_code, payload

    def test_resolve_normalizes_course_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "plan.json"
            output_path = Path(temp_dir) / "normalized.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "courses": [
                            {
                                "course_code": "FIT2099",
                                "week": 4,
                                "entries": [
                                    {"slot": "Workshop 01", "code": "ABC12"},
                                    {"slot": "Applied 01", "code": "XYZ34", "source": "edstem"},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            exit_code, payload = self.run_agent_command(
                ["resolve", "--plan", str(plan_path), "--output", str(output_path), "--json"]
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["data"]["entry_count"], 2)
            self.assertTrue(output_path.exists())

    def test_submit_plan_materializes_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plan_path = temp_root / "plan.json"
            codes_root = temp_root / "codes"
            plan_path.write_text(
                json.dumps(
                    [
                        {"course_code": "FIT2099", "week": 7, "slot": "Workshop 01", "code": "AAA11"},
                        {"course_code": "FIT2099", "week": 7, "slot": "Applied 01", "code": "BBB22"},
                    ]
                ),
                encoding="utf-8",
            )

            with patch("always_attend.submission_plan.codes_db_path", return_value=codes_root):
                exit_code, payload = self.run_agent_command(
                    [
                        "submit",
                        "--plan",
                        str(plan_path),
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["data"]["plan"]["entry_count"], 2)
            self.assertTrue((codes_root / "FIT2099" / "7.json").exists())

    def test_doctor_command_reports_status(self) -> None:
        with patch(
            "always_attend.agent_cli.SessionManager.doctor_payload",
            return_value={"checks": [{"name": "okta", "status": "ok", "details": "/usr/bin/okta"}], "ready": True},
        ):
            exit_code, payload = self.run_agent_command(["doctor", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "doctor")
        self.assertTrue(payload["data"]["ready"])

    def test_run_command_uses_pipeline_exit_code(self) -> None:
        async_payload = {
            "status": "ok",
            "summary": {
                "submitted": [],
                "open_unresolved": [{}],
                "locked": [],
                "known_locked_codes": [],
                "rejected_attempts": [],
                "skipped_low_confidence": [],
            },
            "trace": [],
            "metrics": {
                "open_count": 1,
                "submitted_count": 0,
                "rejected_count": 0,
                "unresolved_count": 1,
            },
            "exit_code": 5,
        }
        with patch("always_attend.agent_cli._pipeline_run", new=AsyncMock(return_value=async_payload)):
            exit_code, payload = self.run_agent_command(
                ["run", "--target", "https://attendance.example.test/student/", "--json"]
            )

        self.assertEqual(exit_code, 5)
        self.assertEqual(payload["metrics"]["unresolved_count"], 1)

    def test_fetch_command_returns_candidates(self) -> None:
        async_payload = {
            "status": "ok",
            "command": "fetch",
            "data": {"items": [], "candidates": [{"source": "edstem", "code": "ABCDE"}], "artifacts": [], "trace": []},
            "exit_code": 0,
        }
        with patch("always_attend.agent_cli._handle_fetch", new=AsyncMock(return_value=async_payload)):
            exit_code, payload = self.run_agent_command(
                ["fetch", "--target", "https://attendance.example.test/student/", "--source", "edstem", "--json"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["data"]["candidates"][0]["source"], "edstem")

    def test_handoff_command_returns_artifacts(self) -> None:
        async_payload = {
            "status": "ok",
            "command": "handoff",
            "data": {
                "open_items": [{"course_code": "FIT2099"}],
                "candidate_hints": [],
                "artifacts": [{"source": "edstem", "image_urls": ["https://example.test/code.png"]}],
                "trace": [],
            },
            "exit_code": 0,
        }
        with patch("always_attend.agent_cli._handle_handoff", new=AsyncMock(return_value=async_payload)):
            exit_code, payload = self.run_agent_command(
                ["handoff", "--target", "https://attendance.example.test/student/", "--json"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["data"]["artifacts"][0]["source"], "edstem")

    def test_build_playwright_storage_state_accepts_cookie_header(self) -> None:
        payload = build_playwright_storage_state(
            {"cookie_header": "sid=abc; csrftoken=def"},
            url="https://attendance.example.test",
        )

        self.assertEqual(len(payload["cookies"]), 2)
        self.assertEqual(payload["cookies"][0]["domain"], "attendance.example.test")
        self.assertEqual(payload["cookies"][0]["secure"], True)


if __name__ == "__main__":
    unittest.main()
