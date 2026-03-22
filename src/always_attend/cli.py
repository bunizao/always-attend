"""Public CLI entrypoint for Always Attend."""

from __future__ import annotations

import sys

from always_attend.agent_cli import main as agent_main
from always_attend.runtime_contract import get_runtime_paths_dict, get_runtime_paths_json


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

    raise SystemExit(agent_main(raw_argv))
