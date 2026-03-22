"""Tests for the AI-native agent CLI workflow."""

from __future__ import annotations

import io
import json
import os
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
        with tempfile.TemporaryDirectory() as temp_dir:
            env_overrides: dict[str, str] = {}
            if "ENV_FILE" not in os.environ:
                env_overrides["ENV_FILE"] = str(Path(temp_dir) / ".env")
            if "ENV_FILE" not in os.environ and "PORTAL_URL" not in os.environ:
                env_overrides["PORTAL_URL"] = ""
            with patch.dict(os.environ, env_overrides, clear=False), redirect_stdout(buffer):
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

    def test_skills_list_reports_bundled_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code, payload = self.run_agent_command(["skills", "list", "--dest", temp_dir, "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "skills.list")
        self.assertEqual(payload["data"]["skills"][0]["name"], "attend-agent-workflow")
        self.assertFalse(payload["data"]["skills"][0]["installed"])
        self.assertIn("agent_skill_dirs", payload["data"])

    def test_skills_install_writes_skill_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as agent_dir:
            exit_code, payload = self.run_agent_command(
                ["skills", "install", "--dest", temp_dir, "--agent-dir", agent_dir, "--json"]
            )

            installed_dir = Path(payload["data"]["installed"][0])
            skill_file = installed_dir / "SKILL.md"
            bootstrap_file = installed_dir / "BOOTSTRAP.md"
            self.assertTrue(skill_file.exists())
            self.assertTrue(bootstrap_file.exists())
            self.assertIn("attend handoff --json", skill_file.read_text(encoding="utf-8"))
            self.assertIn("Read `BOOTSTRAP.md` only when", skill_file.read_text(encoding="utf-8"))
            self.assertIn("uv tool install always-attend", bootstrap_file.read_text(encoding="utf-8"))
            link_path = Path(agent_dir) / "attend-agent-workflow"
            self.assertTrue(link_path.is_symlink())
            self.assertEqual(link_path.resolve(), installed_dir.resolve())
            self.assertEqual(payload["data"]["agent_links"][0]["status"], "linked")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "skills.install")

    def test_repo_skill_markdown_matches_packaged_skill_markdown(self) -> None:
        repo_skill = Path("skills/SKILL.md").read_text(encoding="utf-8")
        packaged_skill = Path("src/always_attend/skills/SKILL.md").read_text(encoding="utf-8")
        repo_bootstrap = Path("skills/BOOTSTRAP.md").read_text(encoding="utf-8")
        packaged_bootstrap = Path("src/always_attend/skills/BOOTSTRAP.md").read_text(encoding="utf-8")

        self.assertEqual(repo_skill, packaged_skill)
        self.assertEqual(repo_bootstrap, packaged_bootstrap)
        self.assertIn("Read `BOOTSTRAP.md` only when", repo_skill)
        self.assertIn("python3 --version", repo_bootstrap)
        self.assertIn("playwright install chromium", repo_bootstrap)
        self.assertIn("attend auth login <attendance-url> --json", repo_bootstrap)

    def test_skills_install_existing_path_requires_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir) / "attend-agent-workflow"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("old", encoding="utf-8")

            exit_code, payload = self.run_agent_command(["skills", "install", "--dest", temp_dir, "--json"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["command"], "skills")
        self.assertIn("Use --force to overwrite", payload["error"])

    def test_skills_install_uses_attend_skills_dir_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as agent_dir, patch.dict(
            "os.environ", {"ATTEND_SKILLS_DIR": temp_dir}, clear=False
        ):
            exit_code, payload = self.run_agent_command(["skills", "install", "--agent-dir", agent_dir, "--json"])
            self.assertTrue((Path(temp_dir) / "attend-agent-workflow" / "SKILL.md").exists())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["data"]["skills_root"], str(Path(temp_dir)))

    def test_skills_install_skips_conflicting_agent_link_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as agent_dir:
            conflict = Path(agent_dir) / "attend-agent-workflow"
            conflict.mkdir(parents=True)
            (conflict / "SKILL.md").write_text("conflict", encoding="utf-8")

            exit_code, payload = self.run_agent_command(
                ["skills", "install", "--dest", temp_dir, "--agent-dir", agent_dir, "--json"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["data"]["agent_links"][0]["status"], "skipped_conflict")

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

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["command"], "run")
        self.assertEqual(payload["next_action"], "configure_target_url")
        self.assertIn("attend config set --target", payload["suggested_command"])

    def test_run_without_target_falls_back_to_demo(self) -> None:
        exit_code, payload = self.run_agent_command(["run", "--json"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["command"], "run")
        self.assertEqual(payload["next_action"], "configure_target_url")

    def test_inspect_demo_returns_items_without_target(self) -> None:
        exit_code, payload = self.run_agent_command(["inspect", "state", "--demo", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "inspect.state")
        self.assertEqual(payload["data"]["items"][0]["course_code"], "FIT2099")

    def test_inspect_without_target_falls_back_to_demo(self) -> None:
        exit_code, payload = self.run_agent_command(["inspect", "state", "--json"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["command"], "inspect")
        self.assertEqual(payload["next_action"], "configure_target_url")

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

    def test_config_get_reads_persisted_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text('PORTAL_URL="https://attendance.example.test/student/"\n', encoding="utf-8")
            with patch.dict(os.environ, {"ENV_FILE": str(env_path)}, clear=True):
                exit_code, payload = self.run_agent_command(["config", "get", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "config.get")
        self.assertTrue(payload["data"]["configured"])
        self.assertEqual(payload["data"]["value"], "https://attendance.example.test/student/")

    def test_config_set_persists_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"ENV_FILE": str(Path(temp_dir) / ".env")},
            clear=True,
        ):
            exit_code, payload = self.run_agent_command(
                ["config", "set", "--target", "https://attendance.example.test/student/", "--json"]
            )

            env_path = Path(payload["data"]["env_file"])
            self.assertTrue(env_path.exists())
            env_text = env_path.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "config.set")
        self.assertEqual(payload["data"]["value"], "https://attendance.example.test/student/")
        self.assertIn('PORTAL_URL="https://attendance.example.test/student/"', env_text)

    def test_config_set_rejects_local_target_without_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"ENV_FILE": str(Path(temp_dir) / ".env")},
            clear=True,
        ):
            exit_code, payload = self.run_agent_command(
                ["config", "set", "--target", "http://127.0.0.1:8081/student/", "--json"]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["command"], "config")
        self.assertIn("Refusing to persist a local attendance URL", payload["error"])

    def test_auth_login_uses_browser_import_when_available(self) -> None:
        with patch.dict(os.environ, {"PORTAL_URL": "https://attendance.example.test/student/"}, clear=True), patch(
            "always_attend.agent_cli.SessionManager.import_browser_session",
            new=AsyncMock(return_value={"status": "ok", "mode": "browser_cookie_import"}),
        ), patch("always_attend.agent_cli.OktaClient") as mock_okta:
            exit_code, payload = self.run_agent_command(["auth", "login", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "auth.login")
        self.assertEqual(payload["data"]["auth_flow"]["completed_method"], "browser_cookie_import")
        self.assertEqual(payload["data"]["target"], "https://attendance.example.test/student/")
        mock_okta.return_value.login.assert_not_called()

    def test_auth_login_falls_back_to_interactive_okta_login(self) -> None:
        with patch.dict(os.environ, {"PORTAL_URL": "https://attendance.example.test/student/"}, clear=True), patch(
            "always_attend.agent_cli.SessionManager.import_browser_session",
            new=AsyncMock(return_value={"status": "failed", "mode": "browser_cookie_import", "reason": "missing"}),
        ), patch("always_attend.agent_cli.OktaClient") as mock_okta:
            mock_okta.return_value.login.return_value.payload = {"ok": True}
            exit_code, payload = self.run_agent_command(["auth", "login", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["data"]["auth_flow"]["completed_method"], "interactive_okta_login")
        self.assertEqual(payload["data"]["session_scope"], "shared_okta_session")
        mock_okta.return_value.login.assert_called_once()
        self.assertTrue(mock_okta.return_value.login.call_args.kwargs["headed"])

    def test_main_loads_persisted_target_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text('PORTAL_URL="https://attendance.example.test/student/"\n', encoding="utf-8")
            with patch.dict(os.environ, {"ENV_FILE": str(env_path)}, clear=True), patch(
                "always_attend.agent_cli._handle_auth",
                return_value={"status": "ok", "command": "auth.check", "data": {}, "exit_code": 0},
            ) as mock_handle:
                exit_code, _ = self.run_agent_command(["auth", "check", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(mock_handle.call_args.args[0].url, "https://attendance.example.test/student/")

    def test_run_with_explicit_target_does_not_persist_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            with patch.dict(os.environ, {"ENV_FILE": str(env_path)}, clear=True), patch(
                "always_attend.agent_cli._pipeline_run",
                new=AsyncMock(
                    return_value={
                        "status": "ok",
                        "command": "run",
                        "summary": {},
                        "trace": [],
                        "metrics": {},
                        "data": {"target": "https://attendance.example.test/student/"},
                        "exit_code": 0,
                    }
                ),
            ):
                exit_code, _ = self.run_agent_command(
                    ["run", "--target", "https://attendance.example.test/student/", "--json"]
                )

        self.assertEqual(exit_code, 0)
        self.assertFalse(env_path.exists())

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
