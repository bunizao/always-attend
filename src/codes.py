"""Domain objects and data sources for attendance codes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class AttendanceCode:
    """Value object representing a single attendance code entry."""

    slot: str
    code: str


class LocalJsonCodeSource:
    """Load the first available attendance code from a local JSON file."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def next_code(self) -> AttendanceCode:
        entries = list(self._load_entries())
        if not entries:
            raise ValueError(f"No attendance codes found in {self._path}")
        entry = entries[0]
        try:
            slot = entry["slot"]
            code = entry["code"]
        except KeyError as exc:
            raise ValueError(f"Attendance entry missing field: {exc.args[0]}") from exc
        if not slot or not code:
            raise ValueError("Attendance entry must include non-empty 'slot' and 'code'")
        return AttendanceCode(slot=str(slot), code=str(code))

    def _load_entries(self) -> Iterable[dict[str, Any]]:
        data = self._path.read_text(encoding="utf-8")
        payload = json.loads(data)
        if isinstance(payload, dict):
            # Support single-entry dict payloads for convenience during prototyping.
            payload = [payload]
        if not isinstance(payload, list):
            raise ValueError("Attendance JSON must be a list of entries")
        for entry in payload:
            if not isinstance(entry, dict):
                raise ValueError("Attendance entry must be an object with 'slot' and 'code'")

            yield entry
