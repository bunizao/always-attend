"""Playwright-backed navigator for submitting attendance codes."""

from __future__ import annotations

import logging
from contextlib import contextmanager

from playwright.sync_api import Browser, Page, sync_playwright

from .codes import AttendanceCode
from .runner import SubmissionNavigator

LOGGER = logging.getLogger(__name__)


class PlaywrightSubmissionNavigator(SubmissionNavigator):
    """Drive the browser to submit a single attendance code."""

    def __init__(
        self,
        *,
        portal_url: str,
        code_input_selector: str,
        submit_button_selector: str,
        success_selector: str,
        headless: bool = True,
    ) -> None:
        self._portal_url = portal_url
        self._code_input_selector = code_input_selector
        self._submit_button_selector = submit_button_selector
        self._success_selector = success_selector
        self._headless = headless

    def submit_code(self, code: AttendanceCode) -> None:
        with sync_playwright() as playwright:
            LOGGER.debug("Launching Chromium (headless=%s)", self._headless)
            browser = playwright.chromium.launch(headless=self._headless)
            try:
                with _new_page(browser) as page:
                    self._perform_submission(page, code)
            finally:
                browser.close()

    def _perform_submission(self, page: Page, code: AttendanceCode) -> None:
        LOGGER.info("Navigating to portal %s", self._portal_url)
        page.goto(self._portal_url)
        page.wait_for_selector(self._code_input_selector, timeout=20_000)
        LOGGER.info("Filling code for %s", code.slot)
        page.fill(self._code_input_selector, code.code)
        page.click(self._submit_button_selector)
        LOGGER.debug("Awaiting success selector: %s", self._success_selector)
        page.wait_for_selector(self._success_selector, timeout=20_000)


@contextmanager
def _new_page(browser: Browser):
    context = browser.new_context()
    page = context.new_page()
    try:
        yield page
    finally:
        page.close()
        context.close()
