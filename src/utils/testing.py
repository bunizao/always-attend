"""Testing utilities for Always Attend."""

from __future__ import annotations

import os
import urllib.request
import urllib.error

from utils.logger import logger

DEFAULT_RESET_URL = "http://127.0.0.1:8081/mock/reset"


def reset_mock_backend(url: str | None = None) -> None:
    """POST to the mock backend reset endpoint (best effort)."""
    target = url or os.getenv("MOCK_RESET_URL", DEFAULT_RESET_URL)
    if not target:
        return

    req = urllib.request.Request(target, method="POST", data=b"")
    try:
        with urllib.request.urlopen(req, timeout=3):
            logger.debug("Mock backend reset via %s", target)
    except urllib.error.HTTPError as exc:
        logger.debug("Mock reset http error %s: %s", exc.code, exc.reason)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Mock reset failed: %s", exc)
