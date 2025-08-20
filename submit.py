import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse
import importlib
import argparse
import re
import random
import time

import pyotp
from playwright.async_api import async_playwright, Page, TimeoutError as PwTimeout

from logger import logger
from env_utils import load_env

def to_base(origin_url: str) -> str:
    pu = urlparse(origin_url)
    return urlunparse((pu.scheme, pu.netloc, "", "", "", ""))


MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def format_anchor(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    dd = str(int(d.strftime("%d")))
    mon = MONTH_ABBR[d.month - 1]
    yy = d.strftime("%y")
    return f"{dd}_{mon}_{yy}"

def parse_anchor(anchor: str) -> Optional[datetime]:
    """Parse a day anchor like '20_Aug_25' into a datetime (local date at midnight)."""
    try:
        parts = anchor.split('_')
        if len(parts) != 3:
            return None
        dd_s, mon_s, yy_s = parts
        day = int(dd_s)
        mon_s_cap = mon_s.capitalize()
        if mon_s_cap not in MONTH_ABBR:
            return None
        month = MONTH_ABBR.index(mon_s_cap) + 1
        year = 2000 + int(yy_s)
        return datetime(year, month, day)
    except Exception:
        return None

def _is_storage_state_effective(path: str) -> bool:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cookies = data.get('cookies') or []
        origins = data.get('origins') or []
        return bool(cookies or origins)
    except Exception:
        return False


async def get_enrolled_courses(page: Page) -> List[str]:
    """
    Scrapes the page to find all enrolled course codes.
    This function assumes that course codes are 3 letters followed by 4 digits.
    """
    logger.info("[STEP] Scraping page for enrolled courses...")
    try:
        if os.getenv("DEBUG_SCRAPING") == "1":
            logger.info("Debug scraping enabled. Page content will be printed.")
            logger.debug(await page.content())

        all_text = " ".join(await page.locator('a').all_inner_texts())

        if not re.search(r'\b([A-Z]{3}\d{4})\b', all_text):
            all_text = await page.content()

        course_codes = re.findall(r'\b([A-Z]{3}\d{4})\b', all_text)
        unique_codes = sorted(list(set(course_codes)))
        logger.info(f"Found {len(unique_codes)} enrolled courses: {unique_codes}")
        return unique_codes
    except Exception as e:
        logger.warning(f"Could not scrape enrolled courses: {e}")
        return []


def parse_codes(course_code: Optional[str] = None, week_number: Optional[str] = None) -> List[Dict[str, Optional[str]]]:
    CODES_FILE = os.getenv("CODES_FILE")
    CODES_URL = os.getenv("CODES_URL")
    CODES_BASE_URL = os.getenv("CODES_BASE_URL")

    result: List[Dict[str, Optional[str]]] = []

    env_slot_re = re.compile(r'^([A-Z]+)_([0-9]+)$')
    for var_name, var_value in os.environ.items():
        m = env_slot_re.match(var_name.upper())
        if m and var_value:
            slot_name = f"{m.group(1).capitalize()} {m.group(2)}"
            result.append({"slot": slot_name, "code": var_value.strip()})
    if result:
        logger.info(f"Loaded {len(result)} codes from per-slot environment variables")
        return result

    if course_code and week_number and CODES_BASE_URL:
        course = ''.join(ch for ch in course_code.upper() if ch.isalnum())
        week = ''.join(ch for ch in week_number if ch.isdigit())
        if week:
            auto_url = f"{CODES_BASE_URL.rstrip('/')}/data/{course}/{week}.json"
            try:
                import urllib.request as ur
                req = ur.Request(auto_url, headers={"User-Agent": "always-attend/1.0"})
                with ur.urlopen(req, timeout=20) as resp:
                    data = json.load(resp)
                if isinstance(data, list):
                    for item in data:
                        code_val = str(item.get("code", "")).strip()
                        if code_val:
                            result.append({"slot": item.get("slot"), "date": item.get("date"), "code": code_val})
                if result:
                    logger.info(f"Loaded {len(result)} codes via auto-discovery: {auto_url}")
                    return result
            except Exception as e:
                logger.warning(f"Auto-discovery failed for {course_code} week {week_number}: {e}")

    if course_code and week_number and not (CODES_BASE_URL or CODES_URL or CODES_FILE):
        course = ''.join(ch for ch in course_code.upper() if ch.isalnum())
        week = ''.join(ch for ch in week_number if ch.isdigit())
        if week:
            local_path = os.path.join('data', course, f"{week}.json")
            if os.path.exists(local_path):
                try:
                    with open(local_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            code_val = str(item.get("code", "")).strip()
                            if code_val:
                                result.append({"slot": item.get("slot"), "date": item.get("date"), "code": code_val})
                    if result:
                        logger.info(f"Loaded {len(result)} codes from local data: {local_path}")
                        return result
                except Exception as e:
                    logger.warning(f"Failed to load local data file {local_path}: {e}")

    if CODES_URL:
        try:
            import urllib.request as ur
            req = ur.Request(CODES_URL, headers={"User-Agent": "always-attend/1.0"})
            with ur.urlopen(req, timeout=20) as resp:
                data = json.load(resp)
            if isinstance(data, list):
                for item in data:
                    code_val = str(item.get("code", "")).strip()
                    if code_val:
                        result.append({"slot": item.get("slot"), "date": item.get("date"), "code": code_val})
            if result:
                logger.info(f"Loaded {len(result)} codes from CODES_URL")
                return result
        except Exception as e:
            logger.warning(f"Failed to fetch CODES_URL: {e}")

    if CODES_FILE and os.path.exists(CODES_FILE):
        try:
            with open(CODES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    code_val = str(item.get("code", "")).strip()
                    if code_val:
                        result.append({"slot": item.get("slot"), "date": item.get("date"), "code": code_val})
            if result:
                logger.info(f"Loaded {len(result)} codes from CODES_FILE={CODES_FILE}")
                return result
        except Exception as e:
            logger.warning(f"Failed to parse CODES_FILE: {e}")

    codes_str = os.getenv("CODES")
    if codes_str:
        pairs = [p.strip() for p in codes_str.split(';') if p.strip()]
        for pair in pairs:
            if ':' in pair:
                slot, code = pair.split(':', 1)
                result.append({"slot": slot.strip(), "code": code.strip()})
        if result:
            logger.info(f"Loaded {len(result)} codes from CODES inline")
    return result


async def fill_first_match(page: Page, selectors: List[str], value: str) -> bool:
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=3000):
                await el.fill(value)
                return True
        except Exception:
            continue
    return False


async def click_first_match(page: Page, selectors: List[str]) -> bool:
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=3000):
                await el.click()
                return True
        except Exception:
            continue
    return False


async def maybe_switch_to_code_factor(page: Page) -> None:
    candidates = [
        'text=/enter code/i',
        'text=/use code/i',
        'text=/use a code/i',
        'text=/Use verification code/i',
        'text=/Verify with something else/i',
        'text=/Enter a code/i',
        'text=/Google Authenticator|Authenticator app/i',
        'text=/Okta Verify/i',
    ]
    await click_first_match(page, candidates)


def gen_totp(secret: str) -> str:
    return pyotp.TOTP(secret).now()


async def login(page: Page) -> None:
    PORTAL_URL = os.getenv("PORTAL_URL")
    USERNAME = os.getenv("USERNAME")
    PASSWORD = os.getenv("PASSWORD")
    TOTP_SECRET = os.getenv("TOTP_SECRET")

    if not (PORTAL_URL and USERNAME and PASSWORD):
        raise RuntimeError("Missing required env: PORTAL_URL, USERNAME, PASSWORD")

    await page.goto(PORTAL_URL, timeout=60_000)

    try:
        maybe_login_field = page.locator('#okta-signin-username, input[name="username"], input[type="password"], #okta-signin-password')
        if not await maybe_login_field.first.is_visible(timeout=2000):
            return
    except Exception:
        pass

    logger.info("[STEP] Filling username/password...")
    user_ok = await fill_first_match(page, [
        'input[name="username"]','input[autocomplete="username"]','input[type="email"]','input[placeholder*="user" i]','input[placeholder*="email" i]','#okta-signin-username'], os.getenv("USERNAME"))
    pass_ok = await fill_first_match(page, [
        'input[name="password"]','input[autocomplete="current-password"]','input[type="password"]','input[placeholder*="pass" i]','#okta-signin-password'], os.getenv("PASSWORD"))
    if user_ok and not pass_ok:
        await click_first_match(page, ['button[type="submit"]','button:has-text("Next")','button:has-text("Continue")'])
        pass_ok = await fill_first_match(page, [
            'input[name="password"]','input[autocomplete="current-password"]','input[type="password"]','input[placeholder*="pass" i]'], os.getenv("PASSWORD"))

    await click_first_match(page, ['button[type="submit"]','input[type="submit"]','button:has-text("Sign in")','button:has-text("Log in")','#okta-signin-submit'])
    await maybe_switch_to_code_factor(page)

    otp = None
    if TOTP_SECRET:
        otp = gen_totp(TOTP_SECRET)
    elif os.getenv('MFA_CODE'):
        otp = os.getenv('MFA_CODE').strip()
    if not otp:
        raise RuntimeError("No MFA code available. Set TOTP_SECRET or MFA_CODE.")

    logger.info("[STEP] Submitting MFA code...")
    otp_ok = await fill_first_match(page, [
        'input[name="otp"]','input[name="code"]','input[name="passcode"]','input[autocomplete="one-time-code"]','input[inputmode="numeric"]','input[type="tel"]','input[id*="code" i]','input[placeholder*="code" i]','input[placeholder*="OTP" i]'], otp)

    if not otp_ok:
        boxes = page.locator('input[aria-label*="digit" i], input[maxlength="1"]')
        try:
            count = await boxes.count()
            if count >= 6:
                for i, ch in enumerate(otp[:count]):
                    await boxes.nth(i).fill(ch)
                otp_ok = True
        except Exception:
            pass
    if not otp_ok:
        raise RuntimeError("Cannot locate OTP input")

    await click_first_match(page, ['button[type="submit"]','input[type="submit"]','button:has-text("Verify")'])
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=30_000)
    except PwTimeout:
        pass


async def is_authenticated(page: Page) -> bool:
    try:
        base_portal = to_base(os.getenv("PORTAL_URL") or "")
        current_base = to_base(page.url or base_portal)
        if base_portal and current_base != base_portal:
            return False
        maybe_login_field = page.locator('#okta-signin-username, input[name="username"], input[type="password"], #okta-signin-password')
        visible = await maybe_login_field.first.is_visible(timeout=1500)
        return not visible
    except Exception:
        return False


async def submit_code_on_entry(page: Page, code: str) -> Tuple[bool, str]:
    logger.debug(f"Submitting code: {code}")
    filled = await fill_first_match(page, [
        'input[name="code"]','input[id*="code" i]','input[placeholder*="code" i]','input[type="text"]'], code)
    if not filled:
        return False, "Cannot locate code input"
    await click_first_match(page, ['button[type="submit"]','input[type="submit"]','button:has-text("Submit")'])
    await page.wait_for_timeout(1500)
    for sel in ['text=/invalid code/i','text=/incorrect code/i','text=/wrong code/i','text=/expired/i','text=/not valid/i']:
        try:
            if await page.locator(sel).first.is_visible():
                return False, "Possibly wrong or expired code"
        except Exception:
            continue
    for sel in ['text=/success/i','text=/submitted/i']:
        try:
            if await page.locator(sel).first.is_visible():
                return True, "submitted"
        except Exception:
            continue
    return True, "submitted (no explicit success hint)"


async def run_submit(dry_run: bool = False) -> None:
    PORTAL_URL = os.getenv("PORTAL_URL")
    BROWSER = os.getenv("BROWSER", "chromium").lower()
    BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "chrome")
    HEADLESS = os.getenv("HEADLESS", "1") not in ("0", "false", "False")
    USER_DATA_DIR = os.getenv("USER_DATA_DIR")
    STORAGE_STATE = os.getenv("STORAGE_STATE", "storage_state.json")
    WEEK_NUMBER = os.getenv("WEEK_NUMBER")

    if not USER_DATA_DIR and os.path.exists(STORAGE_STATE) and not _is_storage_state_effective(STORAGE_STATE):
        logger.warning(f"Detected empty storage state at {STORAGE_STATE}; opening interactive login...")
        try:
            login_mod = importlib.import_module('login')
            await login_mod.run_login(
                portal_url=PORTAL_URL,
                browser_name=os.getenv('BROWSER', 'chromium'),
                channel=BROWSER_CHANNEL,
                headed=True,
                storage_state=STORAGE_STATE,
                user_data_dir=None,
            )
        except Exception as e:
            logger.warning(f"Auto login failed: {e}. Please run `python login.py --headed` manually.")
            return

    async with async_playwright() as p:
        browser_type = p.chromium if BROWSER == 'chromium' else (p.firefox if BROWSER == 'firefox' else p.webkit)
        launch_kwargs = {"headless": HEADLESS}
        if BROWSER == 'chromium' and BROWSER_CHANNEL:
            launch_kwargs["channel"] = BROWSER_CHANNEL

        logger.info(f"Launching browser: {BROWSER} channel={launch_kwargs.get('channel','default')} headless={HEADLESS}")
        context = None
        browser = None
        if USER_DATA_DIR:
            try:
                context = await browser_type.launch_persistent_context(USER_DATA_DIR, **launch_kwargs)
            except Exception as e:
                logger.warning(f"Failed to launch with system channel '{BROWSER_CHANNEL}': {e}. Falling back to default.")
                launch_kwargs.pop('channel', None)
                context = await browser_type.launch_persistent_context(USER_DATA_DIR, **launch_kwargs)
            page = await context.new_page()
        else:
            try:
                browser = await browser_type.launch(**launch_kwargs)
            except Exception as e:
                logger.warning(f"Failed to launch with system channel '{BROWSER_CHANNEL}': {e}. Falling back to default.")
                launch_kwargs.pop('channel', None)
                browser = await browser_type.launch(**launch_kwargs)
            context_kwargs = {}
            if os.path.exists(STORAGE_STATE):
                context_kwargs["storage_state"] = STORAGE_STATE
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

        try:
            try:
                await page.goto(PORTAL_URL, timeout=60_000)
            except Exception:
                pass
            if not await is_authenticated(page):
                logger.warning("Not authenticated; running login flow...")
                await login(page)
            base = to_base(page.url) or to_base(PORTAL_URL)
            start_time = time.monotonic()

            PAGE_NAV_TIMEOUT_MS = int(os.getenv('PAGE_NAV_TIMEOUT_MS', 25000))
            PANEL_WAIT_MS = int(os.getenv('PANEL_WAIT_MS', 6000))
            DAY_SLEEP_MIN = float(os.getenv('DAY_SLEEP_MIN', 1.0))
            DAY_SLEEP_MAX = float(os.getenv('DAY_SLEEP_MAX', 2.2))

            enrolled_courses = await get_enrolled_courses(page)
            if not enrolled_courses:
                logger.error("No enrolled courses found on the page.")
                return

            issues_url = os.getenv("ISSUES_NEW_URL") or "https://github.com/tutu/always-attend/issues/new"
            for course in enrolled_courses:
                logger.info(f"[STEP] Processing course: {course}")
                week_for_course = WEEK_NUMBER or find_latest_week(course)
                if not week_for_course:
                    logger.warning(f"No week detected for {course}. Add data/{course}/<week>.json or set WEEK_NUMBER.")
                    continue

                entries = parse_codes(course_code=course, week_number=week_for_course)
                codes = list({(item.get('code') or '').strip() for item in entries if (item.get('code') or '').strip()})
                if not codes:
                    logger.warning(f"No attendance codes found for {course} week {week_for_course}.")
                    logger.info(f"You can add missing codes by creating an issue at: {issues_url}")
                    continue

                logger.info(f"[OK] Loaded {len(codes)} codes for {course} (week {week_for_course})")

                if dry_run:
                    for code in codes:
                        print(" -", {'course': course, 'week': week_for_course, 'code': code})
                    continue

                monday_dt: Optional[datetime] = None
                try:
                    dates = [datetime.strptime(it['date'], '%Y-%m-%d') for it in entries if it.get('date')]
                    base_day = min(dates) if dates else datetime.now()
                    monday_dt = base_day - timedelta(days=base_day.weekday())
                except Exception:
                    monday_dt = None

                anchors = await collect_day_anchors(page, base, start_monday=monday_dt)
                today_date = datetime.now().date()
                for idx, anchor in enumerate(anchors):
                    try:
                        GLOBAL_TIMEOUT_SEC = int(os.getenv("GLOBAL_TIMEOUT_SEC", "900"))
                    except Exception:
                        GLOBAL_TIMEOUT_SEC = 900
                    if GLOBAL_TIMEOUT_SEC and (time.monotonic() - start_time) > GLOBAL_TIMEOUT_SEC:
                        logger.warning("Global timeout reached; stopping run.")
                        return
                    try:
                        adt = parse_anchor(anchor)
                        if adt and adt.date() > today_date:
                            logger.info("Reached future day; stopping this week's scan.")
                            break
                    except Exception:
                        pass
                    if idx > 0:
                        delay = random.uniform(DAY_SLEEP_MIN, DAY_SLEEP_MAX)
                        logger.debug(f"Sleeping {delay:.2f}s before next day panel...")
                        await asyncio.sleep(delay)
                    units_url = f"{base}/student/Units.aspx#{anchor}"
                    logger.info(f"[STEP] Open day panel: {units_url}")
                    try:
                        await page.goto(units_url, timeout=PAGE_NAV_TIMEOUT_MS)
                        day_panel_selector = f'#dayPanel_{anchor}'
                        js_function = f""" 
                        () => {{
                            const panel = document.querySelector('{day_panel_selector}');
                            if (!panel) return false;
                            const style = window.getComputedStyle(panel);
                            return style.display !== 'none';
                        }}
                        """
                        await page.wait_for_function(js_function, timeout=PANEL_WAIT_MS)
                        root = page.locator(day_panel_selector)
                    except Exception:
                        logger.debug(f"Day {anchor}: dayPanel not found or not visible quickly; scanning whole page for entries.")
                        root = page

                    clickable_entries = root.locator(f'li:not(.ui-disabled):has-text(/{course}/i)')
                    try:
                        entry_count = await clickable_entries.count()
                    except Exception:
                        entry_count = 0
                    logger.debug(f"Day {anchor}: found {entry_count} clickable entries for {course}")

                    for i in range(entry_count):
                        try:
                            entry = clickable_entries.nth(i)
                            text = (await entry.inner_text()).strip()
                            if 'PASS' in text.upper():
                                continue

                            await entry.scroll_into_view_if_needed()
                            await entry.click()
                            await page.wait_for_timeout(500)

                            logger.info(f"[STEP] Processing {course} - {text}...")
                            submitted = False
                            for code_val in codes:
                                ok, msg = await submit_code_on_entry(page, code_val)
                                if ok:
                                    logger.info(f"[OK] Submitted {course}: {msg}")
                                    submitted = True
                                    break
                            if not submitted:
                                logger.warning(f"Failed {course}: no code was accepted for this entry.")

                            await page.goto(units_url, timeout=PAGE_NAV_TIMEOUT_MS)
                            break
                        except Exception as e:
                            logger.warning(f"An error occurred while processing an entry for {course} on {anchor}: {e}")
                            try:
                                await page.goto(units_url, timeout=PAGE_NAV_TIMEOUT_MS)
                            except Exception:
                                logger.error("Failed to recover by navigating back to Units page. Stopping.")
                                return
        finally:
            if browser is not None:
                try:
                    await context.storage_state(path=os.getenv("STORAGE_STATE", "storage_state.json"))
                except Exception:
                    pass
                await browser.close()
            else:
                await context.close()


def main():
    load_env(os.getenv('ENV_FILE', '.env'))

    ap = argparse.ArgumentParser(description="Submit attendance codes (requires prior login)")
    ap.add_argument("--browser", choices=["chromium", "firefox", "webkit"], help="Browser engine override")
    ap.add_argument("--channel", help="Use system browser channel (chromium only): chrome|chrome-beta|msedge|msedge-beta")
    ap.add_argument("--headed", action="store_true", help="Run with browser UI (sets HEADLESS=0)")
    ap.add_argument("--dry-run", action="store_true", help="Print parsed codes and exit (no browser)")
    ap.add_argument("--week", help="Week number to submit (sets WEEK_NUMBER)")
    args = ap.parse_args()

    if args.browser:
        os.environ['BROWSER'] = args.browser
    if args.channel:
        os.environ['BROWSER_CHANNEL'] = args.channel
    if args.headed:
        os.environ['HEADLESS'] = '0'
    if args.week:
        os.environ['WEEK_NUMBER'] = str(args.week)
    
    asyncio.run(run_submit(dry_run=bool(args.dry_run or os.getenv('DRY_RUN') in ('1','true','True'))))


if __name__ == '__main__':
    main()