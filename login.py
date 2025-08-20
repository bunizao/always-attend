import os
import argparse
import asyncio

from playwright.async_api import async_playwright
from logger import log_info, log_warn
import asyncio


def load_env_file(path: str = ".env") -> None:
    """Lightweight .env loader: KEY=VALUE lines into os.environ.
    Does not error if the file is missing. Values with surrounding quotes are unquoted.
    Environment variables that already exist are not overridden.
    """
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' not in line:
                    continue
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and (key not in os.environ):
                    os.environ[key] = val
    except Exception:
        # Best-effort loader; ignore parsing errors
        pass


def _is_storage_state_effective(path: str) -> bool:
    try:
        import json
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cookies = data.get('cookies') or []
        origins = data.get('origins') or []
        return bool(cookies or origins)
    except Exception:
        return False


async def run_login(portal_url: str,
                    browser_name: str = "chromium",
                    channel: str | None = None,
                    headed: bool = True,
                    storage_state: str = "storage_state.json",
                    user_data_dir: str | None = None) -> None:
    async with async_playwright() as p:
        if browser_name == "webkit":
            browser_type = p.webkit
        elif browser_name == "firefox":
            browser_type = p.firefox
        else:
            browser_type = p.chromium

        log_info("Opening browser for interactive login...")
        if user_data_dir:
            try:
                context = await browser_type.launch_persistent_context(
                    user_data_dir,
                    headless=not headed,
                    channel=channel,
                )
            except Exception as e:
                log_warn(f"Failed to launch with system channel '{channel}': {e}. Falling back to default.")
                context = await browser_type.launch_persistent_context(
                    user_data_dir,
                    headless=not headed,
                )
            page = await context.new_page()
            browser = None
        else:
            launch_kwargs = {"headless": not headed}
            if channel and browser_name == "chromium":
                launch_kwargs["channel"] = channel
            try:
                browser = await browser_type.launch(**launch_kwargs)
            except Exception as e:
                log_warn(f"Failed to launch with system channel '{channel}': {e}. Falling back to default.")
                launch_kwargs.pop("channel", None)
                browser = await browser_type.launch(**launch_kwargs)
            context = await browser.new_context()
            page = await context.new_page()

        await page.goto(portal_url, timeout=60_000)
        log_info("Please complete Okta login and MFA in the browser window.")
        log_info("After you are back on the portal, press Enter here to save the session...")
        try:
            input()
        except Exception:
            pass

        if not user_data_dir:
            try:
                await context.storage_state(path=storage_state)
                if _is_storage_state_effective(storage_state):
                    log_info(f"Saved session to {storage_state}")
                else:
                    log_warn(f"Saved session to {storage_state}, but it appears empty.")
                    log_warn("Return to the attendance portal before pressing Enter, then try again.")
            except Exception as e:
                log_warn(f"Failed to save storage state: {e}")

        if browser:
            await browser.close()
        else:
            await context.close()


async def check_session(check_url: str,
                        browser_name: str = "chromium",
                        channel: str | None = None,
                        headed: bool = False,
                        storage_state: str = "storage_state.json",
                        user_data_dir: str | None = None) -> bool:
    """Open a context with the saved session and verify we appear logged in.

    Heuristic: navigate to check_url and assert that common login fields are
    NOT visible within a short timeout. Returns True if considered logged in.
    """
    from urllib.parse import urlparse

    async with async_playwright() as p:
        if browser_name == "webkit":
            browser_type = p.webkit
        elif browser_name == "firefox":
            browser_type = p.firefox
        else:
            browser_type = p.chromium

        context = None
        browser = None
        if user_data_dir:
            context = await browser_type.launch_persistent_context(
                user_data_dir,
                headless=not headed,
                channel=channel,
            )
            page = await context.new_page()
        else:
            launch_kwargs = {"headless": not headed}
            if channel and browser_name == "chromium":
                launch_kwargs["channel"] = channel
            browser = await browser_type.launch(**launch_kwargs)
            context = await browser.new_context(storage_state=storage_state if os.path.exists(storage_state) else None)
            page = await context.new_page()

        try:
            # Robust navigation with retries to avoid transient errors (e.g., net::ERR_SOCKET_NOT_CONNECTED)
            retries = 2
            timeout_ms = int(os.getenv("LOGIN_CHECK_TIMEOUT_MS", "60000"))
            last_err = None
            for attempt in range(retries + 1):
                try:
                    await page.goto(check_url, timeout=timeout_ms)
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    log_warn(f"Session check navigation failed (attempt {attempt+1}/{retries+1}): {e}")
                    await asyncio.sleep(0.8)
            if last_err is not None:
                # Treat as not logged in rather than crashing the app
                return False
            # If we are redirected to Okta domain, likely not authenticated
            host = urlparse(page.url).netloc.lower()
            if 'okta' in host:
                return False
            # Try to detect common login fields; if visible -> not logged in
            login_fields = page.locator('#okta-signin-username, input[name="username"], input[type="password"], #okta-signin-password')
            try:
                visible = await login_fields.first.is_visible(timeout=1500)
            except Exception:
                visible = False
            return not visible
        finally:
            if browser:
                await browser.close()
            else:
                await context.close()

def main():
    # Load env file first so parser defaults can see them
    load_env_file(os.getenv("ENV_FILE", ".env"))

    parser = argparse.ArgumentParser(description="Interactive Okta login helper (saves session state)")
    parser.add_argument("--portal", default=os.getenv("PORTAL_URL", ""), help="Portal URL (e.g., https://attendance.monash.edu.my/student/Default.aspx)")
    parser.add_argument("--browser", default=os.getenv("BROWSER", "chromium"), choices=["chromium", "firefox", "webkit"], help="Browser engine")
    parser.add_argument("--channel", default=os.getenv("BROWSER_CHANNEL", "chrome"), help="Chromium channel: chrome|chrome-beta|msedge|msedge-beta")
    parser.add_argument("--headed", action="store_true", help="Show browser UI (recommended)")
    parser.add_argument("--storage-state", default=os.getenv("STORAGE_STATE", "storage_state.json"), help="Path to save storage_state.json")
    parser.add_argument("--user-data-dir", default=os.getenv("USER_DATA_DIR"), help="Persistent profile directory (optional)")
    parser.add_argument("--check", action="store_true", help="After saving session, verify login by opening the portal again")
    parser.add_argument("--check-only", action="store_true", help="Do not open login; only verify current session state")
    args = parser.parse_args()

    if not args.portal:
        raise SystemExit("Missing --portal or PORTAL_URL")

    # Derive headed from env if not explicitly set; default to headed True
    if args.headed:
        headed = True
    else:
        env_headless = os.getenv("HEADLESS")
        if env_headless is None:
            headed = True
        else:
            headed = (env_headless in ("0", "false", "False"))

    if args.check_only:
        ok = asyncio.run(check_session(
            check_url=args.portal,
            browser_name=args.browser,
            channel=args.channel,
            headed=False,
            storage_state=args.storage_state,
            user_data_dir=args.user_data_dir,
        ))
        log_info("Session check: " + ("OK" if ok else "NOT logged in"))
        raise SystemExit(0 if ok else 1)

    if not headed:
        log_info("Running in headless mode. Use --headed or HEADLESS=0 for a browser window.")

    asyncio.run(run_login(
        portal_url=args.portal,
        browser_name=args.browser,
        channel=args.channel,
        headed=headed,
        storage_state=args.storage_state,
        user_data_dir=args.user_data_dir,
    ))

    if args.check:
        ok = asyncio.run(check_session(
            check_url=args.portal,
            browser_name=args.browser,
            channel=args.channel,
            headed=False,
            storage_state=args.storage_state,
            user_data_dir=args.user_data_dir,
        ))
        log_info("Session check: " + ("OK" if ok else "NOT logged in"))


if __name__ == "__main__":
    main()
