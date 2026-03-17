"""Shared helpers for source collectors."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any

from always_attend.ai_handoff import build_source_artifact
from always_attend.agent_protocol import SourceArtifact
from always_attend.agent_protocol import TraceEvent


COURSE_RE = re.compile(r"\b[A-Z]{3}\d{4}\b")


def find_executable(candidates: tuple[str, ...]) -> str | None:
    """Return the first available executable path."""
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def run_json_command(command: list[str], *, env: dict[str, str] | None = None) -> tuple[Any | None, TraceEvent | None]:
    """Run a JSON CLI command and normalize failure into a trace event."""
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        return None, TraceEvent(
            stage="collect",
            code="source_command_failed",
            message="Source command failed.",
            details={
                "command": command,
                "stderr": (result.stderr or "").strip(),
                "stdout": (result.stdout or "").strip(),
                "returncode": result.returncode,
            },
        )

    stdout = (result.stdout or "").strip()
    if not stdout:
        return {}, None
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError as exc:
        return None, TraceEvent(
            stage="collect",
            code="invalid_json",
            message="Source command did not return valid JSON.",
            details={
                "command": command,
                "error": str(exc),
            },
        )


def extract_course_code(value: str) -> str | None:
    """Extract a normalized course code from arbitrary text."""
    match = COURSE_RE.search((value or "").upper())
    if match:
        return match.group(0)
    return None


def collect_course_filters(open_courses: set[str], explicit_courses: list[str] | None = None) -> set[str]:
    """Return the final set of course filters for the run."""
    selected = {item.upper() for item in (explicit_courses or []) if item}
    if selected:
        return selected
    return {item.upper() for item in open_courses if item}


def artifact_from_payload(
    *,
    source: str,
    command: list[str],
    payload: Any,
    requested_courses: set[str],
) -> SourceArtifact:
    """Build a handoff artifact from a source payload."""
    return build_source_artifact(
        source=source,
        command=command,
        payload=payload,
        requested_courses=requested_courses,
    )
