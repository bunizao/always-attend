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
            plan_path.write_text(
                json.dumps(
                    [
                        {"course_code": "FIT2099", "week": 7, "slot": "Workshop 01", "code": "AAA11"},
                        {"course_code": "FIT2099", "week": 7, "slot": "Applied 01", "code": "BBB22"},
                    ]
                ),
                encoding="utf-8",
            )

            with patch(
                "always_attend.agent_cli.materialize_plan",
                return_value=[str(temp_root / "codes" / "FIT2099" / "7.json")],
            ):
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
            self.assertEqual(len(payload["data"]["written_files"]), 1)

    def test_submit_plan_with_target_executes_submission_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plan_path = temp_root / "plan.json"
            plan_path.write_text(
                json.dumps(
                    [
                        {"course_code": "FIT2099", "week": 7, "slot": "Workshop 01", "code": "AAA11"},
                    ]
                ),
                encoding="utf-8",
            )

            with patch(
                "always_attend.agent_cli.materialize_plan",
                return_value=[str(temp_root / "codes" / "FIT2099" / "7.json")],
            ), patch(
                "always_attend.agent_cli._run_submit_weeks",
                return_value=[{"week": 7, "summary": {"success": True}}],
            ) as mock_run_submit:
                exit_code, payload = self.run_agent_command(
                    [
                        "submit",
                        "--plan",
                        str(plan_path),
                        "--target",
                        "http://127.0.0.1:8081/student/",
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["data"]["runs"][0]["summary"]["success"], True)
        mock_run_submit.assert_called_once()

    def test_doctor_command_reports_status(self) -> None:
        with patch(
            "always_attend.agent_cli.SessionManager.doctor_payload",
            return_value={
                "checks": [
                    {
                        "name": "okta",
                        "status": "ok",
                        "details": "/usr/bin/okta",
                        "install_hint": None,
                    }
                ],
                "ready": True,
            },
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

    def test_run_demo_returns_report_without_target(self) -> None:
        exit_code, payload = self.run_agent_command(["run", "--demo", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "run")
        self.assertIn("summary", payload)
        self.assertEqual(payload["data"]["items"][0]["course_code"], "FIT2099")

    def test_run_dry_run_without_target_falls_back_to_demo(self) -> None:
        exit_code, payload = self.run_agent_command(["run", "--dry-run", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "run")
        self.assertIn("Demo", payload["message"])

    def test_run_without_target_falls_back_to_demo(self) -> None:
        exit_code, payload = self.run_agent_command(["run", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "run")
        self.assertIn("Demo", payload["message"])

    def test_inspect_demo_returns_items_without_target(self) -> None:
        exit_code, payload = self.run_agent_command(["inspect", "state", "--demo", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "inspect.state")
        self.assertEqual(payload["data"]["items"][0]["course_code"], "FIT2099")

    def test_inspect_without_target_falls_back_to_demo(self) -> None:
        exit_code, payload = self.run_agent_command(["inspect", "state", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "inspect.state")
        self.assertIn("Demo", payload["message"])

    def test_match_demo_returns_matches_without_target(self) -> None:
        exit_code, payload = self.run_agent_command(["match", "--demo", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "match")
        self.assertEqual(payload["data"]["matches"][0]["course_code"], "FIT2099")

    def test_submit_demo_returns_report_without_target(self) -> None:
        exit_code, payload = self.run_agent_command(["submit", "--demo", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "submit")
        self.assertIn("attempts", payload["data"])

    def test_report_demo_returns_summary_without_target(self) -> None:
        exit_code, payload = self.run_agent_command(["report", "--demo", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "report")
        self.assertIn("summary", payload)

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

    def test_requested_sources_preserve_explicit_attendance_only(self) -> None:
        from always_attend.agent_cli import _requested_sources

        self.assertEqual(_requested_sources(csv_text="attendance"), [])
        self.assertEqual(_requested_sources(explicit_sources=["attendance"]), [])

    def test_handoff_command_returns_artifacts(self) -> None:
        async_payload = {
            "status": "ok",
            "command": "handoff",
            "data": {
                "open_items": [{"course_code": "FIT2099"}],
                "candidate_hints": [],
                "artifacts": [{"source": "edstem", "image_urls": ["https://example.test/code.png"]}],
                "plan_contract": {"required_fields": ["course_code", "week", "slot", "code"]},
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
        self.assertIn("code", payload["data"]["plan_contract"]["required_fields"])

    def test_handoff_demo_returns_schema_without_session(self) -> None:
        exit_code, payload = self.run_agent_command(["handoff", "--demo", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "handoff")
        self.assertIn("plan_contract", payload["data"])
        self.assertEqual(payload["data"]["open_items"][0]["course_code"], "FIT2099")

    def test_handoff_missing_session_returns_next_action(self) -> None:
        with patch(
            "always_attend.agent_cli._inspect_state",
            new=AsyncMock(side_effect=RuntimeError("No stored session found for this URL")),
        ):
            exit_code, payload = self.run_agent_command(
                ["handoff", "--target", "https://attendance.example.test/student/", "--json"]
            )

        self.assertEqual(exit_code, 3)
        self.assertEqual(payload["command"], "handoff")
        self.assertEqual(payload["next_action"], "auth_login")
        self.assertIn("attend auth login", payload["suggested_command"])

    def test_inspect_local_target_skips_session_bootstrap(self) -> None:
        with patch("always_attend.agent_cli.SessionManager.ensure_storage_state") as mock_ensure, patch(
            "always_attend.agent_cli.AttendanceStateReader.inspect",
            new=AsyncMock(return_value=([], [])),
        ):
            exit_code, payload = self.run_agent_command(
                ["inspect", "state", "--target", "http://127.0.0.1:8081/student/", "--json"]
            )

        self.assertEqual(exit_code, 4)
        mock_ensure.assert_not_called()
        self.assertEqual(payload["command"], "inspect.state")

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
