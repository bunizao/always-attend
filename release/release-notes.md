# always-attend 0.2.0

Introducing the new always-attend for agents.

## Highlights

- `attend` is now agent-first. The main surface centers on `run`, `inspect`, `match`, `submit`, `report`, `doctor`, and `auth`.
- Attendance state is read from the portal DOM before external sources are consulted, so the tool stops guessing blind.
- Gmail, Moodle, Ed, and GOG collectors now feed structured candidates and multimodal handoff artifacts into the matching flow.
- Matching and submission are guarded by explicit confidence thresholds, structured trace events, and post-submit verification.
- Setup and bundled skill flows are designed for agent execution, including machine-readable output paths and bootstrap guidance.

## What Changed

- Replaced more of the legacy human-first CLI flow with native agent commands under `src/always_attend/`.
- Added source collection, code parsing, matcher, submitter, reporter, and session manager modules for the agent workflow.
- Expanded test coverage around agent CLI commands, state reading, parser and matcher logic, source clients, reporting, and mock portal integration.
- Tightened the README and bootstrap story around agent use instead of interactive-user handholding.

## Upgrade Notes

- This release finalizes the earlier `0.2.0a0` prerelease as stable `0.2.0`.
- If you installed the prerelease with `uv tool`, upgrade with `uv tool upgrade always-attend`.
