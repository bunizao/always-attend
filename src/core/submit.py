"""
 █████╗ ██╗     ██╗    ██╗ █████╗ ██╗   ██╗███████╗
██╔══██╗██║     ██║    ██║██╔══██╗╚██╗ ██╔╝██╔════╝
███████║██║     ██║ █╗ ██║███████║ ╚████╔╝ ███████╗
██╔══██║██║     ██║███╗██║██╔══██║  ╚██╔╝  ╚════██║
██║  ██║███████╗╚███╔███╔╝██║  ██║   ██║   ███████║
╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝

 █████╗ ████████╗████████╗███████╗███╗   ██╗██████╗ 
██╔══██╗╚══██╔══╝╚══██╔══╝██╔════╝████╗  ██║██╔══██╗
███████║   ██║      ██║   █████╗  ██╔██╗ ██║██║  ██║
██╔══██║   ██║      ██║   ██╔══╝  ██║╚██╗██║██║  ██║
██║  ██║   ██║      ██║   ███████╗██║ ╚████║██████╔╝
╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═══╝╚═════╝ 
src/core/submit.py
Attendance submission workflow for Always Attend.
"""

import os
import json
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse, urlunparse
import argparse
import re

from playwright.async_api import async_playwright, Page, TimeoutError as PwTimeout

from utils.logger import logger, step, progress, success, debug_detail
from utils.env_utils import load_env
from utils.session import is_storage_state_effective
from core.stats import StatsManager

def to_base(origin_url: str) -> str:
    pu = urlparse(origin_url)
    return urlunparse((pu.scheme, pu.netloc, "", "", "", ""))


def _data_root() -> Path:
    return Path(os.getenv("CODES_DB_PATH", "data")).resolve()


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
    return is_storage_state_effective(path)


def _compute_raw_url_for_path(rel_path: str) -> Optional[str]:
    """Compute a GitHub raw URL for a repository-relative file path.

    Precedence:
    - If `CODES_BASE_URL` is set, join it with `rel_path`.
    - Else, attempt to derive from `git` remote `origin` and current branch.
    """
    try:
        # 1) Explicit base URL via env
        base = os.getenv("CODES_BASE_URL", "").strip()
        if base:
            rel = rel_path.replace(os.sep, "/").lstrip("/")
            return base.rstrip("/") + "/" + rel

        # 2) Derive from git remote
        import subprocess
        remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)
        if remote.returncode != 0:
            return None
        url = (remote.stdout or "").strip()
        owner_repo = ""
        if url.startswith("git@github.com:"):
            owner_repo = url.split(":", 1)[1]
        elif url.startswith("https://github.com/"):
            owner_repo = url.split("https://github.com/", 1)[1]
        owner_repo = owner_repo.rstrip("/")
        if owner_repo.endswith(".git"):
            owner_repo = owner_repo[:-4]
        if not owner_repo or "/" not in owner_repo:
            return None

        branch_proc = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
        branch = (branch_proc.stdout or "").strip() or "main"
        if branch.lower() == "head":
            branch = "main"

        rel = rel_path.replace(os.sep, "/").lstrip("/")
        return f"https://raw.githubusercontent.com/{owner_repo}/{branch}/{rel}"
    except Exception:
        return None


def _env_ms(name: str, default: int) -> int:
    try:
        val = int(os.getenv(name, str(default)))
        return max(val, 0)
    except Exception:
        return default


def _run_git(args: List[str], cwd: Path) -> None:
    import subprocess
    result = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git command failed")


def sync_codes_database() -> None:
    repo_url = os.getenv("CODES_DB_REPO", "").strip()
    if not repo_url:
        return

    dest = _data_root()
    branch = (os.getenv("CODES_DB_BRANCH") or "main").strip() or "main"
    try:
        if (dest / ".git").exists():
            progress("Refreshing codes database…")
            _run_git(["git", "fetch", "--all"], dest)
            _run_git(["git", "checkout", branch], dest)
            _run_git(["git", "pull", "--ff-only", "origin", branch], dest)
        else:
            if dest.exists() and any(dest.iterdir()):
                logger.warning("Codes database path %s exists but is not a git repository; skipping sync.", dest)
                return
            dest.parent.mkdir(parents=True, exist_ok=True)
            progress("Cloning codes database…")
            _run_git(["git", "clone", "--branch", branch, repo_url, str(dest)], dest.parent)
        success("Codes database synced")
    except FileNotFoundError:
        logger.warning("Git is required to sync the codes database. Skipping sync.")
    except Exception as exc:
        logger.warning(f"Codes database sync failed: {exc}")


async def scrape_enrolled_courses(page: Page, base_url: str) -> List[str]:
    """
    Navigates to the attendance info page and scrapes enrolled course codes.
    """
    attendance_info_url = f"{base_url}/student/AttendanceInfo.aspx"
    step("Fetching course list...")
    debug_detail(f"Navigating to {attendance_info_url}")
    await page.goto(attendance_info_url, timeout=30000)

    progress("Parsing enrolled courses...")
    try:
        all_text = await page.content()
        course_codes = re.findall(r'\b([A-Z]{3}\d{4})\b', all_text)
        unique_codes = sorted(list(set(course_codes)))
        success(f"Found {len(unique_codes)} courses: {', '.join(unique_codes)}")
        return unique_codes
    except Exception as e:
        logger.warning(f"Could not scrape enrolled courses: {e}")
        return []


async def _collect_day_anchors(page: Page) -> List[str]:
    anchors: List[str] = []
    try:
        opts = page.locator('#daySel option')
        n = await opts.count()
        for i in range(n):
            val = await opts.nth(i).get_attribute('value')
            if val:
                anchors.append(val)
    except Exception:
        pass
    if not anchors:
        try:
            panels = page.locator('[id^="dayPanel_"]')
            m = await panels.count()
            for i in range(m):
                pid = await panels.nth(i).get_attribute('id')
                if pid and pid.startswith('dayPanel_'):
                    anchors.append(pid[len('dayPanel_'):])
        except Exception:
            pass
    return anchors


def _normalize_slot_text(slot: str) -> str:
    s = (slot or "").strip().lower()
    # normalize common labels e.g., "Workshop 1" -> "workshop 01"
    s = re.sub(r"\b(\d)\b", r"0\1", s)  # pad single digit
    return s


async def open_entry_for_course(page: Page, base_url: str, course_code: str, timeout_ms: int = 12000) -> bool:
    """Open any entry for the course (fallback when slot-specific open is not available)."""
    try:
        if 'Units.aspx' not in (page.url or ''):
            await page.goto(f"{base_url}/student/Units.aspx", timeout=timeout_ms)

        anchors = await _collect_day_anchors(page)
        # Try current visible panel first (without switching)
        try:
            # Scope to currently visible day panel if any
            root = page.locator('div.dayPanel:visible').first
            if await root.count() == 0:
                root = page
            li_nodes = root.locator('li:not(.ui-disabled)').filter(has_text=re.compile(re.escape(course_code), re.I))
            li_count = await li_nodes.count()
            for i in range(li_count):
                li = li_nodes.nth(i)
                try:
                    txt = (await li.inner_text()).lower()
                    if 'pass' in txt:
                        continue
                except Exception:
                    pass
                link = li.locator('a[href*="Entry.aspx"]').first
                if await link.count() == 0:
                    continue
                try:
                    await li.scroll_into_view_if_needed()
                    if not await link.is_visible():
                        await li.click()
                    else:
                        await link.click()
                    try:
                        await page.wait_for_url(lambda u: ('Entry.aspx' in u), timeout=timeout_ms)
                    except Exception:
                        pass
                    if 'Entry.aspx' in (page.url or ''):
                        return True
                except Exception:
                    continue
        except Exception:
            pass

        # Iterate all anchors: select option to ensure panel is visible and stable
        for a in anchors:
            try:
                sel = page.locator('#daySel')
                if await sel.count() > 0:
                    await sel.select_option(value=a)
                # Wait for panel and small settle time
                try:
                    await page.locator(f'#dayPanel_{a}').wait_for(state='visible', timeout=timeout_ms)
                except Exception:
                    await asyncio.sleep(_env_ms('DAY_SWITCH_SETTLE_MS', 150)/1000)
                root = page.locator(f'#dayPanel_{a}') if await page.locator(f'#dayPanel_{a}').count() > 0 else page
                # First try course-filtered entries
                # Prefer course-filtered entries that are visible
                entries = root.locator('li:not(.ui-disabled)').filter(has_text=re.compile(re.escape(course_code), re.I))
                count = await entries.count()
                for i in range(count):
                    li = entries.nth(i)
                    link = li.locator('a[href*="Entry.aspx"]').first
                    if await link.count() == 0:
                        continue
                    try:
                        await li.scroll_into_view_if_needed()
                        if not await link.is_visible():
                            # Click the li to expose link
                            await li.click()
                        else:
                            await link.click()
                        try:
                            await page.wait_for_url(lambda u: ('Entry.aspx' in u), timeout=timeout_ms)
                        except Exception:
                            pass
                        if 'Entry.aspx' in (page.url or ''):
                            return True
                    except Exception:
                        continue
                # Fallback: any Entry.aspx within this panel
                link = root.locator('a[href*="Entry.aspx"]').first
                if await link.count() > 0:
                    try:
                        await link.scroll_into_view_if_needed()
                        await link.click()
                        try:
                            await page.wait_for_url(lambda u: ('Entry.aspx' in u), timeout=timeout_ms)
                        except Exception:
                            pass
                        if 'Entry.aspx' in (page.url or ''):
                            return True
                    except Exception:
                        pass
            except Exception:
                continue
        return False
    except Exception as e:
        logger.warning(f"Failed to open entry for {course_code}: {e}")
        return False


async def open_entry_for_course_slot(page: Page, base_url: str, course_code: str, slot_label: str, timeout_ms: int = 12000) -> Tuple[bool, Optional[str]]:
    """Open the specific entry matching course+slot; returns (opened, anchor_used)."""
    try:
        target_slot_norm = _normalize_slot_text(slot_label)
        if 'Units.aspx' not in (page.url or ''):
            await page.goto(f"{base_url}/student/Units.aspx", timeout=timeout_ms)

        anchors = await _collect_day_anchors(page)

        async def try_in_root(root) -> bool:
            # li that mentions course and slot
            candidates = root.locator('li:not(.ui-disabled)').filter(
                has_text=re.compile(re.escape(course_code), re.I)
            ).filter(
                has_text=re.compile(re.escape(slot_label), re.I)
            )
            count = await candidates.count()
            for i in range(count):
                li = candidates.nth(i)
                link = li.locator('a[href*="Entry.aspx"]').first
                if await link.count() == 0:
                    continue
                try:
                    await li.scroll_into_view_if_needed()
                    if not await link.is_visible():
                        await li.click()
                    else:
                        await link.click()
                    try:
                        await page.wait_for_url(lambda u: ('Entry.aspx' in u), timeout=timeout_ms)
                    except Exception:
                        pass
                    if 'Entry.aspx' in (page.url or ''):
                        return True
                except Exception:
                    continue
            return False

        # try current visible panel (panel not having display:none)
        root = page.locator('div.dayPanel:not([style*="display:none"])').first
        if await root.count() == 0:
            root = page
        if await try_in_root(root):
            # Cannot know anchor; return True,None
            return True, None

        # iterate anchors
        for a in anchors:
            try:
                sel = page.locator('#daySel')
                if await sel.count() > 0:
                    await sel.select_option(value=a)
                try:
                    await page.locator(f'#dayPanel_{a}').wait_for(state='visible', timeout=timeout_ms)
                except Exception:
                    await asyncio.sleep(_env_ms('DAY_SWITCH_SETTLE_MS', 150)/1000)
                visible_root = page.locator(f'#dayPanel_{a}') if await page.locator(f'#dayPanel_{a}').count() > 0 else page
                if await try_in_root(visible_root):
                    return True, a
            except Exception:
                continue
        return False, None
    except Exception as e:
        logger.debug(f"Slot-open failed for {course_code} {slot_label}: {e}")
        return False, None


async def verify_entry_mark(page: Page, base_url: str, anchor: Optional[str], course_code: str, slot_label: str, timeout_ms: int = 8000) -> bool:
    """Verify on Units page that the given course+slot shows a tick icon (success)."""
    try:
        if 'Units.aspx' not in (page.url or ''):
            await page.goto(f"{base_url}/student/Units.aspx", timeout=timeout_ms)
        if anchor:
            sel = page.locator('#daySel')
            if await sel.count() > 0:
                try:
                    await sel.select_option(value=anchor)
                except Exception:
                    pass
            try:
                await page.locator(f'#dayPanel_{anchor}').wait_for(state='visible', timeout=timeout_ms)
            except Exception:
                await asyncio.sleep(0.2)
            root = page.locator(f'#dayPanel_{anchor}') if await page.locator(f'#dayPanel_{anchor}').count() > 0 else page
        else:
            root = page

        # success if li mentioning course+slot has tick icon
        item = root.locator('li').filter(
            has_text=re.compile(re.escape(course_code), re.I)
        ).filter(
            has_text=re.compile(re.escape(slot_label), re.I)
        )
        # require tick.png in this item
        if await item.locator('img[src*="tick"]').count() > 0:
            return True
        return False
    except Exception:
        return False


def find_latest_week(course: str) -> Optional[str]:
    """
    Finds the highest numbered week JSON file in the data directory for a course.
    """
    try:
        course_dir = _data_root() / ''.join(ch for ch in course if ch.isalnum())
        if not course_dir.is_dir():
            return None
        weeks = [
            int(path.stem)
            for path in course_dir.glob('*.json')
            if path.stem.isdigit()
        ]
        if not weeks:
            return None
        return str(max(weeks))q
    except Exception:
        return None

def parse_codes(course_code: Optional[str] = None, week_number: Optional[str] = None) -> List[Dict[str, Optional[str]]]:
    """Load attendance codes from the synchronised data directory."""

    if not course_code or not week_number:
        return []

    course_clean = ''.join(ch for ch in course_code if ch.isalnum())
    week_clean = ''.join(ch for ch in str(week_number) if ch.isdigit())
    data_path = _data_root() / course_clean / f'{week_clean}.json'

    if not data_path.exists():
        logger.warning(f"No attendance codes found for {course_code} week {week_number}.")
        return []

    try:
        with data_path.open('r', encoding='utf-8') as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.error(f"Failed to read attendance codes from {data_path}: {exc}")
        return []

    if not isinstance(payload, list):
        logger.warning(f"Unexpected data structure in {data_path}; expected a list of slots.")
        return []

    return payload


async def is_authenticated(page: Page) -> bool:
    """Check if user is authenticated by looking for login indicators."""
    try:
        login_selectors = [
            '#okta-signin-username',
            'input[name="username"]', 
            'input[type="password"]',
            '#okta-signin-password'
        ]
        for selector in login_selectors:
            if await page.locator(selector).count() > 0:
                return False
        return True
    except Exception:
        return True  # Assume authenticated if check fails


async def submit_code_on_entry(page: Page, code: str) -> Tuple[bool, str]:
    """Submit a single attendance code on the current entry page."""
    try:
        # Find and fill the code input field
        code_selectors = [
            'input[name="ctl00$ContentPlaceHolder1$txtAttendanceCode"]',
            'input[id*="txtAttendanceCode"]',
            'input[type="text"]'
        ]
        
        filled = False
        for selector in code_selectors:
            try:
                element = page.locator(selector).first
                if await element.count() > 0:
                    await element.fill(code)
                    filled = True
                    break
            except Exception:
                continue
        
        if not filled:
            return False, "Could not find code input field"
        
        # Submit the form
        submit_selectors = [
            'input[id*="btnSubmitAttendanceCode"]',
            'input[type="submit"]',
            'button[type="submit"]'
        ]
        
        submitted = False
        for selector in submit_selectors:
            try:
                element = page.locator(selector).first
                if await element.count() > 0:
                    await element.click()
                    submitted = True
                    break
            except Exception:
                continue
        
        if not submitted:
            return False, "Could not find submit button"
        
        # Wait for response and check result
        progress("Waiting for server response...")
        await asyncio.sleep(2)
        
        # Check for success/error messages
        page_text = await page.text_content('body') or ""
        if "successfully" in page_text.lower() or "submitted" in page_text.lower():
            return True, "Code submitted successfully"
        elif "invalid" in page_text.lower() or "error" in page_text.lower():
            return False, "Invalid code or submission error"
        else:
            return True, "Code submitted (status unclear)"
            
    except Exception as e:
        return False, f"Submission error: {str(e)}"


async def collect_day_anchors(page: Page, base: str, start_monday: Optional[datetime] = None) -> List[str]:
    """Collect available day anchors from the attendance portal."""
    try:
        # Navigate to units page to find available weeks
        units_url = f"{base}/student/Units.aspx"
        await page.goto(units_url, timeout=30000)
        
        # Extract day anchors from page links
        links = await page.locator('a').all()
        anchors = []
        
        for link in links:
            href = await link.get_attribute('href') or ""
            if 'day=' in href:
                match = re.search(r'day=([^&]+)', href)
                if match:
                    anchors.append(match.group(1))
        
        return list(set(anchors))
    except Exception as e:
        logger.warning(f"Failed to collect day anchors: {e}")
        return []


async def run_submit(dry_run: bool = False, target_email: Optional[str] = None) -> None:
    """Main submission logic."""
    
    load_env(os.getenv("ENV_FILE", ".env"))
    
    portal_url = os.getenv("PORTAL_URL")
    if not portal_url:
        logger.error("PORTAL_URL not set in environment")
        return

    sync_codes_database()

    base_url = to_base(portal_url)
    browser_name = os.getenv("BROWSER", "chromium")
    # Default to system browsers to avoid Chromium download
    channel = os.getenv("BROWSER_CHANNEL")
    if not channel and browser_name == "chromium":
        # Try system browsers first: Chrome, Edge, then fallback to Chromium
        import platform
        system = platform.system().lower()
        if system == "darwin":  # macOS
            channel = "chrome"  # Try Chrome first, then default Chromium
        elif system == "windows":
            channel = "msedge"  # Try Edge first on Windows
        elif system == "linux":
            channel = "chrome"  # Try Chrome first on Linux
    headless_env = os.getenv("HEADLESS", "1")
    headed = (headless_env in ("0", "false", "False"))
    storage_state = os.getenv("STORAGE_STATE", "storage_state.json")
    
    stats = StatsManager()
    
    async with async_playwright() as p:
        if browser_name == "webkit":
            browser_type = p.webkit
        elif browser_name == "firefox": 
            browser_type = p.firefox
        else:
            browser_type = p.chromium
        
        if channel:
            step(f"Launching system browser ({channel})...")
        else:
            step("Launching browser...")
        debug_detail(f"Browser: {browser_name}, channel: {channel}, headless: {not headed}")

        launch_kwargs = {"headless": not headed}
        if channel and browser_name == "chromium":
            launch_kwargs["channel"] = channel

        try:
            browser = await browser_type.launch(**launch_kwargs)
            if channel:
                success(f"Successfully launched system browser ({channel})")
        except Exception as e:
            if channel:
                logger.warning(f"Failed to launch system browser ({channel}): {e}")
                progress("Falling back to default browser...")
            launch_kwargs.pop("channel", None)
            browser = await browser_type.launch(**launch_kwargs)
        
        # Load session if available
        context_kwargs = {}
        if os.path.exists(storage_state) and _is_storage_state_effective(storage_state):
            context_kwargs["storage_state"] = storage_state
            progress("Loading saved session state...")
        
        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()
        
        try:
            # Navigate to portal and check authentication
            await page.goto(portal_url, timeout=60000)
            
            if not await is_authenticated(page):
                logger.error("Not authenticated. Please run login first.")
                return
            
            # Scrape enrolled courses
            enrolled_courses = await scrape_enrolled_courses(page, base_url)
            if not enrolled_courses:
                logger.error("No enrolled courses found")
                return
            
            await page.goto(f"{base_url}/student/Units.aspx")
            
            # Process each course
            courses_processed: List[str] = []
            codes_submitted: Dict[str, int] = {}
            errors: List[str] = []

            # Optional concurrency across courses
            try:
                max_conc = int(os.getenv('SUBMIT_CONCURRENCY', '1'))
            except Exception:
                max_conc = 1

            sem = asyncio.Semaphore(max_conc if max_conc > 0 else 1)

            async def process_course(course: str) -> None:
                nonlocal courses_processed, codes_submitted, errors
                async with sem:
                    try:
                        step(f"Processing course: {course}")
                        wk = os.getenv("WEEK_NUMBER") or find_latest_week(course)
                        if not wk:
                            logger.warning(f"No week number determined for {course}")
                            return
                        codes = parse_codes(course, wk)
                        if not codes:
                            return
                        # Preview items (no confirmation required)
                        logger.info("The following items will be processed:")
                        for entry in codes:
                            slot_label = entry.get('slot', 'Unknown')
                            code = entry.get('code', 'Missing')
                            logger.info(f"{slot_label}, code {code}")

                        # Show local JSON path and raw URL if applicable
                        course_clean = ''.join(ch for ch in course if ch.isalnum())
                        week_clean = ''.join(ch for ch in str(wk) if ch.isdigit())
                        rel_path = os.path.join('data', course_clean, f'{week_clean}.json')
                        if os.path.exists(rel_path):
                            logger.info(f"Generated codes JSON: {rel_path}")
                            raw_url = _compute_raw_url_for_path(rel_path)
                            if raw_url:
                                logger.info(f"Raw URL: {raw_url}")
                        courses_processed.append(course)
                        if dry_run:
                            logger.info(f"[DRY RUN] Would submit {len(codes)} codes for {course} week {wk}")
                            return
                        # Use a dedicated page for this course
                        p = await context.new_page()
                        submitted = 0
                        try:
                            # Pre-check any entry exists (fast)
                            progress(f"Checking if {course} has attendance entries...")
                            if not await open_entry_for_course(p, base_url, course):
                                logger.warning(f"No entry page found for {course}; skipping this course")
                                await p.close()
                                return
                            # Return to Units
                            try:
                                await p.goto(f"{base_url}/student/Units.aspx", timeout=20000)
                            except Exception:
                                pass
                            for entry in codes:
                                slot_label = entry.get('slot') or ''
                                code = entry.get('code')
                                if not code:
                                    continue
                                # Skip PASS slots entirely
                                if 'pass' in slot_label.lower():
                                    continue
                                try:
                                    progress(f"Opening {course} {slot_label}...")
                                    opened, used_anchor = await open_entry_for_course_slot(p, base_url, course, slot_label)
                                    if not opened:
                                        # fallback to generic open
                                        opened = await open_entry_for_course(p, base_url, course)
                                        used_anchor = used_anchor or None
                                    progress(f"Submitting code for {course} {slot_label}...")
                                    ok, _ = await submit_code_on_entry(p, code)
                                    # navigate back and verify via tick icon
                                    try:
                                        await p.goto(f"{base_url}/student/Units.aspx", timeout=20000)
                                    except Exception:
                                        pass
                                    verified = await verify_entry_mark(p, base_url, used_anchor, course, slot_label)
                                    if ok and verified:
                                        submitted += 1
                                        logger.info(f"✓ {course} {slot_label}: {code}")
                                except Exception as e:
                                    logger.debug(f"Error submitting {course} {slot_label}: {e}")
                                    errors.append(str(e))
                        finally:
                            codes_submitted[course] = submitted
                            try:
                                await p.close()
                            except Exception:
                                pass
                    except Exception as e:
                        errors.append(str(e))

            # Kick off tasks
            tasks = [asyncio.create_task(process_course(c)) for c in enrolled_courses]
            await asyncio.gather(*tasks)

            # Record overall run stats
            overall_success = any(v > 0 for v in codes_submitted.values())
            try:
                stats.record_run(success=overall_success, courses_processed=courses_processed, codes_submitted=codes_submitted, errors=errors)
            except Exception:
                pass
        
        finally:
            await browser.close()


def main():
    """Command line interface."""
    parser = argparse.ArgumentParser(description="Submit attendance codes")
    parser.add_argument("--dry-run", action="store_true", help="Preview codes without submitting")
    parser.add_argument("--week", type=int, help="Target specific week number")  
    # Gmail/email-based extraction removed
    
    args = parser.parse_args()
    
    if args.week:
        os.environ["WEEK_NUMBER"] = str(args.week)
    
    asyncio.run(run_submit(dry_run=args.dry_run, target_email=None))


if __name__ == "__main__":
    main()
