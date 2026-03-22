"""Tests for session manager auth requirements."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
