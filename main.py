import os
import json
import asyncio
import argparse
import importlib
import sys
import subprocess

from env_utils import load_env
from logger import logger

def check_for_updates():
    """Checks for updates and restarts the script if necessary."""
    # Only check for updates if not in a CI environment
    if os.getenv('CI') in ('true', '1'):
        logger.info("CI environment detected, skipping update check.")
        return

    try:
        logger.info("Checking for updates...")
        
        # Check if .git directory exists
        if not os.path.isdir('.git'):
            logger.info("Not a git repository, skipping update check.")
            return

        # Fetch the latest changes from the remote
        subprocess.run(["git", "fetch"], check=True, capture_output=True)
        
        # Check if the local branch is behind
        status_result = subprocess.run(["git", "status", "-uno"], check=True, capture_output=True, text=True)
        
        if "Your branch is behind" in status_result.stdout:
            logger.info("New version available. Pulling changes...")
            
            # Pull the changes
            pull_result = subprocess.run(["git", "pull"], check=True, capture_output=True, text=True)
            logger.info(pull_result.stdout)
            
            logger.info("Update complete. Restarting script...")
            
            # Restart the script
            os.execv(sys.executable, ['python'] + sys.argv)
        else:
            logger.info("Already up to date.")
            
    except FileNotFoundError:
        logger.warning("git command not found. Skipping update check.")
    except subprocess.CalledProcessError as e:
        logger.error(f"An error occurred during update check: {e.stderr}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during update check: {e}")

def _is_storage_state_effective(path: str) -> bool:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cookies = data.get('cookies') or []
        origins = data.get('origins') or []
        return bool(cookies or origins)
    except Exception:
        return False


async def _ensure_session(headed_default: bool) -> None:
    """Ensure a valid session exists; open interactive login if needed."""
    portal_url = os.getenv("PORTAL_URL", "")
    if not portal_url:
        raise RuntimeError("Missing PORTAL_URL in environment or .env")

    browser = os.getenv("BROWSER", "chromium")
    channel = os.getenv("BROWSER_CHANNEL", "chrome")
    storage_state = os.getenv("STORAGE_STATE", "storage_state.json")
    user_data_dir = os.getenv("USER_DATA_DIR")

    needs_login = False
    if user_data_dir:
        needs_login = False
    else:
        if not os.path.exists(storage_state) or not _is_storage_state_effective(storage_state):
            needs_login = True
        else:
            login_mod = importlib.import_module('login')
            ok = await login_mod.check_session(
                check_url=portal_url,
                browser_name=browser,
                channel=channel,
                headed=False,
                storage_state=storage_state,
                user_data_dir=None,
            )
            needs_login = not ok

    if needs_login:
        login_mod = importlib.import_module('login')
        headed = headed_default
        await login_mod.run_login(
            portal_url=portal_url,
            browser_name=browser,
            channel=channel,
            headed=headed,
            storage_state=storage_state,
            user_data_dir=user_data_dir,
        )
    else:
        if os.getenv('SKIP_SESSION_CHECK') in ('1','true','True'):
            return


async def _run_submit(dry_run: bool) -> None:
    submit = importlib.import_module('submit')
    await submit.run_submit(dry_run=dry_run)


if __name__ == "__main__":
    load_env(os.getenv('ENV_FILE', '.env'))

    # Check for updates before doing anything else
    check_for_updates()

    parser = argparse.ArgumentParser(description="Always-attend: auto login + submit with storage_state check")
    parser.add_argument("--browser", choices=["chromium", "firefox", "webkit"], help="Browser engine override")
    parser.add_argument("--channel", help="Use system browser channel (chromium only): chrome|chrome-beta|msedge|msedge-beta")
    parser.add_argument("--headed", action="store_true", help="Run with browser UI (sets HEADLESS=0)")
    parser.add_argument("--dry-run", action="store_true", help="Print parsed codes and exit (no browser)")
    parser.add_argument("--week", help="Week number to submit (sets WEEK_NUMBER)")
    parser.add_argument("--login-only", action="store_true", help="Only perform login/session refresh and exit")
    args = parser.parse_args()

    if args.browser:
        os.environ['BROWSER'] = args.browser
    if args.channel:
        os.environ['BROWSER_CHANNEL'] = args.channel
    if args.headed:
        os.environ['HEADLESS'] = '0'
    if args.week:
        os.environ['WEEK_NUMBER'] = str(args.week)

    env_headless = os.getenv('HEADLESS')
    headed_default = (env_headless in ('0', 'false', 'False', None))

    if args.login_only:
        asyncio.run(_ensure_session(headed_default=headed_default))
    else:
        asyncio.run(_ensure_session(headed_default=headed_default))
        asyncio.run(_run_submit(dry_run=bool(args.dry_run or os.getenv('DRY_RUN') in ('1','true','True'))))