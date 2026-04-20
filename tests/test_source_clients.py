"""Tests for external source adapter integration."""

from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

from always_attend.source_clients import GenericJsonCliAdapter, SourceRequest


class SourceClientTests(unittest.TestCase):
    def test_generic_adapter_exports_okta_session_env(self) -> None:
        captured_env: dict[str, str] = {}

        def fake_run(command, capture_output, text, env):
            del command, capture_output, text
            captured_env.update(env)
            return subprocess.CompletedProcess(args=["dummy"], returncode=0, stdout=json.dumps({"ok": True}), stderr="")

        with patch("always_attend.source_clients.shutil.which", return_value="/usr/bin/dummy"), patch(
            "always_attend.source_clients.SessionManager.build_source_environment",
            return_value={
                "ALWAYS_ATTEND_OKTA_URL": "https://attendance.example.test",
                "OKTA_COOKIE_HEADER": "sid=abc123; csrftoken=def456",
                "ALWAYS_ATTEND_OKTA_COOKIE_HEADER": "sid=abc123; csrftoken=def456",
                "ALWAYS_ATTEND_OKTA_COOKIES_JSON": '[{"name":"sid","value":"abc123"}]',
                "OKTA_COOKIES_JSON": '[{"name":"sid","value":"abc123"}]',
            },
        ), patch("always_attend.source_clients.subprocess.run", side_effect=fake_run):
            payload = GenericJsonCliAdapter(
                source="moodle",
                executable_names=("moodle-cli",),
            ).fetch(SourceRequest(source="moodle", url="https://attendance.example.test"))

        self.assertEqual(payload["payload"], {"ok": True})
        self.assertEqual(captured_env["ALWAYS_ATTEND_OKTA_URL"], "https://attendance.example.test")
        self.assertEqual(captured_env["OKTA_COOKIE_HEADER"], "sid=abc123; csrftoken=def456")
        self.assertTrue(payload["session_env"]["cookie_header_present"])
        self.assertTrue(payload["session_env"]["cookies_json_present"])


if __name__ == "__main__":
    unittest.main()
