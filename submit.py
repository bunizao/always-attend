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

# Unified logger
from logger import (
    log_debug,
    log_info,
    log_step,
    log_ok,
    log_warn,
    log_err,
)
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
    log_step("Scraping page for enrolled courses...")
    try:
        if os.getenv("DEBUG_SCRAPING") == "1":
            log_info("Debug scraping enabled. Page content will be printed.")
            log_debug(await page.content())

        # Try to find course codes in links first, as they are more likely to be there.
        all_text = " ".join(await page.locator('a').all_inner_texts())

        # If no codes in links, get all page text
        if not re.search(r'\b([A-Z]{3}\d{4})\b', all_text):
            all_text = await page.content()

        course_codes = re.findall(r'\b([A-Z]{3}\d{4})\b', all_text)
        unique_codes = sorted(list(set(course_codes)))
        log_info(f"Found {len(unique_codes)} enrolled courses: {unique_codes}")
        return unique_codes
    except Exception as e:
        log_warn(f"Could not scrape enrolled courses: {e}")
        return []


def parse_codes(course_code: Optional[str] = None, week_number: Optional[str] = None) -> List[Dict[str, Optional[str]]]:
    CODES_FILE = os.getenv("CODES_FILE")
    CODES_URL = os.getenv("CODES_URL")
    CODES_BASE_URL = os.getenv("CODES_BASE_URL")

    result: List[Dict[str, Optional[str]]] = []

    # 1) Per-slot env (WORKSHOP_1=..., APPLIED_2=...)
    env_slot_re = re.compile(r'^([A-Z]+)_([0-9]+)$')
    for var_name, var_value in os.environ.items():
        m = env_slot_re.match(var_name.upper())
        if m and var_value:
            slot_name = f"{m.group(1).capitalize()} {m.group(2)}"
            # Omit date when unknown (avoid nulls in JSON)
            result.append({"slot": slot_name, "code": var_value.strip()})
    if result:
        log_info(f"Loaded {len(result)} codes from per-slot environment variables")
        return result

    # 2) Auto-discovery via COURSE_CODE/WEEK_NUMBER/CODES_BASE_URL
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
                    log_info(f"Loaded {len(result)} codes via auto-discovery: {auto_url}")
                    return result
            except Exception as e:
                log_warn(f"Auto-discovery failed for {course_code} week {week_number}: {e}")

    # 2b) Local repository data fallback: data/{course}/{week}.json
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
                        log_info(f"Loaded {len(result)} codes from local data: {local_path}")
                        return result
                except Exception as e:
                    log_warn(f"Failed to load local data file {local_path}: {e}")

    # 3) CODES_URL
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
                log_info(f"Loaded {len(result)} codes from CODES_URL")
                return result
        except Exception as e:
            log_warn(f"Failed to fetch CODES_URL: {e}")

    # 4) CODES_FILE
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
                log_info(f"Loaded {len(result)} codes from CODES_FILE={CODES_FILE}")
                return result
        except Exception as e:
            log_warn(f"Failed to parse CODES_FILE: {e}")

    # 5) CODES inline
    codes_str = os.getenv("CODES")
    if codes_str:
        pairs = [p.strip() for p in codes_str.split(';') if p.strip()]
        for pair in pairs:
            if ':' in pair:
                slot, code = pair.split(':', 1)
                # Omit date when unknown
                result.append({"slot": slot.strip(), "code": code.strip()})
        if result:
            log_info(f"Loaded {len(result)} codes from CODES inline")
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

    # If fields not visible, assume already authenticated
    try:
        maybe_login_field = page.locator('#okta-signin-username, input[name="username"], input[type="password"], #okta-signin-password')
        if not await maybe_login_field.first.is_visible(timeout=2000):
            return
    except Exception:
        pass

    log_step("Filling username/password...")
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

    log_step("Submitting MFA code...")
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


def _build_label_regex(label: str) -> str:
    import re
    # Escape regex special chars except spaces and digits
    esc = []
    for ch in label:
        if ch.isalnum() or ch.isspace():
            esc.append(ch)
        else:
            esc.append(re.escape(ch))
    s = ''.join(esc)
    # Collapse spaces to \s+ and allow separators [-_]
    s = re.sub(r"\s+", r"[\\s_-]+", s)
    # Make digit runs match with optional leading zeros
    s = re.sub(r"(\d+)", lambda m: r"0*" + m.group(1), s)
    # Allow optional segment suffix like -P1 / _P2 / P03 at the end
    s = s + r"(?:[\\s_-]*P?0*\d+)?"
    return s


def _build_tokens_lookahead(label: str) -> str:
    import re
    # Split into alnum tokens; keep order-agnostic via lookaheads
    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", label) if t]
    looks = []
    for t in tokens:
        if t.isdigit():
            looks.append(fr"(?=.*0*{t})")
        elif (t[0] in 'Pp') and t[1:].isdigit():
            looks.append(fr"(?=.*p?0*{t[1:]})")
        else:
            looks.append(fr"(?=.*{re.escape(t)})")
    # Also allow an optional trailing -P\d+ segment
    looks.append(r"(?:.*[\s_-]P?0*\d+)?")
    return ''.join(looks)


async def find_and_open_slot(page: Page, base_url: str, date_str: Optional[str], label: Optional[str]) -> bool:
    if date_str:
        anchor = format_anchor(date_str)
        units_url = f"{base_url}/student/Units.aspx#{anchor}"
    else:
        units_url = f"{base_url}/student/Units.aspx"
    log_step(f"Open schedule page: {units_url}")
    await page.goto(units_url, timeout=60_000)
    if date_str:
        day_panel_sel = f'#dayPanel_{anchor}'
        try:
            await page.wait_for_selector(day_panel_sel, timeout=30_000)
        except PwTimeout:
            return False
        day_panel = page.locator(day_panel_sel)
        search_scope = day_panel
    else:
        search_scope = page

    if not label:
        return False

    # Try exact has-text (case-insensitive by Playwright)
    candidates = search_scope.locator(f'a:has-text("{label}")')
    try:
        count = await candidates.count()
        log_info(f"Found {count} candidates for label '{label}' (exact)")
        if count > 0:
            await candidates.nth(0).click()
            return True
    except Exception:
        pass

    # Try regex that tolerates zero padding, flexible spacing, optional -P\d+ suffix
    regex = _build_label_regex(label)
    candidates = search_scope.locator(f'a:has-text(/{regex}/i)')
    try:
        count = await candidates.count()
        log_info(f"Found {count} candidates for label /{regex}/i (regex)")
        if count > 0:
            await candidates.nth(0).click()
            return True
    except Exception:
        pass
    # Try token lookahead regex: all tokens must appear (order-agnostic)
    la = _build_tokens_lookahead(label)
    candidates = search_scope.locator(f'a:has-text(/{la}/i)')
    try:
        count = await candidates.count()
        log_info(f"Found {count} candidates for tokens /{la}/i (lookahead)")
        if count > 0:
            await candidates.nth(0).click()
            return True
    except Exception:
        pass
    try:
        return False
    except Exception:
        return False


ERROR_HINT_SELECTORS = [
    'text=/invalid code/i','text=/incorrect code/i','text=/wrong code/i','text=/expired/i','text=/not valid/i'
]
SUCCESS_HINT_SELECTORS = ['text=/success/i','text=/submitted/i']


async def submit_code_on_entry(page: Page, code: str) -> Tuple[bool, str]:
    log_debug(f"Submitting code: {code}")
    filled = await fill_first_match(page, [
        'input[name="code"]','input[id*="code" i]','input[placeholder*="code" i]','input[type="text"]'], code)
    if not filled:
        return False, "Cannot locate code input"
    await click_first_match(page, ['button[type="submit"]','input[type="submit"]','button:has-text("Submit")'])
    await page.wait_for_timeout(1500)
    for sel in ERROR_HINT_SELECTORS:
        try:
            if await page.locator(sel).first.is_visible():
                return False, "Possibly wrong or expired code"
        except Exception:
            continue
    for sel in SUCCESS_HINT_SELECTORS:
        try:
            if await page.locator(sel).first.is_visible():
                return True, "submitted"
        except Exception:
            continue
    return True, "submitted (no explicit success hint)"


async def try_submit_code_anywhere(page: Page, base: str, code: str, date_anchor: Optional[str] = None) -> Tuple[bool, str]:
    """Try to submit a code without selecting a specific slot.

    Navigates across a small set of known pages and attempts to locate a code input.
    Returns (ok, message).
    """
    targets: List[str] = []
    # Prefer Units.aspx day anchor where code input typically appears
    if date_anchor:
        targets.append(f"{base}/student/Units.aspx#{date_anchor}")
    else:
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            targets.append(f"{base}/student/Units.aspx#{format_anchor(today_str)}")
        except Exception:
            pass
    targets += [
        f"{base}/student/AttendanceInfo.aspx",
        f"{base}/student/Units.aspx",
        f"{base}/student/Default.aspx",
        base,
    ]
    input_selectors = [
        'input[name="code"]','input[id*="code" i]','input[placeholder*="code" i]',
        'input[name="otp"]','input[name="passcode"]','input[autocomplete="one-time-code"]','input[inputmode="numeric"]','input[type="tel"]'
    ]

    async def has_visible_code_input() -> bool:
        for sel in input_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1000):
                    return True
            except Exception:
                continue
        return False

    async def try_click_ctas() -> None:
        candidates = [
            'button:has-text("Submit attendance")',
            r'text=/\bSubmit\s+attendance\b/i',
            'button:has-text("Submit")',
            'a:has-text("Submit")',
            r'text=/\bAttendance\b/i',
            r'text=/\bEnter\s+code\b/i',
        ]
        for sel in candidates:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1000):
                    await el.click()
                    await page.wait_for_timeout(300)
            except Exception:
                continue
    
    for url in targets:
        try:
            log_debug(f"Try submit on: {url}")
            await page.goto(url, timeout=45_000)
        except Exception:
            continue
        # If there's a code input already, submit
        if await has_visible_code_input():
            return await submit_code_on_entry(page, code)
        # Otherwise, poke likely CTAs to reveal input and retry
        await try_click_ctas()
        if await has_visible_code_input():
            return await submit_code_on_entry(page, code)
    return False, "No code input found across known pages"


async def collect_day_anchors(page: Page, base: str, start_monday: Optional[datetime] = None) -> List[str]:
    url = f"{base}/student/Units.aspx"
    await page.goto(url, timeout=60_000)
    panels = page.locator('[id^="dayPanel_"]')
    anchors: List[str] = []
    try:
        count = await panels.count()
        for i in range(count):
            pid = await panels.nth(i).get_attribute('id')
            if pid and pid.startswith('dayPanel_'):
                anchors.append(pid[len('dayPanel_'):])
    except Exception:
        pass
    # Sort anchors by date and optionally filter to the ISO week starting at start_monday
    dated: List[Tuple[datetime, str]] = []
    for a in anchors:
        dt = parse_anchor(a)
        if dt:
            dated.append((dt, a))
    dated.sort(key=lambda x: x[0])
    if start_monday:
        week_end = start_monday + timedelta(days=6)
        dated = [t for t in dated if start_monday.date() <= t[0].date() <= week_end.date()]
    return [a for _, a in dated] or anchors


def _list_local_codes_for_course(course_code: str) -> List[str]:
    """Aggregate distinct codes from data/{COURSE}/*.json (local repository)."""
    codes: List[str] = []
    try:
        course = ''.join(ch for ch in course_code.upper() if ch.isalnum())
        course_dir = os.path.join('data', course)
        if not os.path.isdir(course_dir):
            return []
        seen = set()
        for name in sorted(os.listdir(course_dir)):
            if not name.endswith('.json'):
                continue
            path = os.path.join(course_dir, name)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    continue
                for item in data:
                    code_val = str((item or {}).get('code') or '').strip()
                    if code_val and code_val not in seen:
                        seen.add(code_val)
                        codes.append(code_val)
            except Exception:
                continue
    except Exception:
        return codes
    return codes


async def run_submit(dry_run: bool = False) -> None:
    PORTAL_URL = os.getenv("PORTAL_URL")
    BROWSER = os.getenv("BROWSER", "chromium").lower()
    BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "chrome")
    HEADLESS = os.getenv("HEADLESS", "1") not in ("0", "false", "False")
    USER_DATA_DIR = os.getenv("USER_DATA_DIR")
    STORAGE_STATE = os.getenv("STORAGE_STATE", "storage_state.json")
    WEEK_NUMBER = os.getenv("WEEK_NUMBER")

    if not USER_DATA_DIR and os.path.exists(STORAGE_STATE) and not _is_storage_state_effective(STORAGE_STATE):
        log_warn(f"Detected empty storage state at {STORAGE_STATE}; opening interactive login...")
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
            log_warn(f"Auto login failed: {e}. Please run `python login.py --headed` manually.")
            return

    async with async_playwright() as p:
        browser_type = p.chromium if BROWSER == 'chromium' else (p.firefox if BROWSER == 'firefox' else p.webkit)
        launch_kwargs = {"headless": HEADLESS}
        if BROWSER == 'chromium' and BROWSER_CHANNEL:
            launch_kwargs["channel"] = BROWSER_CHANNEL

        log_info(f"Launching browser: {BROWSER} channel={launch_kwargs.get('channel','default')} headless={HEADLESS}")
        context = None
        browser = None
        if USER_DATA_DIR:
            try:
                context = await browser_type.launch_persistent_context(USER_DATA_DIR, **launch_kwargs)
            except Exception as e:
                log_warn(f"Failed to launch with system channel '{BROWSER_CHANNEL}': {e}. Falling back to default.")
                launch_kwargs.pop('channel', None)
                context = await browser_type.launch_persistent_context(USER_DATA_DIR, **launch_kwargs)
            page = await context.new_page()
        else:
            try:
                browser = await browser_type.launch(**launch_kwargs)
            except Exception as e:
                log_warn(f"Failed to launch with system channel '{BROWSER_CHANNEL}': {e}. Falling back to default.")
                launch_kwargs.pop('channel', None)
                browser = await browser_type.launch(**launch_kwargs)
            context_kwargs = {}
            if os.path.exists(STORAGE_STATE):
                context_kwargs["storage_state"] = STORAGE_STATE
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

        try:
            # Ensure authenticated
            try:
                await page.goto(PORTAL_URL, timeout=60_000)
            except Exception:
                pass
            if not await is_authenticated(page):
                log_warn("Not authenticated; running login flow...")
                await login(page)
            base = to_base(page.url) or to_base(PORTAL_URL)
            # Global timeout baseline and config
            start_time = time.monotonic()

            # Tuning knobs (env-configurable)
            def _env_float(name: str, default: float) -> float:
                try:
                    return float(os.getenv(name, str(default)))
                except Exception:
                    return default

            def _env_int(name: str, default: int) -> int:
                try:
                    return int(os.getenv(name, str(default)))
                except Exception:
                    return default

            PAGE_NAV_TIMEOUT_MS = _env_int('PAGE_NAV_TIMEOUT_MS', 25000)
            PANEL_WAIT_MS = _env_int('PANEL_WAIT_MS', 6000)
            VISIBLE_WAIT_MS = _env_int('VISIBLE_WAIT_MS', 700)
            DAY_SLEEP_MIN = _env_float('DAY_SLEEP_MIN', 1.0)
            DAY_SLEEP_MAX = _env_float('DAY_SLEEP_MAX', 2.2)
            FALLBACK_GENERIC_SCAN = os.getenv('FALLBACK_GENERIC_SCAN') in ('1','true','True')

            attendance_info_url = f"{base}/student/AttendanceInfo.aspx"
            log_step(f"Navigating to attendance info page: {attendance_info_url}")
            await page.goto(attendance_info_url, timeout=PAGE_NAV_TIMEOUT_MS)

            enrolled_courses = await get_enrolled_courses(page)
            if not enrolled_courses:
                log_err("No enrolled courses found on the page.")
                return

            # Early availability check: for each course, verify local database presence for the target week.
            # Do not interrupt execution; only inform the user how to contribute missing data.
            def _find_latest_week(course: str) -> Optional[str]:
                try:
                    course_dir = os.path.join('data', ''.join(ch for ch in course if ch.isalnum()))
                    if not os.path.isdir(course_dir):
                        return None
                    weeks = []
                    for name in os.listdir(course_dir):
                        if name.endswith('.json'):
                            base = name[:-5]
                            if base.isdigit():
                                weeks.append(int(base))
                    if not weeks:
                        return None
                    return str(max(weeks))
                except Exception:
                    return None

            issues_url = os.getenv("ISSUES_NEW_URL") or "https://github.com/bunizao/always-attend/issues/new"
            WEEK_NUMBER = os.getenv("WEEK_NUMBER") or None
            for course in enrolled_courses:
                target_week = WEEK_NUMBER or _find_latest_week(course)
                course_sanitized = ''.join(ch for ch in course if ch.isalnum())
                local_path = os.path.join('data', course_sanitized, f"{target_week}.json") if target_week else None
                if not target_week or not (local_path and os.path.exists(local_path)):
                    log_warn(f"Missing local codes for {course} week {target_week or '?'}.")
                    log_info(f"You can add them via an Issue: {issues_url}")

            def find_latest_week(course: str) -> Optional[str]:
                try:
                    course_dir = os.path.join('data', ''.join(ch for ch in course if ch.isalnum()))
                    if not os.path.isdir(course_dir):
                        return None
                    weeks = []
                    for name in os.listdir(course_dir):
                        if name.endswith('.json'):
                            base = name[:-5]
                            if base.isdigit():
                                weeks.append(int(base))
                    if not weeks:
                        return None
                    return str(max(weeks))
                except Exception:
                    return None

            for course in enrolled_courses:
                log_step(f"Processing course: {course}")
                # Determine target week: explicit WEEK_NUMBER or latest available week
                week_for_course = WEEK_NUMBER or find_latest_week(course)
                if not week_for_course:
                    log_warn(f"No week detected for {course}. Add data/{course}/<week>.json or set WEEK_NUMBER.")
                    continue

                entries = parse_codes(course_code=course, week_number=week_for_course)
                codes = list({(item.get('code') or '').strip() for item in entries if (item.get('code') or '').strip()})
                code_to_anchor: Dict[str, str] = {}
                for it in entries:
                    code_val = (it.get('code') or '').strip()
                    date_str = (it.get('date') or '').strip()
                    if code_val and date_str:
                        try:
                            code_to_anchor[code_val] = format_anchor(date_str)
                        except Exception:
                            pass

                if not codes:
                    log_warn(f"No attendance codes found for {course} week {week_for_course}.")
                    issues_url = os.getenv("ISSUES_NEW_URL") or "https://github.com/bunizao/always-attend/issues/new"
                    log_info(f"You can add missing codes by creating an issue at: {issues_url}")
                    continue

                log_ok(f"Loaded {len(codes)} codes for {course} (week {week_for_course})")

                if dry_run:
                    for code in codes:
                        print(" -", {'course': course, 'week': week_for_course, 'code': code})
                    continue

                # Iterate day panels, click entries for this course (exclude PASS), try week codes
                # Determine week start (Monday) using entry dates when available, else current week
                monday_dt: Optional[datetime] = None
                try:
                    dates = []
                    for it in entries:
                        ds = (it.get('date') or '').strip()
                        if ds:
                            dates.append(datetime.strptime(ds, '%Y-%m-%d'))
                    if dates:
                        base_day = min(dates)
                    else:
                        base_day = datetime.now()
                    monday_dt = base_day - timedelta(days=base_day.weekday())
                except Exception:
                    monday_dt = None

                anchors = await collect_day_anchors(page, base, start_monday=monday_dt)
                today_date = datetime.now().date()
                for idx, anchor in enumerate(anchors):
                    # Exit strategy: global timeout and attempt caps (configurable)
                    # Read lazily to avoid cluttering top-level scope
                    try:
                        GLOBAL_TIMEOUT_SEC = int(os.getenv("GLOBAL_TIMEOUT_SEC", "900"))
                    except Exception:
                        GLOBAL_TIMEOUT_SEC = 900
                    if GLOBAL_TIMEOUT_SEC and (time.monotonic() - start_time) > GLOBAL_TIMEOUT_SEC:
                        log_warn("Global timeout reached; stopping run.")
                        return
                    # Stop when reaching future days (cannot submit future codes)
                    try:
                        adt = parse_anchor(anchor)
                        if adt and adt.date() > today_date:
                            log_info("Reached future day; stopping this week's scan.")
                            break
                    except Exception:
                        pass
                    if idx > 0:
                        # Sleep only between days; keep it short and configurable
                        delay = random.uniform(DAY_SLEEP_MIN, DAY_SLEEP_MAX)
                        log_debug(f"Sleeping {delay:.2f}s before next day panel...")
                        await asyncio.sleep(delay)
                    units_url = f"{base}/student/Units.aspx#{anchor}"
                    log_step(f"Open day panel: {units_url}")
                    try:
                        await page.goto(units_url, timeout=PAGE_NAV_TIMEOUT_MS)
                        await page.wait_for_selector(f'#dayPanel_{anchor}', timeout=PANEL_WAIT_MS)
                    except Exception:
                        continue
                    day_panel = page.locator(f'#dayPanel_{anchor}')
                    processed_this_day = False
                    tried_entries = 0

                    # Fast path A: direct anchors that already include the course text
                    links_course = day_panel.locator(f'a:has-text(/{course}/i)')
                    try:
                        lcount = await links_course.count()
                    except Exception:
                        lcount = 0
                    for i in range(lcount):
                        try:
                            el = links_course.nth(i)
                            text = (await el.inner_text()).strip()
                            if re.search(r'\bPASS\b', text, flags=re.I):
                                continue
                            await el.scroll_into_view_if_needed()
                            await el.click()
                            # Small grace period for dynamic content
                            await page.wait_for_timeout(200)
                            # Verify page belongs to course or has code input
                            course_ok = False
                            try:
                                if await page.locator(f'text={course}').first.is_visible(timeout=VISIBLE_WAIT_MS):
                                    course_ok = True
                            except Exception:
                                course_ok = False
                            page_has_code_input = False
                            for sel in ['input[name="code"]','input[id*="code" i]','input[placeholder*="code" i]','input[type="text"]']:
                                try:
                                    if await page.locator(sel).first.is_visible(timeout=VISIBLE_WAIT_MS):
                                        page_has_code_input = True
                                        break
                                except Exception:
                                    continue
                            if not (course_ok or page_has_code_input):
                                try:
                                    await page.go_back(timeout=PANEL_WAIT_MS)
                                except Exception:
                                    try:
                                        await page.goto(units_url, timeout=PAGE_NAV_TIMEOUT_MS)
                                    except Exception:
                                        pass
                                continue
                            # Process codes
                            processed_this_day = True
                            tried_entries += 1
                            log_step(f"Processing {course}...")
                            submitted = False
                            for code_val in codes:
                                ok, msg = await submit_code_on_entry(page, code_val)
                                if ok:
                                    log_ok(f"Submitted {course}: {msg}")
                                    submitted = True
                                    break
                            if not submitted:
                                log_warn(f"Failed {course}: no code accepted for this entry")
                            try:
                                await page.go_back(timeout=PANEL_WAIT_MS)
                            except Exception:
                                try:
                                    await page.goto(units_url, timeout=PAGE_NAV_TIMEOUT_MS)
                                except Exception:
                                    pass
                        except Exception:
                            # Any unexpected issue within direct anchor flow: skip this link
                            continue
                    if tried_entries and not FALLBACK_GENERIC_SCAN:
                        # If we processed some entries via direct anchors and fallback is disabled, skip remaining strategies
                        continue

                    # Strategy 1: find containers that mention the course, then click a link/button inside
                    containers = day_panel.locator(
                        f'tr:has-text(/{course}/i) , li:has-text(/{course}/i) , div:has-text(/{course}/i) , section:has-text(/{course}/i) , article:has-text(/{course}/i)'
                    )
                    try:
                        ccount = await containers.count()
                    except Exception:
                        ccount = 0
                    # Fast path: if no course containers and fallback disabled, skip this day quickly
                    if ccount == 0 and not FALLBACK_GENERIC_SCAN:
                        continue
                    for i in range(ccount):
                        try:
                            cont = containers.nth(i)
                            ctext = (await cont.inner_text()).strip()
                        except Exception:
                            continue
                        if re.search(r'\bPASS\b', ctext, flags=re.I):
                            continue
                        # Find a clickable within this container
                        el = cont.locator('a, button, [role="link"], [role="button"]').first
                        try:
                            if not await el.is_visible(timeout=VISIBLE_WAIT_MS):
                                continue
                            await el.click()
                            await page.wait_for_load_state('domcontentloaded', timeout=PANEL_WAIT_MS)
                        except Exception:
                            continue
                        tried_entries += 1
                        processed_this_day = True
                        # Try week codes
                        log_step(f"Processing {course}...")
                        submitted = False
                        for code_val in codes:
                            ok, msg = await submit_code_on_entry(page, code_val)
                            if ok:
                                log_ok(f"Submitted {course}: {msg}")
                                submitted = True
                                break
                        if not submitted:
                            log_warn(f"Failed {course}: no code accepted for this entry")
                        # Return to day panel
                        try:
                            await page.go_back(timeout=PANEL_WAIT_MS)
                        except Exception:
                            try:
                                await page.goto(units_url, timeout=PAGE_NAV_TIMEOUT_MS)
                            except Exception:
                                pass
                    # Strategy 2: fallback to scanning generic links/buttons if nothing matched containers
                    if tried_entries == 0:
                        links = day_panel.locator('a, button, [role="link"], [role="button"]')
                        try:
                            n = await links.count()
                        except Exception:
                            n = 0
                        for i in range(n):
                            try:
                                el = links.nth(i)
                                text = (await el.inner_text()).strip()
                            except Exception:
                                continue
                            if re.search(r'\bPASS\b', text, flags=re.I):
                                continue
                            # Click first, then verify course or code input exists
                            try:
                                await el.click()
                                await page.wait_for_load_state('domcontentloaded', timeout=PANEL_WAIT_MS)
                            except Exception:
                                continue
                            processed_this_day = True
                            course_ok = False
                            try:
                                if await page.locator(f'text={course}').first.is_visible(timeout=VISIBLE_WAIT_MS):
                                    course_ok = True
                            except Exception:
                                course_ok = False
                            # In fallback mode, require explicit course confirmation on the opened page
                            if not course_ok:
                                try:
                                    await page.go_back(timeout=PANEL_WAIT_MS)
                                except Exception:
                                    try:
                                        await page.goto(units_url, timeout=PAGE_NAV_TIMEOUT_MS)
                                    except Exception:
                                        pass
                                continue
                            # Try week codes
                            log_step(f"Processing {course}...")
                            submitted = False
                            for code_val in codes:
                                ok, msg = await submit_code_on_entry(page, code_val)
                                if ok:
                                    log_ok(f"Submitted {course}: {msg}")
                                    submitted = True
                                    break
                            if not submitted:
                                log_warn(f"Failed {course}: no code accepted for this entry")
                            try:
                                await page.go_back(timeout=PANEL_WAIT_MS)
                            except Exception:
                                try:
                                    await page.goto(units_url, timeout=PAGE_NAV_TIMEOUT_MS)
                                except Exception:
                                    pass
                    # Continue scanning remaining days unless a future day is reached
        finally:
            # Save storage state only for non-persistent contexts
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
