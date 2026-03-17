"""Read and normalize attendance site DOM state."""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime
from urllib.parse import urlparse, urlunparse

from playwright.async_api import Page

from always_attend.agent_protocol import AttendanceStateItem, TraceEvent
from always_attend.paths import storage_state_file
from core.browser_controller import BrowserConfig, BrowserController
from core.submit import is_authenticated
from utils.browser_detection import is_browser_channel_available
from utils.session import is_storage_state_effective


MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _to_base(origin_url: str) -> str:
    parsed = urlparse(origin_url)
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def _parse_anchor(anchor: str | None) -> str | None:
    if not anchor:
        return None
    try:
        day_s, month_s, year_s = anchor.split("_")
        day = int(day_s)
        month = MONTH_ABBR.index(month_s.capitalize()) + 1
        year = 2000 + int(year_s)
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except Exception:
        return None


def _extract_slot_label(raw_text: str, course_code: str) -> str:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return raw_text.strip()
    for line in lines:
        cleaned = re.sub(rf"\b{re.escape(course_code)}\b", "", line, flags=re.I).strip("-:– ")
        if cleaned:
            return cleaned
    return lines[0]


def _extract_class_type(slot_label: str) -> str | None:
    lower = slot_label.lower()
    if "workshop" in lower:
        return "workshop"
    if "applied" in lower:
        return "applied"
    if "lab" in lower or "laboratory" in lower:
        return "lab"
    if "tutorial" in lower or "tut" in lower:
        return "tutorial"
    if "lecture" in lower:
        return "lecture"
    return None


def _extract_time_range(text: str) -> str | None:
    match = re.search(
        r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:-|–|to)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b",
        text,
        re.I,
    )
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return None


def _extract_group(text: str) -> str | None:
    match = re.search(r"\b(?:group|grp)\s*([A-Za-z0-9_-]+)\b", text, re.I)
    if match:
        return match.group(1)
    if "separate group" in text.lower():
        return "separate-groups"
    return None


def classify_dom_state(*, has_tick: bool, has_entry_link: bool, is_disabled: bool) -> tuple[str, str]:
    """Classify the DOM state for a single attendance item."""
    if has_tick:
        return "submitted", "Tick icon is present."
    if is_disabled:
        return "locked", "DOM item is disabled."
    if has_entry_link:
        return "open", "Entry link is available."
    return "unresolved", "DOM did not clearly expose an entry state."


async def _collect_day_anchors(page: Page) -> list[str]:
    anchors: list[str] = []
    try:
        options = page.locator("#daySel option")
        count = await options.count()
        for index in range(count):
            value = await options.nth(index).get_attribute("value")
            if value:
                anchors.append(value)
    except Exception:
        pass
    if anchors:
        return anchors
    panels = page.locator('[id^="dayPanel_"]')
    panel_count = await panels.count()
    for index in range(panel_count):
        panel_id = await panels.nth(index).get_attribute("id")
        if panel_id and panel_id.startswith("dayPanel_"):
            anchors.append(panel_id.replace("dayPanel_", "", 1))
    return anchors


class AttendanceStateReader:
    """Inspect the attendance portal and extract normalized state items."""

    async def inspect(
        self,
        *,
        target_url: str,
        headed: bool = False,
        course_filters: list[str] | None = None,
    ) -> tuple[list[AttendanceStateItem], list[TraceEvent]]:
        base_url = _to_base(target_url)
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
        async with BrowserController(config) as controller:
            page = await controller.context.new_page()
            await page.goto(f"{base_url}/student/Units.aspx", timeout=60000)
            if not await is_authenticated(page):
                return [], [
                    TraceEvent(
                        stage="inspect",
                        code="session_invalid",
                        message="Attendance portal session was invalid.",
                        details={"target": target_url},
                    )
                ]
            items = await self._read_items(page)
            if course_filters:
                selected = {item.upper() for item in course_filters}
                items = [item for item in items if item.course_code in selected]
            return items, [
                TraceEvent(
                    stage="inspect",
                    code="state_loaded",
                    message="Attendance site state loaded.",
                    details={"item_count": len(items)},
                )
            ]

    async def _read_items(self, page: Page) -> list[AttendanceStateItem]:
        anchors = await _collect_day_anchors(page)
        items: list[AttendanceStateItem] = []
        seen: set[str] = set()

        async def read_panel(anchor: str | None) -> None:
            if anchor:
                selector = page.locator("#daySel")
                if await selector.count() > 0:
                    try:
                        await selector.select_option(value=anchor)
                        await asyncio.sleep(0.05)
                    except Exception:
                        pass
                root = page.locator(f"#dayPanel_{anchor}")
                if await root.count() == 0:
                    root = page
            else:
                root = page.locator("div.dayPanel:not([style*='display:none'])").first
                if await root.count() == 0:
                    root = page

            nodes = root.locator("li")
            count = await nodes.count()
            for position in range(count):
                li = nodes.nth(position)
                raw_text = (await li.inner_text() or "").strip()
                if not raw_text:
                    continue
                course_match = re.search(r"\b([A-Z]{3}\d{4})\b", raw_text)
                if not course_match:
                    continue
                course_code = course_match.group(1)
                slot_label = _extract_slot_label(raw_text, course_code)
                has_tick = False
                try:
                    has_tick = await li.locator("img[src*='tick']").count() > 0
                except Exception:
                    pass
                is_disabled = False
                try:
                    css_class = (await li.get_attribute("class") or "").lower()
                    is_disabled = "ui-disabled" in css_class
                except Exception:
                    pass
                try:
                    has_entry_link = await li.locator("a[href*='Entry.aspx']").count() > 0
                except Exception:
                    has_entry_link = False
                dom_state, reason = classify_dom_state(
                    has_tick=has_tick,
                    has_entry_link=has_entry_link,
                    is_disabled=is_disabled,
                )
                item_id = f"{course_code}:{anchor or 'visible'}:{position}:{slot_label}"
                if item_id in seen:
                    continue
                seen.add(item_id)
                items.append(
                    AttendanceStateItem(
                        item_id=item_id,
                        course_code=course_code,
                        class_type=_extract_class_type(slot_label),
                        slot_label=slot_label,
                        date=_parse_anchor(anchor),
                        time_range=_extract_time_range(raw_text),
                        group=_extract_group(raw_text),
                        anchor=anchor,
                        dom_state=dom_state,  # type: ignore[arg-type]
                        reason=reason,
                        position=position,
                        raw_text=raw_text,
                    )
                )

        await read_panel(None)
        for anchor in anchors:
            await read_panel(anchor)
        return items
