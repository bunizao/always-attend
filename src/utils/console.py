#!/usr/bin/env python3
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
src/utils/console.py
Console rendering utilities for the Always Attend CLI.
"""
from __future__ import annotations

import os
import shutil
import sys
import textwrap
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

# Import animation utilities
try:
    from .animations import TypewriterBanner, AnimationConfig
    ANIMATIONS_AVAILABLE = True
except ImportError:
    ANIMATIONS_AVAILABLE = False

__all__ = ["PortalConsole", "ConsolePalette"]

@dataclass
class ConsolePalette:
    """Simple ANSI-aware palette used by PortalConsole."""

    reset: str = "\033[0m"
    bold: str = "\033[1m"
    dim: str = "\033[2m"
    cyan: str = "\033[36m"
    blue: str = "\033[34m"
    magenta: str = "\033[35m"
    green: str = "\033[32m"
    yellow: str = "\033[33m"
    red: str = "\033[31m"
    white: str = "\033[97m"
    monash: str = "\033[38;2;0;83;159m"

    @property
    def disabled(self) -> bool:
        return bool(os.getenv("NO_COLOR"))

    def apply(self, text: str, *styles: str) -> str:
        if self.disabled or not styles:
            return text
        return f"{''.join(styles)}{text}{self.reset}"

class PortalConsole:
    """Coordinated helper for rendering a friendly CLI front-end."""

    _BANNER = [
        " █████╗ ██╗     ██╗    ██╗ █████╗ ██╗   ██╗███████╗",
        "██╔══██╗██║     ██║    ██║██╔══██╗╚██╗ ██╔╝██╔════╝",
        "███████║██║     ██║ █╗ ██║███████║ ╚████╔╝ ███████╗",
        "██╔══██║██║     ██║███╗██║██╔══██║  ╚██╔╝  ╚════██║",
        "██║  ██║███████╗╚███╔███╔╝██║  ██║   ██║   ███████║",
        "╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝",
        "",
        " █████╗ ████████╗████████╗███████╗███╗   ██╗██████╗ ",
        "██╔══██╗╚══██╔══╝╚══██╔══╝██╔════╝████╗  ██║██╔══██╗",
        "███████║   ██║      ██║   █████╗  ██╔██╗ ██║██║  ██║",
        "██╔══██║   ██║      ██║   ██╔══╝  ██║╚██╗██║██║  ██║",
        "██║  ██║   ██║      ██║   ███████╗██║ ╚████║██████╔╝",
        "╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═══╝╚═════╝"
    ]

    _GRADIENT_COLORS = [
        "\033[38;2;147;51;234m",  # Rich purple
        "\033[38;2;168;85;247m",  # Bright purple
        "\033[38;2;192;132;252m", # Light purple
        "\033[38;2;216;180;254m", # Pale purple
        "\033[38;2;196;165;255m", # Light lavender
        "\033[38;2;183;148;244m", # Medium lavender
        "\033[38;2;167;139;250m", # Purple-blue
        "\033[38;2;139;92;246m",  # Deep purple-blue
        "\033[38;2;124;58;237m",  # Indigo
        "\033[38;2;99;102;241m",  # Blue-indigo
        "\033[38;2;79;70;229m",   # Deep blue
        "\033[38;2;67;56;202m",   # Royal blue
        "\033[38;2;55;48;163m"    # Dark blue
    ]

    def __init__(self) -> None:
        self.palette = ConsolePalette()
        self.width = max(68, min(self._detect_width(), 120))
        self.is_tty = sys.stdout.isatty()

    def _detect_width(self) -> int:
        return shutil.get_terminal_size((100, 20)).columns

    def _wrap(self, text: str, *, indent: int = 0) -> str:
        wrapper = textwrap.TextWrapper(
            width=self.width - indent,
            subsequent_indent=" " * indent,
            drop_whitespace=False,
        )
        return "\n".join(wrapper.fill(line) if line.strip() else "" for line in text.splitlines())

    def _rule(self, label: str = "", *, accent: str = "blue", char: str = "═") -> str:
        label_text = f" {label} " if label else ""
        pad_total = max(self.width - len(label_text), 0)
        left = pad_total // 2
        right = pad_total - left
        rule_line = f"{char * left}{label_text}{char * right}"
        color = getattr(self.palette, accent, "")
        line = rule_line[: self.width]
        return self.palette.apply(line, color)

    def _center_text(self, text: str) -> str:
        stripped = text.rstrip()
        pad_total = max(self.width - len(stripped), 0)
        left = pad_total // 2
        return " " * left + stripped

    def _play_banner_animation(self, accent: str) -> None:
        if not self.is_tty:
            return
        color = getattr(self.palette, accent, "")
        frames = ["   ", "•  ", "•• ", "•••", "•• ", "•  "]
        for frame in frames:
            text = self._center_text(f"ALWAYS ATTEND {frame}")
            sys.stdout.write(self.palette.apply(text, color, self.palette.bold))
            sys.stdout.flush()
            time.sleep(0.08)
            sys.stdout.write("\r")
        sys.stdout.write(" " * self.width + "\r")
        sys.stdout.flush()

    # ------------------------------------------------------------------ public helpers
    def clear_line(self) -> None:
        print()

    def clear_screen(self) -> None:
        if not self.palette.disabled:
            print("\033[2J\033[H", end="", flush=True)
        else:
            print("\n" * 3)

    def banner(self, subtitle: Optional[str] = None, *, accent: str = "monash") -> None:
        # Use new typewriter banner if available
        if ANIMATIONS_AVAILABLE:
            config = AnimationConfig()
            if config.enabled and config.style == "fancy":
                typewriter = TypewriterBanner(config)
                typewriter.display(subtitle)
                return

        # Fall back to gradient banner implementation
        self._play_banner_animation(accent)

        # Display banner with gradient effect
        for i, line in enumerate(self._BANNER):
            if not line.strip():  # Empty line
                print()
                continue

            # Apply gradient color based on line index
            color = self._GRADIENT_COLORS[i % len(self._GRADIENT_COLORS)]
            centered = self._center_text(line)

            if not self.palette.disabled:
                print(f"{color}{self.palette.bold}{centered}{self.palette.reset}")
            else:
                print(centered)

        if subtitle:
            print(self._rule(subtitle, accent=accent))

    def headline(self, title: str, *, accent: str = "blue") -> None:
        print(self._rule(title, accent=accent))

    def text_block(self, text: str, *, indent: int = 2, tone: Optional[str] = None) -> None:
        payload = self._wrap(text, indent=indent)
        if tone:
            color = getattr(self.palette, tone, "")
            payload = self.palette.apply(payload, color)
        print(payload)

    def bullet_list(self, lines: Iterable[str], *, tone: Optional[str] = None) -> None:
        color = getattr(self.palette, tone, "") if tone else ""
        for line in lines:
            bullet = f"• {line}"
            if tone:
                bullet = self.palette.apply(bullet, color)
            print(self._wrap(bullet, indent=2))

    def prompt(self, prompt_text: str) -> str:
        prompt_color = getattr(self.palette, "green")
        prompt = self.palette.apply(f"{prompt_text.strip()} ", prompt_color, self.palette.bold)
        try:
            return input(prompt)
        except EOFError:
            return ""

    def pause(self, prompt_text: str = "Press Enter to continue…") -> None:
        try:
            input(self.palette.apply(prompt_text, self.palette.dim))
        except EOFError:
            pass

    def prompt_menu(self, title: str, options: List[str], *, allow_quit: bool = False) -> Optional[int]:
        self.headline(title)
        for idx, label in enumerate(options, start=1):
            line = f" {idx}. {label}"
            print(self.palette.apply(line, self.palette.white if not self.palette.disabled else ""))
        if allow_quit:
            print(self.palette.apply(" 0. Exit", self.palette.dim))
        while True:
            raw = self.prompt("→ Select an option:")
            if allow_quit and raw.strip() == "0":
                return None
            if raw.isdigit():
                choice = int(raw)
                if 1 <= choice <= len(options):
                    return choice - 1
            print(self.palette.apply("Invalid choice, try again.", self.palette.yellow))

    def confirm(self, prompt_text: str, *, default: bool = True) -> bool:
        yes_no = "Y/n" if default else "y/N"
        full_prompt = f"{prompt_text} [{yes_no}]"
        while True:
            raw = self.prompt(full_prompt).strip().lower()
            if not raw:
                return default
            if raw in ("y", "yes"):
                return True
            if raw in ("n", "no"):
                return False
            print(self.palette.apply("Please respond with yes or no.", self.palette.yellow))

    def panel(self, title: str, body: Iterable[str], *, accent: str = "magenta") -> None:
        print(self._rule(title, accent=accent))
        for line in body:
            print(self._wrap(line, indent=4))
        print(self._rule(accent=accent))
