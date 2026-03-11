"""Tests for runtime filesystem defaults."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from always_attend import paths


class PathDefaultsTests(unittest.TestCase):
    def test_default_xdg_locations(self) -> None:
        fake_home = Path("/tmp/always-attend-home")
        fake_cwd = Path("/tmp/always-attend-cwd")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("always_attend.paths.Path.home", return_value=fake_home),
            patch("always_attend.paths.Path.cwd", return_value=fake_cwd),
            patch("always_attend.paths.sys.platform", "linux"),
        ):
            self.assertEqual(paths.config_dir(), fake_home / ".config" / "always-attend")
            self.assertEqual(paths.state_dir(), fake_home / ".local" / "state" / "always-attend")
            self.assertEqual(paths.data_dir(), fake_home / ".local" / "share" / "always-attend")
            self.assertEqual(paths.env_file(), fake_home / ".config" / "always-attend" / ".env")
            self.assertEqual(paths.storage_state_file(), fake_home / ".local" / "state" / "always-attend" / "storage_state.json")
            self.assertEqual(paths.stats_file(), fake_home / ".local" / "state" / "always-attend" / "attendance_stats.json")
            self.assertEqual(paths.codes_db_path(), fake_home / ".local" / "share" / "always-attend" / "data")

    def test_windows_locations(self) -> None:
        fake_home = Path("C:/Users/TestUser")
        with (
            patch.dict(
                os.environ,
                {
                    "APPDATA": "C:/Users/TestUser/AppData/Roaming",
                    "LOCALAPPDATA": "C:/Users/TestUser/AppData/Local",
                },
                clear=True,
            ),
            patch("always_attend.paths.Path.home", return_value=fake_home),
            patch("always_attend.paths.Path.cwd", return_value=Path("/tmp/always-attend-win-cwd")),
            patch("always_attend.paths.sys.platform", "win32"),
        ):
            self.assertEqual(paths.config_dir(), Path("C:/Users/TestUser/AppData/Roaming/always-attend/config"))
            self.assertEqual(paths.state_dir(), Path("C:/Users/TestUser/AppData/Local/always-attend/state"))
            self.assertEqual(paths.data_dir(), Path("C:/Users/TestUser/AppData/Local/always-attend/data"))
            self.assertEqual(paths.env_file(), Path("C:/Users/TestUser/AppData/Roaming/always-attend/config/.env"))

    def test_macos_locations(self) -> None:
        fake_home = Path("/Users/tester")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("always_attend.paths.Path.home", return_value=fake_home),
            patch("always_attend.paths.Path.cwd", return_value=Path("/tmp/always-attend-macos-cwd")),
            patch("always_attend.paths.sys.platform", "darwin"),
        ):
            self.assertEqual(paths.config_dir(), fake_home / "Library" / "Application Support" / "always-attend" / "config")
            self.assertEqual(paths.state_dir(), fake_home / "Library" / "Application Support" / "always-attend" / "state")
            self.assertEqual(paths.data_dir(), fake_home / "Library" / "Application Support" / "always-attend" / "data")
            self.assertEqual(paths.env_file(), fake_home / "Library" / "Application Support" / "always-attend" / "config" / ".env")

    def test_explicit_env_overrides_win(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ENV_FILE": "/tmp/custom.env",
                "STORAGE_STATE": "/tmp/storage.json",
                "PORTAL_STATE_FILE": "/tmp/portal.json",
                "ATTENDANCE_STATS_FILE": "/tmp/stats.json",
                "CODES_DB_PATH": "/tmp/data-root",
                "USER_DATA_DIR": "/tmp/profile",
            },
            clear=True,
        ):
            self.assertEqual(paths.env_file(), Path("/tmp/custom.env"))
            self.assertEqual(paths.storage_state_file(), Path("/tmp/storage.json"))
            self.assertEqual(paths.portal_state_file(), Path("/tmp/portal.json"))
            self.assertEqual(paths.stats_file(), Path("/tmp/stats.json"))
            self.assertEqual(paths.codes_db_path(), Path("/tmp/data-root"))
            self.assertEqual(paths.user_data_dir(), Path("/tmp/profile"))

    def test_relative_overrides_resolve_from_env_file_directory(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ENV_FILE": "/tmp/attend-config/.env",
                "STORAGE_STATE": "storage_state.json",
                "ATTENDANCE_STATS_FILE": "attendance_stats.json",
                "CODES_DB_PATH": "data",
                "USER_DATA_DIR": "profile",
            },
            clear=True,
        ):
            self.assertEqual(paths.storage_state_file(), Path("/tmp/attend-config/storage_state.json"))
            self.assertEqual(paths.stats_file(), Path("/tmp/attend-config/attendance_stats.json"))
            self.assertEqual(paths.codes_db_path(), Path("/tmp/attend-config/data"))
            self.assertEqual(paths.user_data_dir(), Path("/tmp/attend-config/profile"))

    def test_repo_local_env_is_kept_for_checkout_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text("", encoding="utf-8")
            (root / "src").mkdir()
            (root / ".env").write_text("PORTAL_URL=test\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True), patch("always_attend.paths.Path.cwd", return_value=root):
                self.assertEqual(paths.env_file(), root / ".env")


if __name__ == "__main__":
    unittest.main()
