"""Workflow orchestration for the MVP single submission path."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Protocol

from .codes import AttendanceCode


class CodeSource(Protocol):
    """Provide attendance codes for submission."""

    def next_code(self) -> AttendanceCode:
        """Return the next code to submit."""


class SubmissionNavigator(Protocol):
    """Abstract navigation layer that knows how to submit a code."""

    def submit_code(self, code: AttendanceCode) -> None:
        """Drive the browser to submit the provided attendance code."""


@dataclass(frozen=True)
class SubmissionResult:
    """Capture the outcome of a submission run."""

    code: AttendanceCode
    elapsed_seconds: float


class SingleSubmissionRunner:
    """Coordinate fetching the next code and handing it to the navigator."""

    def __init__(
        self,
        code_source: CodeSource,
        navigator: SubmissionNavigator,
        logger: logging.Logger | None = None,
        timer: Callable[[], float] = perf_counter,
    ) -> None:
        self._code_source = code_source
        self._navigator = navigator
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._timer = timer

    def run(self) -> SubmissionResult:
        start = self._timer()
        code = self._code_source.next_code()
        self._navigator.submit_code(code)
        elapsed = self._timer() - start
        self._logger.info(
            "Submitted code %s for %s successfully (elapsed %.2fs)",
            code.code,
            code.slot,
            elapsed,
        )
        return SubmissionResult(code=code, elapsed_seconds=elapsed)
