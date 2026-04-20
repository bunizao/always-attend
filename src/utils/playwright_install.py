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
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        details = ""
        if isinstance(exc, subprocess.CalledProcessError):
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            details = stderr or stdout
        suffix = f": {details}" if details else f": {exc}"
        logger.warning(f"Automatic Chromium download failed{suffix}")
        return False

    stderr = (result.stderr or "").strip()
    if stderr:
        logger.info(stderr)
    logger.info("Playwright Chromium download completed.")
    return True
