from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Callable, Awaitable, TYPE_CHECKING, Any

from playwright.async_api import async_playwright

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Playwright, Page
else:
    Browser = BrowserContext = Playwright = Page = Any

from utils.logger import logger


@dataclass
class BrowserConfig:
    """Configuration payload for launching a Playwright browser session."""

    name: str = "chromium"
    channel: Optional[str] = None
    headed: bool = False
    storage_state: Optional[str] = None
    user_data_dir: Optional[str] = None
    timeout_ms: int = 60000


class BrowserLaunchError(RuntimeError):
    """Raised when Playwright cannot launch the requested browser."""


class BrowserController:
    """Async context manager that owns the Playwright lifecycle.

    The controller abstracts browser launch differences (persistent vs regular
    context, channel fallback, storage state loading) so call sites can focus on
    higher level workflows.
    """

    def __init__(self, config: BrowserConfig):
        self._config = config
        self._playwright_cm = async_playwright()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> "BrowserController":
        self._playwright = await self._playwright_cm.__aenter__()
        browser_type = self._resolve_browser_type()
        launch_headless = not self._config.headed

        if self._config.user_data_dir:
            await self._launch_persistent(browser_type, launch_headless)
        else:
            await self._launch_regular(browser_type, launch_headless)

        if not self._context:
            raise BrowserLaunchError("Failed to create Playwright context")

        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
        finally:
            await self._playwright_cm.__aexit__(exc_type, exc, tb)

    @property
    def context(self) -> BrowserContext:
        assert self._context is not None, "BrowserContext not available"
        return self._context

    @property
    def browser(self) -> Optional[Browser]:
        return self._browser

    def _resolve_browser_type(self):
        assert self._playwright is not None
        name = (self._config.name or "chromium").lower()
        if name == "webkit":
            return self._playwright.webkit
        if name == "firefox":
            return self._playwright.firefox
        return self._playwright.chromium

    async def _launch_persistent(self, browser_type, launch_headless: bool) -> None:
        channel = self._config.channel if self._config.name == "chromium" else None
        try:
            self._context = await browser_type.launch_persistent_context(
                self._config.user_data_dir,
                headless=launch_headless,
                channel=channel,
            )
        except Exception as exc:
            if channel:
                logger.warning(f"Failed to launch persistent browser with channel '{channel}': {exc}")
                self._context = await browser_type.launch_persistent_context(
                    self._config.user_data_dir,
                    headless=launch_headless,
                )
            else:
                raise

    async def _launch_regular(self, browser_type, launch_headless: bool) -> None:
        launch_kwargs = {"headless": launch_headless}
        channel_requested = False
        if self._config.channel and self._config.name == "chromium":
            launch_kwargs["channel"] = self._config.channel
            channel_requested = True

        try:
            self._browser = await browser_type.launch(**launch_kwargs)
        except Exception as exc:
            if channel_requested:
                logger.warning(f"Failed to launch channel '{self._config.channel}': {exc}. Retrying without channel.")
                launch_kwargs.pop("channel", None)
                self._browser = await browser_type.launch(**launch_kwargs)
            else:
                raise
        else:
            if channel_requested:
                logger.info(f"Successfully launched system browser ({self._config.channel})")

        storage_state = self._config.storage_state
        context_kwargs = {}
        if storage_state:
            context_kwargs["storage_state"] = storage_state
        self._context = await self._browser.new_context(**context_kwargs)

    async def with_new_page(self, func: Callable[[Page], Awaitable[None]]) -> None:
        """Utility helper for workflows that need an isolated page."""
        page = await self.context.new_page()
        try:
            await func(page)
        finally:
            await page.close()
