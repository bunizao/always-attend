"""Always‑Attend MVP

Command to run:
    python3 -m venv .venv && . .venv/bin/activate
    python -m pip install --upgrade pip
    pip install playwright python-dotenv
    python main.py

Environment variables (.env). If missing, the script will create this template:
  USERNAME=""          # Not necessary, WIP
  PASSWORD=""          # Not necessary, WIP
  TOTP_SECRET=""       # Not necessary, WIP

  # A JSON file path or an https URL, supports format: https://raw.githubusercontent.com/bunizao/always-attend/main/data/{COURSE_CODE}/{WEEK_NUMBER}.json
  CODES_PATH="" 
  # CODES_PATH="https://raw.githubusercontent.com/bunizao/always-attend/main/data"

  # Target portal URL
  PORTAL_URL="https://attendance.monash.edu.my"

  # Headless browser? 1=true (headless), 0=false (headed)
  HEADLESS=1

Flags:
    --login: login only
    --week <int>: submit for a specific week
    --headless <bool>: headless mode

"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from playwright.sync_api import Browser, Page, sync_playwright

# --- .env bootstrap & configuration ---

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    def load_dotenv(*_args: Any, **_kwargs: Any) -> None:  # type: ignore
        return None


ENV_TEMPLATE = """
# Not necessary, WIP
USERNAME=""
PASSWORD=""
TOTP_SECRET=""

# Can be a URL or local path (JSON)
CODES_PATH=""

# Target portal URL
PORTAL_URL="https://attendance.monash.edu.my"

# Headless browser? 1=true, 0=false
HEADLESS=1
""".lstrip()


def ensure_env_file(root: Path) -> None:
    """Create a minimal .env file if missing (no overwrite).

    Keeps the MVP surface small and focused. Users can edit the generated
    file to set the portal URL, codes source, and headless mode.
    """
    env_path = root / ".env"
    if env_path.exists():
        return
    env_path.write_text(ENV_TEMPLATE, encoding="utf-8")
    logging.getLogger("env").info("Created default .env at %s — please review.", env_path)


@dataclass
class Config:
    # Names mirror .env keys for clarity
    PORTAL_URL: str
    CODES_PATH: Optional[str]
    HEADLESS: bool
    STORAGE_STATE: Path


def getenv_bool(name: str, default: bool = False) -> bool:
    """Return True for 1/true/yes/on (case-insensitive), else default."""
    v = os.getenv(name)
    if v is None:
        return default
    return v.lower() in {"1", "true", "yes", "on"}


def load_config(root: Path) -> Config:
    """Load MVP configuration strictly from .env in the script directory."""
    ensure_env_file(root)
    load_dotenv(dotenv_path=root / ".env")
    portal_url = os.getenv("PORTAL_URL") or _missing("PORTAL_URL")
    codes_path = os.getenv("CODES_PATH")
    headless_flag = getenv_bool("HEADLESS", True)
    storage_state = Path("storage_state.json")

    if not codes_path:
        logging.getLogger("config").warning("CODES_PATH not set — run with --login to capture session first.")
    return Config(
        PORTAL_URL=portal_url,
        CODES_PATH=codes_path,
        HEADLESS=headless_flag,
        STORAGE_STATE=storage_state,
    )


def _missing(name: str) -> str:
    raise SystemExit(f"Missing required .env key: {name}")


@dataclass(frozen=True)
class AttendanceCode:
    slot: str
    code: str

## --- Codes loading & validation ---
def _is_base_data_link(loc: str) -> bool:
    """Detect if CODES_PATH points to the repo's /data base URL."""
    s = loc.strip()
    if not s.lower().startswith(("http://", "https://")):
        return False
    return s.rstrip("/").endswith("/data")


def _compose_from_base(loc: str, week: Optional[int]) -> str:
    """Compose a concrete raw GitHub JSON URL from base + COURSE_CODE + week."""
    if week is None:
        raise SystemExit(
            "When CODES_PATH points to the base data URL, you must pass --week <INT> to resolve the JSON file."
        )
    course = os.getenv("COURSE_CODE")
    if not course:
        try:
            course = input("Enter COURSE_CODE (e.g., FIT1058): ").strip()
        except Exception:
            course = ""
    if not course:
        raise SystemExit("COURSE_CODE is required to resolve the data URL (set in .env or input when prompted).")
    base = loc.rstrip("/")
    return f"{base}/{course}/{int(week)}.json"


def load_codes(cfg: Config, week: Optional[int]) -> List[AttendanceCode]:
    """Load codes from local path or URL and normalize to a list of entries."""
    payload: Any
    loc = cfg.CODES_PATH
    if not loc:
        return []
    resolved = _compose_from_base(loc, week) if _is_base_data_link(loc) else loc
    if resolved.lower().startswith(("http://", "https://")):
        logging.getLogger("codes").info("Fetching codes from URL: %s", resolved)
        try:
            with urllib.request.urlopen(resolved) as resp:  # nosec B310
                text = resp.read().decode("utf-8")
            payload = json.loads(text)
        except Exception as exc:
            raise SystemExit(
                "Failed to load JSON from CODES_PATH URL. Ensure it points to a JSON file, e.g. \n"
                "https://raw.githubusercontent.com/bunizao/always-attend/main/data/FIT1045/10.json\n"
                f"Detail: {exc}"
            )
    else:
        p = Path(resolved)
        logging.getLogger("codes").info("Loading codes from file: %s", p)
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SystemExit(
                "Failed to load JSON from CODES_PATH file. Ensure it is valid JSON.\n"
                f"Path: {p}\nDetail: {exc}"
            )
    def normalize_list(lst: List[Any]) -> List[AttendanceCode]:
        """Extract {slot, code} entries; optionally filter by week if present."""
        out: List[AttendanceCode] = []
        for i, item in enumerate(lst):
            if not isinstance(item, dict):
                continue
            if week is not None and "week" in item and int(item["week"]) != int(week):
                continue
            slot = str(item.get("slot") or item.get("name") or f"Week {week or ''} #{i+1}").strip()
            code = str(item.get("code") or item.get("value") or "").strip()
            if code:
                out.append(AttendanceCode(slot=slot, code=code))
        return out

    if isinstance(payload, list):
        out = normalize_list(payload)
        if not out:
            raise SystemExit("Codes JSON list is empty or invalid (expects objects with 'slot' and 'code').")
        return out
    if isinstance(payload, dict):
        # Try map-like payload: {"1": [...], "2": [...]} or {"week": [...]} etc.
        if week is not None and str(week) in payload and isinstance(payload[str(week)], list):
            out = normalize_list(payload[str(week)])
            if not out:
                raise SystemExit("Codes JSON for selected week is empty or invalid.")
            return out
        # pick first list value
        for v in payload.values():
            if isinstance(v, list):
                out = normalize_list(v)
                if not out:
                    raise SystemExit("Codes JSON first list value is empty or invalid.")
                return out
        # fallback single entry
        out = normalize_list([payload])
        if not out:
            raise SystemExit("Codes JSON object missing 'slot'/'code'.")
        return out
    raise SystemExit("Unsupported codes JSON format")


## --- Playwright helpers ---

def launch_browser(headed: bool) -> Browser:
    """Launch system Chrome (or Edge fallback) with Playwright.

    No Chromium download is required; this uses the system-installed browser
    via the channel parameter.
    """
    pw = sync_playwright().start()
    # Prefer system Chrome; fall back to Edge if Chrome channel unavailable
    try:
        browser = pw.chromium.launch(headless=not headed, channel="chrome")
    except Exception:
        browser = pw.chromium.launch(headless=not headed, channel="msedge")
    setattr(browser, "_pw", pw)
    return browser


def close_browser(browser: Browser) -> None:
    """Close the browser and stop the Playwright runtime."""
    pw = getattr(browser, "_pw", None)
    try:
        browser.close()
    finally:
        if pw is not None:
            pw.stop()


def new_page(browser: Browser, storage_state_path: Optional[Path]) -> Page:
    """Create a new context/page, optionally restoring a saved storage state."""
    if storage_state_path and Path(storage_state_path).exists():
        context = browser.new_context(storage_state=str(storage_state_path))
    else:
        context = browser.new_context()
    return context.new_page()


def save_storage_state(page: Page, path: Path) -> None:
    """Persist the current context storage state to JSON on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    state = page.context.storage_state()
    Path(path).write_text(json.dumps(state), encoding="utf-8")
    logging.getLogger("auth").info("Saved storage state to %s", path)


def storage_state_expired(path: Path) -> bool:
    """Heuristically determine if any cookie remains unexpired.

    If no cookie has a future 'expires' value, consider the session expired.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cookies = data.get("cookies", [])
        now = time.time()
        for c in cookies:
            exp = c.get("expires", 0)
            if isinstance(exp, (int, float)) and exp > now:
                return False
        return True
    except Exception:
        return True


## --- Page selectors & timings (MVP) ---
CODE_INPUT_SELECTOR = "input[name='code']"            # selector for code input
SUBMIT_BUTTON_SELECTOR = "button[type='submit']"       # submit button selector
SUCCESS_SELECTOR = "img[src*='tick.png']"              # accepted indicator
PENDING_SELECTOR = "img[src*='question.png']"          # pending indicator
TIMEOUT_MS = 20_000                                    # default wait timeout
WAIT_AFTER_SUBMIT_SEC = 0.5                            # settle time after submit


## --- Authentication / Session reuse ---

def ensure_logged_in(cfg: Config, browser: Browser, login_only: bool) -> None:
    """Reuse existing session if valid; otherwise guide manual SSO login."""
    logger = logging.getLogger("auth")
    need_login = login_only
    if not need_login and cfg.STORAGE_STATE.exists() and not storage_state_expired(cfg.STORAGE_STATE):
        logger.info("Reusing existing session: %s", cfg.STORAGE_STATE)
        page = new_page(browser, cfg.STORAGE_STATE)
        try:
            page.goto(cfg.PORTAL_URL)
            page.wait_for_selector(CODE_INPUT_SELECTOR, timeout=TIMEOUT_MS)
            return
        except Exception:
            logger.warning("Existing session likely invalid; will re-authenticate")
        finally:
            page.context.close()
        need_login = True
    if need_login:
        logger.info("Interactive login flow starting (system browser)")
        page = new_page(browser, None)
        try:
            page.goto(cfg.PORTAL_URL)
            logger.info("Please complete login in the opened browser window…")
            page.wait_for_selector(CODE_INPUT_SELECTOR, timeout=10 * 60 * 1000)
            save_storage_state(page, cfg.STORAGE_STATE)
        finally:
            page.context.close()


## --- Submission flow & CLI runner ---

def submit_one(page: Page, cfg: Config, item: AttendanceCode) -> str:
    """Submit a single code and return status: accepted|pending|unknown."""
    start = time.perf_counter()
    logging.getLogger("submit").info("Submitting %s (%s)", item.slot, item.code)
    page.goto(cfg.PORTAL_URL)
    page.wait_for_selector(CODE_INPUT_SELECTOR, timeout=TIMEOUT_MS)
    page.fill(CODE_INPUT_SELECTOR, item.code)
    page.click(SUBMIT_BUTTON_SELECTOR)
    if WAIT_AFTER_SUBMIT_SEC:
        time.sleep(WAIT_AFTER_SUBMIT_SEC)
    status = "unknown"
    try:
        page.wait_for_selector(SUCCESS_SELECTOR, timeout=TIMEOUT_MS)
        status = "accepted"
    except Exception:
        try:
            page.wait_for_selector(PENDING_SELECTOR, timeout=1_000)
            status = "pending"
        except Exception:
            status = "unknown"
    elapsed = time.perf_counter() - start
    print(f"OK {item.slot} {item.code} in {elapsed:.2f}s -> {status}")
    return status


def run() -> None:
    """Wire up config, auth, code loading, and sequential submissions."""
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    root = Path(__file__).resolve().parent
    cfg = load_config(root)
    # CLI flags: --login, --week, --headless
    import argparse as _ap
    p = _ap.ArgumentParser(add_help=False)
    p.add_argument("--login", action="store_true")
    p.add_argument("--week", type=int)
    p.add_argument("--headless", action="store_true")
    known, _ = p.parse_known_args()
    headless = cfg.HEADLESS or known.headless
    login_only = known.login
    headed = not headless or login_only  # force headed when logging in
    logger = logging.getLogger("main")
    browser = launch_browser(headed=headed)
    try:
        ensure_logged_in(cfg, browser, login_only)
        if login_only:
            logger.info("Login completed; exiting due to --login")
            return
        codes = load_codes(cfg, week=known.week)
        if not codes:
            logger.warning("No codes to submit.")
            return
        page = new_page(browser, cfg.STORAGE_STATE)
        try:
            results = []
            for code in codes:
                status = submit_one(page, cfg, code)
                results.append((code, status))
            accepted = sum(1 for _, s in results if s == "accepted")
            pending = sum(1 for _, s in results if s == "pending")
            logger.info("Summary: accepted=%s, pending=%s, total=%s", accepted, pending, len(results))
        finally:
            page.context.close()
    finally:
        close_browser(browser)


if __name__ == "__main__":
    try:
        run()
    except SystemExit:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Submission failed")
        raise
