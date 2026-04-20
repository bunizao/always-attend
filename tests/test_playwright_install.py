"""Tests for Playwright browser installation helpers."""

from __future__ import annotations

import os
import subprocess
import unittest
from unittest.mock import patch

from utils.playwright_install import ensure_playwright_chromium_installed


class PlaywrightInstallTests(unittest.TestCase):
    def test_install_uses_captured_output_to_keep_stdout_clean(self) -> None:
        with patch.dict(os.environ, {}, clear=False), patch(
            "utils.playwright_install.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-m", "playwright", "install", "chromium"],
                returncode=0,
                stdout="downloaded",
                stderr="notice",
            ),
        ) as mock_run:
            installed = ensure_playwright_chromium_installed()

        self.assertTrue(installed)
        mock_run.assert_called_once_with(
            [unittest.mock.ANY, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_install_returns_false_when_download_fails(self) -> None:
        with patch.dict(os.environ, {}, clear=False), patch(
            "utils.playwright_install.subprocess.run",
            side_effect=subprocess.CalledProcessError(
                1,
                ["python", "-m", "playwright", "install", "chromium"],
                output="",
                stderr="network failure",
            ),
        ):
            installed = ensure_playwright_chromium_installed()

        self.assertFalse(installed)


if __name__ == "__main__":
    unittest.main()
