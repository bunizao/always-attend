"""External source adapters for agent-driven data collection."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any


class SourceCommandError(RuntimeError):
    """Raised when a source command fails or is unavailable."""


@dataclass(frozen=True)
class SourceRequest:
    """Normalized fetch request for an external source."""

    source: str
    kind: str = "auto"
    course: str | None = None
    week: int | None = None
    limit: int | None = None
    exec_args: list[str] = field(default_factory=list)


def _find_executable(candidates: tuple[str, ...]) -> str:
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise SourceCommandError(f"Executable not found. Tried: {', '.join(candidates)}")


def _run_json_command(command: list[str]) -> Any:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "source command failed").strip()
        raise SourceCommandError(message)

    stdout = (result.stdout or "").strip()
    if not stdout:
        return {}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SourceCommandError(f"Invalid JSON from source command: {exc}") from exc


def _extract_course_code(value: str) -> str | None:
    match = re.search(r"\b[A-Z]{3}\d{4}\b", value.upper())
    if match:
        return match.group(0)
    return None


class EdstemAdapter:
    """Typed adapter for the installed `edstem` CLI."""

    executable_names = ("edstem",)

    def fetch(self, request: SourceRequest) -> dict[str, Any]:
        executable = _find_executable(self.executable_names)
        kind = request.kind.lower()

        if kind in {"auto", "courses"} and not request.course:
            command = [executable, "courses", "--json"]
            payload = _run_json_command(command)
            return {
                "source": "edstem",
                "kind": "courses",
                "command": command,
                "payload": payload,
            }

        course_payload = _run_json_command([executable, "courses", "--json"])
        course_id = self._match_course_id(course_payload, request.course)
        if course_id is None:
            raise SourceCommandError(f"Unable to find Edstem course for '{request.course}'.")

        if kind == "lessons":
            command = [executable, "lessons", str(course_id), "--json"]
        else:
            command = [executable, "threads", str(course_id), "--json"]
            if request.limit is not None:
                command.extend(["--max", str(request.limit)])
        command.extend(request.exec_args)

        payload = _run_json_command(command)
        return {
            "source": "edstem",
            "kind": "lessons" if kind == "lessons" else "threads",
            "course": request.course,
            "resolved_course_id": course_id,
            "command": command,
            "payload": payload,
        }

    @staticmethod
    def _match_course_id(course_payload: Any, course: str | None) -> int | None:
        if not course or not isinstance(course_payload, list):
            return None

        target_code = _extract_course_code(course) or course.upper()
        for item in course_payload:
            if not isinstance(item, dict):
                continue
            raw_code = str(item.get("code", ""))
            normalized = _extract_course_code(raw_code) or raw_code.upper()
            if normalized == target_code:
                course_id = item.get("id")
                if isinstance(course_id, int):
                    return course_id
        return None


class GenericJsonCliAdapter:
    """Generic JSON CLI wrapper for sources without typed integration yet."""

    def __init__(self, *, source: str, executable_names: tuple[str, ...]):
        self.source = source
        self.executable_names = executable_names

    def fetch(self, request: SourceRequest) -> dict[str, Any]:
        executable = _find_executable(self.executable_names)
        command = [executable]
        if request.kind not in {"", "auto"}:
            command.append(request.kind)
        if request.exec_args:
            command.extend(request.exec_args)
        else:
            command.append("--json")
        payload = _run_json_command(command)
        return {
            "source": self.source,
            "kind": request.kind,
            "command": command,
            "payload": payload,
        }


def fetch_from_source(request: SourceRequest) -> dict[str, Any]:
    """Dispatch a fetch request to the requested source adapter."""
    source = request.source.lower()
    if source == "edstem":
        return EdstemAdapter().fetch(request)
    if source == "moodle":
        return GenericJsonCliAdapter(
            source="moodle",
            executable_names=("moodle-cli", "moodle"),
        ).fetch(request)
    if source == "gog":
        return GenericJsonCliAdapter(
            source="gog",
            executable_names=("gogcli", "gog"),
        ).fetch(request)
    raise SourceCommandError(f"Unsupported source '{request.source}'.")
