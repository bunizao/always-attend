"""Public CLI entrypoint for Always Attend."""

from __future__ import annotations

import sys
from pathlib import Path

from always_attend.agent_cli import main as agent_main
from always_attend.argv import normalize_cli_argv
from always_attend.runtime_contract import get_runtime_paths_dict, get_runtime_paths_json
from utils.bootstrap import BootstrapError, ensure_runtime_ready


def _is_agent_command(argv: list[str]) -> bool:
    return bool(argv) and argv[0] in {"run", "doctor", "auth", "inspect", "fetch", "match", "submit", "report", "resolve"}


def _is_non_runtime_command(argv: list[str]) -> bool:
    return any(arg in {"-h", "--help", "--version"} for arg in argv)


def _find_project_root() -> Path | None:
    package_dir = Path(__file__).resolve().parent
    for candidate in (package_dir.parent.parent, Path.cwd()):
        if (
            (candidate / "pyproject.toml").exists()
            and (candidate / "requirements.txt").exists()
            and (candidate / "src").is_dir()
        ):
            return candidate
    return None


def _print_bootstrap_error(error: BootstrapError) -> None:
    msg = (
        "[Bootstrap] {}\n"
        "Tip: run 'uv sync' or install the requirements into a virtual environment.\n"
        "      Chromium is downloaded automatically if Playwright needs it at runtime."
    ).format(error)
    print(msg, file=sys.stderr)


def _handle_builtin_command(argv: list[str]) -> bool:
    if not argv or argv[0] != "paths":
        return False

    as_json = "--json" in argv[1:]
    payload = get_runtime_paths_json() if as_json else get_runtime_paths_dict()

    if as_json:
        print(payload)
    else:
        for key, value in payload.items():
            print(f"{key}={value}")
    return True


def main() -> None:
    raw_argv = sys.argv[1:]
    if _handle_builtin_command(raw_argv):
        return

    if _is_agent_command(raw_argv):
        raise SystemExit(agent_main(raw_argv))

    normalized_argv = normalize_cli_argv(raw_argv)

    if _is_non_runtime_command(normalized_argv):
        from core.main import main as core_main

        core_main(normalized_argv)
        return

    project_root = _find_project_root()
    if project_root is not None:
        try:
            ensure_runtime_ready(project_root)
        except BootstrapError as exc:
            _print_bootstrap_error(exc)
            raise SystemExit(1) from exc

    from core.main import main as core_main

    core_main(normalized_argv)
