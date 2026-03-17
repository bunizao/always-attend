"""Agent-first CLI commands for the AI-native attendance workflow."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from always_attend.agent_protocol import AttendanceStateItem, CandidateRecord, MatchResult, SourceArtifact, SubmissionAttempt, TraceEvent
from always_attend.attendance_state_reader import AttendanceStateReader
from always_attend.matcher import match_open_items
from always_attend.okta_client import OktaCliError, OktaClient
from always_attend.reporter import build_report, exit_code_for_report
from always_attend.session_manager import SessionManager
from always_attend.source_collectors import collect_candidates_for_sources
from always_attend.source_clients import SourceCommandError
from always_attend.submission_plan import (
    SubmissionPlanError,
    load_submission_plan,
    materialize_plan,
    plan_summary,
)
from always_attend.submitter import Submitter


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


def _parse_sources(csv_text: str | None, explicit_sources: list[str] | None = None) -> list[str]:
    if explicit_sources:
        return [item.lower() for item in explicit_sources if item]
    values = [item.strip().lower() for item in (csv_text or "").split(",")]
    return [item for item in values if item and item != "attendance"]


def _requested_sources(explicit_sources: list[str] | None = None, csv_text: str | None = None) -> list[str]:
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


def _session_missing_payload(command: str, target: str, error: str) -> dict[str, Any]:
    return {
        "status": "error",
        "command": command,
        "error": error,
        "next_action": "auth_login",
        "suggested_command": f"attend auth login {target} --json",
        "demo_command": "attend handoff --demo --json",
        "message": "A stored session is required before this command can access the attendance site.",
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
    if args.demo or not (args.target or "").strip() or (args.dry_run and not (args.target or "").strip()):
        items, trace = _demo_state_items()
        candidates = _demo_candidates()
        matches = _demo_matches()
        attempts = _demo_attempts()
        report = build_report(items=items, matches=matches, attempts=attempts, trace=trace)
        report["command"] = "run"
        report["message"] = (
            "Demo AI-native attendance run completed."
            if args.demo
            else "Demo AI-native attendance run completed because no target was configured for dry-run."
        )
        if not args.demo and not (args.target or "").strip() and not args.dry_run:
            report["message"] = "Demo AI-native attendance run completed because no target was configured."
        report["data"] = {
            "items": [item.to_dict() for item in items],
            "candidates": [item.to_dict() for item in candidates],
            "artifacts": _demo_handoff_payload(args.target).get("data", {}).get("artifacts", []),
            "matches": [item.to_dict() for item in matches],
            "attempts": [item.to_dict() for item in attempts],
        }
        report["exit_code"] = 0
        return report
    target = _require_target(args.target)
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
        "items": [item.to_dict() for item in final_items],
        "candidates": [item.to_dict() for item in candidates],
        "artifacts": [item.to_dict() for item in artifacts],
        "matches": [item.to_dict() for item in matches],
        "attempts": [item.to_dict() for item in attempts],
    }
    report["exit_code"] = exit_code_for_report(report)
    return report


def _handle_auth(args: argparse.Namespace) -> dict[str, Any]:
    okta = OktaClient()
    target = _require_target(args.url)
    if args.auth_command == "login":
        result = okta.login(
            url=target,
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
            "exit_code": 0,
        }

    result = okta.check(url=target, timeout_ms=args.timeout_ms)
    return {
        "status": "ok",
        "command": "auth.check",
        "message": "Okta session check completed.",
        "data": result.payload,
        "exit_code": 0,
    }


async def _handle_inspect(args: argparse.Namespace) -> dict[str, Any]:
    if args.demo or not (args.target or "").strip():
        items, trace = _demo_state_items()
        return {
            "status": "ok",
            "command": "inspect.state",
            "message": (
                "Demo attendance site state loaded."
                if args.demo
                else "Demo attendance site state loaded because no target was configured."
            ),
            "data": {
                "items": [item.to_dict() for item in items],
                "trace": [item.to_dict() for item in trace],
            },
            "exit_code": 0,
        }
    target = _require_target(args.target)
    items, trace = await _inspect_state(target, headed=args.headed, courses=args.course)
    return {
        "status": "ok",
        "command": "inspect.state",
        "message": "Attendance site state loaded.",
        "data": {
            "items": [item.to_dict() for item in items],
            "trace": [item.to_dict() for item in trace],
        },
        "exit_code": 4 if not any(item.dom_state == "open" for item in items) else 0,
    }


async def _handle_fetch(args: argparse.Namespace) -> dict[str, Any]:
    target = _require_target(args.target)
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
    target = _require_target(args.target)

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
    target = _require_target(args.target)
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
        written_files = materialize_plan(entries)
        return {
            "status": "ok",
            "command": "submit",
            "message": "Legacy plan materialized for submission.",
            "data": {
                "plan": summary,
                "written_files": written_files,
            },
            "exit_code": 0,
        }

    target = _require_target(args.target)
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

    target = _require_target(args.target)
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


def main(argv: list[str]) -> int:
    """Execute an AI-native CLI command."""
    parser = build_agent_parser()
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
        elif args.command == "resolve":
            payload = _handle_resolve(args)
        else:
            payload = asyncio.run(_pipeline_run(args))
    except AgentCliInputError as exc:
        payload = {"status": "error", "command": args.command, "error": str(exc), "exit_code": 2}
    except OktaCliError as exc:
        target = getattr(args, "target", None) or getattr(args, "url", "")
        if "No stored session found" in str(exc) and target:
            payload = _session_missing_payload(args.command, target, str(exc))
        else:
            payload = {"status": "error", "command": args.command, "error": str(exc), "exit_code": 3}
    except (SourceCommandError, SubmissionPlanError) as exc:
        payload = {"status": "error", "command": args.command, "error": str(exc), "exit_code": 1}
    return _emit(payload, json_output=json_output)
