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







## 🚀 Easy Launch

Double‑click to run with the enhanced first‑time setup:

- macOS: double‑click `Always-Attend.command`
- Windows: double‑click `Always-Attend.bat` (or run `Always-Attend.ps1`)

What the launchers do:
- Check for Python (and Git if available)
- Create/activate a virtualenv and install dependencies on first run
- Run a first‑time setup wizard (portal URL, credentials, week, browser)
- Auto‑detect the latest week from `data/*/*.json` and set `WEEK_NUMBER`
  - To prompt every run, set `WEEK_PROMPT=1`
- Simplified execution: calls `python main.py` with no complex menus

First‑time setup features:
- ASCII art banner
- Privacy policy display with consent on first run
- University configuration, including a quick Monash Malaysia option
- Email and password input
- Week number configuration

Notes:
- Git is optional; if not installed, update steps are skipped
- Chrome/Edge must be installed (uses your system browser by default)

Quick start:
```bash
# macOS: Double‑click Always-Attend.command
# Windows: Double‑click Always-Attend.bat

# Or run directly
python main.py
```
When you run it:
- A setup wizard guides configuration if needed
- Privacy policy is shown for awareness and consent
- Supported universities get auto‑configuration (Monash Malaysia option available)
- Intelligent submission: precise slot matching and optimized polling
- If no valid session is found, a browser opens for SSO and MFA; the session is saved
- The tool navigates to your portal and submits codes; watch logs for results
- Optional flags: `--headed`, `--dry-run`, `--week N`

Update later:
```bash
git pull
```

---

See the Environment Variables section below for a full list.

## 📦 Code Sources

Provide attendance codes via one of the sources below (in priority order):

```bash
# Inline codes
export CODES="Workshop 1:ABCD1;Workshop 2:EFGH2"

# Or local file (JSON array of {slot, code, date?})
export CODES_FILE=/path/to/codes.json

# Or remote JSON URL
export CODES_URL=https://example.com/codes.json

# Or auto-discover from repo layout
export CODES_BASE_URL=https://raw.githubusercontent.com/you/repo/main
export WEEK_NUMBER=6
```

## 📊 Statistics Tracking

The tool now automatically tracks your attendance submission statistics:

```bash
# View detailed statistics
python main.py --stats

# Or use the stats module directly
python stats.py
```

Statistics include:
- Total runs and success rate
- Codes submitted per course
- Recent activity timeline
- Error history

## Troubleshooting

- If login keeps asking for MFA: re-run the headed login to refresh `storage_state.json`
- If the browser fails to launch: make sure Google Chrome or Microsoft Edge is installed, or set `BROWSER_CHANNEL` to `chrome`/`msedge`.
- On Windows, if activation fails, run PowerShell as Administrator once, then try `.venv\Scripts\Activate.ps1` again.
- When running, please do NOT use a VPN, as this may cause Okta to refuse the connection.

## FAQ (Windows)

- **Use `py` instead of `python`**: If `python` isn't found or points to another version, use `py` (e.g., `py -m venv .venv`, `py main.py`).
- **Switching between Git Bash and PowerShell**: In terminals like VS Code, use the dropdown to open a new Git Bash or PowerShell window. Some commands (e.g., `source`) only work in Git Bash, while PowerShell uses `.\` for scripts.
- **Path escaping issues**: PowerShell uses backslashes (`\`) and may treat them as escape characters. Wrap paths in quotes or use double backslashes like `C:\path\to\file`. Git Bash uses forward slashes (`/`).

## Command-Line Arguments

main.py

| Argument | Type | Description | Example |
| --- | --- | --- | --- |
| `--browser` | string | Browser engine (`chromium`/`firefox`/`webkit`) | `--browser chromium` |
| `--channel` | string | System Chromium channel | `--channel chrome` |
| `--headed` | flag | Show browser UI (same as `HEADLESS=0`) | `--headed` |
| `--dry-run` | flag | Print parsed codes without submitting | `--dry-run` |
| `--week` | int | Submit codes for week number N | `--week 4` |
| `--login-only` | flag | Only perform login/session refresh and exit | `--login-only` |
| `--stats` | flag | Show attendance statistics and exit | `--stats` |

login.py

| Argument | Type | Description | Example |
| --- | --- | --- | --- |
| `--portal` | string URL | Attendance portal URL (overrides `PORTAL_URL`) | `--portal https://attendance.example.edu/student/Default.aspx` |
| `--browser` | string | Browser engine (`chromium`/`firefox`/`webkit`) | `--browser chromium` |
| `--channel` | string | System Chromium channel | `--channel chrome-beta` |
| `--headed` | flag | Show browser UI (recommended for first login) | `--headed` |
| `--storage-state` | string path | Path to save `storage_state.json` | `--storage-state storage_state.json` |
| `--user-data-dir` | string path | Use a persistent browser profile directory | `--user-data-dir ~/.always-attend-profile` |
| `--check` | flag | After saving, verify login by reopening the portal | `--check` |
| `--check-only` | flag | Only verify current session state; do not open login | `--check-only` |

submit.py

| Argument | Type | Description | Example |
| --- | --- | --- | --- |
| `--browser` | string | Browser engine (`chromium`/`firefox`/`webkit`) | `--browser chromium` |
| `--channel` | string | System Chromium channel | `--channel msedge` |
| `--headed` | flag | Show browser UI | `--headed` |
| `--dry-run` | flag | Print parsed codes without submitting | `--dry-run` |
| `--week` | int | Submit codes for week number N | `--week 6` |

## Environment Variables

| Variable | Type | Required | Description | Example |
| --- | --- | --- | --- | --- |
| `PORTAL_URL` | string URL | Yes | Attendance portal base URL | `https://attendance.monash.edu.my` |
| `CODES_URL` | string URL | No | Direct URL to codes JSON | `https://example.com/codes.json` |
| `CODES_FILE` | string path | No | Local path to codes JSON | `/home/user/codes.json` |
| `CODES` | string | No | Inline `slot:code;slot:code` pairs | `"Workshop 1:ABCD1;Workshop 2:EFGH2"` |
| `CODES_BASE_URL` | string URL | No | Base URL for auto-discovery | `https://raw.githubusercontent.com/user/repo/main` |
| `WEEK_NUMBER` | int | No | Week number for auto-discovery | `4` |
| `USERNAME` | string | No | Okta username for auto-login | `student@example.edu` |
| `PASSWORD` | string | No | Okta password for auto-login | `correcthorsebattery` |
| `TOTP_SECRET` | string (base32) | No | MFA TOTP secret for auto-login | `JBSWY3DPEHPK3PXP` |
| `BROWSER` | string | No | Engine override (`chromium`/`firefox`/`webkit`) | `chromium` |
| `BROWSER_CHANNEL` | string | No | System channel (`chrome`/`msedge`/etc.) | `chrome` |
| `HEADLESS` | flag (0/1 or true/false) | No | Run without UI (0 disables) | `0` |

## Disclaimer

- This project is for educational and personal use only. Use it responsibly and follow your institution’s policies and the website’s terms of use.
- This project is not affiliated with, endorsed by, or sponsored by any university or service provider. All product names, logos, and brands are property of their respective owners.
- You are solely responsible for any use of this tool and any consequences that may arise. The authors provide no guarantee that it will work for your specific setup.

## License

- This project is licensed under the GNU General Public License v3.0 (GPL‑3.0). See the full text in the `LICENSE` file.
- You may copy, modify, and distribute this software under the terms of the GPL‑3.0. It is provided “as is”, without any warranty.
