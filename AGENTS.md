# Always Attend Agent Guide

## Branch Focus

This branch turns `attend` into an agent-first CLI.

The primary interface is:

- `attend run`
- `attend inspect state`
- `attend fetch`
- `attend match`
- `attend submit`
- `attend report`
- `attend doctor`
- `attend auth login`
- `attend auth check`

Agents should treat the attendance site DOM as the source of truth.
Do not start from Gmail, Moodle, or Ed and guess which item is fillable.

## Current Architecture

Core agent-native modules live in `src/always_attend/`:

- `agent_cli.py`: public agent command surface
- `agent_protocol.py`: stable state, candidate, match, submit, and trace types
- `session_manager.py`: shared Okta session and dependency checks
- `attendance_state_reader.py`: read and classify attendance DOM state
- `source_collectors/`: Gmail, Moodle, Ed, and GOG collectors
- `code_parser.py`: extract structured code candidates
- `matcher.py`: five-field matching and confidence scoring
- `submitter.py`: guarded submit flow and post-submit verification
- `reporter.py`: stable summary, metrics, and structured trace output

Legacy portal automation still exists under `src/core/`.
Use it only as a transition layer for browser interactions that have not yet been rewritten.

## Non-Negotiable Rules

- Only comments written in English are allowed.
- Use Conventional Commits only.
- Prefer simple, production-friendly code.
- Do not add heavy abstractions for small features.
- Keep APIs small and behavior explicit.
- Do not guess from human intuition when the DOM, source data, or logs can decide it.
- Do not silently fall back to weaker behavior without a trace event.
- Any agent-facing command must support machine-readable output.
- Standard output must stay clean and machine-readable when `--json` is used.

## Decision Rules

- Attendance state comes first.
  Read `Units.aspx` or `Entry.aspx` before collecting external data.
- Source priority is fixed.
  Use: attendance metadata -> Gmail plain text -> Moodle plain text -> Moodle HTML table -> Ed text -> image links for multimodal analysis.
- Matching is structured.
  Match on `course_code`, `class_type`, `date`, `time_range`, and `group`.
- Submit is guarded.
  High-confidence matches submit directly.
  Mid-confidence matches use best-effort submit and must be re-read from the DOM.
  Low-confidence matches stay unresolved.
- Every important branch must emit a structured trace event.

## Next Iteration Priorities

The next iteration should improve the tool in this order:

1. Replace more legacy `src/core/submit.py` behavior with native logic inside `submitter.py`.
2. Add first-class support for separate groups in Moodle and Ed collectors.
3. Improve candidate parsing for Moodle rich content and image-heavy Ed posts.
4. Improve the AI handoff package so image URLs and text evidence are easier for multimodal models to consume.
5. Strengthen submit-state classification for incorrect code, wrong week, locked DOM, and post-submit unverified states.
6. Expand `attend run` end-to-end tests with realistic saved artifacts and dry-run scenarios.

Do not spend the next iteration on packaging, release automation, or UI polish.
This branch is not trying to be release-ready yet.
It is trying to become reliably agent-executable.

## Commands For Validation

Use these commands unless the task clearly needs something else:

- `PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'`
- `PYTHONPATH=src python -m always_attend doctor --json`
- `PYTHONPATH=src python -m always_attend run --help`
- `PYTHONPATH=src python -m always_attend inspect state --help`
- `PYTHONPATH=src python -m always_attend match --help`

When changing parsing, matching, state reading, or reporting logic, add or update focused tests under `tests/`.

## Acceptance Standard

Do not claim success unless you have executed the affected path.

Minimum bar:

- The code compiles.
- The changed command or branch was run.
- The observed output matches the expected state or schema.
- Tests covering the change pass.
- Any missing dependency or unsupported path is surfaced explicitly in JSON output or trace events.
