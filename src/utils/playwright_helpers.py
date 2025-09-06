from typing import List

from playwright.async_api import Page


async def fill_first_match(page: Page, selectors: List[str], value: str) -> bool:
    """Try to fill the first visible element matching any selector with value."""
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
    """Try to click the first visible element matching any selector."""
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
    """Attempt switching to verification code option in MFA flows."""
    candidates = [
        'text=/enter code/i',
        'text=/use code/i',
        'text=/use a code/i',
        'text=/Use verification code/i',
        'text=/Enter a verification code/i',
        'text=/verification code/i',
        'text=/Verify with something else/i',
        'text=/Enter a code/i',
        'text=/Google Authenticator|Authenticator app/i',
        'text=/Okta Verify/i',
    ]
    await click_first_match(page, candidates)

