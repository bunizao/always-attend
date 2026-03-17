"""Submit structured attendance matches via the legacy portal automation."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse, urlunparse

from always_attend.agent_protocol import AttendanceStateItem, MatchResult, SubmissionAttempt, TraceEvent
from always_attend.paths import storage_state_file
from core.browser_controller import BrowserConfig, BrowserController
from core.submit import (
    SubmissionTarget,
    _normalize_slot_text,
    _open_target_entry,
    is_authenticated,
    submit_code_on_entry,
    verify_entry_mark,
)
from utils.browser_detection import is_browser_channel_available
from utils.session import is_storage_state_effective


def _to_base(origin_url: str) -> str:
    parsed = urlparse(origin_url)
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


class Submitter:
    """Submit structured matches and convert outcomes to state-machine results."""

    async def submit(
        self,
        *,
        target_url: str,
        items: list[AttendanceStateItem],
        matches: list[MatchResult],
        min_confidence: float,
        max_retries: int = 1,
        headed: bool = False,
        dry_run: bool = False,
    ) -> tuple[list[SubmissionAttempt], list[TraceEvent]]:
        if dry_run:
            return self._dry_run_attempts(matches, min_confidence), [
                TraceEvent(
                    stage="submit",
                    code="dry_run",
                    message="Submit stage skipped browser mutation because dry-run was enabled.",
                    details={"match_count": len(matches)},
                )
            ]

        item_index = {item.item_id: item for item in items}
        browser_name = os.getenv("BROWSER", "chromium")
        channel = os.getenv("BROWSER_CHANNEL")
        if browser_name == "chromium" and channel and not is_browser_channel_available(channel):
            channel = None
        storage_path = storage_state_file()
        config = BrowserConfig(
            name=browser_name,
            channel=channel,
            headed=headed,
            storage_state=(str(storage_path) if storage_path.exists() and is_storage_state_effective(str(storage_path)) else None),
            timeout_ms=60000,
        )
        attempts: list[SubmissionAttempt] = []
        trace: list[TraceEvent] = []
        base_url = _to_base(target_url)

        async with BrowserController(config) as controller:
            page = await controller.context.new_page()
            await page.goto(f"{base_url}/student/Units.aspx", timeout=60000)
            if not await is_authenticated(page):
                return [
                    SubmissionAttempt(
                        item_id=item.item_id,
                        course_code=item.course_code,
                        slot_label=item.slot_label,
                        candidate_code=None,
                        confidence=0.0,
                        state="session_invalid",
                        reason="Portal session became invalid before submission.",
                        source=None,
                    )
                    for item in items
                    if item.dom_state == "open"
                ], [
                    TraceEvent(
                        stage="submit",
                        code="session_invalid",
                        message="Portal session became invalid before submission.",
                        details={"target": target_url},
                    )
                ]

            for match in matches:
                item = item_index.get(match.item_id)
                if item is None:
                    continue
                if match.candidate_code is None:
                    attempts.append(
                        SubmissionAttempt(
                            item_id=item.item_id,
                            course_code=item.course_code,
                            slot_label=item.slot_label,
                            candidate_code=None,
                            confidence=match.confidence,
                            state="ambiguous",
                            reason=match.reason,
                            source=match.source,
                        )
                    )
                    continue
                if match.confidence < min_confidence:
                    continue

                outcome = await self._submit_single(
                    page=page,
                    base_url=base_url,
                    item=item,
                    match=match,
                    retries=max_retries,
                )
                attempts.append(outcome)
                trace.append(
                    TraceEvent(
                        stage="submit",
                        code=outcome.state,
                        message="Submission attempt completed.",
                        details=outcome.to_dict(),
                    )
                )
        return attempts, trace

    async def _submit_single(
        self,
        *,
        page,
        base_url: str,
        item: AttendanceStateItem,
        match: MatchResult,
        retries: int,
    ) -> SubmissionAttempt:
        target = SubmissionTarget(
            course_code=item.course_code,
            slot_label=item.slot_label,
            slot_norm=_normalize_slot_text(item.slot_label),
            anchor=item.anchor,
            position=item.position,
            raw_text=item.raw_text,
        )
        opened = await _open_target_entry(page, base_url, target)
        if not opened:
            return SubmissionAttempt(
                item_id=item.item_id,
                course_code=item.course_code,
                slot_label=item.slot_label,
                candidate_code=match.candidate_code,
                confidence=match.confidence,
                state="dom_locked",
                reason="Could not open the target entry from Units.aspx.",
                source=match.source,
            )

        attempt_count = 0
        while attempt_count <= retries:
            attempt_count += 1
            ok, message = await submit_code_on_entry(page, match.candidate_code)
            verified = await verify_entry_mark(page, base_url, item.anchor, item.course_code, item.slot_label)
            if ok and verified:
                return SubmissionAttempt(
                    item_id=item.item_id,
                    course_code=item.course_code,
                    slot_label=item.slot_label,
                    candidate_code=match.candidate_code,
                    confidence=match.confidence,
                    state="submitted_ok",
                    reason="DOM state changed to submitted after code submission.",
                    source=match.source,
                )
            if "invalid" in message.lower():
                return SubmissionAttempt(
                    item_id=item.item_id,
                    course_code=item.course_code,
                    slot_label=item.slot_label,
                    candidate_code=match.candidate_code,
                    confidence=match.confidence,
                    state="incorrect_code",
                    reason=message,
                    source=match.source,
                )
            if ok and not verified:
                return SubmissionAttempt(
                    item_id=item.item_id,
                    course_code=item.course_code,
                    slot_label=item.slot_label,
                    candidate_code=match.candidate_code,
                    confidence=match.confidence,
                    state="post_submit_unverified",
                    reason="Submit succeeded but the DOM did not confirm a submitted state.",
                    source=match.source,
                )
        return SubmissionAttempt(
            item_id=item.item_id,
            course_code=item.course_code,
            slot_label=item.slot_label,
            candidate_code=match.candidate_code,
            confidence=match.confidence,
            state="ambiguous",
            reason="Submitter exhausted retries without a stable DOM outcome.",
            source=match.source,
        )

    @staticmethod
    def _dry_run_attempts(matches: list[MatchResult], min_confidence: float) -> list[SubmissionAttempt]:
        attempts: list[SubmissionAttempt] = []
        for match in matches:
            if match.candidate_code is None:
                continue
            state = "ready" if match.confidence >= min_confidence else "ambiguous"
            reason = "Dry-run candidate would be submitted." if state == "ready" else "Dry-run candidate was below confidence threshold."
            attempts.append(
                SubmissionAttempt(
                    item_id=match.item_id,
                    course_code=match.course_code,
                    slot_label=match.slot_label,
                    candidate_code=match.candidate_code,
                    confidence=match.confidence,
                    state=state,  # type: ignore[arg-type]
                    reason=reason,
                    source=match.source,
                )
            )
        return attempts
