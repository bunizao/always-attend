import os
import json
import asyncio
import argparse
import importlib


def _load_env(path: str = ".env") -> None:
    """Minimal .env loader to populate env defaults (no overrides)."""
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k and (k not in os.environ):
                    os.environ[k] = v
    except Exception:
        pass


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
        # Persistent profile: skip file-based check; rely on portal check
        needs_login = False
    else:
        if not os.path.exists(storage_state) or not _is_storage_state_effective(storage_state):
            needs_login = True
        else:
            # Optional: quick validation by opening portal and checking for login fields
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
        # Optional fast path: bypass check and assume session is valid
        # Set SKIP_SESSION_CHECK=1 to skip future validations (use with care)
        if os.getenv('SKIP_SESSION_CHECK') in ('1','true','True'):
            return


async def _run_submit(dry_run: bool) -> None:
    submit = importlib.import_module('submit')
    await submit.run_submit(dry_run=dry_run)


if __name__ == "__main__":
    _load_env(os.getenv('ENV_FILE', '.env'))

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

    # Derive default headed for login flows: headed by default unless HEADLESS=1
    env_headless = os.getenv('HEADLESS')
    headed_default = (env_headless in ('0', 'false', 'False', None))

    if args.login_only:
        asyncio.run(_ensure_session(headed_default=headed_default))
    else:
        # Ensure session then run submit
        asyncio.run(_ensure_session(headed_default=headed_default))
        asyncio.run(_run_submit(dry_run=bool(args.dry_run or os.getenv('DRY_RUN') in ('1','true','True'))))
