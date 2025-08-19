# always-attend

Automates submitting weekly attendance codes on the Monash site, including Okta MFA handling.

Highlights:
- Runs locally using Python and Playwright.
- Handles Okta login with TOTP or manual code entry.
- Reuses a persisted session (`storage_state.json`) to reduce MFA prompts.

## Logging & Debugging

- Control verbosity via `LOG_LEVEL` env: `DEBUG` | `INFO` | `WARN` | `ERROR` (default: `INFO`).
- Disable ANSI colors with `NO_COLOR=1`.
- Write logs to a file by setting `LOG_FILE=run.log`.
- Extra scraping dump: `DEBUG_SCRAPING=1` will print page HTML while discovering courses.
- Reads codes from a JSON URL, a local file, or environment variables.
- Optional auto-discovery for codes from a base URL.

## How it works

This project consists of two main scripts:

1.  `login.py`: An interactive script to log in to the Monash portal and save your session to a file (`storage_state.json`). This is typically done once to prime the session.
2.  `submit.py`: A script to automatically submit your attendance codes using the saved session.

## Quick start

1.  **Set up your environment**

    Create and activate a Python virtual environment:

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

2.  **Install dependencies**

    Install the required Python packages and browser binaries for Playwright:

    ```bash
    pip install -U pip setuptools wheel
    pip install -r requirements.txt
    python -m playwright install chromium
    ```

3.  **Configure the project**

    Copy the example environment file and edit it with your details:

    ```bash
    cp .env.example .env
    ```

    Now, open `.env` and fill in the required values:
    -   `PORTAL_URL`: The URL to the Monash attendance portal.
    -   `USERNAME` and `PASSWORD`: Your Monash account credentials.
    -   `TOTP_SECRET`: Your MFA secret key (Base32). This is the preferred way to handle MFA.
    -   Set one of the `CODES_*` variables to provide the attendance codes. See the "Code source options" section.

4.  **Log in and create a session**

    Run the interactive login script. This will open a browser window for you to complete the login process.

    ```bash
    python login.py --headed
    ```

    Follow the instructions in the terminal. After you have successfully logged in and the `storage_state.json` file is created, you can close the browser.

5.  **Submit your codes**

    Run the submit script to submit your attendance codes:

    ```bash
    python submit.py
    ```

    The script will use the saved session in `storage_state.json` to submit the codes without needing to log in again.

## Code source options

You can provide attendance codes to the script in several ways (in order of precedence):

1.  **Per-slot environment variables**: Set environment variables like `WORKSHOP_1=CODE1` and `APPLIED_2=CODE2`.
2.  **Auto-discovery**: Set `COURSE_CODE`, `WEEK_NUMBER`, and `CODES_BASE_URL` to automatically fetch codes from a URL like `CODES_BASE_URL/data/{COURSE_CODE}/{WEEK_NUMBER}.json`.
3.  `CODES_URL`: An HTTP(S) URL pointing to a JSON file with the codes.
4.  `CODES_FILE`: A local path to a JSON file with the codes.
5.  `CODES`: A semicolon-separated string of `slot:code` pairs (e.g., `"Workshop 1:ABCDE;Applied 1:FGHIJ"`).

**Example JSON format:**
```json
[
  {"date": "2025-08-18", "slot": "Workshop 1", "code": "JZXBA"},
  {"date": "2025-08-19", "slot": "Workshop 2", "code": "AJYV7"}
]
```

## Command-line arguments

### `login.py`
```bash
python login.py [options]
```
-   `--headed`: (Recommended) Show the browser UI for interactive login.
-   `--portal URL`: Override the portal URL from the environment.
-   `--browser NAME`: Choose the browser (`chromium`, `firefox`, `webkit`).
-   `--check`: After login, verify that the session is valid.
-   `--check-only`: Only verify the current session state without logging in.

### `submit.py`
```bash
python submit.py [options]
```
-   `--dry-run`: Parse codes and print them without submitting.
-   `--browser NAME`: Choose the browser (`chromium`, `firefox`, `webkit`).
-   `--headed`: Show the browser UI.

## Environment variables

-   `PORTAL_URL`: Monash portal entry URL.
-   `USERNAME`, `PASSWORD`: Okta credentials.
-   `TOTP_SECRET`: Base32 secret for 6-digit OTP generation.
-   `MFA_CODE`: A one-off MFA code for a single run (if `TOTP_SECRET` is not set).
-   `CODES_URL`: URL to a JSON file with codes.
-   `CODES_FILE`: Local path to a JSON file with codes.
-   `CODES`: Inline `slot:code;...` string.
-   `COURSE_CODE`, `WEEK_NUMBER`, `CODES_BASE_URL`: For auto-discovery.
-   `ISSUES_NEW_URL`: Issue creation URL to report missing codes (defaults to the project issues page).
-   `BROWSER`: `chromium` (default), `firefox`, or `webkit`.
-   `HEADLESS`: `1` (default) or `0` to show browser UI.
-   `STORAGE_STATE`: Path to save/load the session state (default: `storage_state.json`).

## GitHub Actions Workflow

This repository includes a GitHub Actions workflow that can be used to automatically extract attendance codes from issues and create a JSON file. You can then use this JSON file with `CODES_URL` to submit your attendance. This helps in keeping your credentials secure while automating the code retrieval process.
