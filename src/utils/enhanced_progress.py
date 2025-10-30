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
src/utils/enhanced_progress.py
Enhanced progress tracking with beautiful animations for Always Attend.
"""

import os
import sys
import time
import asyncio
from typing import Optional, Dict, List, Any, Union
from dataclasses import dataclass, field
from threading import Thread, Event
from contextlib import contextmanager

# Rich imports with fallbacks
try:
    from rich.console import Console
    from rich.progress import (
        Progress, TaskID, BarColumn, TextColumn, TimeRemainingColumn,
        SpinnerColumn, MofNCompleteColumn, TransferSpeedColumn
    )
    from rich.live import Live
    from rich.text import Text
    from rich.align import Align
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.style import Style
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

try:
    from utils.animations import AnimationConfig
    ANIMATIONS_AVAILABLE = True
except ImportError:
    ANIMATIONS_AVAILABLE = False


@dataclass
class ProgressStyle:
    """Configuration for progress bar styling."""

    # Color scheme
    primary_color: str = "#0053a0"  # Monash blue
    secondary_color: str = "#00a3e0"  # Light blue
    success_color: str = "#00c851"  # Green
    warning_color: str = "#ff8800"  # Orange
    error_color: str = "#ff4444"  # Red

    # Progress bar styling
    bar_width: int = 40
    show_percentage: bool = True
    show_time: bool = True
    show_speed: bool = False

    # Animation settings
    pulse_effect: bool = True
    gradient_bars: bool = True
    animated_spinners: bool = True

    # Layout
    compact_mode: bool = False
    show_descriptions: bool = True


class EnhancedSpinner:
    """Enhanced spinner with custom animations."""

    SPINNER_FRAMES = {
        "dots": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "pulse": ["●", "○", "●", "○"],
        "gradient": ["🔵", "🟢", "🟡", "🟠", "🔴", "🟠", "🟡", "🟢"],
        "arrow": ["→", "↘", "↓", "↙", "←", "↖", "↑", "↗"],
        "wave": ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█", "▇", "▆", "▅", "▄", "▃", "▂"],
        "blocks": ["■", "□", "▪", "▫"]
    }

    def __init__(self, style: str = "dots", color: str = "cyan"):
        self.frames = self.SPINNER_FRAMES.get(style, self.SPINNER_FRAMES["dots"])
        self.color = color
        self.current_frame = 0

    def next_frame(self) -> str:
        frame = self.frames[self.current_frame]
        self.current_frame = (self.current_frame + 1) % len(self.frames)
        return frame


class GradientBar:
    """Custom gradient progress bar."""

    def __init__(self, width: int = 40, style: ProgressStyle = None):
        self.width = width
        self.style = style or ProgressStyle()

    def render(self, progress: float, prefix: str = "", suffix: str = "") -> str:
        """Render a gradient progress bar."""
        if not RICH_AVAILABLE:
            return self._fallback_render(progress, prefix, suffix)

        filled_width = int(self.width * progress)

        # Simple enhanced bar (gradient effect would require rich.gradient which isn't available)
        filled = "█" * filled_width
        empty = "░" * (self.width - filled_width)
        return f"{prefix}[{filled}{empty}]{suffix}"

    def _fallback_render(self, progress: float, prefix: str = "", suffix: str = "") -> str:
        """Fallback rendering without Rich."""
        filled_width = int(self.width * progress)
        filled = "█" * filled_width
        empty = "░" * (self.width - filled_width)
        return f"{prefix}[{filled}{empty}]{suffix}"


class EnhancedProgressTracker:
    """Enhanced progress tracker with beautiful animations and effects."""

    def __init__(self, style: Optional[ProgressStyle] = None):
        self.style = style or ProgressStyle()
        self.config = AnimationConfig() if ANIMATIONS_AVAILABLE else None
        self.enabled = RICH_AVAILABLE and (self.config and self.config.enabled if self.config else True)

        # Rich components
        self.console = Console() if RICH_AVAILABLE else None
        self.live = None
        self.progress = None

        # Task tracking
        self.tasks: Dict[str, TaskID] = {}
        self.task_info: Dict[str, Dict[str, Any]] = {}

        # Animation state
        self.spinners: Dict[str, EnhancedSpinner] = {}
        self.animation_thread: Optional[Thread] = None
        self.animation_stop_event = Event()

        # Fallback state for non-Rich environments
        self.fallback_tasks: Dict[str, Dict[str, Any]] = {}

    def start(self) -> None:
        """Start the enhanced progress tracking."""
        if not self.enabled or not RICH_AVAILABLE:
            return

        # Create enhanced progress columns
        columns = []

        # Spinner column with enhanced animation
        columns.append(SpinnerColumn("dots", style=self.style.primary_color))

        # Task description with gradient text
        columns.append(
            TextColumn("[bold]{task.fields[stage]}", style=self.style.primary_color)
        )

        # Enhanced gradient progress bar
        if self.style.gradient_bars:
            bar_column = BarColumn(
                bar_width=self.style.bar_width,
                style=self.style.primary_color,
                complete_style=self.style.success_color,
                finished_style=self.style.success_color,
                pulse_style=self.style.secondary_color if self.style.pulse_effect else None
            )
        else:
            bar_column = BarColumn(
                bar_width=self.style.bar_width,
                style=self.style.primary_color,
                complete_style=self.style.success_color
            )
        columns.append(bar_column)

        # Percentage display
        if self.style.show_percentage:
            columns.append(
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%",
                          style="bold " + self.style.primary_color)
            )

        # Count display
        columns.append(MofNCompleteColumn())

        # Time remaining
        if self.style.show_time:
            columns.append(TimeRemainingColumn())

        # Speed display (if enabled)
        if self.style.show_speed:
            columns.append(TransferSpeedColumn())

        self.progress = Progress(*columns, console=self.console, expand=True)

        # Start live display
        self.live = Live(self.progress, console=self.console, refresh_per_second=10)
        self.live.start()

    def stop(self) -> None:
        """Stop progress tracking and clean up."""
        if self.animation_thread and self.animation_thread.is_alive():
            self.animation_stop_event.set()
            self.animation_thread.join(timeout=1.0)

        if self.live:
            try:
                self.live.stop()
            except Exception:
                pass
            self.live = None

        if self.progress:
            self.progress = None

        self.tasks.clear()
        self.task_info.clear()
        self.spinners.clear()

    def add_task(self,
                 task_id: str,
                 description: str,
                 total: int = 100,
                 stage: str = "Processing") -> str:
        """Add a new task with enhanced styling."""
        if not self.enabled or not self.progress:
            # Fallback for non-Rich environments
            self.fallback_tasks[task_id] = {
                "description": description,
                "total": total,
                "completed": 0,
                "stage": stage
            }
            self._print_fallback_status(task_id)
            return task_id

        # Create spinner for this task
        self.spinners[task_id] = EnhancedSpinner("gradient", self.style.primary_color)

        # Add task to Rich progress
        rich_task_id = self.progress.add_task(
            description,
            total=total,
            stage=stage,
            completed=0
        )

        self.tasks[task_id] = rich_task_id
        self.task_info[task_id] = {
            "description": description,
            "total": total,
            "stage": stage,
            "completed": 0
        }

        return task_id

    def update_task(self,
                   task_id: str,
                   advance: int = 1,
                   description: Optional[str] = None,
                   stage: Optional[str] = None) -> None:
        """Update task progress with enhanced effects."""
        if task_id not in self.tasks and task_id not in self.fallback_tasks:
            return

        if not self.enabled or not self.progress:
            # Fallback update
            if task_id in self.fallback_tasks:
                self.fallback_tasks[task_id]["completed"] += advance
                if description:
                    self.fallback_tasks[task_id]["description"] = description
                if stage:
                    self.fallback_tasks[task_id]["stage"] = stage
                self._print_fallback_status(task_id)
            return

        rich_task_id = self.tasks[task_id]

        # Update task info
        self.task_info[task_id]["completed"] += advance
        if description:
            self.task_info[task_id]["description"] = description
        if stage:
            self.task_info[task_id]["stage"] = stage

        # Update Rich progress
        update_kwargs = {"advance": advance}
        if description:
            update_kwargs["description"] = description
        if stage:
            update_kwargs["stage"] = stage

        self.progress.update(rich_task_id, **update_kwargs)

    def complete_task(self,
                     task_id: str,
                     success: bool = True,
                     message: Optional[str] = None) -> None:
        """Complete a task with success/failure indication."""
        if task_id not in self.tasks and task_id not in self.fallback_tasks:
            return

        if not self.enabled or not self.progress:
            # Fallback completion
            if task_id in self.fallback_tasks:
                task = self.fallback_tasks[task_id]
                status = "✅" if success else "❌"
                final_message = message or ("Completed" if success else "Failed")
                print(f"{status} {task['stage']}: {final_message}")
                del self.fallback_tasks[task_id]
            return

        rich_task_id = self.tasks[task_id]

        # Update final status
        status_icon = "✅" if success else "❌"
        final_description = f"{status_icon} {message or self.task_info[task_id]['description']}"

        # Complete the task
        total = self.task_info[task_id]["total"]
        self.progress.update(
            rich_task_id,
            completed=total,
            description=final_description,
            stage=self.task_info[task_id]["stage"]
        )

        # Clean up
        if task_id in self.spinners:
            del self.spinners[task_id]
        if task_id in self.task_info:
            del self.task_info[task_id]
        # Keep task_id in self.tasks for visual persistence

    def set_task_status(self,
                       task_id: str,
                       status: str,
                       color: Optional[str] = None) -> None:
        """Set a custom status for a task."""
        if not self.enabled or task_id not in self.tasks:
            return

        rich_task_id = self.tasks[task_id]
        status_color = color or self.style.primary_color

        self.progress.update(
            rich_task_id,
            stage=f"[{status_color}]{status}[/]"
        )

    def _print_fallback_status(self, task_id: str) -> None:
        """Print fallback status for non-Rich environments."""
        if task_id not in self.fallback_tasks:
            return

        task = self.fallback_tasks[task_id]
        completed = task["completed"]
        total = task["total"]
        percentage = (completed / max(total, 1)) * 100

        # Simple progress bar for fallback
        bar_width = 20
        filled = int(bar_width * (completed / max(total, 1)))
        bar = "█" * filled + "░" * (bar_width - filled)

        print(f"… {task['stage']}: [{bar}] {percentage:.0f}% ({completed}/{total})", end="\r")

        if completed >= total:
            print()  # New line when complete


@contextmanager
def enhanced_progress(style: Optional[ProgressStyle] = None):
    """Context manager for enhanced progress tracking."""
    tracker = EnhancedProgressTracker(style)
    tracker.start()
    try:
        yield tracker
    finally:
        tracker.stop()


# Convenience functions for common use cases
def create_submit_progress_style() -> ProgressStyle:
    """Create a progress style optimized for submit operations."""
    return ProgressStyle(
        primary_color="#0053a0",  # Monash blue
        secondary_color="#00a3e0",  # Light blue
        success_color="#00c851",   # Green
        warning_color="#ff8800",   # Orange
        error_color="#ff4444",     # Red
        bar_width=35,
        show_percentage=True,
        show_time=True,
        show_speed=False,
        pulse_effect=True,
        gradient_bars=True,
        animated_spinners=True,
        compact_mode=False,
        show_descriptions=True
    )


def create_compact_progress_style() -> ProgressStyle:
    """Create a compact progress style for limited space."""
    return ProgressStyle(
        primary_color="#0053a0",
        bar_width=25,
        show_percentage=True,
        show_time=False,
        show_speed=False,
        pulse_effect=False,
        gradient_bars=False,
        animated_spinners=True,
        compact_mode=True,
        show_descriptions=False
    )


# Legacy compatibility with existing ProgressTracker
class ProgressTracker(EnhancedProgressTracker):
    """Legacy compatibility wrapper."""

    def __init__(self):
        super().__init__(create_submit_progress_style())
        self.main_task = None
        self.course_task = None
        self.code_task = None

    def start_overall_progress(self, total_courses: int) -> None:
        """Start the overall course processing progress."""
        self.start()
        self.main_task = self.add_task(
            "main",
            "Processing courses...",
            total=total_courses,
            stage="▶ Overall Progress"
        )

    def start_course_progress(self, course: str, total_submissions: int) -> None:
        """Start progress for a specific course."""
        self.course_task = self.add_task(
            f"course_{course}",
            f"Processing {course}...",
            total=total_submissions,
            stage=f"● {course}"
        )

    def start_code_progress(self, course: str, slot: str, total_attempts: int) -> None:
        """Start progress for code submission attempts."""
        self.code_task = self.add_task(
            f"code_{course}_{slot}",
            f"Submitting codes for {slot}...",
            total=total_attempts,
            stage=f"▸ {course} {slot}"
        )

    def update_code_progress(self, advance: int = 1) -> None:
        """Update code submission progress."""
        if self.code_task:
            self.update_task(self.code_task, advance=advance)

    def complete_code_progress(self, success: bool, code: Optional[str] = None) -> None:
        """Complete code submission progress."""
        if self.code_task:
            message = f"Code submitted: {code}" if success and code else None
            self.complete_task(self.code_task, success=success, message=message)
            self.code_task = None

    def update_course_progress(self, advance: int = 1) -> None:
        """Update course progress."""
        if self.course_task:
            self.update_task(self.course_task, advance=advance)

    def complete_course_progress(self, course: str, submitted: int, total: int) -> None:
        """Complete course progress."""
        if self.course_task:
            message = f"{course}: {submitted}/{total} codes submitted"
            self.complete_task(self.course_task, success=submitted > 0, message=message)
            self.course_task = None

    def update_overall_progress(self, advance: int = 1) -> None:
        """Update overall progress."""
        if self.main_task:
            self.update_task(self.main_task, advance=advance)