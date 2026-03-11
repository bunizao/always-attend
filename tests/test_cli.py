"""Smoke tests for the public CLI entrypoints."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from always_attend.argv import normalize_cli_argv


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
        self.assertIn("attend stats", result.stdout)
        self.assertIn("attend login", result.stdout)
        self.assertIn("attend week 4", result.stdout)
        self.assertIn("--dry-run", result.stdout)

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
        self.assertIn("always-attend 0.1.0", result.stdout.strip())

    def test_subcommand_normalization(self) -> None:
        self.assertEqual(normalize_cli_argv(["stats"]), ["--stats"])
        self.assertEqual(normalize_cli_argv(["login", "--headed"]), ["--login-only", "--headed"])
        self.assertEqual(normalize_cli_argv(["week", "5", "--dry-run"]), ["--week", "5", "--dry-run"])
        self.assertEqual(normalize_cli_argv(["week", "--help"]), ["--help"])


if __name__ == "__main__":
    unittest.main()
