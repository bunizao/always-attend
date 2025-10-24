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
main.py
Entry point delegating to src/core/main.

Always Attend - Main Entry Point
Redirects to the actual main module in src/core/ and ensures runtime parity with
platform launchers by bootstrapping the local virtual environment.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from utils.bootstrap import BootstrapError, ensure_runtime_ready  # noqa: E402


def _print_bootstrap_error(error: BootstrapError) -> None:
    msg = (
        "[Bootstrap] {}\n"
        "Tip: run 'python3 -m venv .venv && source .venv/bin/activate' followed by\n"
        "      'pip install -r requirements.txt' and 'python -m playwright install chromium'."
    ).format(error)
    print(msg, file=sys.stderr)


def run() -> None:
    try:
        ensure_runtime_ready(PROJECT_ROOT)
    except BootstrapError as exc:
        _print_bootstrap_error(exc)
        sys.exit(1)

    from core.main import main as core_main  # noqa: E402
    core_main()


if __name__ == "__main__":
    run()
