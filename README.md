# always-attend-mvp

Prototype implementation for a single attendance submission, built with TDD and Playwright.

## Iteration I1 – Prototype a Single Submission

This iteration loads one attendance code from a local JSON file and drives a Playwright
browser session to submit it. The run logs a single success line with elapsed time to
mirror the validation workflow from the full project.

## Getting Started

1. Create and activate a virtual environment (recommended):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies and Playwright browser binaries:
   ```bash
   pip install -r requirements.txt
   python -m playwright install chromium
   ```

## Prepare Inputs

Create a JSON file containing the attendance code you want to submit:

```json
[
  {"slot": "Workshop 1", "code": "ABCD1"}
]
```

Collect the selectors for the portal you want to automate: the code input field, submit
button, and success indicator.

## Run the Prototype

```bash
python main.py \
  --codes path/to/codes.json \
  --portal-url "https://portal.example.edu/attendance" \
  --code-input-selector "input[name='code']" \
  --submit-button-selector "button[type='submit']" \
  --success-selector "text=Submission received"
```

Optional flag:
- `--headed` runs the browser in headed mode (default headless).

Logs show the elapsed time, confirming selectors and flow for a single submission.

## Tests

Run the TDD suite:

```bash
pytest
```

These tests cover JSON code loading and orchestration between the code source and
navigator.
