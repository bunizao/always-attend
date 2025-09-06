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







## Prerequisites

- Python 3.8 or later (3.11+ recommended)
- Google Chrome or Microsoft Edge installed on your computer

## Install

0) Install Git
- Download from https://git-scm.com/downloads and follow the installer.

1) Clone and enter the project
```bash
git clone https://github.com/bunizao/always-attend.git
cd always-attend
```

2) Create and activate a virtual environment
- macOS / Linux:
```bash
python -m venv .venv
source .venv/bin/activate
```
- Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```
If script execution is disabled, run:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
Then rerun `.venv\Scripts\Activate.ps1`. If PowerShell still errors, right-click PowerShell, choose "Run as administrator", and run `Activate.ps1` again.

3) Install dependencies
```bash
pip install -U pip
pip install -r requirements.txt
```

4) Set environment variables (Optional - First-time setup wizard will handle this)
```bash
cp .env.example .env
```
Then edit `.env` and set your values, or use the launcher's first-time setup wizard. Quick edit in VS Code:
```bash
code .env
```

Important:
- The first-time setup wizard in the launchers will automatically configure most settings
- For Monash University Malaysia, the wizard provides a quick setup option
- Always include the `https://` prefix in URLs
> [!IMPORTANT]
> This project is **not funded, affiliated with, or endorsed by any educational institution**.  
> It is an independent project and has no official connection with any university.

Alternatively, update `PORTAL_URL` inline:
```bash
# macOS
sed -i '' 's/^PORTAL_URL=.*/PORTAL_URL="https:\/\/your.portal.url"/' .env
# Linux
sed -i 's/^PORTAL_URL=.*/PORTAL_URL="https:\/\/your.portal.url"/' .env
```

5) Quick Start - Use the Enhanced Launchers (Recommended)
```bash
# macOS: Double-click Always-Attend.command
# Windows: Double-click Always-Attend.bat

# Or run directly:
python main.py
```
What happens when you run this:
- **First-time setup wizard** guides you through configuration if needed
- **Privacy policy display** ensures compliance awareness
- **Auto-configuration** for supported universities (Monash Malaysia option available)
- **Gmail integration** automatically extracts codes from your institutional email
- **Intelligent submission** with precise slot matching and optimized polling
- If no valid session is found, a browser window opens for one‑time sign‑in and MFA verification
- The script navigates to your attendance portal and submits your codes efficiently
- Check the logs in the terminal for results
- Optional flags: `--headed` to watch the browser, `--dry-run` to preview only, `--week N` to target a specific week

6) Update later
```bash
git pull
```

---

See the Environment Variables section below for a full list.

## 🚀 Easy Launch (New!)

For easier usage, you can now double-click to run with our enhanced first-time setup:

**macOS:**
- Double-click `Always-Attend.command` for the interactive launcher with first-time setup wizard

**Windows:**
- Double-click `Always-Attend.bat` for the enhanced launcher with setup wizard

### First-Time Setup Features:
- **Cool ASCII art banner** for enhanced visual experience
- **Privacy policy display** with consent mechanism (required on first run)
- **University configuration** with quick Monash Malaysia setup option
- **Email and password input** during initial setup
- **Week number configuration** for attendance tracking
- **OCR method selection** with three options:
  - Local OCR (no external services, requires dependencies)
  - AI-powered OCR (Gemini/ChatGPT integration with API key input)
  - Manual extraction (no automatic processing)
- **Simplified execution**: Just runs `python main.py` directly, letting the program auto-determine needed actions
- **No complex menus**: Streamlined user experience focused on core functionality

## 📧 Gmail Integration (New!)

The tool can now automatically extract attendance codes from your institutional Gmail account using the same Okta authentication session:

```bash
# Enable Gmail integration in your .env file (now enabled by default)
GMAIL_ENABLED=1
GMAIL_SEARCH_DAYS=7  # Search last 7 days of emails

# Run normally - Gmail will be checked first for codes automatically
python main.py
```

Features:
- **Default enabled**: Gmail integration is now the primary method for code extraction
- Uses existing Okta session cookies to access institutional Gmail  
- Searches for attendance-related emails automatically
- **Intelligent code extraction** with course grouping and precise slot matching
- **Two-phase submission**: Precise matching first, fallback polling second (eliminates "ridiculous" polling of all codes)
- Identifies course slots and dates from email content
- **Optimized performance**: Groups codes by course and uses smart matching algorithms
- Falls back to other code sources if no Gmail codes found

The Gmail integration looks for patterns like:
- "attendance code: ABC123"
- "your code: DEF456" 
- Workshop/tutorial/lab session information
- Date and slot number extraction

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
| `GMAIL_ENABLED` | flag (0/1 or true/false) | No | Enable Gmail code extraction | `1` |
| `GMAIL_SEARCH_DAYS` | int | No | Days back to search Gmail | `7` |
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
