"""Tests for session manager auth requirements."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from always_attend.okta_client import OktaCliError
from always_attend.session_manager import SessionManager


class SessionManagerTests(unittest.TestCase):
    def test_localhost_target_does_not_require_okta(self) -> None:
        manager = SessionManager()
        self.assertFalse(manager.requires_okta_session("http://127.0.0.1:8081/student/"))
        self.assertFalse(manager.requires_okta_session("http://localhost:8081/student/"))

    def test_remote_target_requires_okta(self) -> None:
        manager = SessionManager()
        self.assertTrue(manager.requires_okta_session("https://attendance.monash.edu.my/student/"))

    def test_ensure_storage_state_reuses_existing_storage_state_when_okta_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_state_path = Path(temp_dir) / "storage_state.json"
            storage_state_path.write_text(
                json.dumps({"cookies": [{"name": "sid", "value": "abc"}], "origins": []}),
                encoding="utf-8",
            )
            manager = SessionManager()
            with patch.dict("os.environ", {"STORAGE_STATE": str(storage_state_path)}, clear=False), patch.object(
                manager._okta,
                "cookies",
                side_effect=OktaCliError("No stored session found"),
            ):
                payload = manager.ensure_storage_state("https://attendance.monash.edu.my/student/")

        self.assertEqual(payload["path"], str(storage_state_path))
        self.assertTrue(payload["reused"])

    def test_check_okta_session_uses_okta_client_for_remote_target(self) -> None:
        manager = SessionManager()
        with patch.object(manager._okta, "check") as mock_check:
            mock_check.return_value.payload = {"ok": True}
            payload = manager.check_okta_session("https://attendance.monash.edu.my/student/", timeout_ms=1234)

        self.assertEqual(payload, {"ok": True})
        mock_check.assert_called_once_with(url="https://attendance.monash.edu.my/student/", timeout_ms=1234)

    def test_import_browser_session_returns_storage_state_payload(self) -> None:
        manager = SessionManager()
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {"STORAGE_STATE": str(Path(temp_dir) / "storage_state.json")},
            clear=False,
        ), patch("core.login.LoginWorkflow._import_session_from_system_browser", new=AsyncMock(return_value=True)):
            payload = asyncio.run(manager.import_browser_session("https://attendance.monash.edu.my/student/", timeout_ms=4321))

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["mode"], "browser_cookie_import")
        self.assertTrue(payload["storage_state"].endswith("storage_state.json"))


if __name__ == "__main__":
    unittest.main()
