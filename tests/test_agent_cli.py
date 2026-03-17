"""Tests for the agent-first CLI workflow."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_submit_materializes_plan_and_skips_cookie_sync_in_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plan_path = temp_root / "plan.json"
            codes_root = temp_root / "codes"
            storage_state = temp_root / "storage_state.json"
            plan_path.write_text(
                json.dumps(
                    [
                        {"course_code": "FIT2099", "week": 7, "slot": "Workshop 01", "code": "AAA11"},
                        {"course_code": "FIT2099", "week": 7, "slot": "Applied 01", "code": "BBB22"},
                    ]
                ),
                encoding="utf-8",
            )

            with patch("always_attend.submission_plan.codes_db_path", return_value=codes_root), patch(
                "always_attend.agent_cli.storage_state_file",
                return_value=storage_state,
            ), patch(
                "always_attend.agent_cli._run_submit_weeks",
                return_value=[{"week": 7, "summary": {"success": True}}],
            ) as mock_submit_weeks, patch(
                "always_attend.agent_cli.OktaClient"
            ) as mock_okta:
                exit_code, payload = self.run_agent_command(
                    [
                        "submit",
                        "--plan",
                        str(plan_path),
                        "--portal-url",
                        "https://attendance.example.test",
                        "--dry-run",
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["data"]["storage_state"]["skipped"], True)
            self.assertTrue((codes_root / "FIT2099" / "7.json").exists())
            mock_submit_weeks.assert_called_once_with([7], dry_run=True)
            mock_okta.assert_not_called()

    def test_build_playwright_storage_state_accepts_cookie_header(self) -> None:
        payload = build_playwright_storage_state(
            {"cookie_header": "sid=abc; csrftoken=def"},
            url="https://attendance.example.test",
        )

        self.assertEqual(len(payload["cookies"]), 2)
        self.assertEqual(payload["cookies"][0]["domain"], "attendance.example.test")
        self.assertEqual(payload["cookies"][0]["secure"], True)

    def test_fetch_command_returns_adapter_payload(self) -> None:
        with patch(
            "always_attend.agent_cli.fetch_from_source",
            return_value={"source": "edstem", "kind": "courses", "payload": [{"id": 1}]},
        ) as mock_fetch:
            exit_code, payload = self.run_agent_command(
                ["fetch", "--source", "edstem", "--kind", "courses", "--json"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["data"]["source"], "edstem")
        mock_fetch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
