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







## 📥 Download This Project

Choose one method to get the folder onto your computer:

### Option 1 — Git (recommended)
- Install Git: https://git-scm.com/downloads
- macOS/Linux:
```bash
git clone https://github.com/bunizao/always-attend.git
cd always-attend
```
- Windows (PowerShell or Command Prompt):
```bat
git clone https://github.com/bunizao/always-attend.git
cd always-attend
```

### Option 2 — Download ZIP (no Git needed)
- Open the project page: https://github.com/bunizao/always-attend
- Click the green "Code" button → "Download ZIP"
- Or direct ZIP link: https://github.com/bunizao/always-attend/archive/refs/heads/main.zip
- Extract the ZIP:
  - Windows: right‑click the ZIP → "Extract All..."
  - macOS: double‑click the ZIP to extract
- Open the extracted `always-attend` folder

### After download
- macOS: double‑click `Always-Attend.command`
- Windows: double‑click `Always-Attend.bat` or right‑click `Always-Attend.ps1` → Run with PowerShell
- The first run will guide setup automatically

## 🚀 Easy Launch

Double‑click to run with the enhanced first‑time setup:

- macOS: double‑click `Always-Attend.command`
- Windows: double‑click `Always-Attend.bat` (or run `Always-Attend.ps1`)

## 📋 Application Workflow

The application follows a structured 4-step workflow with multiple execution modes:

### Core Workflow
1. **Environment Setup** - Bootstrap and install dependencies
2. **Python Check** - Verify Python environment and packages
3. **App Start** - Load config, privacy policy, and first-run setup
4. **Choose Mode** - Select execution mode:

### Execution Modes
- **🔍 Stats** (`--stats`) - View attendance statistics (read-only)
- **📤 Submit** (default) - Main workflow for code submission
- **🔑 Login Only** (`--login-only`) - Refresh session and exit

### Submit Workflow Path
When using Submit mode, the application follows this sequence:
1. Session Check → Sign-in if needed
2. Submission → Dry-run or submit codes
3. Done → Save results and exit

### Login Only Workflow Path
When using Login Only mode:
1. Session Check → Sign-in if needed
2. Done → Exit after refreshing session

### Quick Start
```bash
# Basic execution
python main.py

# View statistics
python main.py --stats

# Refresh login session
python main.py --login-only

# Run specific week
python main.py --week 4

# Show browser (headed mode)
python main.py --headed
```

What the launchers do:
- Check for Python (and Git if available)
- Create/activate a virtualenv and install dependencies on first run
- Run a first‑time setup wizard (portal URL, credentials, week, browser)
- Auto‑detect the latest week from `data/*/*.json` and set `WEEK_NUMBER`

Update later:
```bash
git pull
```

---

## 📦 Attendance Database

Always Attend now reads attendance codes exclusively from the `data/` directory (or the folder specified by `CODES_DB_PATH`). Each course gets its own subfolder and every week is represented by a JSON file:

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

On every run the repository is cloned (if missing) or updated before submission.  Without a repository the tool simply reads whatever JSON files already exist under `data/`.

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

## Environment Variables

| Variable | Type | Required | Description | Example |
| --- | --- | --- | --- | --- |
| `PORTAL_URL` | string URL | Yes | Attendance portal base URL | `https://attendance.monash.edu.my` |
| `CODES_DB_PATH` | string path | No | Root folder containing `COURSE/WEEK.json` files | `/srv/attendance-data` |
| `CODES_DB_REPO` | string URL | No | Git repository that mirrors the data tree | `git@github.com:you/attendance-db.git` |
| `CODES_DB_BRANCH` | string | No | Branch to checkout when syncing the repository | `main` |
| `WEEK_NUMBER` | int | No | Force a specific week instead of auto-detecting | `4` |
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
