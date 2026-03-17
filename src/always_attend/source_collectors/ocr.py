"""OCR source helper."""

from __future__ import annotations

import shutil

from always_attend.agent_protocol import TraceEvent


def ocr_backend_status() -> tuple[bool, TraceEvent | None]:
    """Return OCR backend availability."""
    if shutil.which("tesseract"):
        return True, None
    return False, TraceEvent(
        stage="doctor",
        code="ocr_missing",
        message="No OCR backend was available. Image parsing will fall back to unresolved results.",
        details={"tried": ["tesseract"]},
    )
