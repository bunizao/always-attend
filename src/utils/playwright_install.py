"""Helpers for installing Playwright browser assets on demand."""

from __future__ import annotations

import os
import subprocess
import sys

from utils.logger import logger


_INSTALL_ATTEMPT_ENV = "ALWAYS_ATTEND_PLAYWRIGHT_INSTALL_ATTEMPTED"


def ensure_playwright_chromium_installed() -> bool:
    """Install Playwright Chromium once per process when it is missing."""
    attempted = os.getenv(_INSTALL_ATTEMPT_ENV)
    if attempted in {"1", "true", "True"}:
        return False

    os.environ[_INSTALL_ATTEMPT_ENV] = "1"
    logger.info("Playwright Chromium is unavailable. Attempting automatic download...")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )
    except Exception as exc:
        logger.warning(f"Automatic Chromium download failed: {exc}")
        return False

    logger.info("Playwright Chromium download completed.")
    return True
