import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse, urlunparse
import argparse
import re

from playwright.async_api import async_playwright, Page, TimeoutError as PwTimeout

from utils.logger import logger
from utils.env_utils import load_env, save_email_to_env
from utils.session import is_storage_state_effective
from core.stats import StatsManager

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


async def scrape_enrolled_courses(page: Page, base_url: str) -> List[str]:
    """
    Navigates to the attendance info page and scrapes enrolled course codes.
    """
    attendance_info_url = f"{base_url}/student/AttendanceInfo.aspx"
    logger.info(f"[STEP] Navigating to {attendance_info_url} to find courses...")
    await page.goto(attendance_info_url, timeout=30000)

    logger.info("[STEP] Scraping page for enrolled courses...")
    try:
        all_text = await page.content()
        course_codes = re.findall(r'\b([A-Z]{3}\d{4})\b', all_text)
        unique_codes = sorted(list(set(course_codes)))
        logger.info(f"Found {len(unique_codes)} enrolled courses: {unique_codes}")
        return unique_codes
    except Exception as e:
        logger.warning(f"Could not scrape enrolled courses: {e}")
        return []


def find_latest_week(course: str) -> Optional[str]:
    """
    Finds the highest numbered week JSON file in the data directory for a course.
    """
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

def parse_codes(course_code: Optional[str] = None, week_number: Optional[str] = None) -> List[Dict[str, Optional[str]]]:
    """Parse attendance codes from various sources."""
    
    # Try environment variable CODES
    codes_env = os.getenv("CODES", "").strip()
    if codes_env:
        logger.info("Using inline CODES from environment")
        parsed = []
        for pair in codes_env.split(";"):
            if ":" in pair:
                slot, code = pair.split(":", 1)
                parsed.append({"slot": slot.strip(), "code": code.strip()})
        return parsed
    
    # Try CODES_FILE
    codes_file = os.getenv("CODES_FILE", "").strip()
    if codes_file and os.path.exists(codes_file):
        logger.info(f"Loading codes from file: {codes_file}")
        try:
            with open(codes_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load codes file: {e}")
    
    # Try CODES_URL
    codes_url = os.getenv("CODES_URL", "").strip()
    if codes_url:
        logger.info(f"Loading codes from URL: {codes_url}")
        import aiohttp
        import asyncio
        
        async def fetch_codes():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(codes_url) as response:
                        if response.status == 200:
                            return await response.json()
            except Exception as e:
                logger.warning(f"Failed to fetch codes from URL: {e}")
                return []
        
        return asyncio.run(fetch_codes())
    
    # Try local data directory
    if course_code and week_number:
        course_clean = ''.join(ch for ch in course_code if ch.isalnum())
        data_path = os.path.join('data', course_clean, f'{week_number}.json')
        if os.path.exists(data_path):
            logger.info(f"Loading codes from local data: {data_path}")
            try:
                with open(data_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load local data: {e}")
    
    logger.warning(f"No attendance codes found for {course_code} week {week_number}.")
    logger.info("You can add missing codes by creating an issue at: https://github.com/bunizao/always-attend/issues/new?template=attendance-codes.yml")
    
    return []


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
    
    base_url = to_base(portal_url)
    browser_name = os.getenv("BROWSER", "chromium")
    channel = os.getenv("BROWSER_CHANNEL", "chrome") if browser_name == "chromium" else None
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
        
        logger.info(f"Launching browser: {browser_name} channel={channel} headless={not headed}")
        
        launch_kwargs = {"headless": not headed}
        if channel and browser_name == "chromium":
            launch_kwargs["channel"] = channel
            
        try:
            browser = await browser_type.launch(**launch_kwargs)
        except Exception as e:
            logger.warning(f"Failed to launch with channel '{channel}': {e}. Falling back.")
            launch_kwargs.pop("channel", None)
            browser = await browser_type.launch(**launch_kwargs)
        
        # Load session if available
        context_kwargs = {}
        if os.path.exists(storage_state) and _is_storage_state_effective(storage_state):
            context_kwargs["storage_state"] = storage_state
            logger.info("Loading saved session state")
        
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
            for course in enrolled_courses:
                logger.info(f"[STEP] Processing course: {course}")
                
                # Determine week number
                week_number = os.getenv("WEEK_NUMBER") or find_latest_week(course)
                if not week_number:
                    logger.warning(f"No week number determined for {course}")
                    continue
                
                # Parse codes for this course
                codes = parse_codes(course, week_number)
                if not codes:
                    continue
                
                if dry_run:
                    logger.info(f"[DRY RUN] Would submit {len(codes)} codes for {course} week {week_number}")
                    for entry in codes:
                        logger.info(f"  {entry.get('slot', 'Unknown')}: {entry.get('code', 'Missing')}")
                    continue
                
                # Submit codes
                submitted_count = 0
                for entry in codes:
                    slot = entry.get('slot', 'Unknown')
                    code = entry.get('code')
                    
                    if not code:
                        logger.warning(f"No code available for {slot}")
                        continue
                    
                    # Navigate to specific attendance entry (simplified)
                    try:
                        success, message = await submit_code_on_entry(page, code)
                        if success:
                            submitted_count += 1
                            logger.info(f"✓ {course} {slot}: {code} - {message}")
                        else:
                            logger.warning(f"✗ {course} {slot}: {code} - {message}")
                    except Exception as e:
                        logger.error(f"Error submitting {course} {slot}: {e}")
                
                stats.record_submission(course, submitted_count, len(codes))
                logger.info(f"Course {course} completed: {submitted_count}/{len(codes)} codes submitted")
        
        finally:
            await browser.close()


def main():
    """Command line interface."""
    parser = argparse.ArgumentParser(description="Submit attendance codes")
    parser.add_argument("--dry-run", action="store_true", help="Preview codes without submitting")
    parser.add_argument("--week", type=int, help="Target specific week number")  
    parser.add_argument("--email", help="Target email for code extraction")
    
    args = parser.parse_args()
    
    if args.week:
        os.environ["WEEK_NUMBER"] = str(args.week)
    
    asyncio.run(run_submit(dry_run=args.dry_run, target_email=args.email))


if __name__ == "__main__":
    main()