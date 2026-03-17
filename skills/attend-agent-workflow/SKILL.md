---
name: attend-agent-workflow
description: Use this skill when an agent needs to complete the Always Attend workflow with multimodal evidence. It guides the agent to use `attend doctor`, `attend handoff`, and `attend submit` so image links from Moodle or Ed can be analyzed by the model instead of local OCR.
---

# Attend Agent Workflow

Use this skill when working on Monash attendance with the `attend` CLI.

## Goal

Treat `attend` as the execution tool and the model as the multimodal analyst.

- `attend` reads the attendance site and external sources.
- `attend handoff --json` packages open items, text snippets, and image URLs.
- The model reads those artifacts and decides the likely attendance codes.
- `attend submit --plan ... --json` executes the final submission or dry run.

## Workflow

### 1. Check the environment

Run:

```bash
PYTHONPATH=src python -m always_attend doctor --json
```

If `okta`, `playwright`, `moodle`, or `edstem` are missing, stop and report that clearly.

Do not block on OCR. Image links are meant for the model to inspect directly.

When a required CLI is missing, install it before continuing:

```bash
uv tool install okta-auth-cli
uv tool install moodle-cli
uv tool install edstem-cli
```

If `doctor --json` returns an `install_hint`, prefer that exact command.

### 2. Build the handoff package

Run:

```bash
PYTHONPATH=src python -m always_attend handoff --target <attendance-url> --json
```

If you do not have a live session yet, use:

```bash
PYTHONPATH=src python -m always_attend handoff --demo --json
```

That command returns a schema-valid demo payload so the workflow can still be validated end to end.

The handoff payload contains:

- `open_items`: attendance-site items that are actually fillable
- `candidate_hints`: text-derived candidate codes
- `artifacts`: source payload summaries with:
  - `image_urls`
  - `text_snippets`
  - `course_codes`
- `trace`: structured collection events
- `plan_contract`: the exact JSON shape the model should write before submission

Treat `open_items` as the source of truth.
Treat `artifacts` as evidence.

### 3. Analyze evidence

For each open item:

- Start from course, week, class type, time, and group from the attendance site
- Use text snippets first
- Use image URLs when the source data points to screenshots or embedded images
- Prefer confidence over speed
- Do not invent a code if evidence is weak or conflicting

### 4. Produce a plan

Write a JSON plan in this shape:

```json
[
  {
    "course_code": "FIT2099",
    "week": 7,
    "slot": "Workshop 01",
    "code": "ABCDE"
  }
]
```

Rules:

- Only include items you believe are strong enough to submit
- If evidence is ambiguous, leave the item out and report it as unresolved
- Keep slot labels aligned with the attendance-site item, not the source wording
- Use `plan_contract` from the handoff payload as the authoritative schema when it is present

### 5. Submit or dry run

Dry run first when possible:

```bash
PYTHONPATH=src python -m always_attend submit --plan plan.json --target <attendance-url> --dry-run --json
```

Then real submit:

```bash
PYTHONPATH=src python -m always_attend submit --plan plan.json --target <attendance-url> --json
```

### 6. Final reporting

After submit, use:

```bash
PYTHONPATH=src python -m always_attend report --target <attendance-url> --json
```

Summarize:

- what was submitted
- what remains unresolved
- what was locked
- what evidence was used
- any image URLs that still require human or higher-confidence review

## Guardrails

- Do not guess from Moodle or Ed before reading the attendance site
- Do not treat source screenshots as local OCR work
- Do not submit low-confidence codes just because an image exists
- Do not hide unresolved items; they are part of the output
