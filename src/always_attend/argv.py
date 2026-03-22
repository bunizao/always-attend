"""Shared CLI examples for legacy modules."""

from __future__ import annotations


CLI_EXAMPLES = (
    "Examples:\n"
    "  attend\n"
    "  attend run --target https://attendance.example.edu/student/ --json\n"
    "  attend inspect state --target https://attendance.example.edu/student/ --json\n"
    "  attend auth login https://attendance.example.edu --json\n"
    "  attend fetch --source edstem --course FIT2099 --kind threads --json\n"
    "  attend handoff --target https://attendance.example.edu/student/ --json\n"
    "  attend match --target https://attendance.example.edu/student/ --json\n"
    "  attend report --target https://attendance.example.edu/student/ --json\n"
    "  attend doctor --json\n"
    "  attend resolve --plan plan.json --json\n"
    "  attend submit --plan plan.json --json\n"
    "  attend skills list --json\n"
    "  attend paths --json"
)


def normalize_cli_argv(argv: list[str]) -> list[str]:
    """Return arguments unchanged for legacy internal callers."""
    return argv
