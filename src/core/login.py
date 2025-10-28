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
src/core/login.py
Login and session management routines for Always Attend.
"""

import os
import argparse
import asyncio
from dataclasses import dataclass
from typing import List, Optional

from playwright.async_api import Page
from utils.logger import logger, debug_detail
from utils.env_utils import load_env
from utils.session import is_storage_state_effective
from utils.playwright_helpers import fill_first_match, click_first_match, maybe_switch_to_code_factor
from utils.totp import gen_totp
from core.browser_controller import BrowserConfig, BrowserController
from utils.browser_detection import is_browser_channel_available


@dataclass
class LoginCredentials:
    username: Optional[str]
    password: Optional[str]
    totp_secret: Optional[str]
    mfa_code: Optional[str]


@dataclass
class LoginConfig:
    portal_url: str
    browser_name: str = "chromium"
    channel: Optional[str] = None
    headed: bool = True
    storage_state: str = "storage_state.json"
    user_data_dir: Optional[str] = None
    auto_login_enabled: bool = True
    timeout_ms: int = 60000
    login_check_timeout_ms: int = 60000


async def debug_page_fields(page: Page) -> None:
    """Debug function to log all input fields on the page"""
    try:
        inputs = await page.query_selector_all('input')
        debug_detail(f"Found {len(inputs)} input fields on page")

        for i, input_el in enumerate(inputs):
            try:
                input_type = await input_el.get_attribute('type') or 'text'
                input_name = await input_el.get_attribute('name') or ''
                input_id = await input_el.get_attribute('id') or ''
                input_class = await input_el.get_attribute('class') or ''
                input_placeholder = await input_el.get_attribute('placeholder') or ''
                input_autocomplete = await input_el.get_attribute('autocomplete') or ''

                debug_detail(
                    f"Input {i+1}: type='{input_type}', name='{input_name}', id='{input_id}', class='{input_class}', "
                    f"placeholder='{input_placeholder}', autocomplete='{input_autocomplete}'"
                )
            except Exception as e:
                debug_detail(f"Failed to get attributes for input {i+1}: {e}")

        forms = await page.query_selector_all('form')
        debug_detail(f"Found {len(forms)} forms on page")

    except Exception as e:
        debug_detail(f"Failed to debug page fields: {e}")


async def auto_login(page: Page, creds: LoginCredentials) -> bool:
    """Attempt automatic login with credentials from environment"""
    USERNAME = creds.username
    PASSWORD = creds.password
    TOTP_SECRET = creds.totp_secret
    
    def _flag(val: Optional[str]) -> str:
        return "✓" if val else "✗"

    logger.info(
        "Credentials availability → USERNAME:%s PASSWORD:%s TOTP:%s",
        _flag(USERNAME),
        _flag(PASSWORD),
        _flag(TOTP_SECRET),
    )
    
    if not (USERNAME and PASSWORD):
        logger.warning("No USERNAME or PASSWORD in environment, skipping auto-login")
        return False
    
    logger.info("Attempting automatic login…")
    
    # Wait for page to be fully loaded
    try:
        await page.wait_for_load_state('networkidle', timeout=10000)
        debug_detail("Page finished loading")
    except Exception as e:
        logger.warning(f"Page load timeout: {e}")
    
    # Debug current page
    debug_detail(f"Current URL: {page.url}")
    await debug_page_fields(page)
    
    # Check if we're already on a login page
    try:
        maybe_login_field = page.locator('#okta-signin-username, input[name="username"], input[type="password"], #okta-signin-password')
        if not await maybe_login_field.first.is_visible(timeout=2000):
            logger.info("No login fields found, may already be logged in")
            # Check if we're already on the portal by looking for non-Okta URL
            from urllib.parse import urlparse
            current_host = urlparse(page.url).netloc.lower()
            if 'okta' not in current_host:
                return True
    except Exception:
        pass
    
    # Fill username
    logger.info("Filling username...")
    user_selectors = [
        # Standard Okta selectors
        '#okta-signin-username',
        'input[name="identifier"]',
        'input[name="username"]',
        'input[autocomplete="username"]',
        'input[type="email"]',
        'input[data-se="o-form-input-username"]',
        'input[data-se*="username"]',
        'input[id="idp-discovery-username"]',
        'input[id="input28"]',
        # Generic selectors
        'input[placeholder*="user" i]',
        'input[placeholder*="email" i]',
        'input[placeholder*="学号" i]',
        'input[placeholder*="用户名" i]',
        'input[id*="username" i]',
        'input[id*="user" i]',
        'input[class*="username" i]',
        'input[class*="user" i]',
        # Common form field patterns
        'input[name*="user"]',
        'input[name*="login"]',
        'input[name*="email"]',
        # Fallback - first visible text input if nothing else works
        'input[type="text"]:visible',
        'input:not([type]):visible'
    ]
    debug_detail(f"Trying {len(user_selectors)} username selectors…")
    user_ok = await fill_first_match(page, user_selectors, USERNAME)
    
    if not user_ok:
        logger.warning("Failed to fill username field with any selector")
    
    # Fill password
    logger.info("Filling password...")
    password_selectors = [
        # Standard Okta selectors
        '#okta-signin-password',
        'input[name="password"]',
        'input[autocomplete="current-password"]',
        'input[type="password"]',
        'input[data-se="o-form-input-password"]',
        'input[data-se*="password"]',
        'input[id="okta-signin-password"]',
        'input[id="input38"]',
        # Generic selectors
        'input[placeholder*="pass" i]',
        'input[placeholder*="密码" i]',
        'input[id*="password" i]',
        'input[id*="pass" i]',
        'input[class*="password" i]',
        'input[class*="pass" i]',
        # Common form field patterns
        'input[name*="pass"]',
        'input[name*="pwd"]'
    ]
    debug_detail(f"Trying {len(password_selectors)} password selectors…")
    pass_ok = await fill_first_match(page, password_selectors, PASSWORD)
    
    if not pass_ok:
        logger.warning("Failed to fill password field with any selector")
    
    # If username filled but password didn't, might be two-step login
    if user_ok and not pass_ok:
        logger.info("Two-step login detected, clicking Next...")
        await click_first_match(page, [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Next")',
            'button:has-text("Continue")'
        ])
        
        # Wait for page navigation and password field to appear
        logger.info("Waiting for password page to load...")
        await asyncio.sleep(3)
        
        # Wait for password field to be visible
        try:
            await page.wait_for_selector('input[type="password"], input[name="password"]', timeout=10000)
            logger.info("Password field detected")
        except Exception as e:
            logger.warning(f"Password field not found after Next: {e}")
        
        # Debug the new page
        debug_detail(f"Password page URL: {page.url}")
        await debug_page_fields(page)
        
        # Try password again with extended selectors
        logger.info("Filling password on second page...")
        pass_ok = await fill_first_match(page, password_selectors, PASSWORD)
        
        if pass_ok:
            logger.info("Successfully filled password on second page")
            # Submit the password form
            logger.info("Submitting password form...")
            await click_first_match(page, [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Sign in")',
                'button:has-text("Log in")',
                'button:has-text("Verify")',
                '#okta-signin-submit'
            ])
        else:
            logger.warning("Still failed to fill password field on second page")
            return False
    elif user_ok and pass_ok:
        # Single page login - submit the form
        logger.info("Single page login detected, submitting form...")
        await click_first_match(page, [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
            '#okta-signin-submit'
        ])
    else:
        logger.warning("Could not fill username or password fields")
        return False
    
    # Wait for page to load
    await asyncio.sleep(3)
    
    # Handle MFA if needed
    if TOTP_SECRET:
        logger.info("Handling MFA...")
        await maybe_switch_to_code_factor(page)
        
        # Generate and enter TOTP code
        otp = gen_totp(TOTP_SECRET)
        debug_detail(f"Generated TOTP code: {otp}")
        
        otp_ok = await fill_first_match(page, [
            # Okta-specific selectors based on observed field structure
            'input[name="credentials.passcode"]',
            'input[name="credentials.otp"]',
            # Standard MFA selectors
            'input[name="otp"]',
            'input[name="code"]',
            'input[name="passcode"]',
            'input[autocomplete="one-time-code"]',
            'input[inputmode="numeric"]',
            'input[type="tel"]',
            'input[type="text"][autocomplete="off"]',
            'input[id*="code" i]',
            'input[placeholder*="code" i]',
            'input[placeholder*="OTP" i]',
            # Generic fallbacks
            'input[type="text"]:visible'
        ], otp)
        
        # Try individual digit boxes if single input failed
        if not otp_ok:
            logger.info("Trying individual digit boxes...")
            boxes = page.locator('input[aria-label*="digit" i], input[maxlength="1"]')
            try:
                count = await boxes.count()
                if count >= 6:
                    for i, ch in enumerate(otp[:count]):
                        await boxes.nth(i).fill(ch)
                    otp_ok = True
                    logger.info("Filled individual digit boxes")
            except Exception as e:
                logger.warning(f"Failed to fill digit boxes: {e}")
        
        if otp_ok:
            # Submit MFA form
            logger.info("Submitting MFA code...")
            await click_first_match(page, [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Verify")',
                'button:has-text("Submit")'
            ])
            
            # Wait for MFA to complete
            await asyncio.sleep(5)
        else:
            # Debug MFA page if code filling failed
            logger.warning("Could not enter MFA code, debugging page...")
            await debug_page_fields(page)
            return False
    elif creds.mfa_code:
        logger.info("Using manual MFA code...")
        otp = creds.mfa_code.strip()
        await fill_first_match(page, [
            'input[name="otp"]',
            'input[name="code"]',
            'input[name="passcode"]',
            'input[autocomplete="one-time-code"]'
        ], otp)
        await click_first_match(page, [
            'button[type="submit"]',
            'button:has-text("Verify")'
        ])
        await asyncio.sleep(3)
    
    # Wait for any final redirects and verify we're on the portal
    logger.info("Waiting for authentication to complete...")
    for attempt in range(10):  # Wait up to 10 seconds
        await asyncio.sleep(1)
        current_url = page.url
        from urllib.parse import urlparse
        current_host = urlparse(current_url).netloc.lower()
        
        # Check if we're no longer on Okta and not seeing login fields
        if 'okta' not in current_host:
            try:
                login_fields = page.locator('#okta-signin-username, input[name="username"], input[type="password"], #okta-signin-password')
                has_login_fields = await login_fields.first.is_visible(timeout=1000)
                if not has_login_fields:
                    logger.info(f"Successfully authenticated - now on {current_host}")
                    return True
            except Exception:
                # No login fields found, likely successful
                logger.info(f"Successfully authenticated - now on {current_host}")
                return True
    
    # Check final state
    current_url = page.url
    from urllib.parse import urlparse
    current_host = urlparse(current_url).netloc.lower()
    if 'okta' in current_host:
        logger.warning("Still on Okta domain after login attempt")
        return False
    
    logger.info("Auto-login completed")
    return True


class LoginWorkflow:
    """Encapsulates login orchestration using a BrowserController."""

    def __init__(self, config: LoginConfig):
        self.config = config
        self.credentials = LoginCredentials(
            username=os.getenv("USERNAME"),
            password=os.getenv("PASSWORD"),
            totp_secret=os.getenv("TOTP_SECRET"),
            mfa_code=os.getenv("MFA_CODE"),
        )

    def _browser_config(self, load_storage: bool = False) -> BrowserConfig:
        storage_state = self.config.storage_state if (load_storage and not self.config.user_data_dir) else None
        return BrowserConfig(
            name=self.config.browser_name,
            channel=self.config.channel,
            headed=self.config.headed,
            storage_state=storage_state,
            user_data_dir=self.config.user_data_dir,
            timeout_ms=self.config.timeout_ms,
        )

    async def run(self) -> None:
        """Launch browser and ensure session is stored."""
        async with BrowserController(self._browser_config()) as controller:
            page = await controller.context.new_page()
            await page.goto(self.config.portal_url, timeout=self.config.timeout_ms)

            auto_success = False
            if self.config.auto_login_enabled:
                try:
                    auto_success = await auto_login(page, self.credentials)
                except Exception as exc:
                    logger.warning(f"Auto-login error: {exc}")

            if not auto_success:
                self._prompt_manual_login(auto_success)
                await self._await_user_confirmation()

            await self._persist_session(controller, auto_success)

    async def check_session(self) -> bool:
        """Verify that an existing session is still valid."""
        if self.config.user_data_dir:
            cfg = BrowserConfig(
                name=self.config.browser_name,
                channel=self.config.channel,
                headed=self.config.headed,
                user_data_dir=self.config.user_data_dir,
                timeout_ms=self.config.login_check_timeout_ms,
            )
        else:
            storage = self.config.storage_state if os.path.exists(self.config.storage_state) else None
            if not storage:
                return False
            cfg = BrowserConfig(
                name=self.config.browser_name,
                channel=self.config.channel,
                headed=False,
                storage_state=storage,
                timeout_ms=self.config.login_check_timeout_ms,
            )

        async with BrowserController(cfg) as controller:
            page = await controller.context.new_page()
            attempts = 3
            last_exc: Optional[Exception] = None
            for attempt in range(attempts):
                try:
                    await page.goto(self.config.portal_url, timeout=self.config.login_check_timeout_ms)
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    logger.warning(f"Session check navigation failed (attempt {attempt + 1}/{attempts}): {exc}")
                    await asyncio.sleep(0.8)
            if last_exc is not None:
                return False
            return await self._is_session_active(page)

    async def _persist_session(self, controller: BrowserController, auto_success: bool) -> None:
        if self.config.user_data_dir:
            return
        try:
            await controller.context.storage_state(path=self.config.storage_state)
            if is_storage_state_effective(self.config.storage_state):
                if auto_success:
                    logger.info(f"✅ Session automatically saved to {self.config.storage_state}")
                else:
                    logger.info(f"✅ Saved session to {self.config.storage_state}")
            else:
                logger.warning(f"Saved session to {self.config.storage_state}, but it appears empty.")
        except Exception as exc:
            logger.warning(f"Failed to save storage state: {exc}")

    def _prompt_manual_login(self, auto_attempted: bool) -> None:
        if auto_attempted:
            logger.info("⚠️  Automatic login failed, please complete login manually.")
        else:
            logger.info("Please complete Okta login and MFA in the browser window.")
        logger.info("After you are back on the portal, press Enter here to save the session...")

    async def _await_user_confirmation(self) -> None:
        try:
            await asyncio.to_thread(input)
        except Exception:
            pass

    async def _is_session_active(self, page: Page) -> bool:
        from urllib.parse import urlparse

        host = urlparse(page.url).netloc.lower()
        if 'okta' in host:
            return False
        login_fields = page.locator('#okta-signin-username, input[name="username"], input[type="password"], #okta-signin-password')
        try:
            visible = await login_fields.first.is_visible(timeout=1500)
        except Exception:
            visible = False
        return not visible


async def run_login(portal_url: str,
                    browser_name: str = "chromium",
                    channel: str | None = None,
                    headed: bool = True,
                    storage_state: str = "storage_state.json",
                    user_data_dir: str | None = None,
                    auto_login_enabled: bool = True) -> None:
    config = LoginConfig(
        portal_url=portal_url,
        browser_name=browser_name,
        channel=channel,
        headed=headed,
        storage_state=storage_state,
        user_data_dir=user_data_dir,
        auto_login_enabled=auto_login_enabled,
    )
    workflow = LoginWorkflow(config)
    await workflow.run()


async def check_session(check_url: str,
                        browser_name: str = "chromium",
                        channel: str | None = None,
                        headed: bool = False,
                        storage_state: str = "storage_state.json",
                        user_data_dir: str | None = None) -> bool:
    config = LoginConfig(
        portal_url=check_url,
        browser_name=browser_name,
        channel=channel,
        headed=headed,
        storage_state=storage_state,
        user_data_dir=user_data_dir,
        auto_login_enabled=False,
        login_check_timeout_ms=int(os.getenv("LOGIN_CHECK_TIMEOUT_MS", "60000")),
    )
    workflow = LoginWorkflow(config)
    return await workflow.check_session()

def main():
    load_env(os.getenv("ENV_FILE", ".env"))

    default_channel = os.getenv("BROWSER_CHANNEL")
    if not default_channel and is_browser_channel_available("chrome"):
        default_channel = "chrome"

    parser = argparse.ArgumentParser(description="Interactive Okta login helper (saves session state)")
    parser.add_argument("--portal", default=os.getenv("PORTAL_URL", ""), help="Portal URL (e.g., https://attendance.example.com/student/Default.aspx)")
    parser.add_argument("--browser", default=os.getenv("BROWSER", "chromium"), choices=["chromium", "firefox", "webkit"], help="Browser engine")
    parser.add_argument("--channel", default=default_channel, help="Chromium channel: chrome|chrome-beta|msedge|msedge-beta")
    parser.add_argument("--headed", action="store_true", help="Show browser UI (recommended)")
    parser.add_argument("--storage-state", default=os.getenv("STORAGE_STATE", "storage_state.json"), help="Path to save storage_state.json")
    parser.add_argument("--user-data-dir", default=os.getenv("USER_DATA_DIR"), help="Persistent profile directory (optional)")
    parser.add_argument("--check", action="store_true", help="After saving session, verify login by opening the portal again")
    parser.add_argument("--check-only", action="store_true", help="Do not open login; only verify current session state")
    args = parser.parse_args()

    if not args.portal:
        raise SystemExit("Missing --portal or PORTAL_URL")

    if args.headed:
        headed = True
    else:
        env_headless = os.getenv("HEADLESS")
        if env_headless is None:
            headed = True
        else:
            headed = (env_headless in ("0", "false", "False"))

    channel = args.channel
    if args.browser == "chromium" and channel and not is_browser_channel_available(channel):
        logger.info(
            "Requested browser channel '%s' is unavailable; falling back to bundled Chromium.",
            channel,
        )
        logger.info("Run 'python -m playwright install chromium' if the bundled browser is missing.")
        channel = None

    if args.check_only:
        ok = asyncio.run(check_session(
            check_url=args.portal,
            browser_name=args.browser,
            channel=channel,
            headed=False,
            storage_state=args.storage_state,
            user_data_dir=args.user_data_dir,
        ))
        logger.info("Session check: " + ("OK" if ok else "NOT logged in"))
        raise SystemExit(0 if ok else 1)

    if not headed:
        logger.info("Running in headless mode. Use --headed or HEADLESS=0 for a browser window.")

    asyncio.run(run_login(
        portal_url=args.portal,
        browser_name=args.browser,
        channel=channel,
        headed=headed,
        storage_state=args.storage_state,
        user_data_dir=args.user_data_dir,
    ))

    if args.check:
        ok = asyncio.run(check_session(
            check_url=args.portal,
            browser_name=args.browser,
            channel=channel,
            headed=False,
            storage_state=args.storage_state,
            user_data_dir=args.user_data_dir,
        ))
        logger.info("Session check: " + ("OK" if ok else "NOT logged in"))


if __name__ == "__main__":
    main()
