"""Tests for browser session import helpers and workflow integration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.login import LoginConfig, LoginWorkflow
from utils.browser_session import (
    BrowserSessionSource,
    clone_browser_session_source,
    read_last_used_profile,
    resolve_browser_session_source,
)


class BrowserSessionHelperTests(unittest.TestCase):
    def test_read_last_used_profile_from_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            user_data_dir = Path(temp_dir)
            (user_data_dir / "Local State").write_text(
                json.dumps({"profile": {"last_used": "Profile 3"}}),
                encoding="utf-8",
            )

            self.assertEqual(read_last_used_profile(user_data_dir), "Profile 3")

    def test_resolve_browser_session_source_prefers_env_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            user_data_dir = Path(temp_dir)
            (user_data_dir / "Default").mkdir()
            (user_data_dir / "Profile 7").mkdir()

            with patch.dict(
                "os.environ",
                {
                    "IMPORT_BROWSER_USER_DATA_DIR": str(user_data_dir),
                    "IMPORT_BROWSER_PROFILE": "Profile 7",
                },
                clear=False,
            ):
                source = resolve_browser_session_source("chrome")

            self.assertIsNotNone(source)
            assert source is not None
            self.assertEqual(source.user_data_dir, user_data_dir.resolve())
            self.assertEqual(source.profile_name, "Profile 7")

    def test_clone_browser_session_source_copies_profile_without_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "source"
            source_root.mkdir()
            (source_root / "Local State").write_text("{}", encoding="utf-8")
            profile_dir = source_root / "Default"
            profile_dir.mkdir()
            (profile_dir / "Cookies").write_text("db", encoding="utf-8")
            cache_dir = profile_dir / "Cache"
            cache_dir.mkdir()
            (cache_dir / "tmp").write_text("ignored", encoding="utf-8")

            source = BrowserSessionSource(
                channel="chrome",
                user_data_dir=source_root,
                profile_name="Default",
            )

            destination_root = Path(temp_dir) / "clone"
            clone_browser_session_source(source, destination_root)

            self.assertTrue((destination_root / "Local State").exists())
            self.assertTrue((destination_root / "Default" / "Cookies").exists())
            self.assertFalse((destination_root / "Default" / "Cache").exists())


class LoginWorkflowImportTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_skips_interactive_login_after_successful_import(self) -> None:
        workflow = LoginWorkflow(
            LoginConfig(
                portal_url="https://portal.example.test",
                storage_state="/tmp/storage-state.json",
                import_browser_session=True,
            )
        )

        with patch.object(
            workflow,
            "_import_session_from_system_browser",
            new=AsyncMock(return_value=True),
        ) as mock_import, patch("core.login.BrowserController") as mock_controller:
            await workflow.run()

        mock_import.assert_awaited_once()
        mock_controller.assert_not_called()

    async def test_import_session_from_system_browser_saves_storage_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_state_path = Path(temp_dir) / "storage_state.json"
            source = BrowserSessionSource(
                channel="chrome",
                user_data_dir=Path(temp_dir) / "system-profile",
                profile_name="Default",
            )
            launched_configs = []

            async def save_storage_state(*, path: str) -> None:
                Path(path).write_text('{"cookies":[{"name":"sid"}],"origins":[]}', encoding="utf-8")

            fake_page = SimpleNamespace(
                goto=AsyncMock(),
                url="https://portal.example.test/home",
            )
            fake_context = SimpleNamespace(
                new_page=AsyncMock(return_value=fake_page),
                storage_state=AsyncMock(side_effect=save_storage_state),
            )

            class FakeBrowserController:
                def __init__(self, config):
                    launched_configs.append(config)
                    self.context = fake_context

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb):
                    return None

            workflow = LoginWorkflow(
                LoginConfig(
                    portal_url="https://portal.example.test",
                    storage_state=str(storage_state_path),
                    import_browser_session=True,
                )
            )

            with patch("core.login.resolve_browser_session_source", return_value=source), patch(
                "core.login.clone_browser_session_source",
                side_effect=lambda src, dst: dst,
            ), patch("core.login.BrowserController", FakeBrowserController), patch.object(
                workflow,
                "_is_session_active",
                new=AsyncMock(return_value=True),
            ) as mock_is_active:
                imported = await workflow._import_session_from_system_browser()
                self.assertTrue(imported)
                self.assertTrue(storage_state_path.exists())
                self.assertEqual(len(launched_configs), 1)
                self.assertEqual(launched_configs[0].channel, "chrome")
                self.assertEqual(launched_configs[0].launch_args, ["--profile-directory=Default"])
                mock_is_active.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
