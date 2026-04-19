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

### Final Goal

The goal is simple:
fill every attendance item that is actually open on the attendance site.

Use every available source and every reasonable method to reach that goal:

- attendance DOM state
- Moodle
- Ed
- Gmail via `gmail-cli`, `gws`, or the Codex Gmail plugin connector when available
- text evidence
- image evidence
- direct manual reasoning over the handoff payload
- direct browser interaction when needed

Do not stop at the first weak `match` result.
If the automatic match is noisy, keep digging through the source artifacts yourself.

### Practical Rules

- Treat the attendance site DOM as the source of truth for what is fillable
- Treat `match` as a helper, not the final decision maker
- Prefer explicit attendance-code evidence over generic titles or labels
- Prefer short code-shaped tokens when the evidence suggests a real attendance code
- Prefer Moodle forum posts and image tables when they contain the actual session codes
- If one source is weak, keep searching other sources before giving up
- If the available CLI output is not enough, use the browser directly to inspect the relevant page

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

### Submission Policy

Before any real submit:

1. Build the best plan you can for all currently open items
2. Run `attend submit --plan ... --dry-run --json`
3. Check that the dry run aligns with the intended course, slot, and week
4. Run the real submit command
5. After submit, re-read the DOM or run `attend report --json`

If some items are still unresolved, submit the ones you are confident about and keep working on the rest.

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

- `decision_packet`: the canonical evidence bundle for agent planning
- `open_items`: attendance-site items that are actually fillable
- `candidate_hints`: text-derived candidate codes
- `matches`: structured local matches and evidence references
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
    "item_id": "FIT2099:visible:0:Workshop 01",
    "course_code": "FIT2099",
    "week": 7,
    "slot": "Workshop 01",
    "code": "ABCDE",
    "confidence": 0.97,
    "matched_fields": ["course_code", "class_type", "date", "time_range", "group"],
    "reason": "Strong five-field match.",
    "evidence_refs": ["$.threads[0].body"],
    "source": "edstem"
  }
]
```

Rules:

- `course_code`, `week`, `slot`, and `code` are required
- `item_id`, `confidence`, `matched_fields`, `reason`, `evidence_refs`, and `source` are strongly preferred when available
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
- Do not treat generic uppercase text extracted by the parser as a real attendance code without checking context
- Do not give up after one weak source if other sources are still available
