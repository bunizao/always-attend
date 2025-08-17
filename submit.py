import os
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse
import importlib
import argparse
import re

import pyotp
from playwright.async_api import async_playwright, Page, TimeoutError as PwTimeout


# ===== Helpers =====
def now_hms() -> str:
    return datetime.now().strftime("%H:%M:%S")


# --- simple colored logger ---
USE_COLOR = os.getenv("NO_COLOR") is None

class C:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"

def _c(s: str, color: str) -> str:
    if not USE_COLOR:
        return s
    return f"{color}{s}{C.RESET}"

def log_info(msg: str) -> None:
    print(f"[{now_hms()}] " + _c(msg, C.DIM))

def log_step(msg: str) -> None:
    print(f"[{now_hms()}] " + _c(msg, C.BLUE))

def log_ok(msg: str) -> None:
    print(f"[{now_hms()}] " + _c(msg, C.GREEN))

def log_warn(msg: str) -> None:
    print(f"[{now_hms()}] " + _c(msg, C.YELLOW))

def log_err(msg: str) -> None:
    print(f"[{now_hms()}] " + _c(msg, C.RED))


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
            print(await page.content())

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


def parse_codes(course_code: str, week_number: str) -> List[Dict[str, Optional[str]]]:
    CODES_FILE = os.getenv("CODES_FILE")
    CODES_URL = os.getenv("CODES_URL")
    CODES_BASE_URL = os.getenv("CODES_BASE_URL", "https://raw.githubusercontent.com/bunizao/always-attend/main")

    result: List[Dict[str, Optional[str]]] = []

    # 1) Per-slot env (WORKSHOP_1=..., APPLIED_2=...)
    env_slot_re = re.compile(r'^([A-Z]+)_([0-9]+)$')
    for var_name, var_value in os.environ.items():
        m = env_slot_re.match(var_name.upper())
        if m and var_value:
            slot_name = f"{m.group(1).capitalize()} {m.group(2)}"
            result.append({"slot": slot_name, "date": None, "code": var_value.strip()})
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
                result.append({"slot": slot.strip(), "date": None, "code": code.strip()})
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
        'text=/验证码/',
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
        await click_first_match(page, ['button[type="submit"]','button:has-text("Next")','button:has-text("Continue")','text=/继续|下一步/i'])
        pass_ok = await fill_first_match(page, [
            'input[name="password"]','input[autocomplete="current-password"]','input[type="password"]','input[placeholder*="pass" i]'], os.getenv("PASSWORD"))

    await click_first_match(page, ['button[type="submit"]','input[type="submit"]','button:has-text("Sign in")','button:has-text("Log in")','text=/登录|登入/i','#okta-signin-submit'])
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

    await click_first_match(page, ['button[type="submit"]','input[type="submit"]','button:has-text("Verify")','text=/验证|提交/i'])
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
    'text=/invalid code/i','text=/incorrect code/i','text=/wrong code/i','text=/expired/i','text=/not valid/i','text=/无效|错误|过期/'
]
SUCCESS_HINT_SELECTORS = ['text=/success/i','text=/submitted/i','text=/已提交|成功/']


async def submit_code_on_entry(page: Page, code: str) -> Tuple[bool, str]:
    log_step(f"Submitting code: {code}")
    filled = await fill_first_match(page, [
        'input[name="code"]','input[id*="code" i]','input[placeholder*="code" i]','input[type="text"]'], code)
    if not filled:
        return False, "Cannot locate code input"
    await click_first_match(page, ['button[type="submit"]','input[type="submit"]','button:has-text("Submit")','text=/提交|确认/i'])
    await page.wait_for_timeout(1500)
    for sel in ERROR_HINT_SELECTORS:
        try:
            if await page.locator(sel).first.is_visible():
                return False, "可能是错误或过期的 code"
        except Exception:
            continue
    for sel in SUCCESS_HINT_SELECTORS:
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
    WEEK_NUMBER = os.getenv("WEEK_NUMBER", "3")

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

            attendance_info_url = f"{base}/student/AttendanceInfo.aspx"
            log_step(f"Navigating to attendance info page: {attendance_info_url}")
            await page.goto(attendance_info_url, timeout=60_000)

            enrolled_courses = await get_enrolled_courses(page)
            if not enrolled_courses:
                log_err("No enrolled courses found on the page.")
                return

            for course in enrolled_courses:
                log_step(f"Processing course: {course}")
                entries = parse_codes(course_code=course, week_number=WEEK_NUMBER)

                if not entries:
                    log_warn(f"No attendance codes found for {course} week {WEEK_NUMBER}.")
                    issues_url = os.getenv("ISSUES_NEW_URL")
                    if issues_url:
                        log_info(f"You can add missing codes by creating an issue at: {issues_url}")
                    continue

                log_ok(f"Loaded {len(entries)} code entries for {course}")

                if dry_run:
                    for item in entries:
                        print(" -", item)
                    continue

                for item in entries:
                    slot = item.get("slot")
                    date_str = item.get("date")
                    code_val = (item.get("code") or "").strip()
                    if not code_val:
                        log_info(f"Skip entry without code: {item}")
                        continue
                    if not date_str:
                        log_err(f"Skip entry without date (required): {item}")
                        continue
                    # Validate date format and compute anchor
                    try:
                        anchor = format_anchor(date_str)
                    except Exception:
                        log_err(f"Skip entry with invalid date format (expect YYYY-MM-DD): {item}")
                        continue
                    log_step(f"Processing: date={date_str} (anchor={anchor}) slot={slot}")
                    opened = await find_and_open_slot(page, base, date_str, slot)
                    if not opened:
                        log_warn(" -> Not found or already submitted; skipping")
                        continue
                    ok, msg = await submit_code_on_entry(page, code_val)
                    if ok:
                        log_ok(f" -> OK: {msg}")
                    else:
                        log_err(f" -> FAILED: {msg}")
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
    # Light .env loader
    def load_env(path: str = ".env"):
        try:
            if not os.path.exists(path):
                return
            with open(path, 'r', encoding='utf-8') as f:
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

    load_env(os.getenv('ENV_FILE', '.env'))

    ap = argparse.ArgumentParser(description="Submit attendance codes (requires prior login)")
    ap.add_argument("--browser", choices=["chromium", "firefox", "webkit"], help="Browser engine override")
    ap.add_argument("--channel", help="Use system browser channel (chromium only): chrome|chrome-beta|msedge|msedge-beta")
    ap.add_argument("--headed", action="store_true", help="Run with browser UI (sets HEADLESS=0)")
    ap.add_argument("--dry-run", action="store_true", help="Print parsed codes and exit (no browser)")
    args = ap.parse_args()

    if args.browser:
        os.environ['BROWSER'] = args.browser
    if args.channel:
        os.environ['BROWSER_CHANNEL'] = args.channel
    if args.headed:
        os.environ['HEADLESS'] = '0'

    asyncio.run(run_submit(dry_run=bool(args.dry_run or os.getenv('DRY_RUN') in ('1','true','True'))))


if __name__ == '__main__':
    main()