"""Simple progress tracking for legacy submission flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from utils.logger import progress as log_progress


@dataclass
class TaskInfo:
    """Information about a task to be processed."""

    course: str
    slot: str
    total_codes: int
    current_attempt: int = 0
    success: bool = False
    success_code: Optional[str] = None
    status: str = ""


class SimpleProgressTracker:
    """Plain-text progress tracker focused on stable output."""

    def __init__(self) -> None:
        self.tasks: List[TaskInfo] = []
        self.active_task_index = 0
        self._last_line: str | None = None

    def print_task_list(self, tasks: List[TaskInfo]) -> None:
        """Print the list of tasks to be processed."""
        self.tasks = tasks
        if not tasks:
            return
        for index, task in enumerate(tasks, start=1):
            log_progress(
                "Task {}: {} {} ({} codes)".format(
                    index, task.course, task.slot, task.total_codes
                )
            )

    def start_task(self, task_index: int) -> None:
        """Start processing a specific task."""
        if task_index >= len(self.tasks):
            return
        self.active_task_index = task_index
        task = self.tasks[task_index]
        task.current_attempt = 0
        task.success = False
        task.success_code = None
        task.status = ""
        self._emit_progress(task, 0, force=True)

    def update_task_progress(self, attempt_number: int) -> None:
        """Update the current task progress."""
        if self.active_task_index >= len(self.tasks):
            return
        task = self.tasks[self.active_task_index]
        task.current_attempt = attempt_number
        self._emit_progress(task, attempt_number)

    def complete_task(self, success: bool, success_code: Optional[str] = None) -> None:
        """Complete the current task."""
        if self.active_task_index >= len(self.tasks):
            return
        task = self.tasks[self.active_task_index]
        task.success = success
        task.success_code = success_code
        final_attempt = task.total_codes if success else task.current_attempt
        self._emit_progress(task, final_attempt, force=True)
        if success:
            log_progress(
                "Completed {} {} with {}".format(
                    task.course, task.slot, success_code or "N/A"
                )
            )
        else:
            log_progress(
                "Failed {} {} after {} attempts".format(
                    task.course, task.slot, task.current_attempt
                )
            )

    def stop(self) -> None:
        """Compatibility hook for callers that stop tracking explicitly."""

    def update_status(self, status: str) -> None:
        """Update the status message for the current task."""
        if self.active_task_index >= len(self.tasks):
            return
        task = self.tasks[self.active_task_index]
        task.status = status
        self._emit_progress(task, task.current_attempt, force=True)

    def _emit_progress(self, task: TaskInfo, current: int, *, force: bool = False) -> None:
        total = max(task.total_codes, 1)
        clamped = max(0, min(current, total))
        line = "{} {}/{} {} {}".format(
            task.course,
            clamped,
            total,
            task.slot,
            f"- {task.status}" if task.status else "",
        ).rstrip()
        if force or line != self._last_line:
            log_progress(line)
            self._last_line = line


def create_task_list_from_targets(targets, slot_code_map, ordered_codes) -> List[TaskInfo]:
    """Create a task list from submission targets."""
    from core.submit import _build_candidate_codes

    tasks = []
    used_codes = set()

    for target in targets:
        candidate_codes = _build_candidate_codes(
            target.slot_norm,
            slot_code_map,
            ordered_codes,
            used_codes,
        )
        if candidate_codes:
            tasks.append(
                TaskInfo(
                    course=target.course_code,
                    slot=target.slot_label,
                    total_codes=len(candidate_codes),
                )
            )
    return tasks


class ProgressTracker(SimpleProgressTracker):
    """Compatibility wrapper for legacy submit flows."""

    def __init__(self) -> None:
        super().__init__()
        self._current_task: TaskInfo | None = None

    def start_overall_progress(self, total_courses: int) -> None:
        _ = total_courses

    def start_course_progress(self, course: str, total_submissions: int) -> None:
        _ = (course, total_submissions)

    def start_code_progress(self, course: str, slot: str, total_attempts: int) -> None:
        task = TaskInfo(course=course, slot=slot, total_codes=total_attempts)
        self._current_task = task
        self.tasks = [task]
        self.start_task(0)

    def update_code_progress(self, advance: int = 1) -> None:
        if self._current_task is None:
            return
        self._current_task.current_attempt = advance
        self.update_task_progress(advance)

    def complete_code_progress(self, success: bool, code: Optional[str] = None) -> None:
        self.complete_task(success, code)
        self._current_task = None

    def update_course_progress(self, advance: int = 1) -> None:
        _ = advance

    def complete_course_progress(self, course: str, submitted: int, total: int) -> None:
        _ = (course, submitted, total)

    def update_overall_progress(self, advance: int = 1) -> None:
        _ = advance
