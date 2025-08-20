# Always Attend

An automated tool to submit weekly attendance codes for your university, with built-in handling for Okta Multi-Factor Authentication (MFA).

This project is designed for educational and personal use to demonstrate automation capabilities. Please use it responsibly and in accordance with your institution's policies.

## Features

- **Automated Submission**: Automatically logs in and submits attendance codes.
- **Okta MFA Support**: Handles Okta MFA using TOTP (Authenticator App) secrets.
- **Persistent Sessions**: Reuses your login session to minimize MFA prompts and speed up subsequent runs.
- **Flexible Code Sources**: Load attendance codes from environment variables, local JSON files, or remote URLs.
- **GitHub Actions Integration**: Includes a workflow to automatically fetch codes from GitHub Issues.
- **Cross-Platform**: Runs on any system with Python and Playwright support.

## How It Works

The project uses [Playwright](https://playwright.dev/python/) to control a browser and simulate user actions. It consists of two main scripts:

1.  `login.py`: An interactive script to perform the initial login. It opens a browser, allowing you to enter your credentials and MFA code. Upon success, it saves your session state (cookies and local storage) to a `storage_state.json` file.
2.  `submit.py`: A script that uses the saved session from `storage_state.json` to directly access the attendance portal and submit your codes without needing to log in again.
3.  `main.py`: The main entry point that intelligently checks if a valid session exists. If not, it runs the login process first, then proceeds to submit the codes.

## Quick Start

#### 1. Prerequisites

- Python 3.8+
- A university account with Okta MFA enabled.
- Your TOTP secret key (the Base32 string from your authenticator app).

#### 2. Clone the Repository

```bash
git clone https://github.com/tutu/always-attend.git
cd always-attend
```

#### 3. Set Up a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
# On Windows, use: .venv\Scripts\activate
```

#### 4. Install Dependencies

This will install the required Python packages and the Chromium browser for Playwright.

```bash
pip install -r requirements.txt
playwright install chromium
```

#### 5. Configure Your Credentials

Copy the example environment file and fill in your details.

```bash
cp .env.example .env
```

Now, open the `.env` file in a text editor and set the following:
- `USERNAME`: Your institutional email address.
- `PASSWORD`: Your password.
- `TOTP_SECRET`: Your Base32 encoded TOTP secret key for MFA.

#### 6. Run the Application

Execute the main script. The first time you run it, it will trigger the interactive login process.

```bash
python main.py
```

Follow the prompts in the terminal. A browser window will open for you to complete the login. After a valid session is saved, subsequent runs will be non-interactive and submit codes directly.

## Configuration

Attendance codes can be provided in several ways, listed by priority:

1.  **Environment Variables (Per-Slot)**: Highest priority. Define variables matching your class slots.
    ```bash
    # Example for .env file
    "Workshop 1"="CODE123"
    "Applied 2"="CODE456"
    ```

2.  **Auto-Discovery from URL**: The script can construct a URL to fetch a JSON file.
    - `COURSE_CODE`: e.g., "FIT1045"
    - `WEEK_NUMBER`: e.g., "4"
    - `CODES_BASE_URL`: The base URL where codes are hosted.
    - The script will fetch from `{CODES_BASE_URL}/data/{COURSE_CODE}/{WEEK_NUMBER}.json`.

3.  **Direct URL (`CODES_URL`)**: A direct URL to a JSON file containing the codes.

4.  **Local File (`CODES_FILE`)**: A path to a local JSON file.

5.  **Inline String (`CODES`)**: A semicolon-separated string of `slot:code` pairs.

**Example JSON Format:**
```json
[
  {"date": "2025-08-18", "slot": "Workshop 1", "code": "JZXBA"},
  {"date": "2025-08-19", "slot": "Workshop 2", "code": "AJYV7"}
]
```

## Usage

While `main.py` is the primary entry point, you can use the individual scripts for specific tasks.

#### `main.py` (Recommended)
The main script handles both login and submission intelligently.
```bash
# Run the full process: check session, log in if needed, then submit
python main.py

# Force the browser to be visible
python main.py --headed

# Run in dry-run mode to see what codes would be submitted
python main.py --dry-run
```

#### `login.py`
Use this to manually refresh your session state.
```bash
# Run interactive login to create/update storage_state.json
python login.py --headed

# Check if the current session is still valid
python login.py --check-only
```

#### `submit.py`
Use this to submit codes when you are sure `storage_state.json` is valid.
```bash
# Submit codes using the existing session
python submit.py

# See which codes will be submitted without actually submitting them
python submit.py --dry-run
```

## GitHub Actions Integration

This repository includes a workflow (`.github/workflows/attendance-from-issues.yml`) that automatically extracts attendance codes from newly created GitHub Issues.

- **How it works**: When an issue with the "Attendance Codes" template is created, a workflow runs, parses the issue body, and saves the codes to a JSON file within the repository (e.g., `data/FIT1045/4.json`).
- **Usage**: You can then configure `CODES_BASE_URL` to point to your repository's raw content URL (`https://raw.githubusercontent.com/<your-username>/<your-repo>/main`) to automatically pull the latest codes. This setup allows you to update codes just by creating a GitHub issue, without touching the environment variables.
