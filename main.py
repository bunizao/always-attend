import os
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


async def _delegate_submit(dry_run: bool) -> None:
    submit = importlib.import_module('submit')
    await submit.run_submit(dry_run=dry_run)


if __name__ == "__main__":
    print("[compat] main.py now delegates to submit.py. Prefer `python submit.py` or `python login.py` directly.")
    _load_env(os.getenv('ENV_FILE', '.env'))

    parser = argparse.ArgumentParser(description="Always-attend (compat entry): delegates to submit.py")
    parser.add_argument("--browser", choices=["chromium", "firefox", "webkit"], help="Browser engine override")
    parser.add_argument("--channel", help="Use system browser channel (chromium only): chrome|chrome-beta|msedge|msedge-beta")
    parser.add_argument("--headed", action="store_true", help="Run with browser UI (sets HEADLESS=0)")
    parser.add_argument("--dry-run", action="store_true", help="Print parsed codes and exit (no browser)")
    args = parser.parse_args()

    if args.browser:
        os.environ['BROWSER'] = args.browser
    if args.channel:
        os.environ['BROWSER_CHANNEL'] = args.channel
    if args.headed:
        os.environ['HEADLESS'] = '0'

    asyncio.run(_delegate_submit(dry_run=bool(args.dry_run or os.getenv('DRY_RUN') in ('1','true','True'))))

