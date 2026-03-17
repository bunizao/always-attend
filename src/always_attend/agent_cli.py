"""Agent-first CLI commands for external auth, fetch, resolve, and submit workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from always_attend.okta_client import OktaCliError, OktaClient, write_storage_state_from_okta
from always_attend.paths import storage_state_file
from always_attend.source_clients import SourceCommandError, SourceRequest, fetch_from_source
from always_attend.submission_plan import (
    SubmissionPlanError,
    load_submission_plan,
    materialize_plan,
    plan_summary,
)


def build_agent_parser() -> argparse.ArgumentParser:
    """Build the agent-first command tree."""
    parser = argparse.ArgumentParser(
        prog="attend",
        description="Agent-first CLI for auth, source fetch, plan resolution, and attendance submission.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_parser = subparsers.add_parser("auth", help="Authenticate via the external okta CLI.")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command", required=True)

    auth_login = auth_subparsers.add_parser("login", help="Login via okta and store the shared session.")
    auth_login.add_argument("url", nargs="?", default=os.getenv("PORTAL_URL", ""))
    auth_login.add_argument("--username")
    auth_login.add_argument("--password")
    auth_login.add_argument("--totp-secret")
    auth_login.add_argument("--headed", action="store_true")
    auth_login.add_argument("--timeout-ms", type=int, default=60000)
    auth_login.add_argument("--json", action="store_true")

    auth_check = auth_subparsers.add_parser("check", help="Check whether the shared okta session is valid.")
    auth_check.add_argument("url", nargs="?", default=os.getenv("PORTAL_URL", ""))
    auth_check.add_argument("--timeout-ms", type=int, default=30000)
    auth_check.add_argument("--json", action="store_true")

    auth_cookies = auth_subparsers.add_parser("cookies", help="Show shared okta cookies for a target URL.")
    auth_cookies.add_argument("url", nargs="?", default=os.getenv("PORTAL_URL", ""))
    auth_cookies.add_argument("--domain")
    auth_cookies.add_argument("--json", action="store_true")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch source data via external CLIs.")
    fetch_parser.add_argument("--source", required=True, choices=["moodle", "edstem", "gog"])
    fetch_parser.add_argument("--kind", default="auto")
    fetch_parser.add_argument("--course")
    fetch_parser.add_argument("--week", type=int)
    fetch_parser.add_argument("--limit", type=int)
    fetch_parser.add_argument("--exec-arg", action="append", default=[])
    fetch_parser.add_argument("--json", action="store_true")

    resolve_parser = subparsers.add_parser("resolve", help="Validate and normalize a submission plan JSON file.")
    resolve_parser.add_argument("--plan", required=True)
    resolve_parser.add_argument("--output")
    resolve_parser.add_argument("--json", action="store_true")

    submit_parser = subparsers.add_parser("submit", help="Submit attendance using a normalized plan and shared okta session.")
    submit_parser.add_argument("--plan", required=True)
    submit_parser.add_argument("--portal-url", default=os.getenv("PORTAL_URL", ""))
    submit_parser.add_argument("--dry-run", action="store_true")
    submit_parser.add_argument("--headed", action="store_true")
    submit_parser.add_argument("--json", action="store_true")

    return parser


def _emit(payload: dict[str, Any], *, json_output: bool) -> int:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("status") == "ok" else 1

    if payload.get("status") == "ok":
        print(payload.get("message") or payload["command"])
        return 0

    print(payload.get("error") or "Command failed")
    return 1


def _require_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        raise SubmissionPlanError("Missing portal URL. Set PORTAL_URL or pass it explicitly.")
    return value


def _handle_auth(args: argparse.Namespace) -> dict[str, Any]:
    okta = OktaClient()
    url = _require_url(args.url)

    if args.auth_command == "login":
        result = okta.login(
            url=url,
            username=args.username,
            password=args.password,
            totp_secret=args.totp_secret,
            headed=args.headed,
            timeout_ms=args.timeout_ms,
        )
        return {
            "status": "ok",
            "command": "auth.login",
            "message": "Okta session refreshed.",
            "data": result.payload,
        }

    if args.auth_command == "check":
        result = okta.check(url=url, timeout_ms=args.timeout_ms)
        return {
            "status": "ok",
            "command": "auth.check",
            "message": "Okta session check completed.",
            "data": result.payload,
        }

    result = okta.cookies(url=url, domain=args.domain)
    return {
        "status": "ok",
        "command": "auth.cookies",
        "message": "Okta cookies loaded.",
        "data": result.payload,
    }


def _handle_fetch(args: argparse.Namespace) -> dict[str, Any]:
    payload = fetch_from_source(
        SourceRequest(
            source=args.source,
            kind=args.kind,
            course=args.course,
            week=args.week,
            limit=args.limit,
            exec_args=list(args.exec_arg or []),
        )
    )
    return {
        "status": "ok",
        "command": "fetch",
        "message": f"Fetched {args.source} data.",
        "data": payload,
    }


def _handle_resolve(args: argparse.Namespace) -> dict[str, Any]:
    entries = load_submission_plan(Path(args.plan))
    summary = plan_summary(entries)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {
        "status": "ok",
        "command": "resolve",
        "message": "Submission plan normalized.",
        "data": summary,
    }


def _run_submit_weeks(weeks: list[int], *, dry_run: bool) -> list[dict[str, Any]]:
    from core.submit import run_submit

    results: list[dict[str, Any]] = []
    original_week = os.environ.get("WEEK_NUMBER")
    try:
        for week in weeks:
            os.environ["WEEK_NUMBER"] = str(week)
            summary = asyncio.run(run_submit(dry_run=dry_run, target_email=None))
            results.append({"week": week, "summary": summary})
    finally:
        if original_week is None:
            os.environ.pop("WEEK_NUMBER", None)
        else:
            os.environ["WEEK_NUMBER"] = original_week
    return results


def _handle_submit(args: argparse.Namespace) -> dict[str, Any]:
    portal_url = _require_url(args.portal_url)
    entries = load_submission_plan(Path(args.plan))
    summary = plan_summary(entries)
    written_files = materialize_plan(entries)

    if args.headed:
        os.environ["HEADLESS"] = "0"

    if not args.dry_run:
        okta = OktaClient()
        cookie_result = okta.cookies(url=portal_url)
        storage_info = write_storage_state_from_okta(
            cookie_result.payload,
            url=portal_url,
            output_path=storage_state_file(),
        )
    else:
        storage_info = {
            "path": str(storage_state_file()),
            "cookie_count": 0,
            "skipped": True,
        }

    submit_runs = _run_submit_weeks(summary["weeks"], dry_run=args.dry_run)
    return {
        "status": "ok",
        "command": "submit",
        "message": "Submission workflow executed.",
        "data": {
            "plan": summary,
            "written_files": written_files,
            "storage_state": storage_info,
            "runs": submit_runs,
        },
    }


def main(argv: list[str]) -> int:
    """Execute an agent-first CLI command."""
    parser = build_agent_parser()
    args = parser.parse_args(argv)
    json_output = bool(getattr(args, "json", False))

    try:
        if args.command == "auth":
            payload = _handle_auth(args)
        elif args.command == "fetch":
            payload = _handle_fetch(args)
        elif args.command == "resolve":
            payload = _handle_resolve(args)
        else:
            payload = _handle_submit(args)
    except (OktaCliError, SourceCommandError, SubmissionPlanError) as exc:
        payload = {
            "status": "error",
            "command": f"{args.command}",
            "error": str(exc),
        }

    return _emit(payload, json_output=json_output)
