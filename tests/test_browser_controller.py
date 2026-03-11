"""Tests for Playwright browser launch fallbacks."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.browser_controller import BrowserConfig, BrowserController


class BrowserControllerInstallTests(unittest.IsolatedAsyncioTestCase):
    async def test_launch_regular_installs_chromium_after_failure(self) -> None:
        fake_browser = SimpleNamespace(new_context=AsyncMock(return_value=object()))
        browser_type = SimpleNamespace(
            launch=AsyncMock(side_effect=[RuntimeError("missing browser"), fake_browser])
        )
        controller = BrowserController(BrowserConfig(name="chromium"))

        with patch(
            "core.browser_controller.ensure_playwright_chromium_installed",
            return_value=True,
        ) as mock_install:
            await controller._launch_regular(browser_type, launch_headless=True)

        self.assertIs(controller.browser, fake_browser)
        self.assertIsNotNone(controller.context)
        mock_install.assert_called_once_with()

    async def test_launch_persistent_installs_chromium_after_failure(self) -> None:
        browser_type = SimpleNamespace(
            launch_persistent_context=AsyncMock(side_effect=[RuntimeError("missing browser"), object()])
        )
        controller = BrowserController(
            BrowserConfig(name="chromium", user_data_dir="/tmp/always-attend-profile")
        )

        with patch(
            "core.browser_controller.ensure_playwright_chromium_installed",
            return_value=True,
        ) as mock_install:
            await controller._launch_persistent(browser_type, launch_headless=True)

        self.assertIsNotNone(controller.context)
        mock_install.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
