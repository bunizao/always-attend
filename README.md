<h1 align="center">Always Attend</h1>
<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg">
  <img src="https://img.shields.io/badge/License-GPLv3-blue.svg">
  <img src="https://img.shields.io/github/last-commit/bunizao/always-attend">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey">
  <p align="center">  
  <img src="https://img.shields.io/badge/status-Public%20Beta-orange?style=for-the-badge">
<p align="center">
  An automation helper to submit weekly attendance codes. Now in Public Beta.<br>
  ⚠️ <b>Use responsibly and follow your institution’s policies.</b>
</p>

<p align="center">
  <a href="README_zh.md"><b>中文文档</b></a>
</p>

> [!WARNING]  
> This project is currently in **Public Beta**. Features may change and bugs are expected.     
> Receive Feedback Here: [![Open Issue](https://img.shields.io/badge/Open-Issue-blue)](https://github.com/bunizao/always-attend/issues/new)







## 📥 Get Always Attend

Install the CLI using one of these two supported flows:

### Option 1 — `uv tool` (recommended)
1. Install [uv](https://docs.astral.sh/uv/) if it is not already available:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. Install `always-attend` and expose the bundled `playwright` executable:
   ```bash
   uv tool install --with-executables-from playwright always-attend
   ```
3. Verify the CLI:
   ```bash
   attend --help
   ```

The app prefers your installed Chrome/Edge. If Playwright Chromium is needed and missing, it will be downloaded automatically on first run.

If `attend` is not on your shell `PATH` yet, run:

```bash
uv tool update-shell
```

### Option 2 — `pipx`
1. Install [pipx](https://pipx.pypa.io/stable/installation/) if needed:
   ```bash
   python3 -m pip install --user pipx
   python3 -m pipx ensurepath
   ```
2. Install `always-attend`:
   ```bash
   pipx install always-attend
   ```
3. Expose the `playwright` executable from the injected package:
   ```bash
   pipx inject --include-apps always-attend playwright
   ```
4. Verify the CLI:
   ```bash
   attend --help
   ```

## 🚀 Run The CLI

Public command:

- `attend`

## 🤖 Agents-First Workflow

`attend` is now the single agent-facing entrypoint. The intended execution model is:

1. `attend auth ...` delegates Okta login and session checks to the external `okta` CLI.
2. `attend fetch ...` calls `moodle-cli`, `edstem`, or `gogcli` and passes shared Okta cookie context through environment variables.
3. `attend resolve ...` normalizes an agent-authored submission plan into a stable JSON shape.
4. `attend submit ...` materializes the resolved plan into the local codes store and reuses the Playwright submitter for the final portal submission.

### Quick Start

```bash
# Inspect runtime locations for integrations
attend paths --json

# Refresh or create the shared Okta session
attend auth login https://attendance.example.edu --json

# Check whether the shared session is still valid
attend auth check https://attendance.example.edu --json

# Fetch source data
attend fetch --source edstem --json
attend fetch --source edstem --course FIT2099 --kind threads --json

# Validate a submission plan
attend resolve --plan plan.json --json

# Submit a validated plan
attend submit --plan plan.json --portal-url https://attendance.example.edu --json
```

### Shared Session Contract

When `attend fetch` runs, it exports the shared Okta session to child CLIs using these environment variables:

- `ALWAYS_ATTEND_OKTA_URL`
- `ALWAYS_ATTEND_OKTA_COOKIES_JSON`
- `ALWAYS_ATTEND_OKTA_COOKIE_HEADER`
- `OKTA_COOKIES_JSON`
- `OKTA_COOKIE_HEADER`

Adapters should consume these values instead of implementing their own interactive login flow.

Runtime files default to standard user directories:
- Linux:
  `~/.config/always-attend/.env`,
  `~/.local/state/always-attend/`,
  `~/.local/share/always-attend/codes/`
- macOS:
  `~/Library/Application Support/always-attend/config/.env`,
  `~/Library/Application Support/always-attend/state/`,
  `~/Library/Application Support/always-attend/data/codes/`
- Windows:
  `%APPDATA%\\always-attend\\config\\.env`,
  `%LOCALAPPDATA%\\always-attend\\state\\`,
  `%LOCALAPPDATA%\\always-attend\\data\\codes\\`
- Override any location with env vars such as `ENV_FILE`, `STORAGE_STATE`, `ATTENDANCE_STATS_FILE`, or `CODES_DB_PATH`

Integration contract:
- CLI: `attend paths --json`
- Python: `from always_attend import get_runtime_paths_dict`

## 📦 Attendance Database

Always Attend now reads attendance codes exclusively from `codes_db_path` (by default a dedicated `codes/` directory under the app data directory, or from `CODES_DB_PATH` if overridden). Each course gets its own subfolder and every week is represented by a JSON file:

```
data/
  FIT1045/
    3.json     # [{"slot": "Workshop 01", "code": "LCPPH"}, ...]
  FIT1047/
    7.json
```

If you maintain your codes in a separate Git repository, point the tool at it:

```bash
export CODES_DB_REPO="git@github.com:you/attendance-db.git"
export CODES_DB_BRANCH="main"
```

On every run the repository is cloned into `codes_db_path` (if missing) or updated in place before submission. Without a repository the tool simply reads whatever JSON files already exist there.

## 📊 Statistics Tracking

The tool now automatically tracks your attendance submission statistics:

```bash
# View detailed statistics
attend stats

# Or use the stats module directly
python stats.py
```

Statistics include:
- Total runs and success rate
- Codes submitted per course
- Recent activity timeline
- Error history

## Troubleshooting

- If login keeps asking for MFA: re-run the headed login to refresh the saved session state
- If the browser fails to launch: make sure Google Chrome or Microsoft Edge is installed, or set `BROWSER_CHANNEL` to `chrome`/`msedge`.
- If `attend` is not found after install: restart the terminal, then run `uv tool update-shell` or `python3 -m pipx ensurepath`.
- When running, please do NOT use a VPN, as this may cause Okta to refuse the connection.

## FAQ (Windows)

- **Use `py` instead of `python`**: If `python` isn't found or points to another version, use `py` for bootstrap commands such as `py -m pip install --user pipx`.
- **Switching between Git Bash and PowerShell**: In terminals like VS Code, use the dropdown to open a new Git Bash or PowerShell window. Some commands (e.g., `source`) only work in Git Bash, while PowerShell uses `.\` for scripts.
- **Path escaping issues**: PowerShell uses backslashes (`\`) and may treat them as escape characters. Wrap paths in quotes or use double backslashes like `C:\path\to\file`. Git Bash uses forward slashes (`/`).

## Command-Line Arguments

Primary command: `attend`

| Argument | Type | Description | Example |
| --- | --- | --- | --- |
| `--browser` | string | Browser engine (`chromium`/`firefox`/`webkit`) | `--browser chromium` |
| `--channel` | string | System browser channel (chromium only: `chrome`, `chrome-beta`, `msedge`, etc.) | `--channel chrome` |
| `--headed` | flag | Show browser UI (sets `HEADLESS=0`) | `--headed` |
| `--dry-run` | flag | Print parsed codes and exit without submitting | `--dry-run` |
| `--week` | int | Submit codes for a specific week (sets `WEEK_NUMBER`) | `--week 4` |
| `--login-only` | flag | Refresh the session and exit without submitting | `--login-only` |
| `--stats` | flag | Display cached attendance statistics and exit | `--stats` |
| `--setup` | flag | Launch the configuration wizard interactively | `--setup` |
| `--debug` | flag | Enable debug logging profile | `--debug` |
| `--verbose` | flag | Enable verbose logging profile | `--verbose` |
| `--skip-update` | flag | Skip the git update check before running | `--skip-update` |

## Release Automation

- Push a version tag such as `v0.1.1` to trigger `.github/workflows/release.yml`.
- The workflow validates that the tag matches `pyproject.toml`, builds `sdist` and `wheel`, creates a GitHub Release, and publishes to PyPI.
- PyPI publishing is configured for Trusted Publishing, so the GitHub repository still needs to be registered as a trusted publisher in the target PyPI project.

## Reflection

> I kept building, not to compete with AI, but to finish what I started. I kept adding new ideas, refactoring, polishing small things that no one else would notice. Slowly, the project became not just a tool but a reflection of my curiosity and patience. Finishing it reminded me that the value isn't only in what a program does, but in what I learn while making it.

## Environment Variables

| Variable | Type | Required | Description | Example |
| --- | --- | --- | --- | --- |
| `PORTAL_URL` | string URL | Yes | Attendance portal base URL | `https://attendance.monash.edu.my` |
| `CODES_DB_PATH` | string path | No | Root folder containing `COURSE/WEEK.json` files | `/srv/attendance-data` |
| `CODES_DB_REPO` | string URL | No | Git repository that mirrors the data tree | `git@github.com:you/attendance-db.git` |
| `CODES_DB_BRANCH` | string | No | Branch to checkout when syncing the repository | `main` |
| `WEEK_NUMBER` | int | No | Force a specific week instead of auto-detecting | `4` |
| `SUBMIT_CONCURRENCY` | int | No | Maximum courses processed concurrently | `2` |
| `SUBMIT_TARGET_CONCURRENCY` | int | No | Parallel submission workers per course | `3` |
| `USERNAME` | string | No | Okta username for auto-login | `student@example.edu` |
| `PASSWORD` | string | No | Okta password for auto-login | `correcthorsebattery` |
| `TOTP_SECRET` | string (base32) | No | MFA TOTP secret for auto-login | `JBSWY3DPEHPK3PXP` |
| `AUTO_LOGIN` | flag (0/1) | No | Toggle automatic login | `1` |
| `BROWSER` | string | No | Engine override (`chromium`/`firefox`/`webkit`) | `chromium` |
| `BROWSER_CHANNEL` | string | No | System channel (`chrome`/`msedge`/etc.) | `chrome` |
| `HEADLESS` | flag (0/1 or true/false) | No | Run without UI (0 disables) | `0` |
| `USER_DATA_DIR` | string path | No | Persistent browser profile directory | `~/.always-attend-profile` |
| `LOG_PROFILE` | string | No | Logging profile (`user`/`quiet`/`debug`/`verbose`) | `verbose` |
| `LOG_FILE` | string path | No | Optional log file destination | `/tmp/always-attend.log` |
| `SKIP_UPDATE_CHECK` | flag (0/1 or true/false) | No | Skip remote git pull when set | `1` |

## Disclaimer

- This project is for educational and personal use only. Use it responsibly and follow your institution’s policies and the website’s terms of use.
- This project is not affiliated with, endorsed by, or sponsored by any university or service provider. All product names, logos, and brands are property of their respective owners.
- You are solely responsible for any use of this tool and any consequences that may arise. The authors provide no guarantee that it will work for your specific setup.

## License

- This project is licensed under the GNU General Public License v3.0 (GPL‑3.0). See the full text in the `LICENSE` file.
- You may copy, modify, and distribute this software under the terms of the GPL‑3.0. It is provided “as is”, without any warranty.
