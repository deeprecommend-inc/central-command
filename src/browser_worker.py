"""
Browser Worker - Single browser session with proxy and UA
"""
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass
from enum import Enum
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeout
from playwright._impl._errors import TargetClosedError
from loguru import logger

from .proxy_manager import ProxyConfig
from .ua_manager import BrowserProfile


class ErrorType(Enum):
    """Error type classification for better handling"""
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    PROXY = "proxy"
    ELEMENT_NOT_FOUND = "element_not_found"
    BROWSER_CLOSED = "browser_closed"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


@dataclass
class WorkerResult:
    """Result from browser worker task"""

    success: bool
    data: Any = None
    error: Optional[str] = None
    error_type: Optional[ErrorType] = None
    screenshot_path: Optional[str] = None

    @property
    def is_retryable(self) -> bool:
        """Check if error is retryable"""
        if self.success:
            return False
        retryable_types = {ErrorType.TIMEOUT, ErrorType.CONNECTION, ErrorType.PROXY}
        return self.error_type in retryable_types


def _classify_error(error: Exception) -> tuple[ErrorType, str]:
    """Classify error type and return formatted message"""
    error_str = str(error).lower()

    # Timeout errors
    if isinstance(error, (asyncio.TimeoutError, PlaywrightTimeout)):
        return ErrorType.TIMEOUT, f"Timeout: {error}"

    # Connection errors
    if isinstance(error, (ConnectionError, ConnectionRefusedError, ConnectionResetError)):
        return ErrorType.CONNECTION, f"Connection error: {error}"

    # Browser closed errors
    if isinstance(error, TargetClosedError):
        return ErrorType.BROWSER_CLOSED, f"Browser closed: {error}"

    # Proxy-related errors (string matching)
    proxy_indicators = ["proxy", "tunnel", "econnrefused", "econnreset", "etimedout", "502", "503", "407"]
    if any(indicator in error_str for indicator in proxy_indicators):
        return ErrorType.PROXY, f"Proxy error: {error}"

    # Element not found
    element_indicators = ["selector", "element", "not found", "no element", "waiting for"]
    if any(indicator in error_str for indicator in element_indicators):
        return ErrorType.ELEMENT_NOT_FOUND, f"Element not found: {error}"

    # Connection related (string matching fallback)
    conn_indicators = ["network", "connection", "socket", "refused", "reset", "unreachable"]
    if any(indicator in error_str for indicator in conn_indicators):
        return ErrorType.CONNECTION, f"Connection error: {error}"

    return ErrorType.UNKNOWN, str(error)


def _validate_url(url: str) -> Optional[str]:
    """Validate URL format. Returns error message if invalid, None if valid."""
    if not url:
        return "URL cannot be empty"
    if not url.startswith(("http://", "https://")):
        return "URL must start with http:// or https://"
    return None


def _validate_path(path: str) -> Optional[str]:
    """Validate file path for security (cross-platform). Returns error message if invalid."""
    if not path:
        return "Path cannot be empty"

    # Normalize path to detect traversal
    normalized = Path(path).resolve()

    # Check for directory traversal (.. in original path)
    if ".." in path:
        return "Path traversal not allowed"

    # Define allowed directories (cross-platform)
    allowed_dirs = [
        Path(tempfile.gettempdir()).resolve(),  # System temp dir (Linux: /tmp, Windows: %TEMP%)
        Path.cwd().resolve(),
    ]

    # Check if path is within allowed directories
    for allowed in allowed_dirs:
        try:
            normalized.relative_to(allowed)
            return None  # Path is valid
        except ValueError:
            continue

    return f"Path must be within allowed directories: {[str(d) for d in allowed_dirs]}"


class BrowserWorker:
    """Single browser worker with proxy and user agent configuration"""

    DEFAULT_TIMEOUT = 30000  # 30 seconds

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

        try:
            if self._page:
                await self._page.close()
        except Exception as e:
            logger.debug(f"Worker {self.worker_id}: Page close error (ignored): {e}")

        try:
            if self._context:
                await self._context.close()
        except Exception as e:
            logger.debug(f"Worker {self.worker_id}: Context close error (ignored): {e}")

        try:
            if self._browser:
                await self._browser.close()
        except Exception as e:
            logger.debug(f"Worker {self.worker_id}: Browser close error (ignored): {e}")

        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug(f"Worker {self.worker_id}: Playwright stop error (ignored): {e}")

    async def navigate(self, url: str, wait_until: str = "domcontentloaded", timeout: int = DEFAULT_TIMEOUT) -> WorkerResult:
        """Navigate to URL with proper error handling"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        # Validate URL
        url_error = _validate_url(url)
        if url_error:
            return WorkerResult(success=False, error=url_error, error_type=ErrorType.VALIDATION)

        try:
            logger.debug(f"Worker {self.worker_id}: Navigating to {url}")
            response = await self._page.goto(url, wait_until=wait_until, timeout=timeout)

            # Check for HTTP error status codes
            if response and response.status >= 400:
                error_msg = f"HTTP {response.status}"
                if response.status in (502, 503, 504):
                    return WorkerResult(success=False, error=error_msg, error_type=ErrorType.PROXY)
                elif response.status == 407:
                    return WorkerResult(success=False, error="Proxy authentication required", error_type=ErrorType.PROXY)
                else:
                    return WorkerResult(success=False, error=error_msg, error_type=ErrorType.CONNECTION)

            return WorkerResult(
                success=True,
                data={"status": response.status if response else None, "url": self._page.url},
            )

        except PlaywrightTimeout as e:
            logger.warning(f"Worker {self.worker_id}: Navigation timeout: {url}")
            return WorkerResult(success=False, error=f"Navigation timeout: {e}", error_type=ErrorType.TIMEOUT)

        except TargetClosedError as e:
            logger.error(f"Worker {self.worker_id}: Browser closed during navigation")
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            logger.error(f"Worker {self.worker_id}: Navigation error ({error_type.value}): {e}")
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def get_content(self) -> WorkerResult:
        """Get page content"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        try:
            content = await self._page.content()
            title = await self._page.title()
            return WorkerResult(success=True, data={"title": title, "content": content})

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Timeout getting content: {e}", error_type=ErrorType.TIMEOUT)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def screenshot(self, path: str) -> WorkerResult:
        """Take screenshot with path validation"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        # Validate path for security
        path_error = _validate_path(path)
        if path_error:
            return WorkerResult(success=False, error=path_error, error_type=ErrorType.VALIDATION)

        try:
            await self._page.screenshot(path=path, full_page=True)
            return WorkerResult(success=True, screenshot_path=path)

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Screenshot timeout: {e}", error_type=ErrorType.TIMEOUT)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except OSError as e:
            return WorkerResult(success=False, error=f"File system error: {e}", error_type=ErrorType.VALIDATION)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def click(self, selector: str, timeout: int = DEFAULT_TIMEOUT) -> WorkerResult:
        """Click element with proper error handling"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        if not selector:
            return WorkerResult(success=False, error="Selector cannot be empty", error_type=ErrorType.VALIDATION)

        try:
            await self._page.click(selector, timeout=timeout)
            return WorkerResult(success=True)

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Click timeout - element not found: {selector}", error_type=ErrorType.ELEMENT_NOT_FOUND)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def fill(self, selector: str, value: str, timeout: int = DEFAULT_TIMEOUT) -> WorkerResult:
        """Fill input field with proper error handling"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        if not selector:
            return WorkerResult(success=False, error="Selector cannot be empty", error_type=ErrorType.VALIDATION)

        try:
            await self._page.fill(selector, value, timeout=timeout)
            return WorkerResult(success=True)

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Fill timeout - element not found: {selector}", error_type=ErrorType.ELEMENT_NOT_FOUND)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def evaluate(self, script: str) -> WorkerResult:
        """Evaluate JavaScript with proper error handling"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        if not script:
            return WorkerResult(success=False, error="Script cannot be empty", error_type=ErrorType.VALIDATION)

        try:
            result = await self._page.evaluate(script)
            return WorkerResult(success=True, data=result)

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Script timeout: {e}", error_type=ErrorType.TIMEOUT)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def wait_for_selector(self, selector: str, timeout: int = DEFAULT_TIMEOUT) -> WorkerResult:
        """Wait for selector to appear with proper error handling"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        if not selector:
            return WorkerResult(success=False, error="Selector cannot be empty", error_type=ErrorType.VALIDATION)

        try:
            await self._page.wait_for_selector(selector, timeout=timeout)
            return WorkerResult(success=True)

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Selector not found within timeout: {selector}", error_type=ErrorType.ELEMENT_NOT_FOUND)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def scroll(self, direction: str = "down", amount: int = 500) -> WorkerResult:
        """Scroll the page"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        if direction not in ("up", "down", "left", "right"):
            return WorkerResult(success=False, error="Invalid direction. Use: up, down, left, right", error_type=ErrorType.VALIDATION)

        try:
            if direction == "down":
                await self._page.evaluate(f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await self._page.evaluate(f"window.scrollBy(0, -{amount})")
            elif direction == "right":
                await self._page.evaluate(f"window.scrollBy({amount}, 0)")
            elif direction == "left":
                await self._page.evaluate(f"window.scrollBy(-{amount}, 0)")
            return WorkerResult(success=True, data={"direction": direction, "amount": amount})

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Scroll timeout: {e}", error_type=ErrorType.TIMEOUT)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def hover(self, selector: str, timeout: int = DEFAULT_TIMEOUT) -> WorkerResult:
        """Hover over element"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        if not selector:
            return WorkerResult(success=False, error="Selector cannot be empty", error_type=ErrorType.VALIDATION)

        try:
            await self._page.hover(selector, timeout=timeout)
            return WorkerResult(success=True)

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Hover timeout - element not found: {selector}", error_type=ErrorType.ELEMENT_NOT_FOUND)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def select(self, selector: str, value: str, timeout: int = DEFAULT_TIMEOUT) -> WorkerResult:
        """Select option from dropdown"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        if not selector:
            return WorkerResult(success=False, error="Selector cannot be empty", error_type=ErrorType.VALIDATION)

        try:
            await self._page.select_option(selector, value, timeout=timeout)
            return WorkerResult(success=True, data={"selected": value})

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Select timeout - element not found: {selector}", error_type=ErrorType.ELEMENT_NOT_FOUND)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def get_text(self, selector: str, timeout: int = DEFAULT_TIMEOUT) -> WorkerResult:
        """Get text content of element"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        if not selector:
            return WorkerResult(success=False, error="Selector cannot be empty", error_type=ErrorType.VALIDATION)

        try:
            element = await self._page.wait_for_selector(selector, timeout=timeout)
            if element:
                text = await element.text_content()
                return WorkerResult(success=True, data={"text": text})
            return WorkerResult(success=False, error=f"Element not found: {selector}", error_type=ErrorType.ELEMENT_NOT_FOUND)

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Get text timeout - element not found: {selector}", error_type=ErrorType.ELEMENT_NOT_FOUND)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def wait_for_navigation(self, timeout: int = DEFAULT_TIMEOUT) -> WorkerResult:
        """Wait for navigation to complete"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=timeout)
            return WorkerResult(success=True, data={"url": self._page.url})

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Navigation timeout: {e}", error_type=ErrorType.TIMEOUT)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def type(self, selector: str, text: str, delay: int = 50, timeout: int = DEFAULT_TIMEOUT) -> WorkerResult:
        """Type text into element with delay between keystrokes"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        if not selector:
            return WorkerResult(success=False, error="Selector cannot be empty", error_type=ErrorType.VALIDATION)

        try:
            await self._page.type(selector, text, delay=delay, timeout=timeout)
            return WorkerResult(success=True)

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Type timeout - element not found: {selector}", error_type=ErrorType.ELEMENT_NOT_FOUND)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    async def press(self, key: str) -> WorkerResult:
        """Press a keyboard key"""
        if not self._page:
            return WorkerResult(success=False, error="Browser not started", error_type=ErrorType.VALIDATION)

        if not key:
            return WorkerResult(success=False, error="Key cannot be empty", error_type=ErrorType.VALIDATION)

        try:
            await self._page.keyboard.press(key)
            return WorkerResult(success=True, data={"key": key})

        except PlaywrightTimeout as e:
            return WorkerResult(success=False, error=f"Key press timeout: {e}", error_type=ErrorType.TIMEOUT)

        except TargetClosedError as e:
            return WorkerResult(success=False, error=f"Browser closed: {e}", error_type=ErrorType.BROWSER_CLOSED)

        except Exception as e:
            error_type, error_msg = _classify_error(e)
            return WorkerResult(success=False, error=error_msg, error_type=error_type)

    @property
    def page(self) -> Optional[Page]:
        """Access underlying page object"""
        return self._page
