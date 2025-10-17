import os
import json
import asyncio
import argparse
import importlib
import sys
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict

from utils.env_utils import load_env, ensure_env_file, append_to_env_file
from utils.logger import logger, step, success, set_log_profile
from utils.session import is_storage_state_effective
from config.config_wizard import ConfigWizard
from utils.console import PortalConsole


def _ensure_env_file(env_file: str) -> None:
    """Backwards-compatible wrapper for env file creation."""
    ensure_env_file(env_file)


def _append_to_env_file(env_file: str, key: str, value: str) -> None:
    """Backwards-compatible wrapper for updating env file."""
    append_to_env_file(env_file, key, value)


class PortalState:
    """Persisted state for the CLI portal experience."""

    def __init__(self, path: Optional[Path] = None):
        default_path = Path(os.getenv("PORTAL_STATE_FILE", ".portal_state.json"))
        self.path = path or default_path
        self.data: Dict[str, bool] = {
            "welcome_ack": False,
            "privacy_ack": False,
        }
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    self.data.update({k: bool(v) for k, v in payload.items()})
            except Exception:
                # ignore corrupted state; a new file will be written
                pass

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Unable to persist portal state: %s", exc)

    def flag(self, key: str) -> bool:
        return bool(self.data.get(key, False))

    def set_flag(self, key: str, value: bool = True) -> None:
        self.data[key] = value
        self.save()


class PortalExperience:
    """Encapsulates the interactive CLI veneer shared by launchers."""

    def __init__(self) -> None:
        self.console = PortalConsole()
        self.state = PortalState()
        self.interactive = sys.stdin.isatty()

    def show_welcome(self) -> None:
        self.console.clear_screen()
        self.console.banner("Always Attend Portal")
        self.console.text_block(
            "Automation assistant for attendance management. "
            "Your credentials stay local; we simply streamline the repetitive steps.",
            indent=4,
            tone="dim",
        )
        self.console.clear_line()
        if not self.state.flag("welcome_ack"):
            self.console.panel(
                "Quick Start",
                [
                    "We will guide you through language preference, configuration wizard, and login flow.",
                    "Use the number prompts shown to interact; press Ctrl+C any time to exit.",
                ],
                accent="blue",
            )
            self.state.set_flag("welcome_ack")

    def ensure_privacy_notice(self) -> None:
        if not self.interactive or self.state.flag("privacy_ack"):
            return
        self.console.panel(
            "Usage Notice",
            [
                "This tool is for personal automation only; comply with your institution's policies.",
                "Credentials and session data are stored locally. Keep your machine secure.",
                "The maintainers provide no warranty and this project is not affiliated with any provider.",
            ],
            accent="yellow",
        )
        if self.console.confirm("Accept and continue?", default=True):
            self.state.set_flag("privacy_ack")
            self.console.clear_line()
        else:
            self.console.text_block("Consent declined. Exiting…", indent=2, tone="yellow")
            raise SystemExit(0)

    def configure_language(self) -> None:
        from utils.localization import get_available_languages, set_language

        languages = get_available_languages()
        if not languages:
            return
        saved = os.getenv("LANGUAGE_PREFERENCE")
        if saved and saved in languages:
            set_language(saved)
            return
        if not self.interactive:
            default_lang = "en" if "en" in languages else next(iter(languages))
            set_language(default_lang)
            os.environ["LANGUAGE_PREFERENCE"] = default_lang
            return

        options = [f"{name} ({code})" for code, name in languages.items()]
        choice = self.console.prompt_menu("Select Your Language", options)
        if choice is None:
            selected_code = "en" if "en" in languages else next(iter(languages))
        else:
            selected_code = list(languages.keys())[choice]

        set_language(selected_code)
        os.environ["LANGUAGE_PREFERENCE"] = selected_code
        env_file = os.getenv("ENV_FILE", ".env")
        _ensure_env_file(env_file)
        _append_to_env_file(env_file, "LANGUAGE_PREFERENCE", selected_code)
        selected_label = languages.get(selected_code, selected_code)
        self.console.text_block(f"Language set to {selected_label}.", indent=4, tone="green")
        self.console.clear_line()

def check_for_updates():
    """Attempt to pull latest changes; continue silently on failure."""
    if os.getenv('CI') in ('true', '1'):
        return
    try:
        if not os.path.isdir('.git'):
            return
        step("Checking repository updates")
        # Simple pull; if there are updates, restart this process
        pull = subprocess.run(["git", "pull", "--ff-only"], capture_output=True, text=True)
        if pull.returncode != 0:
            # Noisy errors aren't helpful at runtime; continue
            return
        out = (pull.stdout or "").strip()
        if out and "Already up to date" not in out:
            logger.log(logging.INFO, out, layer="progress")
            success("Repository updated; reloading with fresh code.")
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

    experience = PortalExperience()
    experience.show_welcome()
    experience.ensure_privacy_notice()
    experience.configure_language()

    parser = argparse.ArgumentParser(
        description="Always-attend: auto login + submit with storage_state check"
    )
    parser.add_argument("--browser", choices=["chromium", "firefox", "webkit"], help="Browser engine override")
    parser.add_argument("--channel", help="Use system browser channel (chromium only): chrome|chrome-beta|msedge|msedge-beta")
    parser.add_argument("--headed", action="store_true", help="Run with browser UI (sets HEADLESS=0)")
    parser.add_argument("--dry-run", action="store_true", help="Print parsed codes and exit (no browser)")
    parser.add_argument("--week", help="Week number to submit (sets WEEK_NUMBER)")
    parser.add_argument("--login-only", action="store_true", help="Only perform login/session refresh and exit")
    parser.add_argument("--stats", action="store_true", help="Show attendance statistics and exit")
    parser.add_argument("--setup", action="store_true", help="Run configuration wizard")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    # Run configuration wizard if requested or on first run
    if args.setup or ConfigWizard.should_run_wizard():
        if args.setup or ConfigWizard.prompt_user_for_wizard():
            step("Launching configuration wizard")
            wizard = ConfigWizard()
            wizard.run()
            load_env(os.getenv('ENV_FILE', '.env'))

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
    if args.debug:
        set_log_profile("debug")

    env_headless = os.getenv('HEADLESS')
    headed_default = (env_headless in ('0', 'false', 'False', None))

    if args.stats:
        from core.stats import StatsManager
        experience.console.headline("Attendance Statistics")
        stats = StatsManager()
        stats.print_stats()
        sys.exit(0)

    if args.login_only:
        step("Refreshing session only (no submission)")
        asyncio.run(_ensure_session(headed_default=headed_default))
    else:
        step("Ensuring session is ready")
        asyncio.run(_ensure_session(headed_default=headed_default))
        if args.dry_run or os.getenv('DRY_RUN') in ('1','true','True'):
            experience.console.headline("Dry Run Preview")
        else:
            experience.console.headline("Submission Workflow")
        asyncio.run(_run_submit(dry_run=bool(args.dry_run or os.getenv('DRY_RUN') in ('1','true','True')), target_email=None))
        success("Workflow completed")


if __name__ == "__main__":
    main()
