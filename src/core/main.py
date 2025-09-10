import os
import json
import asyncio
import argparse
import importlib
import sys
import subprocess
from typing import Optional

from utils.env_utils import load_env, ensure_env_file, append_to_env_file
from utils.logger import logger
from utils.session import is_storage_state_effective
from config.config_wizard import ConfigWizard


def _ensure_env_file(env_file: str) -> None:
    """Backwards-compatible wrapper for env file creation."""
    ensure_env_file(env_file)


def _append_to_env_file(env_file: str, key: str, value: str) -> None:
    """Backwards-compatible wrapper for updating env file."""
    append_to_env_file(env_file, key, value)


def check_for_updates():
    """Attempt to pull latest changes; continue silently on failure."""
    if os.getenv('CI') in ('true', '1'):
        return
    try:
        if not os.path.isdir('.git'):
            return
        # Simple pull; if there are updates, restart this process
        pull = subprocess.run(["git", "pull", "--ff-only"], capture_output=True, text=True)
        if pull.returncode != 0:
            # Noisy errors aren't helpful at runtime; continue
            return
        out = (pull.stdout or "").strip()
        if out and "Already up to date" not in out:
            logger.info(out)
            # Restart the script after update
            os.execv(sys.executable, ['python'] + sys.argv)
    except FileNotFoundError:
        # git not available; ignore
        return
    except Exception:
        # any unexpected issue; continue
        return

def _is_storage_state_effective(path: str) -> bool:
    # Preserve name for existing calls while delegating to util
    return is_storage_state_effective(path)


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
            login_mod = importlib.import_module('core.login')
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
        login_mod = importlib.import_module('core.login')
        headed = headed_default
        await login_mod.run_login(
            portal_url=portal_url,
            browser_name=browser,
            channel=channel,
            headed=headed,
            storage_state=storage_state,
            user_data_dir=user_data_dir,
            auto_login_enabled=os.getenv('AUTO_LOGIN', '1') in ('1', 'true', 'True'),
        )
    else:
        if os.getenv('SKIP_SESSION_CHECK') in ('1','true','True'):
            return


async def _run_submit(dry_run: bool, target_email: Optional[str] = None) -> None:
    submit = importlib.import_module('core.submit')
    await submit.run_submit(dry_run=dry_run, target_email=target_email)


def main():
    load_env(os.getenv('ENV_FILE', '.env'))

    # Language selection at startup
    from utils.localization import get_localization_manager, create_language_menu, get_available_languages, set_language
    
    # Check if language preference is already set
    lm = get_localization_manager()
    if not os.getenv('LANGUAGE_PREFERENCE'):
        print("\n" + "=" * 60)
        print("🌍 Language Selection / 语言选择 / 語言選擇")
        print("=" * 60)
        print(create_language_menu())
        
        try:
            available_langs = list(get_available_languages().keys())
            choice = input("\nEnter your choice (1-3): ").strip()
            
            if choice in ['1', '2', '3']:
                lang_index = int(choice) - 1
                if 0 <= lang_index < len(available_langs):
                    selected_lang = available_langs[lang_index]
                    set_language(selected_lang)
                    
                    # Save language preference to environment
                    os.environ['LANGUAGE_PREFERENCE'] = selected_lang
                    
                    # Ensure .env file exists and save language preference
                    env_file = os.getenv('ENV_FILE', '.env')
                    _ensure_env_file(env_file)
                    _append_to_env_file(env_file, 'LANGUAGE_PREFERENCE', selected_lang)
                    
                    print(f"\n✅ Language set to: {get_available_languages()[selected_lang]}")
            
        except (ValueError, EOFError, KeyboardInterrupt):
            # Use default language if selection fails
            print("\n📝 Using default language (English)")
        
        print("\n" + "=" * 60)
    else:
        # Load saved language preference
        saved_lang = os.getenv('LANGUAGE_PREFERENCE')
        if saved_lang in get_available_languages():
            set_language(saved_lang)

    parser = argparse.ArgumentParser(description="Always-attend: auto login + submit with storage_state check")
    parser.add_argument("--browser", choices=["chromium", "firefox", "webkit"], help="Browser engine override")
    parser.add_argument("--channel", help="Use system browser channel (chromium only): chrome|chrome-beta|msedge|msedge-beta")
    parser.add_argument("--headed", action="store_true", help="Run with browser UI (sets HEADLESS=0)")
    parser.add_argument("--dry-run", action="store_true", help="Print parsed codes and exit (no browser)")
    parser.add_argument("--week", help="Week number to submit (sets WEEK_NUMBER)")
    parser.add_argument("--login-only", action="store_true", help="Only perform login/session refresh and exit")
    parser.add_argument("--stats", action="store_true", help="Show attendance statistics and exit")
    parser.add_argument("--setup", action="store_true", help="Run configuration wizard")
    args = parser.parse_args()

    # Run configuration wizard if requested or on first run
    if args.setup or ConfigWizard.should_run_wizard():
        if args.setup or ConfigWizard.prompt_user_for_wizard():
            wizard = ConfigWizard()
            wizard.run()
            
            # Reload environment after wizard
            load_env(os.getenv('ENV_FILE', '.env'))

    # Check for updates before doing anything else
    if not args.setup:
        check_for_updates()

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

    if args.stats:
        from core.stats import StatsManager
        stats = StatsManager()
        stats.print_stats()
        sys.exit(0)

    if args.login_only:
        asyncio.run(_ensure_session(headed_default=headed_default))
    else:
        asyncio.run(_ensure_session(headed_default=headed_default))
        asyncio.run(_run_submit(dry_run=bool(args.dry_run or os.getenv('DRY_RUN') in ('1','true','True')), target_email=None))


if __name__ == "__main__":
    main()
