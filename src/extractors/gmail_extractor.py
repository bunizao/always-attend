import os
import re
import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from urllib.parse import urljoin, urlparse, quote

from playwright.async_api import async_playwright, Page, TimeoutError as PwTimeout

from utils.logger import logger
from utils.gmail_cache import GmailCache
from utils.env_utils import load_env

class GmailCodeExtractor:
    def __init__(self):
        self.gmail_base_url = "https://mail.google.com"
        self._last_query: Optional[str] = None
        self._last_search_url: Optional[str] = None
        self.codes_patterns = [
            # Common attendance code patterns
            r'attendance\s+code[:\s]+([A-Z0-9]{4,8})',
            r'code[:\s]+([A-Z0-9]{4,8})',
            r'your\s+code[:\s]+([A-Z0-9]{4,8})',
            r'verification\s+code[:\s]+([A-Z0-9]{4,8})',
            r'access\s+code[:\s]+([A-Z0-9]{4,8})',
            # Pattern for codes in subject or body
            r'\b([A-Z0-9]{4,8})\b',
        ]
        
        # Initialize OCR extractor if available
        self.ocr_extractor = None
        self._init_ocr_extractor()
        
    def _init_ocr_extractor(self):
        """Initialize OCR extractor if configured"""
        try:
            # Check if OCR is enabled and configured
            ocr_enabled = os.getenv("OCR_ENABLED", "1") in ("1", "true", "True")
            has_gemini = bool(os.getenv("GEMINI_API_KEY"))
            has_openai = bool(os.getenv("OPENAI_API_KEY"))
            
            if ocr_enabled and (has_gemini or has_openai):
                from extractors.ocr_extractor import OCRCodeExtractor
                self.ocr_extractor = OCRCodeExtractor()
                logger.info("[INIT] OCR extractor initialized")
            else:
                logger.info("[INIT] OCR not configured or disabled")
        except ImportError:
            logger.warning("[INIT] OCR extractor not available (missing dependencies)")
        except Exception as e:
            logger.warning(f"[INIT] Failed to initialize OCR extractor: {e}")
        
    def _extract_course_code(self, text: str) -> Optional[str]:
        """Extract course code like FIT1047 from arbitrary text."""
        try:
            # Match patterns like FIT1047, FIT1047_S2_2025, etc.
            m = re.search(r'([A-Z]{3}\d{4})', (text or '').upper())
            return m.group(1) if m else None
        except Exception:
            return None

    async def _ensure_on_search(self, page: Page) -> None:
        """Ensure we are on a Gmail search results page, not Inbox.

        If current URL isn't a search URL, re-navigate to the last search URL or re-run the last query.
        """
        try:
            url = page.url
        except Exception:
            url = ""
        
        # Check if we're on a search results page
        # Gmail can show search results in multiple URL formats:
        # 1. https://mail.google.com/mail/u/0/#search/query
        # 2. https://mail.google.com/mail/u/0/?q=query (but may redirect to #inbox)
        # 3. https://mail.google.com/mail/u/0/?q=query#search/query
        is_search = ('/#search/' in url) or ('?q=' in url and '#search' in url) or ('?q=' in url and '#inbox' not in url)
        
        if is_search:
            logger.debug(f"[DEBUG] Already on search page: {url}")
            return
            
        logger.debug(f"[DEBUG] Not on search page, current URL: {url}")
        
        # Try to go back to last search URL first
        if self._last_search_url:
            try:
                logger.debug(f"[DEBUG] Navigating back to last search URL: {self._last_search_url}")
                await page.goto(self._last_search_url, timeout=15000)
                await page.wait_for_selector('[role="main"] tr[jsaction], .zA, [data-thread-id]', timeout=8000)
                logger.debug("[DEBUG] Successfully returned to search results")
                return
            except Exception as e:
                logger.debug(f"[DEBUG] Failed to return to last search URL: {e}")
        
        # Try re-running the last query
        last_q = self._last_query or os.getenv('LAST_GMAIL_QUERY', '')
        if last_q:
            logger.debug(f"[DEBUG] Re-running search query: {last_q}")
            await self._perform_gmail_search(page, last_q)
            return
            
        logger.warning("[WARNING] Could not ensure we're on search results page")

    async def extract_codes_from_gmail(self, 
                                     page: Page,
                                     storage_state: str = None,
                                     search_days: int = 7,
                                     search_query: str = None,
                                     week_number: str = None,
                                     target_email: str = None) -> List[Dict[str, Any]]:
        """
        Extract attendance codes from Gmail using existing Okta session.
        Supports both text extraction and OCR for image-based codes.
        
        Args:
            page: Playwright page with existing session
            storage_state: Path to storage state file
            search_days: How many days back to search for emails
            search_query: Custom search query for emails
            week_number: Week number to search for
            target_email: Specific email address to use for Gmail login
            
        Returns:
            List of extracted codes with metadata
        """
        
        # Optional overall timeout guard
        try:
            timeout_sec = int(os.getenv("GMAIL_EXTRACT_TIMEOUT_SEC", "300"))  # Increased to 5 minutes
        except Exception:
            timeout_sec = 300

        # Determine effective query early and check cache (unless force refresh)
        effective_query = search_query or self._build_search_query(search_days, week_number)
        cache = GmailCache()
        cache_key = cache.make_key(search_query=effective_query, target_email=target_email)
        if os.getenv('GMAIL_FORCE_REFRESH', '0') not in ('1','true','True'):
            cached = cache.get(cache_key)
            if cached is not None:
                logger.info(f"[CACHE] Using cached Gmail results ({len(cached.get('codes', []))} codes)")
                return cached.get('codes', [])

        async def _do_extract() -> List[Dict[str, Any]]:
            logger.info(f"[STEP] Navigating to Gmail...")
            await page.goto(self.gmail_base_url, timeout=45000)

            # Debug: Log current URL and title
            current_url = page.url
            try:
                page_title = await page.title()
                logger.info(f"[DEBUG] Current page: {current_url}")
                logger.info(f"[DEBUG] Page title: {page_title}")
            except Exception:
                logger.info(f"[DEBUG] Current page: {current_url}")

            # Wait for page to fully load and check if we need authentication
            await page.wait_for_load_state('domcontentloaded')
            current_url = page.url

            # Handle email input if we're on a login page
            if target_email and 'accounts.google.com' in current_url:
                logger.info(f"[STEP] Detected Google login page, attempting email input...")
                await self._handle_email_input(page, target_email)
                # Wait after email input for potential redirects
                # Wait for next page to load or redirect
                try:
                    await page.wait_for_url(lambda u: ('mail.google.com' in u) or ('okta' in u) or ('signin' in u), timeout=10000)
                except Exception:
                    pass
                current_url = page.url
                logger.info(f"[DEBUG] URL after email input attempt: {current_url}")

            # Wait for Gmail to load - try multiple selectors for different Gmail interfaces
            gmail_loaded = False
            gmail_selectors = [
                '[role="main"]',  # Standard Gmail interface
                '.aeJ',  # Gmail main content area
                '#\\:1',  # Gmail compose area (ID selector)
                '[gh="tl"]',  # Gmail toolbar
                '.nH',  # Gmail main wrapper
                '.aDP',  # Gmail left sidebar
                '.Tm .aeN'  # Gmail conversation list
            ]

            logger.debug(f"[DEBUG] Trying to detect Gmail interface on: {current_url}")
            for selector in gmail_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    logger.info(f"[OK] Gmail loaded successfully (detected via {selector})")
                    gmail_loaded = True
                    break
                except PwTimeout:
                    logger.debug(f"[DEBUG] Selector {selector} not found")
                    continue

            if not gmail_loaded:
                # Debug: Log page content to understand what we're seeing
                try:
                    page_content = await page.content()
                    logger.debug(f"[DEBUG] Page content length: {len(page_content)} characters")
                    # Look for common elements that might indicate what page we're on
                    if 'accounts.google.com' in current_url:
                        logger.info(f"[DEBUG] Still on Google accounts page - may need account selection or email input")
                        # Try email input again if we haven't tried yet
                        if target_email:
                            logger.info(f"[STEP] Attempting email input on accounts page...")
                            await self._handle_email_input(page, target_email)
                            await page.wait_for_timeout(5000)  # Wait longer for redirect
                    elif 'login' in current_url.lower() or 'signin' in current_url.lower():
                        logger.info(f"[DEBUG] On login page - may need authentication")
                    elif 'mail.google.com' in current_url:
                        logger.info(f"[DEBUG] On Gmail domain but interface not detected")
                    else:
                        logger.info(f"[DEBUG] Unknown page type")
                except Exception as e:
                    logger.debug(f"[DEBUG] Could not analyze page content: {e}")

                logger.warning("Gmail interface not fully detected, but continuing - Gmail may still be functional")

            # Check if we need to select account or sign in
            await self._handle_account_selection(page)

            # Build search query
            q = search_query or effective_query
            logger.info(f"[STEP] Searching for emails with query: {q}")

            # Use Gmail search (prefer direct URL navigation for speed)
            os.environ['LAST_GMAIL_QUERY'] = q
            await self._perform_gmail_search(page, q)

            # Phase A: ensure we are on search results, then collect text hints and images
            await self._ensure_on_search(page)
            text_codes, image_items = await self._collect_text_and_images(page)

            # Phase B: OCR all images in batch
            ocr_codes: List[Dict[str, Any]] = []
            if self.ocr_extractor and image_items:
                ocr_method = os.getenv("OCR_METHOD", "auto")
                try:
                    ocr_codes = await self.ocr_extractor.extract_codes_from_images(image_items, ocr_method, page)
                    for c in ocr_codes:
                        c['source'] = 'gmail_ocr'
                except Exception as e:
                    logger.warning(f"[OCR] Batch OCR failed: {e}")

            # Merge and deduplicate
            codes = []
            seen = set()
            for item in (text_codes + ocr_codes):
                key = (item.get('code') or '').upper()
                if key and key not in seen:
                    seen.add(key)
                    codes.append(item)

            logger.info(f"[OK] Extracted {len(codes)} attendance codes from Gmail (text+OCR)")

            # Save to cache (store minimal payload)
            try:
                cache.set(cache_key, {"codes": codes})
                logger.debug("[CACHE] Saved Gmail results to cache")
            except Exception:
                pass

            # Also persist a JSON artifact of OCR results if any
            try:
                if ocr_codes:
                    out_dir = os.getenv('GMAIL_OCR_OUT_DIR', 'data')
                    os.makedirs(out_dir, exist_ok=True)
                    out_path = os.path.join(out_dir, 'gmail_ocr_results.json')
                    payload = [{
                        'code': item.get('code'),
                        'image_url': item.get('image_url'),
                        'subject': item.get('subject') or item.get('email_subject') or '',
                        'source': item.get('source'),
                    } for item in ocr_codes]
                    with open(out_path, 'w', encoding='utf-8') as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)
                    logger.info(f"[OK] Saved OCR JSON: {out_path}")
            except Exception as e:
                logger.debug(f"[WARN] Failed to write OCR JSON: {e}")

            # Purge OCR cache at the end as requested by user
            if self.ocr_extractor:
                try:
                    self.ocr_extractor.purge_cache()
                    logger.info("[CLEANUP] OCR cache purged")
                except Exception as e:
                    logger.warning(f"[CLEANUP] Failed to purge OCR cache: {e}")

            # Optionally purge Gmail search cache as well
            if os.getenv('GMAIL_PURGE_CACHE_AFTER') in ('1','true','True'):
                try:
                    cache.purge()
                    logger.info("[CLEANUP] Gmail cache purged")
                except Exception:
                    pass

            return codes

        try:
            return await asyncio.wait_for(_do_extract(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            logger.warning(f"[TIMEOUT] Gmail extraction exceeded {timeout_sec}s; returning no results")
            return []
    
    async def _handle_account_selection(self, page: Page) -> None:
        """Handle Google account selection if needed."""
        try:
            current_url = page.url
            logger.debug(f"[DEBUG] Checking account selection on: {current_url}")
            
            # Check if we're on account selection page
            if 'accounts.google.com' in current_url:
                logger.info("[STEP] Handling Google account selection...")
                
                # Wait a bit for the page to fully load
                await page.wait_for_timeout(2000)
                
                # Look for account selection elements
                account_selectors = [
                    '[data-identifier*="@"]',  # Account with email
                    '[aria-label*="account"]',  # Account with aria-label
                    '.BHzsHc',  # Account selection item
                    '.bdf4dc',  # Account card
                    '[data-email*="@"]',  # Data email attribute
                    '.ahS7he',  # Account container
                ]
                
                account_found = False
                for selector in account_selectors:
                    try:
                        await page.wait_for_selector(selector, timeout=5000)
                        accounts = page.locator(selector)
                        count = await accounts.count()
                        
                        if count > 0:
                            logger.info(f"[DEBUG] Found {count} accounts using selector: {selector}")
                            
                            # Try to find the school account
                            for i in range(count):
                                try:
                                    account_text = await accounts.nth(i).inner_text()
                                    logger.debug(f"[DEBUG] Account {i+1}: {account_text}")
                                    
                                    # Look for Monash or student account
                                    if any(keyword in account_text.lower() for keyword in ['monash', 'student', '@student.monash']):
                                        logger.info(f"[OK] Selecting Monash account: {account_text}")
                                        await accounts.nth(i).click()
                                        account_found = True
                                        break
                                except Exception as e:
                                    logger.debug(f"[DEBUG] Error checking account {i+1}: {e}")
                                    continue
                            
                            # If no specific account found, click the first one
                            if not account_found and count > 0:
                                logger.info("[INFO] No specific Monash account found, selecting first account")
                                await accounts.first.click()
                                account_found = True
                            
                            break
                            
                    except PwTimeout:
                        logger.debug(f"[DEBUG] Account selector {selector} not found")
                        continue
                
                if not account_found:
                    logger.warning("[WARNING] No account selection elements found")
                else:
                    # Wait for redirect - could be to Gmail or Okta
                    try:
                        logger.debug("[DEBUG] Waiting for redirect...")
                        await page.wait_for_timeout(5000)  # Give more time for redirect
                        current_url = page.url
                        logger.info(f"[DEBUG] Current URL after account selection: {current_url}")
                        
                        # Check if redirected to Okta for SSO
                        if 'okta.com' in current_url:
                            logger.info("[STEP] Detected Okta SSO redirect, handling authentication...")
                            await self._handle_okta_sso(page)
                        elif 'mail.google.com' in current_url:
                            logger.info("[OK] Successfully redirected to Gmail")
                        else:
                            # Try waiting a bit more for potential redirect
                            logger.debug("[DEBUG] Waiting longer for potential redirect...")
                            await page.wait_for_timeout(10000)
                            final_url = page.url
                            if 'okta.com' in final_url:
                                logger.info("[STEP] Detected delayed Okta SSO redirect...")
                                await self._handle_okta_sso(page)
                            elif 'mail.google.com' in final_url:
                                logger.info("[OK] Successfully redirected to Gmail after delay")
                            else:
                                logger.info(f"[DEBUG] Unexpected redirect URL: {final_url}")
                            
                    except Exception as e:
                        logger.warning(f"[WARNING] Error during redirect handling: {e}")
                
            else:
                logger.debug(f"[DEBUG] Not on Google accounts page, skipping account selection")
                
        except Exception as e:
            logger.debug(f"[DEBUG] Account selection handling error: {e}")
    
    async def _handle_okta_sso(self, page: Page) -> None:
        """Handle Okta SSO authentication - perform fresh login."""
        try:
            logger.info("[STEP] Detected Okta SSO redirect - performing fresh authentication...")
            
            # Import the auto_login function to handle Okta authentication
            import sys
            import os
            sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
            from core.login import auto_login
            
            # Perform fresh Okta login
            login_success = await auto_login(page)
            
            if login_success:
                logger.info("[OK] Okta authentication completed successfully")
                
                # Wait for redirect back to Gmail or account selection
                logger.debug("[DEBUG] Waiting for redirect after Okta authentication...")
                
                try:
                    # Wait for either Gmail or account selection page
                    await page.wait_for_url(lambda url: 
                        'mail.google.com' in url or 'accounts.google.com' in url, 
                        timeout=60000)
                    
                    current_url = page.url
                    logger.info(f"[OK] Post-auth redirect to: {current_url}")
                    
                    # If we're back on Gmail, we're done
                    if 'mail.google.com' in current_url:
                        logger.info("[OK] Successfully reached Gmail after Okta auth")
                        return
                        
                    # If we're on account selection, handle it
                    if 'accounts.google.com' in current_url:
                        logger.info("[STEP] Handling account selection after Okta auth...")
                        await self._handle_account_selection(page)
                        
                except Exception as e:
                    logger.warning(f"[WARNING] Post-auth redirect timeout: {e}")
                    current_url = page.url
                    logger.info(f"[DEBUG] Current URL after timeout: {current_url}")
            else:
                logger.warning("[WARNING] Okta authentication failed")
                    
        except Exception as e:
            logger.warning(f"[WARNING] Error during Okta SSO authentication: {e}")
    
    async def _handle_email_input(self, page: Page, target_email: str) -> None:
        """Handle email input if we're on a Google login page."""
        try:
            current_url = page.url
            logger.info(f"[DEBUG] Checking for email input on: {current_url}")
            
            # Check if we're on a Google login page that requires email input
            if any(domain in current_url for domain in ['accounts.google.com', 'myaccount.google.com', 'signin']):
                logger.info(f"[STEP] Filling email: {target_email}")
                
                # Wait for page to be ready
                await page.wait_for_timeout(2000)
                
                # Look for email input field - try most specific selectors first
                email_selectors = [
                    'input[id="identifierId"]',  # Google's standard email input ID
                    'input[name="identifier"]',
                    'input[type="email"]',
                    'input[autocomplete="username"]',
                    'input[autocomplete="email"]',
                    'input[aria-label*="email" i]',
                    'input[placeholder*="email" i]',
                    'input[placeholder*="username" i]',
                    '#Email, #email',
                    'input[name="Email"]',
                    'input[name="username"]',
                    'input.whsOnd',  # Google's CSS class for email input
                    '[jsname="YPqjbf"]'  # Google's jsname for email input
                ]
                
                email_filled = False
                logger.info(f"[DEBUG] Trying {len(email_selectors)} email selectors...")
                
                for selector in email_selectors:
                    try:
                        logger.debug(f"[DEBUG] Trying selector: {selector}")
                        await page.wait_for_selector(selector, timeout=3000)
                        email_element = page.locator(selector).first
                        
                        if await email_element.is_visible():
                            logger.info(f"[DEBUG] Found email input using selector: {selector}")
                            
                            # Add delay to make the process visible
                            await page.wait_for_timeout(1000)
                            logger.info(f"[DEBUG] About to fill email field with: {target_email}")
                            
                            # Clear and fill email
                            await email_element.clear()
                            await page.wait_for_timeout(500)  # Make it visible
                            await email_element.fill(target_email)
                            await page.wait_for_timeout(1000)  # Let user see the filled email
                            
                            logger.info(f"[DEBUG] Email field filled, now looking for submit button...")
                            
                            # Try to submit
                            next_selectors = [
                                'button[type="submit"]',
                                'input[type="submit"]',
                                'button:has-text("Next")',
                                'button:has-text("Continue")',
                                '#identifierNext',
                                'button[id*="next" i]'
                            ]
                            
                            for next_selector in next_selectors:
                                try:
                                    logger.debug(f"[DEBUG] Trying next button selector: {next_selector}")
                                    next_button = page.locator(next_selector).first
                                    if await next_button.is_visible():
                                        logger.info(f"[DEBUG] Found next button, clicking...")
                                        await next_button.click()
                                        logger.info(f"[OK] Email submitted: {target_email}")
                                        email_filled = True
                                        break
                                except Exception as e:
                                    logger.debug(f"[DEBUG] Next button selector failed: {e}")
                                    continue
                            
                            if email_filled:
                                # Wait for next step or redirect - this might be Okta
                                logger.debug("[DEBUG] Waiting for redirect after email submission...")
                                await page.wait_for_timeout(5000)
                                
                                # Check if we were redirected to Okta
                                current_url = page.url
                                logger.debug(f"[DEBUG] URL after email submission: {current_url}")
                                
                                if 'okta.com' in current_url:
                                    logger.info("[STEP] Detected Okta redirect after email submission...")
                                    await self._handle_okta_sso(page)
                                    return
                                
                                break
                        else:
                            logger.debug(f"[DEBUG] Email element not visible for selector: {selector}")
                                
                    except Exception as e:
                        logger.debug(f"[DEBUG] Error with email selector {selector}: {e}")
                        continue
                
                if not email_filled:
                    logger.warning(f"[WARNING] Could not fill email automatically")
                    # Try a fallback approach - click on the page and type
                    try:
                        logger.info(f"[FALLBACK] Trying to click anywhere on page and type email...")
                        await page.click('body')
                        await page.wait_for_timeout(500)
                        await page.keyboard.type(target_email)
                        await page.wait_for_timeout(1000)
                        await page.keyboard.press('Tab')
                        await page.wait_for_timeout(500)
                        await page.keyboard.press('Enter')
                        logger.info(f"[FALLBACK] Tried fallback email input method")
                    except Exception as e:
                        logger.debug(f"[FALLBACK] Fallback method failed: {e}")
                else:
                    logger.info(f"[DEBUG] Email input completed successfully")
                    
        except Exception as e:
            logger.warning(f"[DEBUG] Email input handling error: {e}")
    
    def _build_search_query(self, search_days: int, week_number: str = None) -> str:
        """Build Gmail search query for attendance-related emails."""
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=search_days)
        
        # Format dates for Gmail search (YYYY/MM/DD)
        start_str = start_date.strftime("%Y/%m/%d")
        end_str = end_date.strftime("%Y/%m/%d")
        
        # Use minimal search terms - Gmail has fuzzy search
        # User specifically requested "attendance codes" (plural)
        parts = ["attendance codes", "@monash.edu"]
        if week_number:
            parts.append(f"week {week_number}")

        base_query = " ".join(parts)
        date_query = f"after:{start_str} before:{end_str}"
        return f"{base_query} {date_query}"
    
    async def _perform_gmail_search(self, page: Page, query: str) -> None:
        """Perform search in Gmail (prefer direct URL to speed up)."""
        try:
            logger.debug(f"[DEBUG] Starting Gmail search for: {query}")
            direct_first = os.getenv("GMAIL_DIRECT_SEARCH", "1") in ("1", "true", "True")

            async def do_direct_search() -> bool:
                try:
                    q_enc = quote(query, safe='')
                    
                    # Method 1: Try hash-based search first (most reliable)
                    url_hash = f"https://mail.google.com/mail/u/0/#search/{q_enc}"
                    await page.goto(url_hash, timeout=20000)
                    await page.wait_for_timeout(2000)  # Wait for search to process
                    
                    # Check if we're actually on search results
                    current_url = page.url
                    if '/#search/' in current_url:
                        try:
                            await page.wait_for_selector('[role="main"] tr[jsaction], .zA, [data-thread-id]', timeout=6000)
                            logger.info(f"[OK] Gmail hash search navigated: {url_hash}")
                            os.environ['LAST_GMAIL_QUERY'] = query
                            self._last_query = query
                            self._last_search_url = url_hash
                            return True
                        except Exception:
                            logger.debug("[DEBUG] Hash search loaded but no email elements found")
                    
                    # Method 2: Query param style with forced search hash
                    url_q = f"https://mail.google.com/mail/u/0/?q={q_enc}#search/{q_enc}"
                    await page.goto(url_q, timeout=20000)
                    await page.wait_for_timeout(2000)
                    
                    current_url = page.url
                    if '#search/' in current_url or ('#inbox' not in current_url and '?q=' in current_url):
                        try:
                            await page.wait_for_selector('[role="main"] tr[jsaction], .zA, [data-thread-id]', timeout=6000)
                            logger.info(f"[OK] Gmail query-param search navigated: {url_q}")
                            os.environ['LAST_GMAIL_QUERY'] = query
                            self._last_query = query
                            self._last_search_url = url_q
                            return True
                        except Exception:
                            logger.debug("[DEBUG] Query param search loaded but no email elements found")
                    
                    # Method 3: If we ended up on inbox, force navigation to search
                    if '#inbox' in current_url:
                        logger.debug("[DEBUG] Gmail redirected to inbox, forcing search navigation")
                        # Use JavaScript to force search
                        try:
                            js_search = f"""
                                window.location.hash = 'search/{q_enc}';
                            """
                            await page.evaluate(js_search)
                            await page.wait_for_timeout(3000)
                            
                            current_url = page.url
                            if '#search/' in current_url:
                                await page.wait_for_selector('[role="main"] tr[jsaction], .zA, [data-thread-id]', timeout=6000)
                                logger.info(f"[OK] Gmail JavaScript search navigated: {current_url}")
                                os.environ['LAST_GMAIL_QUERY'] = query
                                self._last_query = query
                                self._last_search_url = current_url
                                return True
                        except Exception as e:
                            logger.debug(f"[DEBUG] JavaScript search failed: {e}")
                    
                    return False
                except Exception as e:
                    logger.debug(f"[DEBUG] Direct search failed: {e}")
                    return False

            if direct_first:
                if await do_direct_search():
                    # Verify we're actually on search results
                    current_url = page.url
                    is_search = ('/#search/' in current_url) or ('?q=' in current_url and '#search' in current_url) or ('?q=' in current_url and '#inbox' not in current_url)
                    if is_search:
                        logger.info(f"[OK] Gmail search completed for: {query}")
                        logger.debug(f"[DEBUG] Confirmed on search page: {current_url}")
                        return
                    else:
                        logger.warning(f"[WARNING] Search navigation successful but not on search page: {current_url}")
                        # Try to wait a bit more for the page to load properly
                        await page.wait_for_timeout(2000)
                        current_url = page.url
                        is_search = ('/#search/' in current_url) or ('?q=' in current_url and 'search' in current_url)
                        if is_search:
                            logger.info(f"[OK] Gmail search completed after delay: {query}")
                            return

            # Fallback: interact with the UI search box
            if os.getenv("GMAIL_UI_SEARCH_FALLBACK", "0") not in ("1", "true", "True"):
                logger.debug("[DEBUG] UI search fallback disabled by env; skipping")
                return
            logger.debug("[DEBUG] Falling back to UI search box...")
            search_selectors = [
                'input[aria-label*="Search"]',
                'input[name="q"]',
                '[role="search"] input',
            ]

            search_box = None
            for selector in search_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=3000)
                    el = page.locator(selector).first
                    if await el.is_visible():
                        search_box = el
                        break
                except Exception:
                    continue

            if search_box is None:
                # Try keyboard to focus
                try:
                    await page.keyboard.press('/')
                except Exception:
                    pass

            if search_box is not None:
                try:
                    await search_box.click()
                    # Clear and type
                    # Try both Control and Meta to be robust across OS
                    try:
                        await page.keyboard.press('Control+a')
                    except Exception:
                        pass
                    try:
                        await page.keyboard.press('Meta+a')
                    except Exception:
                        pass
                    await page.keyboard.type(query)
                    await page.keyboard.press('Enter')
                except Exception as e:
                    logger.debug(f"[DEBUG] Typing into search box failed: {e}")

            # Wait a moment for results
            await page.wait_for_selector('[role="main"] tr[jsaction], .zA, [data-thread-id]', timeout=6000)
            os.environ['LAST_GMAIL_QUERY'] = query
            self._last_query = query
            try:
                # Read current URL as the last search URL
                self._last_search_url = page.url
            except Exception:
                pass
            logger.info(f"[OK] Gmail search completed for: {query}")

        except Exception as e:
            logger.warning(f"Gmail search failed: {e}")

    async def _collect_text_and_images(self, page: Page) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Collect text codes and image descriptors across search results, then OCR separately.

        Returns (text_codes, image_items). image_items are dicts with at least 'src' field.
        """
        text_codes: List[Dict[str, Any]] = []
        all_images: List[Dict[str, Any]] = []

        # Ensure we're on search results page before processing
        await self._ensure_on_search(page)
        
        # Reuse selection logic from _extract_codes_from_emails, but defer OCR and aggregate
        try:
            await page.wait_for_timeout(2000)  # Give more time for search results to load

            # First, verify we're actually on search results
            current_url = page.url
            is_search = ('/#search/' in current_url) or ('?q=' in current_url and '#search' in current_url) or ('?q=' in current_url and '#inbox' not in current_url)
            
            if not is_search:
                logger.warning(f"[WARNING] Still not on search page after ensure: {current_url}")
                # Try one more time to get to search results
                if self._last_search_url:
                    try:
                        await page.goto(self._last_search_url, timeout=15000)
                        await page.wait_for_timeout(2000)
                    except Exception as e:
                        logger.warning(f"[WARNING] Final attempt to get to search failed: {e}")
                        return text_codes, all_images

            email_selectors = [
                '[role="main"] tr[jsaction]',
                '.zA',
                '[data-thread-id]',
                '.Cl.aqJ',
                'tr.zA.yW',
                '.aDP [role="main"] tr',
                '.aeF tr'
            ]

            emails = None
            email_count = 0
            for selector in email_selectors:
                try:
                    emails = page.locator(selector)
                    count = await emails.count()
                    if count > 0:
                        email_count = count
                        logger.info(f"[DEBUG] Found {count} emails using selector: {selector}")
                        break
                except Exception:
                    continue

            if not emails or email_count == 0:
                logger.warning("No emails found in search results")
                # Debug: check what's on the page
                try:
                    page_text = await page.inner_text('body')
                    if 'no conversations' in page_text.lower():
                        logger.info("[DEBUG] Gmail shows 'no conversations' - search returned no results")
                    else:
                        logger.debug(f"[DEBUG] Page content preview: {page_text[:200]}...")
                except Exception:
                    pass
                return text_codes, all_images

            # Apply optional cap - user specifically wants only 4 original emails
            try:
                max_emails = int(os.getenv("GMAIL_MAX_EMAILS", "4"))  # Changed from 20 to 4
            except Exception:
                max_emails = 4
            email_count = min(email_count, max_emails)

            for i in range(email_count):
                email_el = emails.nth(i)
                # Extract subject/preview quickly from list row
                subject_text = ""
                preview_text = ""
                try:
                    subject_text = await email_el.locator('.bog, [data-thread-id] span[id]:last-child').first.inner_text()
                except Exception:
                    pass
                try:
                    preview_text = await email_el.locator('.y2, .aYp').first.inner_text()
                except Exception:
                    pass

                # Text code extraction from listing
                listing_text = f"{subject_text} {preview_text}"
                for code in self._extract_codes_from_text(listing_text):
                    text_codes.append({
                        'code': code,
                        'subject': subject_text.strip(),
                        'preview': (preview_text or '').strip()[:100],
                        'course': self._extract_course_code(listing_text),
                        'source': 'gmail_text',
                        'extracted_at': datetime.now().isoformat(),
                    })

                # Open the email to scan images, then go back to search results
                try:
                    logger.debug(f"[DEBUG] Processing email {i+1}/{email_count}: {subject_text[:30]}...")
                    await email_el.click(timeout=10000)
                    # Wait for message view content
                    try:
                        await page.wait_for_selector('div.a3s, [data-message-id]', timeout=8000)
                    except Exception:
                        await page.wait_for_timeout(1000)
                    
                    if self.ocr_extractor:
                        try:
                            images = await asyncio.wait_for(
                                self.ocr_extractor.detect_images_in_gmail(page),
                                timeout=20.0  # 20s for slower Gmail loads
                            )
                            # Tag with subject for later context
                            for img in images:
                                item = dict(img)
                                item['email_subject'] = subject_text
                                all_images.append(item)
                            logger.debug(f"[DEBUG] Found {len(images)} images in email {i+1}")
                        except asyncio.TimeoutError:
                            logger.warning(f"[WARNING] Image detection timeout for email {i+1}")
                        except Exception as e:
                            logger.debug(f"[DEBUG] Error detecting images in email {i+1}: {e}")

                    # Also try to extract text codes from full body if present (handles no-image emails)
                    try:
                        body_elem = page.locator('div.a3s, .ii.gt').first
                        if await body_elem.count() > 0:
                            body_text = await body_elem.inner_text()
                            body_codes = self._extract_codes_from_text(body_text)
                            if body_codes:
                                for c in body_codes:
                                    text_codes.append({
                                        'code': c,
                                        'subject': subject_text.strip(),
                                        'preview': (preview_text or '').strip()[:100],
                                        'course': self._extract_course_code(subject_text) or self._extract_course_code(body_text),
                                        'source': 'gmail_text_body',
                                        'extracted_at': datetime.now().isoformat(),
                                    })
                    except Exception as e:
                        logger.debug(f"[DEBUG] Failed to extract text codes from body for email {i+1}: {e}")
                except Exception as e:
                    logger.warning(f"[WARNING] Error processing email {i+1}: {e}")
                finally:
                    # Return to search results without jumping to inbox
                    try:
                        logger.debug(f"[DEBUG] Returning to search results after processing email {i+1}")
                        
                        # Method 1: Try going back with browser back button
                        try:
                            await page.go_back(timeout=5000)
                            await page.wait_for_timeout(1000)
                            current_url = page.url
                            if ('/#search/' in current_url) or ('?q=' in current_url and '#inbox' not in current_url):
                                logger.debug("[DEBUG] Successfully returned via back button")
                                continue
                        except Exception as e:
                            logger.debug(f"[DEBUG] Back button failed: {e}")
                        
                        # Method 2: Direct navigation to last search URL
                        if self._last_search_url:
                            logger.debug(f"[DEBUG] Navigating to last search URL: {self._last_search_url}")
                            await page.goto(self._last_search_url, timeout=15000)
                            await page.wait_for_selector('[role="main"] tr[jsaction], .zA, [data-thread-id]', timeout=8000)
                            logger.debug("[DEBUG] Successfully returned via direct navigation")
                        else:
                            # Method 3: Re-run search query
                            last_query = self._last_query or os.getenv('LAST_GMAIL_QUERY', '')
                            if last_query:
                                logger.debug(f"[DEBUG] Re-running search query: {last_query}")
                                await asyncio.wait_for(self._perform_gmail_search(page, last_query), timeout=10.0)
                            else:
                                logger.debug("[DEBUG] Using ensure_on_search fallback")
                                await self._ensure_on_search(page)
                                
                    except Exception as e:
                        logger.debug(f"[DEBUG] Failed to return to search results: {e}")
                        # Final fallback: try to re-navigate to search
                        try:
                            last_query = self._last_query or os.getenv('LAST_GMAIL_QUERY', '')
                            if last_query:
                                logger.debug("[DEBUG] Final fallback: re-running search")
                                await self._perform_gmail_search(page, last_query)
                        except Exception as fallback_e:
                            logger.warning(f"[WARNING] All attempts to return to search failed: {fallback_e}")
                            break  # Exit the loop if we can't get back to search results

        except Exception as e:
            logger.warning(f"Error during collection of text/images: {e}")

        # Deduplicate text codes
        dedup: Dict[str, Dict[str, Any]] = {}
        for item in text_codes:
            dedup[item['code']] = item
        return list(dedup.values()), all_images
    
    async def _extract_codes_from_emails(self, page: Page) -> List[Dict[str, Any]]:
        """Extract attendance codes from Gmail email list and contents."""
        codes = []
        processed_images = set()  # Track processed image URLs to avoid duplicates
        
        try:
            # Wait for email list to load
            logger.debug("[DEBUG] Waiting for email list to load...")
            await page.wait_for_timeout(2000)
            
            # Debug: Check current page state
            current_url = page.url
            logger.debug(f"[DEBUG] Current URL during email extraction: {current_url}")
            
            # Multiple selectors for different Gmail interfaces
            email_selectors = [
                '[role="main"] tr[jsaction]',  # Gmail email rows (standard)
                '.zA',  # Gmail conversation row (classic)
                '[data-thread-id]',  # Email thread (new)
                '.Cl.aqJ',  # Compact view emails
                'tr.zA.yW',  # Standard list view
                '.aDP [role="main"] tr',  # Main content area emails
                '.aeF tr'  # Email list container
            ]
            
            emails = None
            email_count = 0
            used_selector = None
            
            logger.debug(f"[DEBUG] Trying {len(email_selectors)} email selectors...")
            for selector in email_selectors:
                try:
                    emails = page.locator(selector)
                    count = await emails.count()
                    if count > 0:
                        email_count = count
                        used_selector = selector
                        logger.info(f"[DEBUG] Found {count} emails using selector: {selector}")
                        break
                    else:
                        logger.debug(f"[DEBUG] Selector {selector} found 0 emails")
                except Exception as e:
                    logger.debug(f"[DEBUG] Error with selector {selector}: {e}")
                    continue
            
            if not emails or email_count == 0:
                logger.warning("No emails found in search results - trying fallback detection")
                # Fallback: look for any clickable email-like elements
                fallback_selectors = [
                    '[role="main"] [role="listitem"]',
                    '.nH [role="listitem"]',
                    '.AO [role="listitem"]',
                    '[role="main"] tbody tr',  # Table rows in main
                    '.aDP tbody tr',  # Table rows in content
                ]
                
                logger.debug(f"[DEBUG] Trying {len(fallback_selectors)} fallback selectors...")
                for fallback_selector in fallback_selectors:
                    try:
                        emails = page.locator(fallback_selector)
                        count = await emails.count()
                        if count > 0:
                            email_count = count
                            used_selector = fallback_selector
                            logger.info(f"[DEBUG] Found {count} emails using fallback selector: {fallback_selector}")
                            break
                        else:
                            logger.debug(f"[DEBUG] Fallback selector {fallback_selector} found 0 emails")
                    except Exception as e:
                        logger.debug(f"[DEBUG] Error with fallback selector {fallback_selector}: {e}")
                        continue
            
            if not emails or email_count == 0:
                logger.warning("No emails found in search results")
                
                # Debug: Try to understand what's on the page
                try:
                    page_text = await page.inner_text('body')
                    logger.debug(f"[DEBUG] Page body text length: {len(page_text)} characters")
                    
                    # Look for common Gmail messages
                    if 'no conversations' in page_text.lower():
                        logger.info("[DEBUG] Gmail shows 'no conversations' - search returned no results")
                    elif 'search' in page_text.lower():
                        logger.info("[DEBUG] Page contains search-related text")
                    elif 'inbox' in page_text.lower():
                        logger.info("[DEBUG] Page shows inbox interface")
                    else:
                        logger.debug(f"[DEBUG] Page text preview: {page_text[:200]}...")
                        
                except Exception as e:
                    logger.debug(f"[DEBUG] Could not analyze page text: {e}")
                
                return codes
            
            # Apply content filtering first to reduce irrelevant emails
            relevant_emails = await self._filter_relevant_emails(page, emails, email_count)
            
            # Limit to first 4 relevant emails as requested by user
            original_count = len(relevant_emails)
            relevant_emails = relevant_emails[:4]  # Changed from 10 to 4
            if original_count > 4:
                logger.info(f"[DEBUG] Processing first 4 of {original_count} relevant emails (user requested only 4 original emails)")
            
            email_count = len(relevant_emails)
            
            logger.debug(f"[DEBUG] Processing {email_count} emails using selector: {used_selector}")
            
            for i, email_idx in enumerate(relevant_emails):
                try:
                    logger.debug(f"[DEBUG] Processing email {i+1}/{email_count}")
                    await self._extract_codes_from_single_email(page, emails.nth(email_idx), codes, processed_images)
                except Exception as e:
                    logger.debug(f"[DEBUG] Error processing email {i+1}: {e}")
                    continue
            
        except Exception as e:
            logger.warning(f"Error extracting codes from emails: {e}")
        
        # Remove duplicates
        unique_codes = []
        seen_codes = set()
        for code_info in codes:
            code_key = (code_info['code'], code_info.get('subject', ''))
            if code_key not in seen_codes:
                seen_codes.add(code_key)
                unique_codes.append(code_info)
        
        logger.debug(f"[DEBUG] Extracted {len(codes)} total codes, {len(unique_codes)} unique codes")
        return unique_codes
    
    async def _filter_relevant_emails(self, page: Page, emails, email_count: int) -> List[int]:
        """Filter emails to only those likely to contain attendance codes."""
        relevant_indices = []
        
        # Keywords that indicate attendance-related emails
        attendance_keywords = [
            'attendance', 'code', 'verification', 'access', 'workshop', 
            'tutorial', 'practical', 'lab', 'session', 'week', 'class'
        ]
        
        # Course code patterns (e.g., FIT1047, BUS2020)
        course_pattern = r'\b[A-Z]{2,4}\d{4}\b'
        
        logger.debug(f"[DEBUG] Pre-filtering {email_count} emails for relevance...")
        
        for i in range(min(email_count, 50)):  # Check up to 50 emails maximum
            try:
                email_element = emails.nth(i)
                
                # Extract subject and preview text quickly
                subject_text = ""
                preview_text = ""
                
                # Quick subject extraction with timeout
                try:
                    subject_elem = email_element.locator('.bog, .y6 span[id], [data-thread-id] span[id]:last-child').first
                    subject_text = await subject_elem.inner_text(timeout=1000)
                except:
                    pass
                
                # Quick preview extraction with timeout
                try:
                    preview_elem = email_element.locator('.y2, .y3, .aYp, .akt').first
                    preview_text = await preview_elem.inner_text(timeout=1000)
                except:
                    pass
                
                email_text = f"{subject_text} {preview_text}".lower()
                
                # Check for attendance-related keywords
                has_attendance_keyword = any(keyword in email_text for keyword in attendance_keywords)
                
                # Check for course codes
                has_course_code = bool(re.search(course_pattern, f"{subject_text} {preview_text}"))
                
                # Check for potential codes in text (basic pattern)
                has_potential_code = bool(re.search(r'\b[A-Z0-9]{4,8}\b', f"{subject_text} {preview_text}"))
                
                # Email is relevant if it has attendance keywords AND (course code OR potential code)
                if has_attendance_keyword and (has_course_code or has_potential_code):
                    relevant_indices.append(i)
                    logger.debug(f"[DEBUG] Email {i+1} relevant: {subject_text[:30]}...")
                    
                    # Stop if we have enough relevant emails (user wants only 4)
                    if len(relevant_indices) >= 4:
                        break
                        
            except Exception as e:
                logger.debug(f"[DEBUG] Error filtering email {i+1}: {e}")
                continue
        
        logger.info(f"[DEBUG] Found {len(relevant_indices)} relevant emails out of {min(email_count, 50)} checked")
        return relevant_indices
    
    async def _extract_codes_from_single_email(self, page: Page, email_element, codes: List[Dict[str, Any]], processed_images: set) -> None:
        """Extract codes from a single email including OCR for images."""
        try:
            # Get email subject and preview text with multiple selectors
            subject_text = ""
            preview_text = ""
            
            # Try multiple subject selectors for different Gmail interfaces
            subject_selectors = [
                '[data-thread-id] span[id]:last-child',  # Standard thread subject
                '.bog',  # Classic subject
                '.y6 span[id]',  # Alternative subject
                'span[data-thread-id]',  # Thread-based subject
                '.aYF',  # Subject in conversation view
                '.aoT',  # Subject line
                'span.bog',  # Bold subject text
                '.a4W span'  # Subject span in conversation
            ]
            
            for subject_selector in subject_selectors:
                try:
                    subject_elem = email_element.locator(subject_selector).first
                    if await subject_elem.count() > 0:
                        subject_text = await subject_elem.inner_text()
                        if subject_text and subject_text.strip():
                            break
                except Exception:
                    continue
            
            # Try multiple preview selectors
            preview_selectors = [
                '.y2',  # Standard preview
                '.y3',  # Alternative preview
                '.aYp',  # Preview text in list
                '.bog + span',  # Text after subject
                '.y6 + span',  # Following span
                '.akt',  # Snippet text
                '.ar9 .aYp'  # Preview in conversation list
            ]
            
            for preview_selector in preview_selectors:
                try:
                    preview_elem = email_element.locator(preview_selector).first
                    if await preview_elem.count() > 0:
                        preview_text = await preview_elem.inner_text()
                        if preview_text and preview_text.strip():
                            break
                except Exception:
                    continue
            
            # Extract codes from text
            email_text = f"{subject_text} {preview_text}"
            text_codes = self._extract_codes_from_text(email_text)
            
            # Add text-based codes
            for code in text_codes:
                codes.append({
                    'code': code,
                    'subject': subject_text.strip(),
                    'preview': preview_text.strip()[:100],
                    'source': 'gmail_text',
                    'extracted_at': datetime.now().isoformat()
                })
            
            # If OCR is available, try to extract codes from images
            if self.ocr_extractor:
                await self._extract_codes_from_email_images(page, email_element, subject_text, codes, processed_images)
            
            # If we found codes, try to open the email for more details
            if text_codes:
                await self._try_extract_from_full_email(page, email_element, codes[-len(text_codes):])
            
        except Exception as e:
            logger.debug(f"Error extracting from single email: {e}")
    
    async def _extract_codes_from_email_images(self, page: Page, email_element, subject_text: str, codes: List[Dict[str, Any]], processed_images: set) -> None:
        """Extract attendance codes from images in email using OCR."""
        try:
            # Click on email to open it
            original_url = page.url
            await email_element.click()
            await page.wait_for_timeout(2000)
            
            # Detect images in the opened email
            images = await self.ocr_extractor.detect_images_in_gmail(page)
            
            # Filter out already processed images
            new_images = []
            for img in images:
                img_url = img['src']
                if img_url not in processed_images:
                    new_images.append(img)
                    processed_images.add(img_url)
                else:
                    logger.debug(f"Skipping already processed image: {img_url[:100]}...")
            
            if new_images:
                logger.info(f"Found {len(new_images)} new images in email: {subject_text[:50]} (skipped {len(images) - len(new_images)} duplicates)")
                
                # Extract codes from new images only
                ocr_method = os.getenv("OCR_METHOD", "auto")
                image_codes = await self.ocr_extractor.extract_codes_from_images(new_images, ocr_method, page)
                
                # Add OCR codes to results
                for code_info in image_codes:
                    codes.append({
                        'code': code_info['code'],
                        'subject': subject_text.strip(),
                        'course': self._extract_course_code(subject_text),
                        'source': 'gmail_ocr',
                        'method': code_info.get('method', 'unknown'),
                        'image_url': code_info.get('image_url', ''),
                        'confidence': code_info.get('confidence', 'medium'),
                        'extracted_at': datetime.now().isoformat()
                    })
                
                logger.info(f"Extracted {len(image_codes)} codes from {len(new_images)} new images via OCR")
                
                # If no codes found via OCR, create GitHub issue as fallback
                if not image_codes and os.getenv("GITHUB_TOKEN"):
                    course_code = self._extract_course_code_from_subject(subject_text)
                    issue_url = await self.ocr_extractor.create_github_issue(new_images, course_code)
                    if issue_url:
                        logger.info(f"Created GitHub issue for manual processing: {issue_url}")
            else:
                logger.debug(f"All images in email already processed: {subject_text[:50]}")
            
            # Navigate back to email list
            if page.url != original_url:
                await self._ensure_on_search(page)
                await page.wait_for_timeout(500)
                
        except Exception as e:
            logger.warning(f"Error extracting codes from email images: {e}")
            # Try to navigate back on error
            try:
                await self._ensure_on_search(page)
            except Exception:
                pass
    
    def _extract_course_code_from_subject(self, subject: str) -> Optional[str]:
        """Extract course code from email subject."""
        # Look for patterns like FIT1047, BUS2020, etc.
        course_pattern = r'\b([A-Z]{3}\d{4})\b'
        match = re.search(course_pattern, subject.upper())
        return match.group(1) if match else None
    
    async def _try_extract_from_full_email(self, page: Page, email_element, recent_codes: List[Dict[str, str]]) -> None:
        """Try to extract more details by opening the full email."""
        try:
            # Click on email to open it
            await email_element.click()
            await page.wait_for_timeout(2000)
            
            # Try to get full email content
            content_selectors = [
                '[role="main"] [data-message-id] .ii.gt',  # Gmail message body
                '.adn.ads .ii.gt',  # Alternative message body
                '[data-message-id] div[dir="ltr"]',  # Message content
            ]
            
            full_content = ""
            for selector in content_selectors:
                try:
                    content_elem = page.locator(selector).first
                    if await content_elem.count() > 0:
                        full_content = await content_elem.inner_text()
                        break
                except Exception:
                    continue
            
            if full_content:
                # Extract additional details
                for code_info in recent_codes:
                    # Look for slot/session information
                    code = code_info['code']
                    slot_patterns = [
                        rf'(?:workshop|tutorial|practical|lab|session)\s*(\d+).*?{code}',
                        rf'{code}.*?(?:workshop|tutorial|practical|lab|session)\s*(\d+)',
                        rf'(?:week|wk)\s*(\d+).*?{code}',
                        rf'{code}.*?(?:week|wk)\s*(\d+)',
                    ]
                    
                    for pattern in slot_patterns:
                        match = re.search(pattern, full_content, re.IGNORECASE)
                        if match:
                            slot_num = match.group(1)
                            code_info['slot'] = f"Workshop {slot_num}"
                            break
                    
                    # Look for date information
                    date_patterns = [
                        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                        r'(\d{4}-\d{2}-\d{2})',
                    ]
                    
                    for pattern in date_patterns:
                        match = re.search(pattern, full_content)
                        if match:
                            code_info['date'] = match.group(1)
                            break
            
            # Go back to email list
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(1000)
            
        except Exception as e:
            logger.debug(f"Error extracting from full email: {e}")
    
    def _extract_codes_from_text(self, text: str) -> List[str]:
        """Extract attendance codes from text using regex patterns."""
        codes = []
        
        for pattern in self.codes_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # Validate code format
                if isinstance(match, tuple):
                    match = match[0]
                
                code = match.strip().upper()
                if self._is_valid_attendance_code(code):
                    codes.append(code)
        
        return list(set(codes))  # Remove duplicates
    
    def _is_valid_attendance_code(self, code: str) -> bool:
        """Validate if a string looks like an attendance code."""
        # Basic validation rules
        if len(code) < 4 or len(code) > 8:
            return False
        
        # Should contain letters and/or numbers
        if not re.match(r'^[A-Z0-9]+$', code):
            return False
        
        # Should have at least one letter and one number (common pattern)
        has_letter = any(c.isalpha() for c in code)
        has_number = any(c.isdigit() for c in code)
        
        # Skip common false positives
        false_positives = {
            'HTTP', 'HTTPS', 'HTML', 'CSS', 'JSON', 'XML',
            'USER', 'PASS', 'LOGIN', 'AUTH', 'TEST', 'DEMO',
            'ADMIN', 'ROOT', 'NULL', 'TRUE', 'FALSE'
        }
        
        if code in false_positives:
            return False
        # Reject course codes like FIT1043
        if re.match(r'^[A-Z]{3}\d{4}$', code):
            return False

        return has_letter and has_number
    
    def format_codes_for_submit(self, gmail_codes: List[Dict[str, str]]) -> List[Dict[str, Optional[str]]]:
        """Format Gmail-extracted codes for the submit module."""
        formatted_codes = []
        
        for code_info in gmail_codes:
            formatted_code = {
                'code': code_info['code'],
                'slot': code_info.get('slot'),
                'date': code_info.get('date'),
                'source': 'gmail',
                'subject': code_info.get('subject', ''),
            }
            formatted_codes.append(formatted_code)
        
        return formatted_codes

async def get_codes_from_gmail(browser_name: str = "chromium",
                              channel: str = "chrome", 
                              headless: bool = True,
                              storage_state: str = "storage_state.json",
                              search_days: int = 7,
                              search_query: str = None,
                              week_number: str = None,
                              target_email: str = None) -> List[Dict[str, Optional[str]]]:
    """
    Main function to extract attendance codes from Gmail.
    
    Args:
        browser_name: Browser engine to use
        channel: Browser channel
        headless: Run in headless mode
        storage_state: Path to storage state file
        search_days: Days to search back
        search_query: Custom search query
        week_number: Week number to search for
        target_email: Email address to use for Gmail login
        
    Returns:
        List of formatted attendance codes
    """
    
    extractor = GmailCodeExtractor()
    
    async with async_playwright() as p:
        # Launch browser
        browser_type = getattr(p, browser_name)
        launch_kwargs = {"headless": headless}
        
        if browser_name == 'chromium' and channel:
            launch_kwargs["channel"] = channel
        
        try:
            browser = await browser_type.launch(**launch_kwargs)
        except Exception as e:
            logger.warning(f"Failed to launch with channel '{channel}': {e}. Falling back to default.")
            launch_kwargs.pop('channel', None)
            browser = await browser_type.launch(**launch_kwargs)
        
        # Create context with existing session
        context_kwargs = {}
        if os.path.exists(storage_state):
            context_kwargs["storage_state"] = storage_state
        
        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()
        
        try:
            # Extract codes from Gmail
            gmail_codes = await extractor.extract_codes_from_gmail(
                page=page,
                storage_state=storage_state,
                search_days=search_days,
                search_query=search_query,
                week_number=week_number,
                target_email=target_email
            )
            
            # Format for submit module
            formatted_codes = extractor.format_codes_for_submit(gmail_codes)
            
            return formatted_codes
            
        finally:
            await browser.close()

def _save_email_to_env(email: str) -> None:
    """Save email to .env file for future use"""
    try:
        env_file = os.getenv('ENV_FILE', '.env')
        
        # Read existing .env content
        env_lines = []
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                env_lines = f.readlines()
        
        # Check if SCHOOL_EMAIL already exists
        email_exists = False
        for i, line in enumerate(env_lines):
            if line.strip().startswith('SCHOOL_EMAIL='):
                env_lines[i] = f'SCHOOL_EMAIL="{email}"\n'
                email_exists = True
                break
        
        # If SCHOOL_EMAIL doesn't exist, add it
        if not email_exists:
            env_lines.append(f'\n# School email for Gmail integration\n')
            env_lines.append(f'SCHOOL_EMAIL="{email}"\n')
        
        # Write back to .env file
        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(env_lines)
        
        print(f"💾 Email saved to {env_file} for future use")
        
    except Exception as e:
        logger.warning(f"Failed to save email to .env file: {e}")


def main():
    """Test the Gmail code extraction."""
    load_env(os.getenv('ENV_FILE', '.env'))
    
    import argparse
    parser = argparse.ArgumentParser(description="Extract attendance codes from Gmail")
    parser.add_argument("--browser", default="chromium", choices=["chromium", "firefox", "webkit"])
    parser.add_argument("--channel", default="chrome", help="Browser channel")
    parser.add_argument("--headed", action="store_true", help="Run with browser UI")
    parser.add_argument("--days", type=int, default=7, help="Days to search back")
    parser.add_argument("--query", help="Custom search query")
    parser.add_argument("--storage-state", default="storage_state.json", help="Storage state file")
    parser.add_argument("--email", help="Email address to use for Gmail login")
    parser.add_argument("--week", help="Week number to search for")
    
    args = parser.parse_args()
    
    # Interactive email input if not provided
    target_email = args.email
    if not target_email:
        target_email = os.getenv("SCHOOL_EMAIL")  # Check if email is already saved
        
    if not target_email:
        try:
            target_email = input("Enter your school email address (preferably ending with .edu): ").strip()
            if not target_email:
                print("❌ No email address provided")
                return
            
            # Validate email format
            if '@' not in target_email:
                print("❌ Invalid email format")
                return
            
            # Save to .env file for future use
            _save_email_to_env(target_email)
            print(f"✅ Using email: {target_email}")
            
        except KeyboardInterrupt:
            print("\n❌ User cancelled")
            return
        except Exception as e:
            print(f"❌ Input error: {e}")
            return
    
    async def run_extraction():
        codes = await get_codes_from_gmail(
            browser_name=args.browser,
            channel=args.channel,
            headless=not args.headed,
            storage_state=args.storage_state,
            search_days=args.days,
            search_query=args.query,
            week_number=args.week,
            target_email=target_email
        )
        
        if codes:
            print(f"\n📧 Found {len(codes)} attendance codes from Gmail:")
            for code in codes:
                print(f"  Code: {code['code']}")
                if code.get('slot'):
                    print(f"    Slot: {code['slot']}")
                if code.get('date'):
                    print(f"    Date: {code['date']}")
                if code.get('subject'):
                    print(f"    Subject: {code['subject'][:50]}...")
                print()
        else:
            print("❌ No attendance codes found in Gmail")
    
    asyncio.run(run_extraction())

if __name__ == "__main__":
    main()
