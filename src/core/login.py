import os
import argparse
import asyncio
from typing import List

from playwright.async_api import async_playwright, Page
from utils.logger import logger
from utils.env_utils import load_env
from utils.session import is_storage_state_effective
from utils.playwright_helpers import fill_first_match, click_first_match, maybe_switch_to_code_factor
from utils.totp import gen_totp


async def debug_page_fields(page: Page) -> None:
    """Debug function to log all input fields on the page"""
    try:
        # Get all input elements
        inputs = await page.query_selector_all('input')
        logger.info(f"Found {len(inputs)} input fields on page:")
        
        for i, input_el in enumerate(inputs):
            try:
                input_type = await input_el.get_attribute('type') or 'text'
                input_name = await input_el.get_attribute('name') or ''
                input_id = await input_el.get_attribute('id') or ''
                input_class = await input_el.get_attribute('class') or ''
                input_placeholder = await input_el.get_attribute('placeholder') or ''
                input_autocomplete = await input_el.get_attribute('autocomplete') or ''
                
                logger.info(f"  Input {i+1}: type='{input_type}', name='{input_name}', id='{input_id}', class='{input_class}', placeholder='{input_placeholder}', autocomplete='{input_autocomplete}'")
            except Exception as e:
                logger.debug(f"Failed to get attributes for input {i+1}: {e}")
        
        # Also check for any forms
        forms = await page.query_selector_all('form')
        logger.info(f"Found {len(forms)} forms on page")
        
    except Exception as e:
        logger.warning(f"Failed to debug page fields: {e}")


async def auto_login(page: Page) -> bool:
    """Attempt automatic login with credentials from environment"""
    USERNAME = os.getenv("USERNAME")
    PASSWORD = os.getenv("PASSWORD")
    TOTP_SECRET = os.getenv("TOTP_SECRET")
    
    logger.info(f"Environment check - USERNAME: {'SET' if USERNAME else 'NOT SET'}")
    logger.info(f"Environment check - PASSWORD: {'SET' if PASSWORD else 'NOT SET'}")
    logger.info(f"Environment check - TOTP_SECRET: {'SET' if TOTP_SECRET else 'NOT SET'}")
    
    if not (USERNAME and PASSWORD):
        logger.warning("No USERNAME or PASSWORD in environment, skipping auto-login")
        return False
    
    logger.info("Attempting automatic login...")
    
    # Wait for page to be fully loaded
    try:
        await page.wait_for_load_state('networkidle', timeout=10000)
        logger.info("Page finished loading")
    except Exception as e:
        logger.warning(f"Page load timeout: {e}")
    
    # Debug current page
    logger.info(f"Current URL: {page.url}")
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
        'input[name="username"]',
        'input[autocomplete="username"]',
        'input[type="email"]',
        'input[data-se="o-form-input-username"]',
        'input[data-se*="username"]',
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
    logger.info(f"Trying {len(user_selectors)} username selectors...")
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
    logger.info(f"Trying {len(password_selectors)} password selectors...")
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
        logger.info(f"Password page URL: {page.url}")
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
        logger.info(f"Generated TOTP code: {otp}")
        
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
    elif os.getenv('MFA_CODE'):
        logger.info("Using manual MFA code...")
        otp = os.getenv('MFA_CODE').strip()
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


async def run_login(portal_url: str,
                    browser_name: str = "chromium",
                    channel: str | None = None,
                    headed: bool = True,
                    storage_state: str = "storage_state.json",
                    user_data_dir: str | None = None,
                    auto_login_enabled: bool = True) -> None:
    async with async_playwright() as p:
        if browser_name == "webkit":
            browser_type = p.webkit
        elif browser_name == "firefox":
            browser_type = p.firefox
        else:
            browser_type = p.chromium

        logger.info("Opening browser for login...")
        if user_data_dir:
            try:
                context = await browser_type.launch_persistent_context(
                    user_data_dir,
                    headless=not headed,
                    channel=channel,
                )
            except Exception as e:
                logger.warning(f"Failed to launch with system channel '{channel}': {e}. Falling back to default.")
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
                logger.warning(f"Failed to launch with system channel '{channel}': {e}. Falling back to default.")
                launch_kwargs.pop("channel", None)
                browser = await browser_type.launch(**launch_kwargs)
            context = await browser.new_context()
            page = await context.new_page()

        await page.goto(portal_url, timeout=60_000)
        
        # Track auto-login success for session saving logic
        auto_login_success = False
        
        # Attempt automatic login if enabled and credentials are available
        if auto_login_enabled:
            try:
                login_success = await auto_login(page)
                if login_success:
                    auto_login_success = True
                    logger.info("✅ Automatic login completed successfully!")
                    # Wait a bit for any redirects to complete
                    await asyncio.sleep(3)
                    
                    # Save session immediately after successful auto-login
                    if not user_data_dir:
                        try:
                            await context.storage_state(path=storage_state)
                            if is_storage_state_effective(storage_state):
                                logger.info(f"✅ Session automatically saved to {storage_state}")
                            else:
                                logger.warning(f"Session saved to {storage_state}, but appears empty")
                                logger.info("Please complete login manually in the browser window")
                                logger.info("After you are back on the portal, press Enter to save session...")
                                try:
                                    input()
                                except Exception:
                                    pass
                        except Exception as e:
                            logger.warning(f"Failed to save session after auto-login: {e}")
                            logger.info("Please complete login manually in the browser window")
                            logger.info("After you are back on the portal, press Enter to save session...")
                            try:
                                input()
                            except Exception:
                                pass
                else:
                    logger.info("⚠️  Automatic login failed, please complete login manually")
                    logger.info("Please complete Okta login and MFA in the browser window.")
                    logger.info("After you are back on the portal, press Enter here to save the session...")
                    try:
                        input()
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Auto-login error: {e}")
                logger.info("Please complete Okta login and MFA in the browser window.")
                logger.info("After you are back on the portal, press Enter here to save the session...")
                try:
                    input()
                except Exception:
                    pass
        else:
            logger.info("Please complete Okta login and MFA in the browser window.")
            logger.info("After you are back on the portal, press Enter here to save the session...")
            try:
                input()
            except Exception:
                pass

        # Only save session manually if auto-login failed or wasn't used
        if not user_data_dir and not (auto_login_enabled and auto_login_success):
            try:
                await context.storage_state(path=storage_state)
                if is_storage_state_effective(storage_state):
                    logger.info(f"✅ Saved session to {storage_state}")
                else:
                    logger.warning(f"Saved session to {storage_state}, but it appears empty.")
                    logger.warning("Return to the attendance portal before pressing Enter, then try again.")
            except Exception as e:
                logger.warning(f"Failed to save storage state: {e}")

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
                    logger.warning(f"Session check navigation failed (attempt {attempt+1}/{retries+1}): {e}")
                    await asyncio.sleep(0.8)
            if last_err is not None:
                return False
            host = urlparse(page.url).netloc.lower()
            if 'okta' in host:
                return False
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
    load_env(os.getenv("ENV_FILE", ".env"))

    parser = argparse.ArgumentParser(description="Interactive Okta login helper (saves session state)")
    parser.add_argument("--portal", default=os.getenv("PORTAL_URL", ""), help="Portal URL (e.g., https://attendance.example.com/student/Default.aspx)")
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
        logger.info("Session check: " + ("OK" if ok else "NOT logged in"))
        raise SystemExit(0 if ok else 1)

    if not headed:
        logger.info("Running in headless mode. Use --headed or HEADLESS=0 for a browser window.")

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
        logger.info("Session check: " + ("OK" if ok else "NOT logged in"))


if __name__ == "__main__":
    main()
