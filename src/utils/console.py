from __future__ import annotations

import os
import shutil
import textwrap
from dataclasses import dataclass
from typing import Iterable, List, Optional

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

    @property
    def disabled(self) -> bool:
        return bool(os.getenv("NO_COLOR"))

    def apply(self, text: str, *styles: str) -> str:
        if self.disabled or not styles:
            return text
        return f"{''.join(styles)}{text}{self.reset}"


class PortalConsole:
    """Coordinated helper for rendering a friendly CLI front-end."""

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

    def __init__(self) -> None:
        self.palette = ConsolePalette()
        self.width = max(68, min(self._detect_width(), 120))

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
        pad = self.width - len(label_text)
        rule_line = f"{char * max(pad, 0)}{label_text}"
        color = getattr(self.palette, accent, "")
        return self.palette.apply(rule_line[: self.width], color)

    # ------------------------------------------------------------------ public helpers
    def clear_line(self) -> None:
        print()

    def banner(self, subtitle: Optional[str] = None, *, accent: str = "cyan") -> None:
        banner = self.palette.apply(self._BANNER.strip("\n"), getattr(self.palette, accent), self.palette.bold)
        print(banner)
        if subtitle:
            print(self._rule(subtitle, accent="blue"))

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
        border = self._rule(accent=accent, char="─")
        print(border)
        print(self.palette.apply(f"{title}", getattr(self.palette, accent), self.palette.bold))
        print(border)
        for line in body:
            print(self._wrap(line, indent=4))
        print(border)
