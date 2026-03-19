"""Tests for session manager auth requirements."""

from __future__ import annotations

import unittest

from always_attend.session_manager import SessionManager


class SessionManagerTests(unittest.TestCase):
    def test_localhost_target_does_not_require_okta(self) -> None:
        manager = SessionManager()
        self.assertFalse(manager.requires_okta_session("http://127.0.0.1:8081/student/"))
        self.assertFalse(manager.requires_okta_session("http://localhost:8081/student/"))

    def test_remote_target_requires_okta(self) -> None:
        manager = SessionManager()
        self.assertTrue(manager.requires_okta_session("https://attendance.monash.edu.my/student/"))


if __name__ == "__main__":
    unittest.main()
