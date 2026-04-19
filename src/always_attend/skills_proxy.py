"""Proxy `attend skills` commands to the external `npx skills` CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_SKILLS_SOURCE = "https://github.com/bunizao/always-attend/tree/main/skills"
ALIASED_SUBCOMMANDS = {
    "add",
    "remove",
    "rm",
    "list",
    "ls",
    "find",
    "update",
    "upgrade",
    "experimental_install",
    "experimental_sync",
    "init",
}
DEPRECATED_SUBCOMMAND_ALIASES = {
    "install": "add",
}


def run_skills_proxy(argv: list[str]) -> int:
    """Execute `attend skills ...` via `npx skills ...`."""
    json_output = False
    passthrough: list[str] = []
    for arg in argv:
        if arg == "--json":
            json_output = True
            continue
        passthrough.append(arg)

    if not passthrough or passthrough[0] in {"-h", "--help"}:
        return _emit_help(json_output=json_output)

    raw_subcommand = passthrough[0]
    subcommand = DEPRECATED_SUBCOMMAND_ALIASES.get(raw_subcommand, raw_subcommand)
    if subcommand not in ALIASED_SUBCOMMANDS:
        return _emit_error(
            command=f"skills.{raw_subcommand}",
            error=f"Unsupported skills subcommand '{raw_subcommand}'.",
            json_output=json_output,
            exit_code=2,
        )

    npx_executable = shutil.which("npx")
    if npx_executable is None:
        return _emit_error(
            command=f"skills.{subcommand}",
            error="Missing required dependency 'npx'. Install Node.js/npm first.",
            json_output=json_output,
            exit_code=1,
        )

    forwarded_args = passthrough[1:]
    command = _build_skills_command(
        npx_executable=npx_executable,
        subcommand=subcommand,
        forwarded_args=forwarded_args,
        json_output=json_output,
    )
    result = subprocess.run(command, capture_output=True, text=True)

    if json_output:
        return _emit_json_result(
            command=f"skills.{subcommand}",
            proxied_command=command,
            result=result,
            deprecated_alias=(raw_subcommand != subcommand),
        )

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def _build_skills_command(
    *,
    npx_executable: str,
    subcommand: str,
    forwarded_args: list[str],
    json_output: bool,
) -> list[str]:
    command = [npx_executable, "skills", subcommand]
    if subcommand == "add":
        source = _skills_source()
        if forwarded_args and not forwarded_args[0].startswith("-"):
            source = forwarded_args[0]
            forwarded_args = forwarded_args[1:]
        command.append(source)
        if "--full-depth" not in forwarded_args:
            command.append("--full-depth")
    command.extend(forwarded_args)
    if json_output and subcommand in {"list", "ls"} and "--json" not in forwarded_args:
        command.append("--json")
    return command


def _skills_source() -> str:
    configured = (os.getenv("ATTEND_SKILLS_SOURCE") or "").strip()
    if configured:
        return configured

    local_skills_dir = Path.cwd() / "skills"
    if (local_skills_dir / "SKILL.md").is_file():
        return str(local_skills_dir)

    return DEFAULT_SKILLS_SOURCE


def _emit_help(*, json_output: bool) -> int:
    help_text = (
        "Usage: attend skills <subcommand> [args...]\n\n"
        "This is a thin alias over `npx skills ...`.\n"
        f"`attend skills add` defaults to source `{_skills_source()}`.\n\n"
        "Examples:\n"
        "  attend skills add --all\n"
        "  attend skills add --agent codex --skill attend-agent-workflow\n"
        "  attend skills list\n"
        "  attend skills find attendance\n"
    )
    if json_output:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "command": "skills.help",
                    "message": "Skills proxy help rendered.",
                    "data": {
                        "default_source": _skills_source(),
                        "aliased_subcommands": sorted(ALIASED_SUBCOMMANDS),
                        "deprecated_subcommand_aliases": DEPRECATED_SUBCOMMAND_ALIASES,
                    },
                    "exit_code": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    print(help_text)
    return 0


def _emit_error(
    *,
    command: str,
    error: str,
    json_output: bool,
    exit_code: int,
) -> int:
    if json_output:
        print(
            json.dumps(
                {
                    "status": "error",
                    "command": command,
                    "error": error,
                    "exit_code": exit_code,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return exit_code
    print(error)
    return exit_code


def _emit_json_result(
    *,
    command: str,
    proxied_command: list[str],
    result: subprocess.CompletedProcess[str],
    deprecated_alias: bool,
) -> int:
    data: dict[str, Any] = {
        "proxied_command": proxied_command,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
    }
    if deprecated_alias:
        data["deprecated_alias"] = True

    if command in {"skills.list", "skills.ls"}:
        stdout = (result.stdout or "").strip()
        if stdout:
            try:
                data["payload"] = json.loads(stdout)
            except json.JSONDecodeError:
                pass

    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "command": command,
        "message": "Skills command proxied to npx skills.",
        "data": data,
        "exit_code": result.returncode,
    }
    if result.returncode != 0:
        payload["error"] = data["stderr"] or data["stdout"] or "Skills command failed."
    print(json.dumps(payload, indent=2, sort_keys=True))
    return result.returncode
