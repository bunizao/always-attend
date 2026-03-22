"""Smoke tests for the public CLI entrypoints."""

from __future__ import annotations

import os
import json
import subprocess
import sys
import unittest
from pathlib import Path

from always_attend.runtime_contract import get_runtime_paths_dict


REPO_ROOT = Path(__file__).resolve().parents[1]


class CliEntrypointTests(unittest.TestCase):
    def run_command(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        return subprocess.run(
            list(args),
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def assert_help_output(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("run", result.stdout)
        self.assertIn("inspect", result.stdout)
        self.assertIn("auth", result.stdout)
        self.assertIn("skills", result.stdout)

    def test_attend_console_script_help(self) -> None:
        scripts_dir = Path(sys.executable).parent
        attend_bin = scripts_dir / ("attend.exe" if os.name == "nt" else "attend")
        self.assertTrue(attend_bin.exists(), f"{attend_bin} does not exist")
        result = self.run_command(str(attend_bin), "--help")
        self.assert_help_output(result)

    def test_python_module_help(self) -> None:
        result = self.run_command(sys.executable, "-m", "always_attend", "--help")
        self.assert_help_output(result)

    def test_legacy_main_py_help(self) -> None:
        result = self.run_command(sys.executable, "main.py", "--help")
        self.assert_help_output(result)

    def test_version_flag(self) -> None:
        result = self.run_command(sys.executable, "-m", "always_attend", "--version")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("always-attend 0.1.2", result.stdout.strip())

    def test_paths_builtin_json(self) -> None:
        result = self.run_command(sys.executable, "-m", "always_attend", "paths", "--json")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["contract_version"], "2")
        self.assertIn("app_data_dir", payload)
        self.assertIn("env_file", payload)
        self.assertIn("storage_state_file", payload)

    def test_paths_python_api(self) -> None:
        payload = get_runtime_paths_dict()
        self.assertEqual(payload["contract_version"], "2")
        self.assertIn("app_data_dir", payload)
        self.assertIn("codes_db_path", payload)

    def test_agent_auth_help(self) -> None:
        result = self.run_command(sys.executable, "-m", "always_attend", "auth", "--help")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("login", result.stdout)
        self.assertIn("check", result.stdout)

    def test_agent_run_help(self) -> None:
        result = self.run_command(sys.executable, "-m", "always_attend", "run", "--help")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--target", result.stdout)
        self.assertIn("--sources", result.stdout)
        self.assertIn("--min-confidence", result.stdout)

    def test_agent_handoff_help(self) -> None:
        result = self.run_command(sys.executable, "-m", "always_attend", "handoff", "--help")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--sources", result.stdout)
        self.assertIn("--week", result.stdout)
        self.assertIn("--demo", result.stdout)

    def test_agent_skills_help(self) -> None:
        result = self.run_command(sys.executable, "-m", "always_attend", "skills", "--help")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("install", result.stdout)
        self.assertIn("list", result.stdout)


if __name__ == "__main__":
    unittest.main()
