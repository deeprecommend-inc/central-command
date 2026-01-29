"""
Browser Worker - Single browser session with proxy and UA
"""
import asyncio
from typing import Optional, Any
from dataclasses import dataclass
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger

from .proxy_manager import ProxyConfig
from .ua_manager import BrowserProfile


@dataclass
class WorkerResult:
    """Result from browser worker task"""

    success: bool
    data: Any = None
    error: Optional[str] = None
    screenshot_path: Optional[str] = None


class BrowserWorker:
    """Single browser worker with proxy and user agent configuration"""

    def __init__(
        self,
        worker_id: str,
        proxy: Optional[ProxyConfig] = None,
        profile: Optional[BrowserProfile] = None,
        headless: bool = True,
    ):
        self.worker_id = worker_id
        self.proxy = proxy
        self.profile = profile
        self.headless = headless
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._playwright = None

    async def start(self) -> None:
        """Initialize browser with proxy and profile"""
        logger.info(f"Worker {self.worker_id}: Starting browser")

        self._playwright = await async_playwright().start()

        # Browser launch options
        launch_options = {"headless": self.headless}

        # Add proxy if configured
        if self.proxy:
            launch_options["proxy"] = {"server": self.proxy.get_url()}
            logger.debug(f"Worker {self.worker_id}: Using proxy {self.proxy.country}")

        self._browser = await self._playwright.chromium.launch(**launch_options)

        # Context options from profile
        context_options = {}
        if self.profile:
            context_options = self.profile.to_playwright_context()
            logger.debug(f"Worker {self.worker_id}: Using UA {self.profile.user_agent[:50]}...")

        self._context = await self._browser.new_context(**context_options)
        self._page = await self._context.new_page()

    async def stop(self) -> None:
        """Clean up browser resources"""
        logger.info(f"Worker {self.worker_id}: Stopping browser")

        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> WorkerResult:
        """Navigate to URL"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started")

        try:
            logger.debug(f"Worker {self.worker_id}: Navigating to {url}")
            response = await self._page.goto(url, wait_until=wait_until)
            return WorkerResult(
                success=True,
                data={"status": response.status if response else None, "url": self._page.url},
            )
        except Exception as e:
            logger.error(f"Worker {self.worker_id}: Navigation error: {e}")
            return WorkerResult(success=False, error=str(e))

    async def get_content(self) -> WorkerResult:
        """Get page content"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started")

        try:
            content = await self._page.content()
            title = await self._page.title()
            return WorkerResult(success=True, data={"title": title, "content": content})
        except Exception as e:
            return WorkerResult(success=False, error=str(e))

    async def screenshot(self, path: str) -> WorkerResult:
        """Take screenshot"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started")

        try:
            await self._page.screenshot(path=path, full_page=True)
            return WorkerResult(success=True, screenshot_path=path)
        except Exception as e:
            return WorkerResult(success=False, error=str(e))

    async def click(self, selector: str) -> WorkerResult:
        """Click element"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started")

        try:
            await self._page.click(selector)
            return WorkerResult(success=True)
        except Exception as e:
            return WorkerResult(success=False, error=str(e))

    async def fill(self, selector: str, value: str) -> WorkerResult:
        """Fill input field"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started")

        try:
            await self._page.fill(selector, value)
            return WorkerResult(success=True)
        except Exception as e:
            return WorkerResult(success=False, error=str(e))

    async def evaluate(self, script: str) -> WorkerResult:
        """Evaluate JavaScript"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started")

        try:
            result = await self._page.evaluate(script)
            return WorkerResult(success=True, data=result)
        except Exception as e:
            return WorkerResult(success=False, error=str(e))

    async def wait_for_selector(
        self, selector: str, timeout: int = 30000
    ) -> WorkerResult:
        """Wait for selector to appear"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started")

        try:
            await self._page.wait_for_selector(selector, timeout=timeout)
            return WorkerResult(success=True)
        except Exception as e:
            return WorkerResult(success=False, error=str(e))

    @property
    def page(self) -> Optional[Page]:
        """Access underlying page object"""
        return self._page
