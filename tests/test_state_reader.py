"""Tests for attendance DOM state classification helpers."""

from __future__ import annotations

import unittest

from always_attend.attendance_state_reader import classify_dom_state


class AttendanceStateReaderTests(unittest.TestCase):
    def test_tick_is_submitted(self) -> None:
        state, reason = classify_dom_state(has_tick=True, has_entry_link=True, is_disabled=False)
        self.assertEqual(state, "submitted")
        self.assertIn("Tick", reason)

    def test_entry_link_is_open(self) -> None:
        state, reason = classify_dom_state(has_tick=False, has_entry_link=True, is_disabled=False)
        self.assertEqual(state, "open")
        self.assertIn("Entry link", reason)

    def test_disabled_is_locked(self) -> None:
        state, reason = classify_dom_state(has_tick=False, has_entry_link=False, is_disabled=True)
        self.assertEqual(state, "locked")
        self.assertIn("disabled", reason)

    def test_missing_dom_is_unresolved(self) -> None:
        state, reason = classify_dom_state(has_tick=False, has_entry_link=False, is_disabled=False)
        self.assertEqual(state, "unresolved")
        self.assertIn("did not clearly", reason)


if __name__ == "__main__":
    unittest.main()
