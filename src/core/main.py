"""Core CLI workflow orchestration for Always Attend."""

import os
import asyncio
import argparse
import importlib
import sys
from typing import Optional

from always_attend import __version__
from always_attend.argv import CLI_EXAMPLES, normalize_cli_argv
from always_attend.paths import codes_db_path, env_file as default_env_file, storage_state_file, user_data_dir as default_user_data_dir
from utils.env_utils import load_env
from utils.logger import apply_env_configuration, logger, step, success, set_log_profile
from utils.session import is_storage_state_effective
from utils.browser_detection import is_browser_channel_available

def _is_storage_state_effective(path: str) -> bool:
    # Preserve name for existing calls while delegating to util
    return is_storage_state_effective(path)


async def _ensure_session(headed_default: bool) -> None:
    """Ensure a valid session exists; open interactive login if needed."""
    portal_url = os.getenv("PORTAL_URL", "")
    if not portal_url:
        raise RuntimeError("Missing PORTAL_URL in environment or .env")

    browser = os.getenv("BROWSER", "chromium")
    channel_env = os.getenv("BROWSER_CHANNEL")
    channel: Optional[str]
    if browser == "chromium":
        if channel_env:
            if not is_browser_channel_available(channel_env):
                logger.info(
                    "Requested browser channel '%s' is unavailable; falling back to bundled Chromium.",
                    channel_env,
                )
                channel = None
            else:
                channel = channel_env
        else:
            if is_browser_channel_available("chrome"):
                channel = "chrome"
            else:
                channel = None
                logger.info(
                    "System Chrome was not detected. "
                    "Playwright's managed Chromium will be used instead. "
                    "If Chromium is missing, it will be downloaded automatically."
                )
    else:
        channel = channel_env

    storage_state = str(storage_state_file())
    resolved_user_data_dir = default_user_data_dir()
    user_data_dir = str(resolved_user_data_dir) if resolved_user_data_dir is not None else None

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
            import_browser_session=os.getenv('IMPORT_BROWSER_SESSION', '1') in ('1', 'true', 'True'),
        )
    else:
        if os.getenv('SKIP_SESSION_CHECK') in ('1','true','True'):
            return


async def _run_submit(dry_run: bool, target_email: Optional[str] = None) -> None:
    submit = importlib.import_module('core.submit')
    await submit.run_submit(dry_run=dry_run, target_email=target_email)


def main(argv: Optional[list[str]] = None):
    load_env(str(default_env_file()))
    apply_env_configuration()
    codes_root = codes_db_path().expanduser().resolve()
    logger.debug("Using codes directory: %s", codes_root)

    parser = argparse.ArgumentParser(
        description="Always-attend: auto login + submit with storage_state check",
        epilog=CLI_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"always-attend {__version__}")
    parser.add_argument("--browser", choices=["chromium", "firefox", "webkit"], help="Browser engine override")
    parser.add_argument("--channel", help="Use system browser channel (chromium only): chrome|chrome-beta|msedge|msedge-beta")
    parser.add_argument("--headed", action="store_true", help="Run with browser UI (sets HEADLESS=0)")
    parser.add_argument("--dry-run", action="store_true", help="Print parsed codes and exit (no browser)")
    parser.add_argument("--week", help="Week number to submit (sets WEEK_NUMBER)")
    parser.add_argument("--login-only", action="store_true", help="Only perform login/session refresh and exit")
    parser.add_argument("--import-browser-session", action="store_true", help="Import an existing login session from the detected system browser profile (enabled by default)")
    parser.add_argument("--stats", action="store_true", help="Show attendance statistics and exit")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--verbose", action="store_true", help="Enable high-detail logging (same as debug)")
    raw_args = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(normalize_cli_argv(raw_args))

    if args.browser:
        os.environ['BROWSER'] = args.browser
    if args.channel:
        os.environ['BROWSER_CHANNEL'] = args.channel
    if args.headed:
        os.environ['HEADLESS'] = '0'
    if args.week:
        os.environ['WEEK_NUMBER'] = str(args.week)
    if args.import_browser_session:
        os.environ['IMPORT_BROWSER_SESSION'] = '1'
    if args.debug or args.verbose:
        profile = "verbose" if args.verbose and not args.debug else "debug"
        set_log_profile(profile)

    env_headless = os.getenv('HEADLESS')
    headed_default = (env_headless in ('0', 'false', 'False', None))

    if args.stats:
        from core.stats import StatsManager
        stats = StatsManager()
        stats.print_stats()
        sys.exit(0)

    if args.login_only:
        step("Refreshing session only (no submission)")
        asyncio.run(_ensure_session(headed_default=headed_default))
    else:
        step("Ensuring session is ready")
        asyncio.run(_ensure_session(headed_default=headed_default))
        asyncio.run(_run_submit(dry_run=bool(args.dry_run or os.getenv('DRY_RUN') in ('1','true','True')), target_email=None))
        success("Workflow completed")


if __name__ == "__main__":
    main()
