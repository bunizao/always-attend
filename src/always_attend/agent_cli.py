"""Agent-first CLI commands for the AI-native attendance workflow."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from always_attend import __version__
from always_attend.agent_protocol import AttendanceStateItem, CandidateRecord, MatchResult, SourceArtifact, SubmissionAttempt, TraceEvent
from always_attend.attendance_state_reader import AttendanceStateReader
from always_attend.matcher import match_open_items
from always_attend.okta_client import OktaCliError, OktaClient
from always_attend.paths import env_file as runtime_env_file, storage_state_file
from always_attend.reporter import build_report, exit_code_for_report
from always_attend.session_manager import SessionManager
from always_attend.skill_installer import (
    discover_agent_skill_dirs,
    SkillInstallError,
    default_skills_dir,
    install_bundled_skills,
    list_bundled_skills,
    sync_skill_symlinks,
)
from always_attend.source_collectors import collect_candidates_for_sources
from always_attend.source_clients import SourceCommandError
from always_attend.submission_plan import (
    SubmissionPlanError,
    load_submission_plan,
    materialize_plan,
    plan_summary,
)
from always_attend.submitter import Submitter
from utils.env_utils import append_to_env_file, ensure_env_file, load_env


class AgentCliInputError(RuntimeError):
    """Raised when agent CLI input is invalid."""


def _default_target() -> str:
    return os.getenv("PORTAL_URL", "")


def _default_sources() -> str:
    return "attendance,gmail,moodle,edstem"


def build_agent_parser() -> argparse.ArgumentParser:
    """Build the AI-native command tree."""
    parser = argparse.ArgumentParser(
        prog="attend",
        description="AI-native attendance CLI for Codex/OpenClaw-style agents.",
    )
    parser.add_argument("--version", action="version", version=f"always-attend {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Inspect, collect, match, submit, and report in one command.")
    _add_pipeline_args(run_parser)

    doctor_parser = subparsers.add_parser("doctor", help="Check CLI and OCR dependencies.")
    doctor_parser.add_argument("--json", action="store_true")

    auth_parser = subparsers.add_parser("auth", help="Authenticate via the external okta CLI.")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command", required=True)

    auth_login = auth_subparsers.add_parser("login", help="Login via okta and refresh the shared session.")
    auth_login.add_argument("url", nargs="?", default=_default_target())
    auth_login.add_argument("--username")
    auth_login.add_argument("--password")
    auth_login.add_argument("--totp-secret")
    auth_login.add_argument("--headed", action="store_true")
    auth_login.add_argument("--timeout-ms", type=int, default=60000)
    auth_login.add_argument("--json", action="store_true")

    auth_check = auth_subparsers.add_parser("check", help="Verify the shared okta session.")
    auth_check.add_argument("url", nargs="?", default=_default_target())
    auth_check.add_argument("--timeout-ms", type=int, default=30000)
    auth_check.add_argument("--json", action="store_true")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect runtime state from the attendance site.")
    inspect_subparsers = inspect_parser.add_subparsers(dest="inspect_command", required=True)
    inspect_state = inspect_subparsers.add_parser("state", help="Read and classify Units.aspx DOM state.")
    inspect_state.add_argument("--target", default=_default_target())
    inspect_state.add_argument("--demo", action="store_true")
    inspect_state.add_argument("--headed", action="store_true")
    inspect_state.add_argument("--course", action="append", default=[])
    inspect_state.add_argument("--json", action="store_true")

    fetch_parser = subparsers.add_parser("fetch", help="Collect normalized candidates from external sources.")
    fetch_parser.add_argument("--target", default=_default_target())
    fetch_parser.add_argument("--source", action="append", default=[])
    fetch_parser.add_argument("--kind")
    fetch_parser.add_argument("--course", action="append", default=[])
    fetch_parser.add_argument("--week", type=int)
    fetch_parser.add_argument("--headed", action="store_true")
    fetch_parser.add_argument("--json", action="store_true")

    handoff_parser = subparsers.add_parser("handoff", help="Prepare text and image evidence for external multimodal AI.")
    handoff_parser.add_argument("--target", default=_default_target())
    handoff_parser.add_argument("--sources", default=_default_sources())
    handoff_parser.add_argument("--course", action="append", default=[])
    handoff_parser.add_argument("--week", type=int)
    handoff_parser.add_argument("--demo", action="store_true")
    handoff_parser.add_argument("--headed", action="store_true")
    handoff_parser.add_argument("--json", action="store_true")

    match_parser = subparsers.add_parser("match", help="Match open attendance items against source candidates.")
    _add_pipeline_args(match_parser, include_submit_controls=False)

    submit_parser = subparsers.add_parser("submit", help="Submit structured matches or a legacy plan.")
    submit_parser.add_argument("--target", default=_default_target())
    submit_parser.add_argument("--input")
    submit_parser.add_argument("--plan")
    submit_parser.add_argument("--demo", action="store_true")
    submit_parser.add_argument("--dry-run", action="store_true")
    submit_parser.add_argument("--headed", action="store_true")
    submit_parser.add_argument("--min-confidence", type=float, default=0.80)
    submit_parser.add_argument("--max-retries", type=int, default=1)
    submit_parser.add_argument("--json", action="store_true")

    report_parser = subparsers.add_parser("report", help="Generate a stable summary from current state or a saved artifact.")
    report_parser.add_argument("--input")
    report_parser.add_argument("--target", default=_default_target())
    report_parser.add_argument("--demo", action="store_true")
    report_parser.add_argument("--source", action="append", default=[])
    report_parser.add_argument("--course", action="append", default=[])
    report_parser.add_argument("--week", type=int)
    report_parser.add_argument("--headed", action="store_true")
    report_parser.add_argument("--json", action="store_true")

    skills_parser = subparsers.add_parser(
        "skills",
        help="Export bundled skills into a neutral directory for any agent.",
    )
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command", required=True)

    skills_list = skills_subparsers.add_parser("list", help="List bundled skills and export status.")
    skills_list.add_argument("--dest")
    skills_list.add_argument("--agent-dir", action="append", default=[])
    skills_list.add_argument("--json", action="store_true")

    skills_install = skills_subparsers.add_parser(
        "install",
        help="Export bundled skills into the default or requested directory.",
    )
    skills_install.add_argument("--name", action="append", default=[])
    skills_install.add_argument("--dest")
    skills_install.add_argument("--agent-dir", action="append", default=[])
    skills_install.add_argument("--force", action="store_true")
    skills_install.add_argument("--json", action="store_true")

    resolve_parser = subparsers.add_parser("resolve", help="Validate and normalize a legacy submission plan file.")
    resolve_parser.add_argument("--plan", required=True)
    resolve_parser.add_argument("--output")
    resolve_parser.add_argument("--json", action="store_true")

    return parser


def _add_pipeline_args(parser: argparse.ArgumentParser, *, include_submit_controls: bool = True) -> None:
    parser.add_argument("--target", default=_default_target())
    parser.add_argument("--mode", default="fill_all_open")
    parser.add_argument("--sources", default=_default_sources())
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-confidence", type=float, default=0.80)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--week", type=int)
    parser.add_argument("--course", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    if not include_submit_controls:
        return


def _emit(payload: dict[str, Any], *, json_output: bool) -> int:
    exit_code = int(payload.get("exit_code", 0 if payload.get("status") == "ok" else 1))
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return exit_code
    if payload.get("status") == "ok":
        print(payload.get("message") or payload.get("command") or "ok")
    else:
        print(payload.get("error") or "Command failed")
    return exit_code


def _require_target(target: str) -> str:
    value = (target or "").strip()
    if not value:
        raise AgentCliInputError("Missing target URL. Set PORTAL_URL or pass --target.")
    return value


def _persist_target_url(target: str) -> dict[str, Any]:
    value = _require_target(target)
    env_path = runtime_env_file()
    ensure_env_file(str(env_path))
    append_to_env_file(str(env_path), "PORTAL_URL", value)
    os.environ["PORTAL_URL"] = value
    return {
        "key": "PORTAL_URL",
        "value": value,
        "env_file": str(env_path),
        "persisted": True,
    }


def _require_and_persist_target(target: str) -> tuple[str, dict[str, Any]]:
    value = _require_target(target)
    return value, _persist_target_url(value)


def _target_required_payload(command: str) -> dict[str, Any]:
    return {
        "status": "error",
        "command": command,
        "error": "Missing target URL. Ask the user for the attendance base URL.",
        "message": "The attendance base URL is required before this command can run.",
        "user_feedback": "Ask the user for the attendance base URL. The next successful command will save it to the persistent config automatically.",
        "next_action": "configure_target_url",
        "config_key": "PORTAL_URL",
        "config_path": str(runtime_env_file()),
        "exit_code": 2,
    }


def _parse_sources(csv_text: str | None, explicit_sources: list[str] | None = None) -> list[str]:
    if explicit_sources:
        return [item.lower() for item in explicit_sources if item and item.lower() != "attendance"]
    values = [item.strip().lower() for item in (csv_text or "").split(",")]
    return [item for item in values if item and item != "attendance"]


def _requested_sources(explicit_sources: list[str] | None = None, csv_text: str | None = None) -> list[str]:
    if explicit_sources is not None:
        return _parse_sources(None, explicit_sources)
    if csv_text is not None:
        return _parse_sources(csv_text)
    sources = _parse_sources(csv_text, explicit_sources)
    if sources:
        return sources
    return _parse_sources(_default_sources())


def _item_from_dict(payload: dict[str, Any]) -> AttendanceStateItem:
    return AttendanceStateItem(**payload)


def _match_from_dict(payload: dict[str, Any]) -> MatchResult:
    return MatchResult(**payload)


def _attempt_from_dict(payload: dict[str, Any]) -> SubmissionAttempt:
    return SubmissionAttempt(**payload)


def _event_from_dict(payload: dict[str, Any]) -> TraceEvent:
    return TraceEvent(**payload)


def _load_json_file(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


async def _run_submit_weeks(
    weeks: list[int],
    *,
    dry_run: bool,
    target_url: str,
    codes_root: Path,
) -> list[dict[str, Any]]:
    from core.submit import run_submit

    results: list[dict[str, Any]] = []
    original_week = os.environ.get("WEEK_NUMBER")
    original_target = os.environ.get("PORTAL_URL")
    original_codes = os.environ.get("CODES_DB_PATH")
    try:
        os.environ["PORTAL_URL"] = target_url
        os.environ["CODES_DB_PATH"] = str(codes_root)
        for week in weeks:
            os.environ["WEEK_NUMBER"] = str(week)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                summary = await run_submit(dry_run=dry_run, target_email=None)
            results.append({"week": week, "summary": summary})
    finally:
        if original_week is None:
            os.environ.pop("WEEK_NUMBER", None)
        else:
            os.environ["WEEK_NUMBER"] = original_week
        if original_target is None:
            os.environ.pop("PORTAL_URL", None)
        else:
            os.environ["PORTAL_URL"] = original_target
        if original_codes is None:
            os.environ.pop("CODES_DB_PATH", None)
        else:
            os.environ["CODES_DB_PATH"] = original_codes
    return results


def _session_missing_payload(command: str, target: str, error: str) -> dict[str, Any]:
    return {
        "status": "error",
        "command": command,
        "error": error,
        "next_action": "auth_login",
        "suggested_command": f"attend auth login {target} --json",
        "demo_command": "attend handoff --demo --json",
        "message": "A stored session is required before this command can access the attendance site.",
        "user_feedback": "No reusable session was found. Start the auth flow so the agent can import browser cookies or open an interactive login window.",
        "exit_code": 3,
    }


def _demo_handoff_payload(target: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "command": "handoff",
        "message": "Demo AI handoff package generated.",
        "data": {
            "target": target or "https://attendance.example.edu/student/",
            "source_priority": _requested_sources(csv_text=_default_sources()),
            "open_items": [
                {
                    "course_code": "FIT2099",
                    "slot_label": "Workshop 01",
                    "class_type": "workshop",
                    "date": "2026-03-17",
                    "time_range": "10:00-12:00",
                    "group": "A1",
                }
            ],
            "candidate_hints": [],
            "artifacts": [
                {
                    "source": "edstem",
                    "command": ["edstem", "threads", "30595", "--json"],
                    "course_codes": ["FIT2099"],
                    "week_hints": [7],
                    "group_hints": ["A1"],
                    "artifact_kind": "mixed",
                    "image_urls": ["https://example.test/code.png"],
                    "text_snippets": ["FIT2099 Week 7 Workshop Group A1 code is shown in the linked image."],
                    "notes": ["Demo payload for first-time agent validation."],
                }
            ],
            "plan_contract": {
                "required_fields": ["course_code", "week", "slot", "code"],
                "shape": [
                    {
                        "course_code": "FIT2099",
                        "week": 7,
                        "slot": "Workshop 01",
                        "code": "ABCDE",
                    }
                ],
            },
            "instructions": [
                "Treat open_items from the attendance site as the source of truth.",
                "Use text snippets and image_urls from artifacts as evidence for multimodal analysis.",
                "Infer the most likely attendance codes from source evidence, then write a JSON plan with course_code, week, slot, and code.",
                "Pass that plan to attend submit --plan ... --json or continue with attend report for review.",
            ],
            "trace": [],
        },
        "exit_code": 0,
    }


def _demo_state_items() -> tuple[list[AttendanceStateItem], list[TraceEvent]]:
    items = [
        AttendanceStateItem(
            item_id="demo:FIT2099:Workshop01",
            course_code="FIT2099",
            class_type="workshop",
            slot_label="Workshop 01",
            date="2026-03-17",
            time_range="10:00-12:00",
            group="A1",
            anchor="17_Mar_26",
            dom_state="open",
            reason="Demo entry link is available.",
            position=0,
            raw_text="FIT2099 Workshop 01 Group A1 10:00-12:00",
        )
    ]
    trace = [
        TraceEvent(
            stage="inspect",
            code="demo_state_loaded",
            message="Demo attendance state loaded without live credentials.",
            details={"item_count": len(items)},
        )
    ]
    return items, trace


def _demo_matches() -> list[MatchResult]:
    return [
        MatchResult(
            item_id="demo:FIT2099:Workshop01",
            course_code="FIT2099",
            slot_label="Workshop 01",
            candidate_code="ABCDE",
            confidence=0.97,
            reason="Demo structured match produced a high-confidence candidate.",
            matched_fields=["course_code", "class_type", "date", "time_range", "group"],
            conflicting_fields=[],
            source="edstem",
            class_type="workshop",
            date="2026-03-17",
            time_range="10:00-12:00",
            group="A1",
            raw_slot="Workshop 01",
        )
    ]


def _demo_candidates() -> list[CandidateRecord]:
    return [
        CandidateRecord(
            source="edstem",
            course_code="FIT2099",
            class_type="workshop",
            date="2026-03-17",
            time_range="10:00-12:00",
            group="A1",
            raw_slot="Workshop 01",
            code="ABCDE",
            evidence="$.artifacts[0].text_snippets[0]",
            extraction_mode="demo_text",
            confidence_hint=0.97,
        )
    ]


def _demo_attempts() -> list[SubmissionAttempt]:
    return [
        SubmissionAttempt(
            item_id="demo:FIT2099:Workshop01",
            course_code="FIT2099",
            slot_label="Workshop 01",
            candidate_code="ABCDE",
            confidence=0.97,
            state="submitted_ok",
            reason="Demo submission simulated a successful portal submit.",
            source="edstem",
        )
    ]


async def _inspect_state(target: str, *, headed: bool, courses: list[str]) -> tuple[list[AttendanceStateItem], list[TraceEvent]]:
    session_manager = SessionManager()
    if session_manager.requires_okta_session(target):
        session_manager.ensure_storage_state(target)
    return await AttendanceStateReader().inspect(
        target_url=target,
        headed=headed,
        course_filters=courses,
    )


async def _pipeline_match(
    *,
    target: str,
    headed: bool,
    sources: list[str],
    week: int | None,
    courses: list[str],
) -> tuple[list[AttendanceStateItem], list[Any], list[SourceArtifact], list[MatchResult], list[TraceEvent]]:
    items, trace = await _inspect_state(target, headed=headed, courses=courses)
    session_manager = SessionManager()
    candidates, collect_trace, artifacts = collect_candidates_for_sources(
        items=items,
        sources=sources,
        session_manager=session_manager,
        target_url=target,
        week=week,
        explicit_courses=courses,
    )
    trace.extend(collect_trace)
    matches = match_open_items(items, candidates)
    trace.append(
        TraceEvent(
            stage="match",
            code="matching_completed",
            message="Structured matching completed.",
            details={
                "item_count": len(items),
                "candidate_count": len(candidates),
                "match_count": len(matches),
            },
        )
    )
    return items, candidates, artifacts, matches, trace


async def _pipeline_run(args: argparse.Namespace) -> dict[str, Any]:
    if args.demo:
        items, trace = _demo_state_items()
        candidates = _demo_candidates()
        matches = _demo_matches()
        attempts = _demo_attempts()
        report = build_report(items=items, matches=matches, attempts=attempts, trace=trace)
        report["command"] = "run"
        report["message"] = "Demo AI-native attendance run completed."
        report["data"] = {
            "items": [item.to_dict() for item in items],
            "candidates": [item.to_dict() for item in candidates],
            "artifacts": _demo_handoff_payload(args.target).get("data", {}).get("artifacts", []),
            "matches": [item.to_dict() for item in matches],
            "attempts": [item.to_dict() for item in attempts],
        }
        report["exit_code"] = 0
        return report
    target, persisted_target = _require_and_persist_target(args.target)
    items, candidates, artifacts, matches, trace = await _pipeline_match(
        target=target,
        headed=args.headed,
        sources=_parse_sources(args.sources),
        week=args.week,
        courses=args.course,
    )
    attempts, submit_trace = await Submitter().submit(
        target_url=target,
        items=items,
        matches=matches,
        min_confidence=args.min_confidence,
        max_retries=args.max_retries,
        headed=args.headed,
        dry_run=args.dry_run,
    )
    trace.extend(submit_trace)
    final_items = items
    if not args.dry_run:
        final_items, reread_trace = await _inspect_state(target, headed=args.headed, courses=args.course)
        trace.extend(reread_trace)
    report = build_report(
        items=final_items,
        matches=matches,
        attempts=attempts,
        trace=trace,
    )
    report["command"] = "run"
    report["message"] = "AI-native attendance run completed."
    report["data"] = {
        "target_config": persisted_target,
        "items": [item.to_dict() for item in final_items],
        "candidates": [item.to_dict() for item in candidates],
        "artifacts": [item.to_dict() for item in artifacts],
        "matches": [item.to_dict() for item in matches],
        "attempts": [item.to_dict() for item in attempts],
    }
    report["exit_code"] = exit_code_for_report(report)
    return report


def _handle_auth(args: argparse.Namespace) -> dict[str, Any]:
    target, persisted_target = _require_and_persist_target(args.url)
    if args.auth_command == "login":
        browser_import = asyncio.run(_try_browser_cookie_import(target, timeout_ms=args.timeout_ms))
        auth_flow: dict[str, Any] = {
            "browser_cookie_import": browser_import,
            "interactive_login": None,
            "completed_method": None,
        }
        if browser_import["status"] == "ok":
            auth_flow["completed_method"] = "browser_cookie_import"
            return {
                "status": "ok",
                "command": "auth.login",
                "message": "Browser cookies were imported into the saved portal session.",
                "user_feedback": "Saved the attendance URL and reused an existing browser session. The agent can continue without asking you to log in again.",
                "data": {
                    "target": target,
                    "target_config": persisted_target,
                    "auth_flow": auth_flow,
                    "session_scope": "portal_storage_state",
                },
                "exit_code": 0,
            }

        okta = OktaClient()
        result = okta.login(
            url=target,
            username=args.username,
            password=args.password,
            totp_secret=args.totp_secret,
            headed=True,
            timeout_ms=args.timeout_ms,
        )
        auth_flow["interactive_login"] = {
            "status": "ok",
            "mode": "okta_headed",
            "payload": result.payload,
        }
        auth_flow["completed_method"] = "interactive_okta_login"
        return {
            "status": "ok",
            "command": "auth.login",
            "message": "Interactive login completed after browser cookie import was unavailable.",
            "user_feedback": "Saved the attendance URL. A browser window was used for login, and the session is now refreshed.",
            "data": {
                "target": target,
                "target_config": persisted_target,
                "auth_flow": auth_flow,
                "session_scope": "shared_okta_session",
            },
            "exit_code": 0,
        }

    okta = OktaClient()
    result = okta.check(url=target, timeout_ms=args.timeout_ms)
    return {
        "status": "ok",
        "command": "auth.check",
        "message": "Okta session check completed.",
        "user_feedback": "Checked the saved session for the configured attendance URL.",
        "data": {
            "target": target,
            "target_config": persisted_target,
            "session": result.payload,
        },
        "exit_code": 0,
    }


async def _handle_inspect(args: argparse.Namespace) -> dict[str, Any]:
    if args.demo:
        items, trace = _demo_state_items()
        return {
            "status": "ok",
            "command": "inspect.state",
            "message": "Demo attendance site state loaded.",
            "data": {
                "items": [item.to_dict() for item in items],
                "trace": [item.to_dict() for item in trace],
            },
            "exit_code": 0,
        }
    target, persisted_target = _require_and_persist_target(args.target)
    items, trace = await _inspect_state(target, headed=args.headed, courses=args.course)
    return {
        "status": "ok",
        "command": "inspect.state",
        "message": "Attendance site state loaded.",
        "data": {
            "target_config": persisted_target,
            "items": [item.to_dict() for item in items],
            "trace": [item.to_dict() for item in trace],
        },
        "exit_code": 4 if not any(item.dom_state == "open" for item in items) else 0,
    }


async def _handle_fetch(args: argparse.Namespace) -> dict[str, Any]:
    target, persisted_target = _require_and_persist_target(args.target)
    items, trace = await _inspect_state(target, headed=args.headed, courses=args.course)
    candidates, collect_trace, artifacts = collect_candidates_for_sources(
        items=items,
        sources=_requested_sources(args.source),
        session_manager=SessionManager(),
        target_url=target,
        week=args.week,
        explicit_courses=args.course,
    )
    trace.extend(collect_trace)
    return {
        "status": "ok",
        "command": "fetch",
        "message": "Source collection completed.",
        "data": {
            "target_config": persisted_target,
            "items": [item.to_dict() for item in items],
            "candidates": [item.to_dict() for item in candidates],
            "artifacts": [item.to_dict() for item in artifacts],
            "trace": [item.to_dict() for item in trace],
        },
        "exit_code": 0 if candidates else 4,
    }


async def _handle_handoff(args: argparse.Namespace) -> dict[str, Any]:
    if args.demo:
        return _demo_handoff_payload((args.target or "").strip())
    target, persisted_target = _require_and_persist_target(args.target)

    try:
        items, trace = await _inspect_state(target, headed=args.headed, courses=args.course)
    except (OktaCliError, RuntimeError) as exc:
        if "No stored session found" in str(exc):
            return _session_missing_payload("handoff", target, str(exc))
        raise
    requested_sources = _requested_sources(csv_text=args.sources)
    candidates, collect_trace, artifacts = collect_candidates_for_sources(
        items=items,
        sources=requested_sources,
        session_manager=SessionManager(),
        target_url=target,
        week=args.week,
        explicit_courses=args.course,
    )
    trace.extend(collect_trace)
    open_items = [item.to_dict() for item in items if item.dom_state == "open"]
    return {
        "status": "ok",
        "command": "handoff",
        "message": "AI handoff package generated.",
        "data": {
            "target": target,
            "target_config": persisted_target,
            "source_priority": requested_sources,
            "open_items": open_items,
            "candidate_hints": [item.to_dict() for item in candidates],
            "artifacts": [item.to_dict() for item in artifacts],
            "plan_contract": {
                "required_fields": ["course_code", "week", "slot", "code"],
                "shape": [
                    {
                        "course_code": "FIT2099",
                        "week": 7,
                        "slot": "Workshop 01",
                        "code": "ABCDE",
                    }
                ],
            },
            "instructions": [
                "Treat open_items from the attendance site as the source of truth.",
                "Use text snippets and image_urls from artifacts as evidence for multimodal analysis.",
                "Infer the most likely attendance codes from source evidence, then write a JSON plan with course_code, week, slot, and code.",
                "Pass that plan to attend submit --plan ... --json or continue with attend report for review.",
            ],
            "trace": [item.to_dict() for item in trace],
        },
        "exit_code": 0 if open_items else 4,
    }


async def _handle_match(args: argparse.Namespace) -> dict[str, Any]:
    if args.demo:
        items, trace = _demo_state_items()
        matches = _demo_matches()
        candidates = _demo_candidates()
        return {
            "status": "ok",
            "command": "match",
            "message": "Demo structured matching completed.",
            "data": {
                "items": [item.to_dict() for item in items],
                "candidates": [item.to_dict() for item in candidates],
                "artifacts": _demo_handoff_payload(args.target).get("data", {}).get("artifacts", []),
                "matches": [item.to_dict() for item in matches],
                "trace": [item.to_dict() for item in trace],
            },
            "exit_code": 0,
        }
    target, persisted_target = _require_and_persist_target(args.target)
    items, candidates, artifacts, matches, trace = await _pipeline_match(
        target=target,
        headed=args.headed,
        sources=_parse_sources(args.sources),
        week=args.week,
        courses=args.course,
    )
    return {
        "status": "ok",
        "command": "match",
        "message": "Structured matching completed.",
        "data": {
            "target_config": persisted_target,
            "items": [item.to_dict() for item in items],
            "candidates": [item.to_dict() for item in candidates],
            "artifacts": [item.to_dict() for item in artifacts],
            "matches": [item.to_dict() for item in matches],
            "trace": [item.to_dict() for item in trace],
        },
        "exit_code": 0 if matches else 4,
    }


async def _handle_submit(args: argparse.Namespace) -> dict[str, Any]:
    if args.demo:
        items, trace = _demo_state_items()
        matches = _demo_matches()
        attempts = _demo_attempts()
        report = build_report(items=items, matches=matches, attempts=attempts, trace=trace)
        report["command"] = "submit"
        report["message"] = "Demo submit stage completed."
        report["data"] = {
            "items": [item.to_dict() for item in items],
            "matches": [item.to_dict() for item in matches],
            "attempts": [item.to_dict() for item in attempts],
        }
        report["exit_code"] = 0
        return report
    if args.plan:
        entries = load_submission_plan(Path(args.plan))
        summary = plan_summary(entries)
        with tempfile.TemporaryDirectory(prefix="always-attend-plan-") as temp_dir:
            temp_root = Path(temp_dir)
            codes_root = temp_root / "codes"
            original_codes = os.environ.get("CODES_DB_PATH")
            try:
                os.environ["CODES_DB_PATH"] = str(codes_root)
                written_files = materialize_plan(entries)
            finally:
                if original_codes is None:
                    os.environ.pop("CODES_DB_PATH", None)
                else:
                    os.environ["CODES_DB_PATH"] = original_codes

            data = {
                "plan": summary,
                "written_files": written_files,
            }
            target = (args.target or "").strip()
            if target:
                runs = await _run_submit_weeks(
                    summary["weeks"],
                    dry_run=args.dry_run,
                    target_url=target,
                    codes_root=codes_root,
                )
                data["runs"] = runs
                message = "Structured submit executed from plan."
            else:
                message = "Legacy plan materialized for submission."
            return {
                "status": "ok",
                "command": "submit",
                "message": message,
                "data": data,
                "exit_code": 0,
            }

    target, persisted_target = _require_and_persist_target(args.target)
    if args.input:
        payload = _load_json_file(args.input)
        items = [_item_from_dict(item) for item in payload.get("items", [])]
        matches = [_match_from_dict(item) for item in payload.get("matches", [])]
        trace = [_event_from_dict(item) for item in payload.get("trace", [])]
    else:
        items, _, _, matches, trace = await _pipeline_match(
            target=target,
            headed=args.headed,
            sources=_requested_sources(csv_text=_default_sources()),
            week=None,
            courses=[],
        )
    attempts, submit_trace = await Submitter().submit(
        target_url=target,
        items=items,
        matches=matches,
        min_confidence=args.min_confidence,
        max_retries=args.max_retries,
        headed=args.headed,
        dry_run=args.dry_run,
    )
    trace.extend(submit_trace)
    final_items = items
    if not args.dry_run:
        final_items, reread_trace = await _inspect_state(target, headed=args.headed, courses=[])
        trace.extend(reread_trace)
    report = build_report(items=final_items, matches=matches, attempts=attempts, trace=trace)
    report["command"] = "submit"
    report["message"] = "Structured submit stage completed."
    report["data"] = {
        "target_config": persisted_target,
        "items": [item.to_dict() for item in final_items],
        "matches": [item.to_dict() for item in matches],
        "attempts": [item.to_dict() for item in attempts],
    }
    report["exit_code"] = exit_code_for_report(report)
    return report


async def _handle_report(args: argparse.Namespace) -> dict[str, Any]:
    if args.demo:
        items, trace = _demo_state_items()
        matches = _demo_matches()
        attempts = _demo_attempts()
        report = build_report(items=items, matches=matches, attempts=attempts, trace=trace)
        report["command"] = "report"
        report["message"] = "Demo structured report generated."
        report["data"] = {
            "items": [item.to_dict() for item in items],
            "candidates": [item.to_dict() for item in _demo_candidates()],
            "artifacts": _demo_handoff_payload(args.target).get("data", {}).get("artifacts", []),
            "matches": [item.to_dict() for item in matches],
            "attempts": [item.to_dict() for item in attempts],
        }
        report["exit_code"] = 0
        return report
    if args.input:
        payload = _load_json_file(args.input)
        if {"summary", "trace", "metrics"} <= set(payload):
            payload["command"] = "report"
            payload["message"] = "Existing report artifact loaded."
            payload["exit_code"] = exit_code_for_report(payload)
            return payload
        items = [_item_from_dict(item) for item in payload.get("items", [])]
        matches = [_match_from_dict(item) for item in payload.get("matches", [])]
        attempts = [_attempt_from_dict(item) for item in payload.get("attempts", [])]
        trace = [_event_from_dict(item) for item in payload.get("trace", [])]
        report = build_report(items=items, matches=matches, attempts=attempts, trace=trace)
        report["command"] = "report"
        report["message"] = "Structured report generated from artifact."
        report["exit_code"] = exit_code_for_report(report)
        return report

    target, persisted_target = _require_and_persist_target(args.target)
    items, candidates, artifacts, matches, trace = await _pipeline_match(
        target=target,
        headed=args.headed,
        sources=_requested_sources(args.source, _default_sources()),
        week=args.week,
        courses=args.course,
    )
    report = build_report(items=items, matches=matches, attempts=[], trace=trace)
    report["command"] = "report"
    report["message"] = "Structured report generated."
    report["data"] = {
        "target_config": persisted_target,
        "items": [item.to_dict() for item in items],
        "candidates": [item.to_dict() for item in candidates],
        "artifacts": [item.to_dict() for item in artifacts],
        "matches": [item.to_dict() for item in matches],
    }
    report["exit_code"] = exit_code_for_report(report)
    return report


def _handle_doctor() -> dict[str, Any]:
    payload = SessionManager().doctor_payload()
    return {
        "status": "ok",
        "command": "doctor",
        "message": "Dependency checks completed.",
        "data": payload,
        "exit_code": 0 if payload["ready"] else 1,
    }


def _handle_resolve(args: argparse.Namespace) -> dict[str, Any]:
    entries = load_submission_plan(Path(args.plan))
    summary = plan_summary(entries)
    if args.output:
        Path(args.output).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {
        "status": "ok",
        "command": "resolve",
        "message": "Submission plan normalized.",
        "data": summary,
        "exit_code": 0,
    }


def _handle_skills(args: argparse.Namespace) -> dict[str, Any]:
    destination = Path(args.dest).expanduser() if getattr(args, "dest", None) else None
    skills_root = destination or default_skills_dir()
    requested_agent_dirs = [Path(item).expanduser() for item in getattr(args, "agent_dir", []) if item]
    discovered_agents = discover_agent_skill_dirs() if not requested_agent_dirs else []
    if args.skills_command == "list":
        skills = list_bundled_skills(skills_dir=destination)
        return {
            "status": "ok",
            "command": "skills.list",
            "message": "Bundled skills listed.",
            "data": {
                "skills_root": str(skills_root),
                "skills": skills,
                "agent_skill_dirs": (
                    [{"agent": str(path), "path": str(path)} for path in requested_agent_dirs]
                    if requested_agent_dirs
                    else discovered_agents
                ),
            },
            "exit_code": 0,
        }

    installed = install_bundled_skills(
        requested_names=args.name,
        skills_dir=destination,
        force=args.force,
    )
    links = sync_skill_symlinks(
        installed,
        agent_skill_dirs=requested_agent_dirs or None,
        force=args.force,
    )
    return {
        "status": "ok",
        "command": "skills.install",
        "message": "Bundled skills installed.",
        "data": {
            "skills_root": str(skills_root),
            "installed": [str(path) for path in installed],
            "agent_links": links,
        },
        "exit_code": 0,
    }


def main(argv: list[str]) -> int:
    """Execute an AI-native CLI command."""
    load_env(str(runtime_env_file()))
    parser = build_agent_parser()
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    json_output = bool(getattr(args, "json", False))
    try:
        if args.command == "auth":
            payload = _handle_auth(args)
        elif args.command == "doctor":
            payload = _handle_doctor()
        elif args.command == "inspect":
            payload = asyncio.run(_handle_inspect(args))
        elif args.command == "fetch":
            payload = asyncio.run(_handle_fetch(args))
        elif args.command == "handoff":
            payload = asyncio.run(_handle_handoff(args))
        elif args.command == "match":
            payload = asyncio.run(_handle_match(args))
        elif args.command == "submit":
            payload = asyncio.run(_handle_submit(args))
        elif args.command == "report":
            payload = asyncio.run(_handle_report(args))
        elif args.command == "skills":
            payload = _handle_skills(args)
        elif args.command == "resolve":
            payload = _handle_resolve(args)
        else:
            payload = asyncio.run(_pipeline_run(args))
    except AgentCliInputError as exc:
        if "Missing target URL" in str(exc):
            payload = _target_required_payload(args.command)
        else:
            payload = {"status": "error", "command": args.command, "error": str(exc), "exit_code": 2}
    except OktaCliError as exc:
        target = getattr(args, "target", None) or getattr(args, "url", "")
        if "No stored session found" in str(exc) and target:
            payload = _session_missing_payload(args.command, target, str(exc))
        else:
            payload = {"status": "error", "command": args.command, "error": str(exc), "exit_code": 3}
    except (SourceCommandError, SubmissionPlanError, SkillInstallError) as exc:
        payload = {"status": "error", "command": args.command, "error": str(exc), "exit_code": 1}
    return _emit(payload, json_output=json_output)


async def _try_browser_cookie_import(target: str, *, timeout_ms: int) -> dict[str, Any]:
    from core.login import LoginConfig, LoginWorkflow

    workflow = LoginWorkflow(
        LoginConfig(
            portal_url=target,
            headed=False,
            storage_state=str(storage_state_file()),
            import_browser_session=True,
            auto_login_enabled=False,
            timeout_ms=timeout_ms,
            login_check_timeout_ms=timeout_ms,
        )
    )
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            imported = await workflow._import_session_from_system_browser()
    except Exception as exc:
        return {
            "status": "failed",
            "mode": "browser_cookie_import",
            "reason": str(exc),
        }
    if imported:
        return {
            "status": "ok",
            "mode": "browser_cookie_import",
            "storage_state": str(storage_state_file()),
        }
    return {
        "status": "failed",
        "mode": "browser_cookie_import",
        "reason": "No reusable browser session was found.",
    }
