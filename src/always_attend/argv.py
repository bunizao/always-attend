"""CLI argument normalization for public subcommands."""

from __future__ import annotations


CLI_EXAMPLES = (
    "Examples:\n"
    "  attend\n"
    "  attend run --target https://attendance.example.edu/student/ --json\n"
    "  attend inspect state --target https://attendance.example.edu/student/ --json\n"
    "  attend auth login https://attendance.example.edu --json\n"
    "  attend fetch --source edstem --course FIT2099 --kind threads --json\n"
    "  attend match --target https://attendance.example.edu/student/ --json\n"
    "  attend report --target https://attendance.example.edu/student/ --json\n"
    "  attend doctor --json\n"
    "  attend resolve --plan plan.json --json\n"
    "  attend submit --plan plan.json --json\n"
    "  attend stats\n"
    "  attend login\n"
    "  attend paths --json\n"
    "  attend week 4\n"
    "  attend week 4 --dry-run"
)


def normalize_cli_argv(argv: list[str]) -> list[str]:
    """Translate public subcommands into the existing flag-based interface."""
    if not argv:
        return []

    command, *rest = argv

    if command == "help":
        return ["--help", *rest]

    if command == "stats":
        return ["--stats", *rest]

    if command == "login":
        return ["--login-only", *rest]

    if command == "week":
        if not rest:
            raise SystemExit(
                "usage: attend week <number> [options]\n"
                "error: the following arguments are required: number"
            )
        if rest[0] in {"-h", "--help"}:
            return ["--help", *rest[1:]]
        return ["--week", *rest]

    return argv
