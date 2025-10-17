import os
import json
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set, Any
from urllib.parse import urlparse, urlunparse, urljoin
import argparse
import re

from playwright.async_api import Page

from utils.logger import logger, step, progress, success, debug_detail, spinner
from utils.env_utils import load_env
from utils.session import is_storage_state_effective
from core.stats import StatsManager
from core.browser_controller import BrowserConfig, BrowserController
import difflib
import subprocess
from pathlib import Path

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
    return is_storage_state_effective(path)


@dataclass
class SubmissionConfig:
    portal_url: str
    base_url: str
    browser_name: str = "chromium"
    channel: Optional[str] = None
    headed: bool = False
    storage_state: str = "storage_state.json"
    user_data_dir: Optional[str] = None
    dry_run: bool = False
    target_email: Optional[str] = None
    concurrency: int = 1
    week_override: Optional[str] = None
    timeout_ms: int = 60000


def _data_root() -> Path:
    return Path(os.getenv("CODES_DB_PATH", "data")).resolve()


def _run_git(args: List[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git command failed")


def sync_attendance_database() -> None:
    repo_url = os.getenv("CODES_DB_REPO", "").strip()
    if not repo_url:
        return

    dest = _data_root()
    branch = (os.getenv("CODES_DB_BRANCH") or "main").strip() or "main"
    try:
        if (dest / ".git").exists():
            progress("Refreshing attendance database…")
            _run_git(["git", "fetch", "--all"], dest)
            _run_git(["git", "checkout", branch], dest)
            _run_git(["git", "pull", "--ff-only", "origin", branch], dest)
        else:
            if dest.exists() and any(dest.iterdir()):
                logger.warning(
                    "Codes database path %s exists but is not a git repository; skipping sync.",
                    dest,
                )
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


@dataclass
class EntryCandidate:
    anchor: Optional[str]
    href: Optional[str]
    raw_label: str
    norm: str
    tokens: Set[str]
    display_label: str
    has_link: bool
    is_completed: bool


def _normalize_label(text: str) -> str:
    s = (text or "").lower()
    s = s.replace("laboratory", "lab")
    s = s.replace("tutorial", "tut")
    s = s.replace("lecture", "lec")
    s = s.replace("workshop", "workshop")
    s = s.replace("applied", "applied")
    s = s.replace("–", " ")
    s = s.replace("-", " ")
    s = s.replace(":", "")
    s = re.sub(r"\b\d{1,2}\s*\d{2}\b", "", s)
    s = re.sub(r"\b\d{1,2}(?:am|pm)\b", "", s)
    s = re.sub(r"\b(?:mon|tue|wed|thu|fri|sat|sun)\w*\b", "", s)
    s = re.sub(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b", "", s)
    s = re.sub(r"\b(?:am|pm)\b", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\b(\d)\b", lambda m: f"{int(m.group(1)):02d}", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _tokenize_label(text: str) -> Set[str]:
    if not text:
        return set()
    return set(text.split())


def _score_slot_match(slot_norm: str, slot_tokens: Set[str], candidate: EntryCandidate) -> float:
    if not slot_norm:
        return 0.0
    if slot_norm in candidate.norm:
        return 1.0
    seq_ratio = difflib.SequenceMatcher(None, slot_norm, candidate.norm).ratio()
    overlap = 0.0
    if slot_tokens:
        overlap = len(slot_tokens & candidate.tokens) / len(slot_tokens)
    return seq_ratio * 0.7 + overlap * 0.3


async def _select_day_anchor(page: Page, anchor: Optional[str], settle_ms: int = 150) -> None:
    if not anchor:
        return
    sel = page.locator('#daySel')
    if await sel.count() == 0:
        return
    try:
        await sel.select_option(value=anchor)
    except Exception:
        return
    try:
        await page.locator(f'#dayPanel_{anchor}').wait_for(state='visible', timeout=settle_ms + 3000)
    except Exception:
        await asyncio.sleep(settle_ms / 1000)


async def ensure_units_page(page: Page, base_url: str, timeout_ms: int) -> None:
    if 'Units.aspx' not in (page.url or ''):
        await page.goto(f"{base_url}/student/Units.aspx", timeout=timeout_ms)


async def collect_course_entries(page: Page, base_url: str, course_code: str) -> List[EntryCandidate]:
    await ensure_units_page(page, base_url, 20000)
    anchors = await _collect_day_anchors(page)
    seen_hrefs: Set[str] = set()
    candidates: List[EntryCandidate] = []

    for anchor in [None, *anchors]:
        await _select_day_anchor(page, anchor)
        root = page
        if anchor:
            panel = page.locator(f'#dayPanel_{anchor}')
            if await panel.count() > 0:
                root = panel
        entries = root.locator('li:not(.ui-disabled)').filter(has_text=re.compile(re.escape(course_code), re.I))
        count = await entries.count()
        for i in range(count):
            li = entries.nth(i)
            link = li.locator('a[href*="Entry.aspx"]').first
            has_link = await link.count() > 0
            href = None
            if has_link:
                href = await link.get_attribute('href')
                if not href or href in seen_hrefs:
                    continue
                seen_hrefs.add(href)
            try:
                raw_label = await li.inner_text()
            except Exception:
                raw_label = ""
            norm = _normalize_label(raw_label)
            tokens = _tokenize_label(norm)
            display_label = ' '.join(raw_label.split()) or norm or "Unknown slot"
            try:
                completed = await li.locator('img[src*="tick"]').count() > 0
            except Exception:
                completed = False

            candidates.append(
                EntryCandidate(
                    anchor=anchor,
                    href=href,
                    raw_label=raw_label,
                    norm=norm,
                    tokens=tokens,
                    display_label=display_label,
                    has_link=has_link,
                    is_completed=completed,
                )
            )
    return candidates


def pick_candidate_for_slot(slot_label: str, entries: List[EntryCandidate]) -> Optional[EntryCandidate]:
    slot_norm = _normalize_label(slot_label)
    slot_tokens = _tokenize_label(slot_norm)
    best: Optional[EntryCandidate] = None
    best_score = 0.0
    for entry in entries:
        score = _score_slot_match(slot_norm, slot_tokens, entry)
        if score > best_score:
            best = entry
            best_score = score
    if best_score < 0.45:
        return None
    return best


async def open_entry_candidate(page: Page, base_url: str, candidate: EntryCandidate, timeout_ms: int = 12000) -> bool:
    await ensure_units_page(page, base_url, timeout_ms)
    await _select_day_anchor(page, candidate.anchor)

    locator = None
    if candidate.href:
        locator = page.locator(f'a[href="{candidate.href}"]').first
        if await locator.count() == 0:
            token = candidate.href.split("Entry.aspx", 1)[-1]
            locator = page.locator(f'a[href*="{token}"]').first

    if locator and await locator.count() > 0:
        try:
            await locator.scroll_into_view_if_needed()
            await locator.click()
            try:
                await page.wait_for_url(lambda u: ('Entry.aspx' in u), timeout=timeout_ms)
            except Exception:
                pass
            if 'Entry.aspx' in (page.url or ''):
                return True
        except Exception:
            pass

    if candidate.href:
        target = urljoin(f"{base_url}/student/", candidate.href)
        try:
            await page.goto(target, timeout=timeout_ms)
            return 'Entry.aspx' in (page.url or '')
        except Exception:
            return False

    return False


async def verify_entry_candidate(page: Page, base_url: str, candidate: EntryCandidate, timeout_ms: int = 8000) -> bool:
    await ensure_units_page(page, base_url, timeout_ms)
    await _select_day_anchor(page, candidate.anchor)

    locator = page.locator(f'a[href="{candidate.href}"]').first
    if await locator.count() == 0:
        token = candidate.href.split("Entry.aspx", 1)[-1]
        locator = page.locator(f'a[href*="{token}"]').first
    if await locator.count() == 0:
        return False
    li = locator.locator("xpath=ancestor::li[1]")
    try:
        return await li.locator('img[src*="tick"]').count() > 0
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
            for path in course_dir.glob("*.json")
            if path.stem.isdigit()
        ]
        if not weeks:
            return None
        return str(max(weeks))
    except Exception:
        return None

def parse_codes(course_code: Optional[str] = None, week_number: Optional[str] = None) -> List[Dict[str, Optional[str]]]:
    """Load attendance codes from the synchronised data repository."""

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
        logger.warning(f"Unexpected structure in {data_path}; expected a list of slots.")
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
        await asyncio.sleep(1.5)

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


class SubmitWorkflow:
    """Coordinator for attendance submission workflow."""

    def __init__(self, config: SubmissionConfig):
        self.config = config
        self.stats = StatsManager()
        self.courses_processed: List[str] = []
        self.codes_submitted: Dict[str, int] = {}
        self.errors: List[str] = []
        self._result_lock = asyncio.Lock()

    def _browser_config(self) -> BrowserConfig:
        storage_state = None
        if not self.config.user_data_dir:
            candidate = self.config.storage_state
            if candidate and os.path.exists(candidate) and _is_storage_state_effective(candidate):
                storage_state = candidate
                progress("Loading saved session state...")
        return BrowserConfig(
            name=self.config.browser_name,
            channel=self.config.channel,
            headed=self.config.headed,
            storage_state=storage_state,
            user_data_dir=self.config.user_data_dir,
        )

    def _log_launch_choice(self) -> None:
        if self.config.channel:
            step(f"Launching system browser ({self.config.channel})...")
        else:
            step("Launching browser...")
        debug_detail(
            f"Browser: {self.config.browser_name}, "
            f"channel: {self.config.channel}, "
            f"headless: {not self.config.headed}"
        )

    async def run(self) -> None:
        self._log_launch_choice()
        browser_cfg = self._browser_config()
        async with BrowserController(browser_cfg) as controller:
            page = await controller.context.new_page()
            await page.goto(self.config.portal_url, timeout=self.config.timeout_ms)

            if not await is_authenticated(page):
                logger.error("Not authenticated. Please run login first.")
                return

            enrolled_courses = await scrape_enrolled_courses(page, self.config.base_url)
            if not enrolled_courses:
                logger.error("No enrolled courses found")
                return

            await page.goto(f"{self.config.base_url}/student/Units.aspx", timeout=self.config.timeout_ms)
            await self._process_courses(controller, enrolled_courses)
            await self._record_stats()

    async def _process_courses(self, controller: BrowserController, courses: List[str]) -> None:
        max_conc = max(1, self.config.concurrency)
        sem = asyncio.Semaphore(max_conc)
        tasks = [asyncio.create_task(self._process_single_course(controller, sem, course)) for course in courses]
        await asyncio.gather(*tasks)

    async def _process_single_course(
        self,
        controller: BrowserController,
        sem: asyncio.Semaphore,
        course: str,
    ) -> None:
        async with sem:
            try:
                await self._handle_course(controller, course)
            except Exception as exc:
                logger.debug(f"Unhandled error while processing {course}: {exc}")
                async with self._result_lock:
                    self.errors.append(str(exc))

    async def _handle_course(self, controller: BrowserController, course: str) -> None:
        step(f"Processing course: {course}")
        week = self._determine_week(course)
        if not week:
            logger.warning(f"No week number determined for {course}")
            return

        codes = parse_codes(course, week)
        if not codes:
            return

        self._preview_course(course, week, codes)
        await self._store_course(course)

        code_pool = [
            {
                "slot": entry.get('slot') or '',
                "code": entry.get('code'),
                "norm": _normalize_label(entry.get('slot') or ''),
                "tokens": _tokenize_label(_normalize_label(entry.get('slot') or '')),
            }
            for entry in codes
            if entry.get('code') and 'pass' not in (entry.get('slot') or '').lower()
        ]

        if not code_pool:
            await self._record_course_result(course, submitted=0)
            return

        if self.config.dry_run:
            total = len(code_pool)
            async with spinner(self._progress_display(course, "Preparing", 0, total)) as spin:
                for index, entry in enumerate(code_pool, start=1):
                    slot_label = entry['slot']
                    spin.update(self._progress_display(course, slot_label, index, total))
                    logger.info(f"[DRY RUN] {course} {slot_label}: {entry['code']}")
                    await asyncio.sleep(0.05)
                spin.update(self._progress_display(course, "Completed", total, total))
                spin.succeed()
            await self._record_course_result(course, submitted=0)
            return

        page = await controller.context.new_page()
        submitted = 0
        try:
            entries = await collect_course_entries(page, self.config.base_url, course)
            if not entries:
                logger.warning(f"No attendance entries visible for {course}")
                return

            entry_targets = [cand for cand in entries if cand.has_link and not cand.is_completed and 'pass' not in cand.norm]
            if not entry_targets:
                logger.warning(f"No actionable entries found for {course}")
                return

            available_codes = code_pool.copy()
            total = len(entry_targets)

            fail_reasons: List[str] = []

            async with spinner(self._progress_display(course, "Preparing", 0, total)) as spin:
                for index, candidate in enumerate(entry_targets, start=1):
                    match = self._pick_code_for_candidate(candidate, available_codes)
                    if match is None:
                        display_label = candidate.display_label
                        spin.update(self._progress_display(course, display_label, index, total))
                        spin.note(f"{course} {display_label}: no available code", level="warning")
                        async with self._result_lock:
                            self.errors.append(f"{course} {display_label}: no available code")
                        fail_reasons.append(f"{display_label}: no code")
                        continue

                    code_idx, code_entry = match
                    code_entry = available_codes.pop(code_idx)
                    code = code_entry['code']
                    slot_label = code_entry['slot'] or candidate.display_label

                    spin.update(self._progress_display(course, slot_label, index, total))

                    opened = await open_entry_candidate(
                        page,
                        self.config.base_url,
                        candidate,
                        timeout_ms=self.config.timeout_ms,
                    )
                    if not opened:
                        spin.note(f"{course} {slot_label}: unable to open entry", level="warning")
                        async with self._result_lock:
                            self.errors.append(f"{course} {slot_label}: unable to open entry")
                        fail_reasons.append(f"{slot_label}: open failed")
                        continue

                    ok, reason = await submit_code_on_entry(page, code)
                    await ensure_units_page(page, self.config.base_url, self.config.timeout_ms)
                    if not ok:
                        spin.note(f"{course} {slot_label}: {reason or 'submission error'}", level="warning")
                        async with self._result_lock:
                            self.errors.append(f"{course} {slot_label}: {reason or 'submission error'}")
                        fail_reasons.append(f"{slot_label}: {reason or 'submit error'}")
                        continue

                    verified = await verify_entry_candidate(
                        page,
                        self.config.base_url,
                        candidate,
                        timeout_ms=self.config.timeout_ms,
                    )
                    if verified:
                        submitted += 1
                        logger.info(f"✓ {course} {slot_label}: {code}")
                    else:
                        spin.note(f"{course} {slot_label}: verification failed", level="warning")
                        async with self._result_lock:
                            self.errors.append(f"{course} {slot_label}: verification failed")
                        fail_reasons.append(f"{slot_label}: verification failed")

                spin.update(self._progress_display(course, "Completed", total, total))
                if submitted:
                    spin.succeed()
                else:
                    summary = fail_reasons[0] if fail_reasons else "no attempts"
                    spin.fail(f"0/{total} codes submitted ({summary})")
        finally:
            await page.close()
            await self._record_course_result(course, submitted=submitted)

    def _determine_week(self, course: str) -> Optional[str]:
        if self.config.week_override:
            return self.config.week_override
        env_week = os.getenv("WEEK_NUMBER")
        if env_week:
            return str(env_week)
        return find_latest_week(course)

    def _preview_course(self, course: str, week: str, codes: List[Dict[str, Optional[str]]]) -> None:
        course_clean = ''.join(ch for ch in course if ch.isalnum())
        week_clean = ''.join(ch for ch in str(week) if ch.isdigit())
        rel_path = _data_root() / course_clean / f'{week_clean}.json'
        debug_detail(f"{course}: {len(codes)} codes loaded from {rel_path}")

    async def _store_course(self, course: str) -> None:
        async with self._result_lock:
            self.courses_processed.append(course)

    async def _record_course_result(self, course: str, submitted: int) -> None:
        async with self._result_lock:
            self.codes_submitted[course] = submitted

    async def _record_stats(self) -> None:
        overall_success = any(v > 0 for v in self.codes_submitted.values())
        try:
            self.stats.record_run(
                success=overall_success,
                courses_processed=self.courses_processed,
                codes_submitted=self.codes_submitted,
                errors=self.errors,
            )
        except Exception:
            pass

    def _progress_display(self, course: str, slot_label: str, index: int, total: int) -> str:
        total = max(total, 1)
        clamped_index = max(0, min(index, total))
        ratio = clamped_index / total
        bar_width = 12
        filled = int(ratio * bar_width)
        bar = '█' * filled + '░' * (bar_width - filled)
        label = slot_label or 'Preparing'
        return f"[{bar}] {clamped_index}/{total} {course} – {label}"

    def _candidate_label(self, candidate: EntryCandidate) -> str:
        return candidate.display_label

    def _pick_code_for_candidate(
        self,
        candidate: EntryCandidate,
        codes: List[Dict[str, Any]],
    ) -> Optional[Tuple[int, Dict[str, Any]]]:
        best_idx = -1
        best_score = 0.0
        for idx, code_entry in enumerate(codes):
            score = _score_slot_match(code_entry['norm'], code_entry['tokens'], candidate)
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx == -1:
            return None if not codes else (0, codes[0])
        if best_score < 0.25 and codes:
            return 0, codes[0]
        return best_idx, codes[best_idx]

async def run_submit(dry_run: bool = False, target_email: Optional[str] = None) -> None:
    """Main submission logic."""
    
    load_env(os.getenv("ENV_FILE", ".env"))
    
    portal_url = os.getenv("PORTAL_URL")
    if not portal_url:
        logger.error("PORTAL_URL not set in environment")
        return
    
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
    try:
        concurrency = int(os.getenv('SUBMIT_CONCURRENCY', '1'))
    except Exception:
        concurrency = 1

    user_data_dir = os.getenv("USER_DATA_DIR")
    week_override = os.getenv("WEEK_NUMBER")

    sync_attendance_database()

    config = SubmissionConfig(
        portal_url=portal_url,
        base_url=base_url,
        browser_name=browser_name,
        channel=channel,
        headed=headed,
        storage_state=storage_state,
        user_data_dir=user_data_dir,
        dry_run=dry_run,
        target_email=target_email,
        concurrency=max(1, concurrency),
        week_override=week_override,
    )

    workflow = SubmitWorkflow(config)
    await workflow.run()


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
