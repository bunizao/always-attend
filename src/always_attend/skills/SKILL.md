---
name: attend-agent-workflow
description: Use this skill when an agent needs to bootstrap Always Attend on a cold machine, validate dependencies, and complete the attendance workflow with multimodal evidence.
---

# Attend Agent Workflow

Use this skill when working on Monash attendance with the `attend` CLI.

## Goal

Treat `attend` as the execution tool and the model as the multimodal analyst.

- `attend` reads the attendance site and external sources.
- `attend handoff --json` packages open items, text snippets, and image URLs.
- The model reads those artifacts and decides the likely attendance codes.
- `attend submit --plan ... --json` executes the final submission or dry run.

## User Interaction Contract

The agent is responsible for user interaction.
`attend` returns machine-readable state, but it does not run a conversational wizard.

Always translate command results into clear user feedback.
Do not make the user read raw JSON unless they explicitly ask for it.

### User Situations

Handle these situations explicitly:

1. Missing attendance base URL
2. Missing dependencies from `attend doctor --json`
3. Saved URL exists and can be reused
4. No reusable session is available
5. Browser cookie import succeeds
6. Browser cookie import fails and interactive login is required
7. Existing `storage_state` can be reused
8. No open attendance items exist
9. Open items exist but evidence is insufficient
10. Submission is rejected by the portal
11. DOM state is locked or post-submit state is unverified
12. Submission completes successfully

### Required Agent Behavior

For every run, follow this order:

1. Run `attend doctor --json`
2. If the target URL is missing, ask the user for the attendance base URL
3. If the user wants that URL reused later, run `attend config set --target <attendance-url> --json`
4. If session access is required, run `attend auth login <attendance-url> --json`
5. Explain whether auth succeeded by browser cookie import or interactive login
6. Run the requested inspect, handoff, match, submit, or run command
7. Summarize the outcome in user language

### Feedback Rules

The agent must always tell the user:

- what URL is being used
- whether the URL is only for this run or saved for future reuse
- whether auth reused browser cookies or required manual login
- what succeeded
- what failed
- what needs user action next

### Standard Feedback Chain

Use this response pattern:

1. Environment status
   Tell the user whether dependencies are ready or which install commands are required.
2. Target status
   If the attendance URL is missing, ask for it.
   Save it only when the user wants it reused later.
3. Auth status
   Tell the user that browser cookie import will be attempted first.
   If that fails, tell them an interactive login window is required.
4. Execution status
   Tell the user which command is running and why.
5. Outcome summary
   Group the result into submitted, unresolved, rejected, locked, and next action.

### Required Wording Intent

Keep the wording direct and explicit.

- Missing URL: ask for the attendance base URL and ask whether it should be saved as the default
- Cookie import success: say login was reused and no manual login is needed
- Interactive login required: say a window must be completed by the user
- Success: say how many items were submitted and what remains unresolved
- Failure: say which stage failed and what the next user action is

## Bootstrap

Read `BOOTSTRAP.md` only when the machine is not already ready for `attend`.

Use that file for:

- first-run setup on a blank machine
- `attend: command not found`
- missing Python, `uv`, or Always Attend install
- `doctor --json` dependency repair
- Playwright browser installation
- the handoff to `attend auth login`

## Workflow

### 1. Build the handoff package

Run:

```bash
attend handoff --target <attendance-url> --json
```

If you do not have a live session yet, use:

```bash
attend handoff --demo --json
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

### 2. Analyze evidence

For each open item:

- Start from course, week, class type, time, and group from the attendance site
- Use text snippets first
- Use image URLs when the source data points to screenshots or embedded images
- Prefer confidence over speed
- Do not invent a code if evidence is weak or conflicting

### 3. Produce a plan

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

### 4. Submit or dry run

Dry run first when possible:

```bash
attend submit --plan plan.json --target <attendance-url> --dry-run --json
```

Then real submit:

```bash
attend submit --plan plan.json --target <attendance-url> --json
```

### 5. Final reporting

After submit, use:

```bash
attend report --target <attendance-url> --json
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
- Do not silently switch to demo mode when a real attendance URL is required
- Do not leave the user without a plain-language summary of failures and next actions
