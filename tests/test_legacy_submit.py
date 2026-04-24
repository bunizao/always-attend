"""Focused tests for the legacy submit flow."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core import submit as legacy_submit


class LegacySubmitSlotTests(unittest.TestCase):
    def test_normalize_slot_text_ignores_time_prefix(self) -> None:
        self.assertEqual(
            legacy_submit._normalize_slot_text("12:00 pm Applied 01"),
            legacy_submit._normalize_slot_text("Applied 01"),
        )

    def test_build_candidate_codes_prefers_slot_match_after_time_normalization(self) -> None:
        slot_code_map = {
            legacy_submit._normalize_slot_text("Applied 01"): ["RIGHT1"],
            legacy_submit._normalize_slot_text("Applied 07"): ["OTHER7"],
        }
        ordered_codes = ["WRONG9", "RIGHT1", "OTHER7"]

        candidate_codes = legacy_submit._build_candidate_codes(
            legacy_submit._normalize_slot_text("12:00 pm Applied 01"),
            slot_code_map,
            ordered_codes,
        )

        self.assertEqual(candidate_codes, ["RIGHT1", "WRONG9", "OTHER7"])


class LegacySubmitOutcomeTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_requires_verified_tick_before_success(self) -> None:
        page = SimpleNamespace(goto=AsyncMock())
        target = legacy_submit.SubmissionTarget(
            course_code="FIT2099",
            slot_label="12:00 pm Applied 01",
            slot_norm=legacy_submit._normalize_slot_text("12:00 pm Applied 01"),
            anchor="24_Apr_26",
            position=0,
            raw_text="FIT2099 12:00 pm Applied 01",
        )
        used_codes: set[str] = set()

        with patch("core.submit._open_target_entry", new=AsyncMock(return_value=True)), patch(
            "core.submit.submit_code_on_entry",
            new=AsyncMock(return_value=(True, "Code submitted successfully")),
        ), patch(
            "core.submit.verify_entry_mark",
            new=AsyncMock(return_value=False),
        ):
            outcome = await legacy_submit._submit_codes_for_target(
                page,
                "https://attendance.example.test",
                target,
                {target.slot_norm: ["RM6DV"]},
                ["RM6DV"],
                used_codes,
                asyncio.Lock(),
            )

        self.assertFalse(outcome.success)
        self.assertIsNone(outcome.code)
        self.assertEqual(outcome.attempts, 1)
        self.assertEqual(used_codes, set())

    async def test_submit_records_verified_codes_in_used_pool(self) -> None:
        page = SimpleNamespace(goto=AsyncMock())
        target = legacy_submit.SubmissionTarget(
            course_code="FIT2099",
            slot_label="12:00 pm Applied 01",
            slot_norm=legacy_submit._normalize_slot_text("12:00 pm Applied 01"),
            anchor="24_Apr_26",
            position=0,
            raw_text="FIT2099 12:00 pm Applied 01",
        )
        used_codes: set[str] = set()
        used_codes_lock = asyncio.Lock()

        with patch("core.submit._open_target_entry", new=AsyncMock(return_value=True)), patch(
            "core.submit.submit_code_on_entry",
            new=AsyncMock(
                side_effect=[
                    (True, "Code submitted (status unclear)"),
                    (True, "Code submitted successfully"),
                ]
            ),
        ), patch(
            "core.submit.verify_entry_mark",
            new=AsyncMock(side_effect=[False, True]),
        ):
            outcome = await legacy_submit._submit_codes_for_target(
                page,
                "https://attendance.example.test",
                target,
                {target.slot_norm: ["RM6DV", "GOOD1"]},
                ["RM6DV", "GOOD1", "SPARE2"],
                used_codes,
                used_codes_lock,
            )

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.code, "GOOD1")
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(used_codes, {"GOOD1"})
        self.assertEqual(
            legacy_submit._build_candidate_codes(target.slot_norm, {}, ["GOOD1", "SPARE2"], used_codes),
            ["SPARE2"],
        )


if __name__ == "__main__":
    unittest.main()
