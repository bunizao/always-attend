# always-attend

Automates submitting weekly attendance codes on the Monash site, including Okta MFA handling.

Highlights:
- Runs locally (Python or Docker) using Playwright.
- Handles Okta login with TOTP or manual code entry.
- Reuses a persisted session (`storage_state.json`) to reduce MFA prompts.
- Reads codes from a JSON URL (e.g., produced by GitHub Actions) or a local file.
- Optional auto-discovery: if you expose codes at `CODES_BASE_URL/data/{COURSE_CODE}/{WEEK_NUMBER}.json`, the script can find them automatically.

## Quick start (Python)

1) Create and activate venv

```bash
python3 -m venv .venv
. .venv/bin/activate
```

2) Install deps and browsers

```bash
pip install -U pip setuptools wheel
pip install -r requirements.txt
python -m playwright install chromium
```

3) Copy `.env.example` to `.env` and fill values (username/password, TOTP_SECRET or MFA_CODE, and either CODES_URL or CODES_FILE).

4) Run

```bash
python main.py
```

Interactive Okta login (headed browser) to prime session only:

```bash
HEADLESS=0 INTERACTIVE_LOGIN=1 LOGIN_ONLY=1 python main.py
```
This opens a browser window for you to complete Okta login. After finishing MFA and returning to the portal, press Enter in the terminal. The script saves `storage_state.json` and exits. Subsequent runs can be headless using the saved state.

## Quick start (Docker)

```bash
docker build -t always-attend .
docker run --rm \
  --env-file .env \
  -v "$(pwd)/data:/data" \
  -e STORAGE_STATE=/data/storage_state.json \
  always-attend
```

Or with docker-compose:

```bash
mkdir -p data
docker compose up --build
```

Interactive login in Docker:

```bash
docker run --rm -it \
  --env-file .env \
  -e STORAGE_STATE=/data/storage_state.json \
  -e HEADLESS=0 -e INTERACTIVE_LOGIN=1 -e LOGIN_ONLY=1 \
  -v "$(pwd)/data:/data" \
  always-attend
```

## Code source options

- `CODES_URL`: HTTP(S) URL pointing to JSON produced by OCR/Actions.
- `CODES_FILE`: local JSON file path.
- `CODES`: semicolon-separated `slot:code` pairs for ad-hoc runs.
- Auto-discovery via:
  - `COURSE_CODE` (e.g., FIT1111), `WEEK_NUMBER` (e.g., 3), and `CODES_BASE_URL` (e.g., `https://raw.githubusercontent.com/<org>/<repo>/main`).
  - The script will request `CODES_BASE_URL/data/{COURSE_CODE}/{WEEK_NUMBER}.json`.

Example JSON:

```json
[
  {"date": "2025-08-18", "slot": "Workshop 1", "code": "JZXBA"},
  {"date": "2025-08-19", "slot": "Workshop 2", "code": "AJYV7"}
]
```

## Okta MFA

- Preferred: provide `TOTP_SECRET` (Base32) so the script generates 6‑digit codes automatically.
- One-off: set `MFA_CODE` for a single run, or run interactively and enter the code when prompted.
- The script attempts to switch to a “Use/Enter a code” flow if push is the default.

## Persistence

- The script stores an authenticated state in `STORAGE_STATE` (default `storage_state.json`).
- On subsequent runs, this state is loaded to reduce redundant MFA challenges.

## CLI

You can use subcommands and flags for clearer workflows.

```bash
# Submit codes (default behavior)
python main.py submit --browser chromium

# Interactive Okta login only (prime storage state, then exit)
python main.py login --headed --interactive
```

Flags:
- `--browser`: `chromium|firefox|webkit` (overrides `BROWSER`).
- `--headed`: show browser UI (sets `HEADLESS=0`).
- `--interactive`: wait for you to finish Okta login in the opened browser (sets `INTERACTIVE_LOGIN=1`).

If no subcommand is provided, `submit` is assumed.

## Environment variables

- `PORTAL_URL`: Monash portal entry, e.g. `https://attendance.monash.edu.my/student/Default.aspx`.
- `USERNAME` / `PASSWORD`: Okta credentials.
- `TOTP_SECRET`: Base32 secret for 6‑digit OTP generation (preferred MFA).
- `MFA_CODE`: One‑off code for a single run (when no `TOTP_SECRET`).
- `CODES_URL`: HTTP(S) URL to JSON (e.g. from GitHub Actions/OCR output).
- `CODES_FILE`: Local JSON file path for codes.
- `CODES`: Fallback inline pairs, e.g. `"Workshop 1:ABCDE;Applied 1:6B7UF"`.
- `COURSE_CODE` / `WEEK_NUMBER` / `CODES_BASE_URL`: enable auto-discovery at `CODES_BASE_URL/data/{COURSE_CODE}/{WEEK_NUMBER}.json`.
- `ISSUES_NEW_URL`: link to your New Issue page to submit missing codes.
- `BROWSER`: `chromium|firefox|webkit` (default `chromium`).
- `HEADLESS`: `1` (default) or `0` to show browser UI.
- `INTERACTIVE_LOGIN`: `1` to let you manually complete Okta login.
- `LOGIN_ONLY`: `1` to only login and save `STORAGE_STATE`, then exit.
- `STORAGE_STATE`: Path to save/load storage state (default `storage_state.json`).

## Workflow with GitHub Actions (optional)

Let an Action OCR the attendance code from issue attachments, write a `codes.json` to your repo, then run locally with:

```bash
export CODES_URL="https://raw.githubusercontent.com/<org>/<repo>/main/codes.json"
python main.py
```

This keeps secrets local while sharing only the codes JSON publicly.

With the provided workflow and template, each issue generates:

- `data/{COURSE_CODE}/{WEEK_NUMBER}.json` in the repository.
- A comment with the Raw URL. You can set `CODES_BASE_URL=https://raw.githubusercontent.com/<org>/<repo>/main`, `COURSE_CODE`, and `WEEK_NUMBER` to let the script auto-discover the JSON, or set `CODES_URL` directly.


## Prebuilt images (CI)

This repo includes a GitHub Actions workflow that builds multi-arch Docker images and pushes to GHCR on every push to `main` and on tags (`v*`).

- Registry: `ghcr.io/<owner>/<repo>` (all lowercase)
- Example pull:
  - `docker pull ghcr.io/<owner>/<repo>:main`
  - `docker pull ghcr.io/<owner>/<repo>:<git-sha>`
  - `docker pull ghcr.io/<owner>/<repo>:v1.0.0`

You can then run with your `.env` as shown above:

```bash
docker run --rm --env-file .env ghcr.io/<owner>/<repo>:main
```

