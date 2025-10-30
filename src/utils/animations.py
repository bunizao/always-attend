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
src/utils/animations.py
Animation utilities for the Always Attend CLI interface.
"""

import os
import sys
import time
import shutil
import random
from typing import Optional, List
from rich.console import Console
from rich.text import Text
from rich.live import Live

__all__ = ["TypewriterBanner", "AnimationConfig"]


class AnimationConfig:
    """Configuration for CLI animations."""

    def __init__(self):
        # Read explicit animation preference; defaults to 'on' for richer UX
        raw_mode = os.getenv("CLI_ANIMATIONS", "on").strip().lower()
        mode = raw_mode if raw_mode in {"on", "off", "auto"} else "on"

        force_enable = os.getenv("FORCE_ANIMATIONS", "false").lower() == "true"
        no_color = bool(os.getenv("NO_COLOR"))
        stdout_is_tty = sys.stdout.isatty()

        if mode == "off" or no_color:
            self.enabled = False
        elif force_enable:
            self.enabled = True
        elif mode == "auto":
            self.enabled = stdout_is_tty
        else:  # mode == "on"
            self.enabled = stdout_is_tty

        speed_raw = os.getenv("ANIMATION_SPEED", "normal").strip().lower()
        allowed_speeds = {"fast", "normal", "slow", "instant"}
        self._custom_char_delay: Optional[float] = None
        self._custom_line_delay: Optional[float] = None

        if speed_raw in allowed_speeds:
            self.speed = speed_raw
        else:
            try:
                numeric_speed = max(float(speed_raw), 0.0)
            except ValueError:
                numeric_speed = None
            if numeric_speed is not None:
                self.speed = "custom"
                self._custom_char_delay = numeric_speed
                self._custom_line_delay = numeric_speed * 3
            else:
                self.speed = "normal"

        line_override = os.getenv("ANIMATION_LINE_DELAY")
        if line_override:
            try:
                self._custom_line_delay = max(float(line_override), 0.0)
            except ValueError:
                pass

        self.style = os.getenv("CLI_STYLE", "fancy")  # fancy, simple, minimal
        self._mode = mode
        self._stdout_is_tty = stdout_is_tty
        self._no_color = no_color
        if os.getenv("CLI_ANIMATIONS_DEBUG") == "1":
            status = "enabled" if self.enabled else "disabled"
            print(
                f"[animations] {status} (mode={self._mode}, style={self.style}, "
                f"tty={self._stdout_is_tty}, no_color={self._no_color})",
                file=sys.stderr,
                flush=True,
            )

    @property
    def char_delay(self) -> float:
        """Get character delay based on animation speed."""
        if not self.enabled or self.style == "minimal":
            return 0.0

        if self._custom_char_delay is not None:
            return self._custom_char_delay

        speed_map = {
            "fast": 0.001,
            "normal": 0.004,
            "slow": 0.012,
            "instant": 0.0,
        }
        return speed_map.get(self.speed, speed_map["normal"])

    @property
    def line_delay(self) -> float:
        """Get line delay based on animation speed."""
        if not self.enabled or self.style == "minimal":
            return 0.0

        if self._custom_line_delay is not None:
            return self._custom_line_delay

        speed_map = {
            "fast": 0.003,
            "normal": 0.02,
            "slow": 0.06,
            "instant": 0.0,
        }
        return speed_map.get(self.speed, speed_map["normal"])


class TypewriterBanner:
    """Typewriter effect for ASCII art banners."""

    _BANNER = r"""
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
"""

    def __init__(self, config: Optional[AnimationConfig] = None):
        self.config = config or AnimationConfig()
        self.console = Console()
        self.width = max(68, min(self._detect_width(), 120))
        self._sparks_enabled = self.config.enabled and self.config.style == "fancy"
        self._spark_probability = 0.18
        self._spark_colors = ("gold1", "light_goldenrod1", "khaki1")

    def _detect_width(self) -> int:
        return shutil.get_terminal_size((100, 20)).columns

    def _center_text(self, text: str) -> str:
        """Center text based on terminal width."""
        stripped = text.rstrip()
        pad_total = max(self.width - len(stripped), 0)
        left = pad_total // 2
        return " " * left + stripped

    def _create_gradient_style(self, char_index: int, total_chars: int) -> str:
        """Create a gradient color effect for characters."""
        # Define gradient from cyan to blue to monash blue
        progress = char_index / max(total_chars, 1)

        if progress < 0.33:
            # Cyan phase
            return "cyan"
        elif progress < 0.66:
            # Blue phase
            return "blue"
        else:
            # Monash blue phase
            return "#0053a0"  # Monash blue RGB

    def _compose_display(self, lines: List[Text]) -> Text:
        """Compose banner lines into a single renderable."""
        if not lines:
            return Text("", no_wrap=True)

        block = Text(no_wrap=True)
        for idx, line in enumerate(lines):
            block.append_text(line.copy())
            if idx != len(lines) - 1:
                block.append("\n")
        return block

    def _select_spark_index(self, line: Text) -> Optional[int]:
        """Select a character index near the edges for spark highlighting."""
        plain = line.plain
        indices = [idx for idx, ch in enumerate(plain) if ch.strip()]
        if not indices:
            return None
        return random.choice([indices[0], indices[-1]])

    def _typewrite_line(self, line: str, live: Live, current_display: List[Text], line_index: int) -> None:
        """Stream a single banner line with optional spark highlights."""
        centered_line = self._center_text(line)
        total_visible = sum(1 for ch in centered_line if ch.strip())
        if len(current_display) <= line_index:
            current_display.append(Text(no_wrap=True))

        base_line = Text(no_wrap=True)
        visible_count = 0

        for char in centered_line:
            if char.strip():
                visible_count += 1
                style = self._create_gradient_style(visible_count, total_visible)
                base_line.append(char, style=style)
                delay = self.config.char_delay
            else:
                base_line.append(char)
                delay = 0.0

            display_line = base_line.copy()

            if (
                self._sparks_enabled
                and visible_count > 0
                and self.config.char_delay > 0.0
                and random.random() <= self._spark_probability
            ):
                spark_index = self._select_spark_index(display_line)
                if spark_index is not None:
                    display_line.stylize(random.choice(self._spark_colors), spark_index, spark_index + 1)

            current_display[line_index] = display_line
            live.update(self._compose_display(current_display))

            if delay:
                time.sleep(delay)

        current_display[line_index] = base_line
        live.update(self._compose_display(current_display))

        if line_index < len(self._get_banner_lines()) - 1 and self.config.line_delay:
            time.sleep(self.config.line_delay)

    def _get_banner_lines(self) -> List[str]:
        """Get banner lines, filtering out empty ones."""
        return [line for line in self._BANNER.strip().splitlines() if line.strip()]

    def display(self, subtitle: Optional[str] = None) -> None:
        """Display banner with typewriter effect."""
        if not self.config.enabled:
            # Fall back to simple display
            self._display_simple(subtitle)
            return

        if self.console.is_terminal:
            self.console.clear()

        banner_lines = self._get_banner_lines()
        banner_width = max((len(line.rstrip()) for line in banner_lines), default=60)
        target_width = min(max(banner_width, 1), 120)

        current_width = self.console.size.width
        if not current_width or current_width <= 0:
            current_width = shutil.get_terminal_size((target_width, 20)).columns

        if current_width and current_width < target_width:
            self.width = current_width
        else:
            self.width = target_width
        self.width = max(1, int(self.width))

        current_display: List[Text] = []

        with Live(self._compose_display(current_display), console=self.console, refresh_per_second=60, transient=False) as live:
            for index, banner_line in enumerate(banner_lines):
                self._typewrite_line(banner_line, live, current_display, index)

        # Add subtitle if provided
        if subtitle:
            rule_line = self._create_rule(subtitle)
            centered_rule = self._center_text(rule_line)
            self.console.print()
            self.console.print(centered_rule)

    def _display_simple(self, subtitle: Optional[str] = None) -> None:
        """Simple fallback display without animation."""
        banner_lines = self._get_banner_lines()

        for line in banner_lines:
            centered = self._center_text(line)
            styled_text = Text(centered, style="#0053a0", no_wrap=True)  # Monash blue
            self.console.print(styled_text)

        if subtitle:
            rule_line = self._create_rule(subtitle)
            self.console.print("")
            self.console.print(rule_line)

    def _create_rule(self, subtitle: str) -> str:
        """Create a rule line with subtitle."""
        label_text = f" {subtitle} "
        pad_total = max(self.width - len(label_text), 0)
        left = pad_total // 2
        right = pad_total - left
        rule_line = f"{'═' * left}{label_text}{'═' * right}"
        return rule_line[:self.width]


def create_typewriter_banner(subtitle: Optional[str] = None, config: Optional[AnimationConfig] = None) -> None:
    """Convenience function to create and display a typewriter banner."""
    banner = TypewriterBanner(config)
    banner.display(subtitle)


# Compatibility with existing animation in console.py
def play_loading_animation(text: str = "ALWAYS ATTEND", accent: str = "cyan") -> None:
    """Simple loading animation for compatibility."""
    config = AnimationConfig()
    if not config.enabled:
        return

    console = Console()
    frames = ["   ", "•  ", "•• ", "•••", "•• ", "•  "]

    for frame in frames:
        display_text = f"{text} {frame}"
        width = shutil.get_terminal_size((100, 20)).columns
        pad_total = max(width - len(display_text), 0)
        left = pad_total // 2
        centered = " " * left + display_text

        console.print(centered, style=f"{accent} bold", end="\r")
        time.sleep(0.08)

    # Clear the line
    console.print(" " * width, end="\r")
