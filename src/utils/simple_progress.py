"""
 █████╗ ██╗     ██╗    ██╗ █████╗ ██╗   ██╗███████╗
██╔══██╗██║     ██║    ██║██╔══██╗╚██╗ ██╔╝██╔════╝
███████║██║     ██║ █╗ ██║███████║ ╚████╔╝ ███████╗
██╔══██║██║     ██║███╗██║██╔══██║  ╚██╔╝  ╚════██║
██║  ██║███████╗╚███╔███╔╝██║  ██║   ██║   ███████║
╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝

 █████╗ ████████╗████████╗███████╗███╗   ██╗██████╗
██╔══██╗╚══██╔══╝╚══██╔══╝██╔════╝████╗  ██║██╔══██╗
███████║   ██║      ██║   █████╗  ██╔██╗ ██║██║  ██║
██╔══██║   ██║      ██║   ██╔══╝  ██║╚██╗██║██║  ██║
██║  ██║   ██║      ██║   ███████╗██║ ╚████║██████╔╝
╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═══╝╚═════╝
src/utils/simple_progress.py
Simple and clean progress tracking for Always Attend.
"""

import os
import sys
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from utils.logger import progress as log_progress

# Try Rich imports for better display
try:
    from rich.console import Console
    from rich.progress import Progress, TaskID, TextColumn, TimeElapsedColumn, ProgressColumn
    from rich.text import Text
    from rich.table import Table, Column, box
    from rich.panel import Panel
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
TaskID = Any  # type: ignore  # Fallback type


if RICH_AVAILABLE:

    class BlockBarColumn(ProgressColumn):
        """Square-filled bar column compatible with Rich caching."""

        def __init__(
            self,
            width: int = 26,
            *,
            border_style: str = "bright_cyan",
            fill_style: str = "cyan",
            finished_style: str = "green",
            empty_style: str = "grey23",
        ) -> None:
            self.width = max(width, 1)
            self.border_style = border_style
            self.fill_style = fill_style
            self.finished_style = finished_style
            self.empty_style = empty_style
            self._table_column = Column(no_wrap=True, justify="left")
            self._renderable_cache: Dict[int, Tuple[float, Text]] = {}

        def get_table_column(self) -> Column:  # type: ignore[override]
            return self._table_column

        def render(self, task) -> Text:  # type: ignore[override]
            bar_width = self.width
            if task.total in (0, None) or task.total == 0:
                ratio = 0.0
            else:
                ratio = min(max(task.completed / task.total, 0.0), 1.0)

            filled = int(bar_width * ratio)
            empty = bar_width - filled

            text = Text("▐", style=self.border_style)
            if filled:
                style = self.finished_style if task.finished else self.fill_style
                text.append("█" * filled, style=style)
            if empty:
                text.append("░" * empty, style=self.empty_style)
            text.append("▌", style=self.border_style)
            return text

    class AsciiSpinnerColumn(ProgressColumn):
        """ASCII spinner column that plays nicely with Rich caching."""

        def __init__(self, frames: Optional[List[str]] = None, style: str = "bright_magenta") -> None:
            self.frames = frames or ["-", "\\", "|", "/"]
            self.style = style
            self._frame_state: Dict[int, int] = {}
            self._table_column = Column(no_wrap=True, justify="left")
            self._renderable_cache: Dict[int, Tuple[float, Text]] = {}

        def get_table_column(self) -> Column:  # type: ignore[override]
            return self._table_column

        def render(self, task) -> Text:  # type: ignore[override]
            if task.finished:
                return Text("✓", style="green")

            index = self._frame_state.get(task.id, 0)
            frame = self.frames[index % len(self.frames)]
            self._frame_state[task.id] = index + 1
            return Text(frame, style=self.style)


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
    """Simple, clean progress tracker focused on clarity and UX."""

    def __init__(self):
        self.console = Console() if RICH_AVAILABLE else None
        rich_flag = os.getenv("CLI_PROGRESS_RICH")
        self.use_rich = (
            bool(self.console)
            and sys.stdout.isatty()
            and (rich_flag is None or rich_flag.lower() not in {"0", "false"})
        )
        self.tasks: List[TaskInfo] = []
        self.active_task_index: int = 0
        self.progress = None
        self.progress_task_id: Optional[TaskID] = None
        self._last_progress: Dict[str, int] = {}
        self.bar_width = 26

    def print_task_list(self, tasks: List[TaskInfo]) -> None:
        """Print the list of tasks to be processed."""
        self.tasks = tasks

        if not tasks:
            return

        if self.use_rich and self.console:
            table = Table(
                Column(header="#", justify="right", style="bright_cyan"),
                Column(header="Course", style="bold white"),
                Column(header="Slot", style="cyan"),
                Column(header="Codes", justify="center", style="magenta"),
                box=box.ROUNDED,
                expand=False,
            )
            for i, task in enumerate(tasks, 1):
                table.add_row(
                    f"{i}",
                    task.course,
                    task.slot,
                    f"{task.total_codes}",
                )
            panel = Panel(
                table,
                title="📋 Tasks to Process",
                border_style="bright_cyan",
            )
            self.console.print(panel)
        else:
            print("\n📋 Tasks to Process:")
            print("=" * 50)

            for i, task in enumerate(tasks, 1):
                print(f"{i:2d}. {task.course} {task.slot} ({task.total_codes} codes to try)")

            print("=" * 50)
            print()
            sys.stdout.flush()

    def start_task(self, task_index: int) -> None:
        """Start processing a specific task."""
        if task_index >= len(self.tasks):
            return

        self.active_task_index = task_index
        task = self.tasks[task_index]

        # Reset task state
        task.current_attempt = 0
        task.success = False
        task.success_code = None
        task.status = ""

        if self.progress:
            try:
                self.progress.stop()
            except Exception:
                pass
            self.progress = None
            self.progress_task_id = None

        if self.use_rich and self.console:
            bar_column = BlockBarColumn(
                width=self.bar_width,
                border_style="bright_cyan",
                fill_style="cyan",
                finished_style="green",
                empty_style="grey30",
            )

            self.progress = Progress(
                AsciiSpinnerColumn(),
                TextColumn("[bold bright_cyan]{task.fields[name]}"),
                bar_column,
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("[dim]{task.completed}/{task.total}[/]"),
                TextColumn("[dim]{task.fields[status]}[/]"),
                TimeElapsedColumn(),
                console=self.console,
                expand=True,
                transient=True,
            )

            self.progress.start()
            self.progress_task_id = self.progress.add_task(
                f"{task.course} {task.slot}",
                total=max(task.total_codes, 1),
                completed=0,
                name=f"{task.course} {task.slot}",
                status="",
            )
        else:
            key = self._task_key(task)
            self._last_progress[key] = -1
            log_progress(self._format_progress_line(task, 0))

    def update_task_progress(self, attempt_number: int) -> None:
        """Update the current task's progress."""
        if self.active_task_index >= len(self.tasks):
            return

        task = self.tasks[self.active_task_index]
        task.current_attempt = attempt_number

        if self.use_rich and self.progress and self.progress_task_id is not None:
            # Update Rich progress bar
            self.progress.update(
                self.progress_task_id,
                completed=min(attempt_number, max(task.total_codes, 1)),
                description=(
                    f"[cyan]{task.course}[/] {task.slot} • trying {attempt_number}/{task.total_codes}"
                ),
                status=task.status,
            )
        else:
            key = self._task_key(task)
            current = min(attempt_number, task.total_codes)
            if self._last_progress.get(key) != current:
                log_progress(self._format_progress_line(task, current))
                self._last_progress[key] = current

    def complete_task(self, success: bool, success_code: Optional[str] = None) -> None:
        """Complete the current task."""
        if self.active_task_index >= len(self.tasks):
            return

        task = self.tasks[self.active_task_index]
        task.success = success
        task.success_code = success_code

        if self.use_rich and self.progress and self.progress_task_id is not None:
            final_total = max(task.total_codes, 1)
            final_completed = final_total if success else min(task.current_attempt, final_total)
            description = (
                f"[bold green]✓[/] {task.course} {task.slot} • {success_code or 'N/A'}"
                if success
                else f"[bold red]✗[/] {task.course} {task.slot} • {task.current_attempt} attempts"
            )

            self.progress.update(
                self.progress_task_id,
                completed=final_completed,
                description=description,
                status=task.status,
            )
            self.progress.stop()
            self.progress = None
            self.progress_task_id = None

            if self.console:
                if success:
                    body = f"[bold green]✅ {task.course} {task.slot}[/]\n[cyan]{success_code or 'N/A'}[/]"
                    border = "bright_cyan"
                else:
                    body = f"[bold red]❌ {task.course} {task.slot}[/]\nFailed after {task.current_attempt} attempts"
                    border = "red"
                self.console.print(Panel.fit(body, border_style=border, padding=(0, 2)))
                self.console.print()
        else:
            final_count = task.total_codes if success else task.current_attempt
            key = self._task_key(task)
            if self._last_progress.get(key) != min(final_count, task.total_codes or 1):
                log_progress(self._format_progress_line(task, final_count))
                self._last_progress[key] = min(final_count, task.total_codes or 1)
            status = "✅" if success else "❌"
            detail = success_code or "N/A" if success else f"Failed after {task.current_attempt} attempts"
            log_progress(f"  {status} {task.course} {task.slot} • {detail}")

    def stop(self) -> None:
        """Stop progress tracking and clean up."""
        if self.use_rich and self.progress:
            try:
                self.progress.stop()
            except Exception:
                pass
            self.progress = None
            self.progress_task_id = None

    def update_status(self, status: str) -> None:
        """Update the status message for the current task."""
        if self.active_task_index >= len(self.tasks):
            return
        task = self.tasks[self.active_task_index]
        task.status = status
        if self.use_rich and self.progress and self.progress_task_id is not None:
            self.progress.update(self.progress_task_id, status=status)
        else:
            key = self._task_key(task)
            log_progress(self._format_progress_line(task, task.current_attempt))

    def _task_key(self, task: TaskInfo) -> str:
        return f"{task.course}|{task.slot}"

    def _block_bar(self, current: int, total: int) -> str:
        total = max(total, 1)
        current = max(0, min(current, total))
        ratio = current / total
        filled = int(self.bar_width * ratio)
        empty = self.bar_width - filled
        return f"▐{'█' * filled}{'░' * empty}▌"

    def _format_progress_line(self, task: TaskInfo, current: int) -> str:
        total = max(task.total_codes, 1)
        current_clamped = max(0, min(current, total))
        bar = self._block_bar(current_clamped, total)
        percentage = int((current_clamped / total) * 100)
        return (
            f"… {bar} {percentage:>3}% "
            f"({current_clamped}/{total}) "
            f"{task.course} {task.slot}"
            + (f" • {task.status}" if task.status else "")
        )

# Convenience function to create task list from targets
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
            used_codes
        )

        if candidate_codes:
            tasks.append(TaskInfo(
                course=target.course_code,
                slot=target.slot_label,
                total_codes=len(candidate_codes)
            ))

    return tasks


# Legacy compatibility wrapper for existing code
class ProgressTracker(SimpleProgressTracker):
    """Legacy compatibility wrapper that maps to new simple tracker."""

    def __init__(self):
        super().__init__()
        self._task_map = {}  # Map task IDs to indices

    def start_overall_progress(self, total_courses: int) -> None:
        """Legacy method - now does nothing since we removed overall progress."""
        pass  # Removed as requested

    def start_course_progress(self, course: str, total_submissions: int) -> None:
        """Legacy method - handled by individual task tracking."""
        pass  # Course level progress integrated into task level

    def start_code_progress(self, course: str, slot: str, total_attempts: int) -> None:
        """Start progress for code submission attempts."""
        # Find or create task
        task_key = f"{course}_{slot}"

        # Create task if it doesn't exist
        if not hasattr(self, '_current_tasks'):
            self._current_tasks = {}

        if task_key not in self._current_tasks:
            task = TaskInfo(course=course, slot=slot, total_codes=total_attempts)
            self._current_tasks[task_key] = task
            self.tasks = [task]
            self.start_task(0)

    def update_code_progress(self, advance: int = 1) -> None:
        """Update code submission progress."""
        if hasattr(self, '_current_tasks') and self._current_tasks:
            # Get current task
            for task in self._current_tasks.values():
                task.current_attempt = advance
                self.update_task_progress(task.current_attempt)
                break

    def complete_code_progress(self, success: bool, code: Optional[str] = None) -> None:
        """Complete code submission progress."""
        self.complete_task(success, code)

    def update_course_progress(self, advance: int = 1) -> None:
        """Legacy method - now does nothing."""
        pass

    def complete_course_progress(self, course: str, submitted: int, total: int) -> None:
        """Legacy method - now does nothing."""
        pass

    def update_overall_progress(self, advance: int = 1) -> None:
        """Legacy method - now does nothing since overall progress removed."""
        pass
