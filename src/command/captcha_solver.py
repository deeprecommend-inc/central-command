"""
CAPTCHA Solver - Automatic CAPTCHA detection and solving

Features:
- CAPTCHA detection (reCAPTCHA, hCaptcha, image CAPTCHA)
- Integration with solving services (2Captcha, Anti-Captcha)
- Automatic solving middleware
"""
from __future__ import annotations

import asyncio
import base64
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Callable
from loguru import logger


class CaptchaType(str, Enum):
    """Supported CAPTCHA types"""
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    IMAGE = "image"
    TEXT = "text"
    FUNCAPTCHA = "funcaptcha"
    TURNSTILE = "turnstile"
    UNKNOWN = "unknown"


@dataclass
class CaptchaInfo:
    """Detected CAPTCHA information"""
    captcha_type: CaptchaType
    site_key: Optional[str] = None
    page_url: str = ""
    data_s: Optional[str] = None  # reCAPTCHA data-s parameter
    enterprise: bool = False
    invisible: bool = False
    action: Optional[str] = None  # reCAPTCHA v3 action
    min_score: float = 0.3  # reCAPTCHA v3 minimum score
    image_data: Optional[bytes] = None  # For image CAPTCHA
    extra: dict = field(default_factory=dict)


@dataclass
class CaptchaSolution:
    """CAPTCHA solution result"""
    success: bool
    token: Optional[str] = None
    text: Optional[str] = None  # For image/text CAPTCHA
    error: Optional[str] = None
    cost: float = 0.0
    solve_time_ms: int = 0
    provider: str = ""


class CaptchaSolver(ABC):
    """Abstract base class for CAPTCHA solvers"""

    @abstractmethod
    async def solve(self, captcha: CaptchaInfo) -> CaptchaSolution:
        """Solve CAPTCHA"""
        pass

    @abstractmethod
    async def get_balance(self) -> float:
        """Get account balance"""
        pass

    @abstractmethod
    def supports(self, captcha_type: CaptchaType) -> bool:
        """Check if solver supports CAPTCHA type"""
        pass


class TwoCaptchaSolver(CaptchaSolver):
    """
    2Captcha.com solver integration.

    Supports:
    - reCAPTCHA v2/v3
    - hCaptcha
    - Image CAPTCHA
    - FunCaptcha
    - Turnstile

    Example:
        solver = TwoCaptchaSolver(api_key="your_api_key")
        solution = await solver.solve(captcha_info)
        if solution.success:
            print(f"Token: {solution.token}")
    """

    BASE_URL = "http://2captcha.com"

    def __init__(
        self,
        api_key: str,
        soft_id: Optional[str] = None,
        callback_url: Optional[str] = None,
        poll_interval: float = 5.0,
        timeout: float = 120.0,
    ):
        self._api_key = api_key
        self._soft_id = soft_id
        self._callback_url = callback_url
        self._poll_interval = poll_interval
        self._timeout = timeout

    def supports(self, captcha_type: CaptchaType) -> bool:
        return captcha_type in (
            CaptchaType.RECAPTCHA_V2,
            CaptchaType.RECAPTCHA_V3,
            CaptchaType.HCAPTCHA,
            CaptchaType.IMAGE,
            CaptchaType.TEXT,
            CaptchaType.FUNCAPTCHA,
            CaptchaType.TURNSTILE,
        )

    async def solve(self, captcha: CaptchaInfo) -> CaptchaSolution:
        """Solve CAPTCHA using 2Captcha"""
        import time
        import aiohttp

        start_time = time.time()

        try:
            # Submit CAPTCHA
            task_id = await self._submit(captcha)
            if not task_id:
                return CaptchaSolution(
                    success=False,
                    error="Failed to submit CAPTCHA",
                    provider="2captcha",
                )

            # Poll for result
            result = await self._poll_result(task_id)

            solve_time = int((time.time() - start_time) * 1000)

            if result:
                return CaptchaSolution(
                    success=True,
                    token=result if captcha.captcha_type != CaptchaType.IMAGE else None,
                    text=result if captcha.captcha_type == CaptchaType.IMAGE else None,
                    solve_time_ms=solve_time,
                    provider="2captcha",
                )
            else:
                return CaptchaSolution(
                    success=False,
                    error="Timeout waiting for solution",
                    solve_time_ms=solve_time,
                    provider="2captcha",
                )

        except Exception as e:
            logger.error(f"2Captcha solve error: {e}")
            return CaptchaSolution(
                success=False,
                error=str(e),
                provider="2captcha",
            )

    async def _submit(self, captcha: CaptchaInfo) -> Optional[str]:
        """Submit CAPTCHA to 2Captcha"""
        import aiohttp

        params = {
            "key": self._api_key,
            "json": 1,
        }

        if self._soft_id:
            params["soft_id"] = self._soft_id

        if captcha.captcha_type == CaptchaType.RECAPTCHA_V2:
            params["method"] = "userrecaptcha"
            params["googlekey"] = captcha.site_key
            params["pageurl"] = captcha.page_url
            if captcha.invisible:
                params["invisible"] = 1
            if captcha.data_s:
                params["data-s"] = captcha.data_s
            if captcha.enterprise:
                params["enterprise"] = 1

        elif captcha.captcha_type == CaptchaType.RECAPTCHA_V3:
            params["method"] = "userrecaptcha"
            params["version"] = "v3"
            params["googlekey"] = captcha.site_key
            params["pageurl"] = captcha.page_url
            params["action"] = captcha.action or "verify"
            params["min_score"] = captcha.min_score
            if captcha.enterprise:
                params["enterprise"] = 1

        elif captcha.captcha_type == CaptchaType.HCAPTCHA:
            params["method"] = "hcaptcha"
            params["sitekey"] = captcha.site_key
            params["pageurl"] = captcha.page_url

        elif captcha.captcha_type == CaptchaType.TURNSTILE:
            params["method"] = "turnstile"
            params["sitekey"] = captcha.site_key
            params["pageurl"] = captcha.page_url

        elif captcha.captcha_type == CaptchaType.FUNCAPTCHA:
            params["method"] = "funcaptcha"
            params["publickey"] = captcha.site_key
            params["pageurl"] = captcha.page_url

        elif captcha.captcha_type in (CaptchaType.IMAGE, CaptchaType.TEXT):
            params["method"] = "base64"
            if captcha.image_data:
                params["body"] = base64.b64encode(captcha.image_data).decode()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.BASE_URL}/in.php",
                    data=params,
                ) as resp:
                    data = await resp.json()

                    if data.get("status") == 1:
                        return data.get("request")
                    else:
                        logger.error(f"2Captcha submit error: {data.get('request')}")
                        return None

        except Exception as e:
            logger.error(f"2Captcha submit exception: {e}")
            return None

    async def _poll_result(self, task_id: str) -> Optional[str]:
        """Poll for CAPTCHA solution"""
        import aiohttp
        import time

        start_time = time.time()

        while time.time() - start_time < self._timeout:
            await asyncio.sleep(self._poll_interval)

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{self.BASE_URL}/res.php",
                        params={
                            "key": self._api_key,
                            "action": "get",
                            "id": task_id,
                            "json": 1,
                        },
                    ) as resp:
                        data = await resp.json()

                        if data.get("status") == 1:
                            return data.get("request")
                        elif data.get("request") == "CAPCHA_NOT_READY":
                            continue
                        else:
                            logger.error(f"2Captcha poll error: {data.get('request')}")
                            return None

            except Exception as e:
                logger.error(f"2Captcha poll exception: {e}")

        return None

    async def get_balance(self) -> float:
        """Get account balance"""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/res.php",
                    params={
                        "key": self._api_key,
                        "action": "getbalance",
                        "json": 1,
                    },
                ) as resp:
                    data = await resp.json()
                    if data.get("status") == 1:
                        return float(data.get("request", 0))
                    return 0.0
        except Exception as e:
            logger.error(f"2Captcha balance error: {e}")
            return 0.0


class AntiCaptchaSolver(CaptchaSolver):
    """
    Anti-Captcha.com solver integration.

    Similar API to 2Captcha but with different endpoints.
    """

    BASE_URL = "https://api.anti-captcha.com"

    def __init__(
        self,
        api_key: str,
        soft_id: Optional[int] = None,
        poll_interval: float = 5.0,
        timeout: float = 120.0,
    ):
        self._api_key = api_key
        self._soft_id = soft_id
        self._poll_interval = poll_interval
        self._timeout = timeout

    def supports(self, captcha_type: CaptchaType) -> bool:
        return captcha_type in (
            CaptchaType.RECAPTCHA_V2,
            CaptchaType.RECAPTCHA_V3,
            CaptchaType.HCAPTCHA,
            CaptchaType.IMAGE,
            CaptchaType.FUNCAPTCHA,
            CaptchaType.TURNSTILE,
        )

    async def solve(self, captcha: CaptchaInfo) -> CaptchaSolution:
        """Solve CAPTCHA using Anti-Captcha"""
        import time
        import aiohttp

        start_time = time.time()

        try:
            # Create task
            task_id = await self._create_task(captcha)
            if not task_id:
                return CaptchaSolution(
                    success=False,
                    error="Failed to create task",
                    provider="anti-captcha",
                )

            # Get result
            result = await self._get_result(task_id)

            solve_time = int((time.time() - start_time) * 1000)

            if result:
                return CaptchaSolution(
                    success=True,
                    token=result.get("token"),
                    text=result.get("text"),
                    solve_time_ms=solve_time,
                    provider="anti-captcha",
                )
            else:
                return CaptchaSolution(
                    success=False,
                    error="Timeout waiting for solution",
                    solve_time_ms=solve_time,
                    provider="anti-captcha",
                )

        except Exception as e:
            logger.error(f"Anti-Captcha solve error: {e}")
            return CaptchaSolution(
                success=False,
                error=str(e),
                provider="anti-captcha",
            )

    async def _create_task(self, captcha: CaptchaInfo) -> Optional[int]:
        """Create solving task"""
        import aiohttp

        task = {}

        if captcha.captcha_type == CaptchaType.RECAPTCHA_V2:
            task["type"] = "RecaptchaV2TaskProxyless"
            task["websiteURL"] = captcha.page_url
            task["websiteKey"] = captcha.site_key
            if captcha.invisible:
                task["isInvisible"] = True
            if captcha.enterprise:
                task["type"] = "RecaptchaV2EnterpriseTaskProxyless"

        elif captcha.captcha_type == CaptchaType.RECAPTCHA_V3:
            task["type"] = "RecaptchaV3TaskProxyless"
            task["websiteURL"] = captcha.page_url
            task["websiteKey"] = captcha.site_key
            task["minScore"] = captcha.min_score
            task["pageAction"] = captcha.action or "verify"
            if captcha.enterprise:
                task["isEnterprise"] = True

        elif captcha.captcha_type == CaptchaType.HCAPTCHA:
            task["type"] = "HCaptchaTaskProxyless"
            task["websiteURL"] = captcha.page_url
            task["websiteKey"] = captcha.site_key

        elif captcha.captcha_type == CaptchaType.TURNSTILE:
            task["type"] = "TurnstileTaskProxyless"
            task["websiteURL"] = captcha.page_url
            task["websiteKey"] = captcha.site_key

        elif captcha.captcha_type == CaptchaType.FUNCAPTCHA:
            task["type"] = "FunCaptchaTaskProxyless"
            task["websiteURL"] = captcha.page_url
            task["websitePublicKey"] = captcha.site_key

        elif captcha.captcha_type == CaptchaType.IMAGE:
            task["type"] = "ImageToTextTask"
            if captcha.image_data:
                task["body"] = base64.b64encode(captcha.image_data).decode()

        payload = {
            "clientKey": self._api_key,
            "task": task,
        }

        if self._soft_id:
            payload["softId"] = self._soft_id

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.BASE_URL}/createTask",
                    json=payload,
                ) as resp:
                    data = await resp.json()

                    if data.get("errorId") == 0:
                        return data.get("taskId")
                    else:
                        logger.error(f"Anti-Captcha create error: {data.get('errorDescription')}")
                        return None

        except Exception as e:
            logger.error(f"Anti-Captcha create exception: {e}")
            return None

    async def _get_result(self, task_id: int) -> Optional[dict]:
        """Get task result"""
        import aiohttp
        import time

        start_time = time.time()

        while time.time() - start_time < self._timeout:
            await asyncio.sleep(self._poll_interval)

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.BASE_URL}/getTaskResult",
                        json={
                            "clientKey": self._api_key,
                            "taskId": task_id,
                        },
                    ) as resp:
                        data = await resp.json()

                        if data.get("errorId") != 0:
                            logger.error(f"Anti-Captcha result error: {data.get('errorDescription')}")
                            return None

                        if data.get("status") == "ready":
                            solution = data.get("solution", {})
                            return {
                                "token": solution.get("gRecaptchaResponse") or solution.get("token"),
                                "text": solution.get("text"),
                            }

            except Exception as e:
                logger.error(f"Anti-Captcha result exception: {e}")

        return None

    async def get_balance(self) -> float:
        """Get account balance"""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.BASE_URL}/getBalance",
                    json={"clientKey": self._api_key},
                ) as resp:
                    data = await resp.json()
                    if data.get("errorId") == 0:
                        return float(data.get("balance", 0))
                    return 0.0
        except Exception as e:
            logger.error(f"Anti-Captcha balance error: {e}")
            return 0.0


class CaptchaDetector:
    """
    Detect CAPTCHA on web pages.

    Example:
        detector = CaptchaDetector()
        captcha = await detector.detect(page)
        if captcha:
            print(f"Found: {captcha.captcha_type}")
    """

    # reCAPTCHA v2 selectors
    RECAPTCHA_V2_SELECTORS = [
        "iframe[src*='recaptcha']",
        ".g-recaptcha",
        "#g-recaptcha",
        "[data-sitekey]",
    ]

    # reCAPTCHA v3 indicators
    RECAPTCHA_V3_PATTERNS = [
        r"grecaptcha\.execute",
        r"recaptcha/api.js\?.*render=",
    ]

    # hCaptcha selectors
    HCAPTCHA_SELECTORS = [
        "iframe[src*='hcaptcha']",
        ".h-captcha",
        "[data-hcaptcha-sitekey]",
    ]

    # Turnstile selectors
    TURNSTILE_SELECTORS = [
        "iframe[src*='challenges.cloudflare.com']",
        ".cf-turnstile",
    ]

    # Image CAPTCHA selectors
    IMAGE_CAPTCHA_SELECTORS = [
        "img[src*='captcha']",
        ".captcha-image",
        "[id*='captcha'] img",
        "canvas.captcha",
        "[data-captcha-image]",
        "img[alt*='captcha' i]",
        ".challenge-image",
    ]

    @staticmethod
    async def _query_selector(page, selector: str):
        """browser-use 0.11.8 compatible query_selector replacement"""
        elements = await page.get_elements_by_css_selector(selector)
        return elements[0] if elements else None

    async def detect(self, page) -> Optional[CaptchaInfo]:
        """
        Detect CAPTCHA on page.

        Args:
            page: browser-use Page object (CDP-based)

        Returns:
            CaptchaInfo if CAPTCHA found, None otherwise
        """
        page_url = await page.get_url()

        # Check reCAPTCHA v2
        captcha = await self._detect_recaptcha_v2(page, page_url)
        if captcha:
            return captcha

        # Check reCAPTCHA v3
        captcha = await self._detect_recaptcha_v3(page, page_url)
        if captcha:
            return captcha

        # Check hCaptcha
        captcha = await self._detect_hcaptcha(page, page_url)
        if captcha:
            return captcha

        # Check Turnstile
        captcha = await self._detect_turnstile(page, page_url)
        if captcha:
            return captcha

        # Check image CAPTCHA
        captcha = await self._detect_image_captcha(page, page_url)
        if captcha:
            return captcha

        return None

    async def _detect_recaptcha_v2(self, page, page_url: str) -> Optional[CaptchaInfo]:
        """Detect reCAPTCHA v2"""
        for selector in self.RECAPTCHA_V2_SELECTORS:
            try:
                element = await self._query_selector(page, selector)
                if element:
                    site_key = await self._get_recaptcha_sitekey(page, element)
                    if site_key:
                        # Check if invisible
                        invisible = await page.evaluate("""
                            () => {
                                const el = document.querySelector('.g-recaptcha');
                                return el && el.getAttribute('data-size') === 'invisible';
                            }
                        """)

                        return CaptchaInfo(
                            captcha_type=CaptchaType.RECAPTCHA_V2,
                            site_key=site_key,
                            page_url=page_url,
                            invisible=invisible or False,
                        )
            except Exception:
                continue

        return None

    async def _detect_recaptcha_v3(self, page, page_url: str) -> Optional[CaptchaInfo]:
        """Detect reCAPTCHA v3"""
        try:
            html = await page.evaluate("() => document.documentElement.outerHTML")

            for pattern in self.RECAPTCHA_V3_PATTERNS:
                if re.search(pattern, html):
                    # Extract site key from render parameter
                    match = re.search(r'render=([a-zA-Z0-9_-]+)', html)
                    if match:
                        site_key = match.group(1)
                        if site_key != "explicit":
                            return CaptchaInfo(
                                captcha_type=CaptchaType.RECAPTCHA_V3,
                                site_key=site_key,
                                page_url=page_url,
                            )
        except Exception:
            pass

        return None

    async def _detect_hcaptcha(self, page, page_url: str) -> Optional[CaptchaInfo]:
        """Detect hCaptcha"""
        for selector in self.HCAPTCHA_SELECTORS:
            try:
                element = await self._query_selector(page, selector)
                if element:
                    site_key = await self._get_hcaptcha_sitekey(page, element)
                    if site_key:
                        return CaptchaInfo(
                            captcha_type=CaptchaType.HCAPTCHA,
                            site_key=site_key,
                            page_url=page_url,
                        )
            except Exception:
                continue

        return None

    async def _detect_turnstile(self, page, page_url: str) -> Optional[CaptchaInfo]:
        """Detect Cloudflare Turnstile"""
        for selector in self.TURNSTILE_SELECTORS:
            try:
                element = await self._query_selector(page, selector)
                if element:
                    site_key = await page.evaluate("""
                        () => {
                            const el = document.querySelector('.cf-turnstile');
                            return el ? el.getAttribute('data-sitekey') : null;
                        }
                    """)
                    if site_key:
                        return CaptchaInfo(
                            captcha_type=CaptchaType.TURNSTILE,
                            site_key=site_key,
                            page_url=page_url,
                        )
            except Exception:
                continue

        return None

    async def _detect_image_captcha(self, page, page_url: str) -> Optional[CaptchaInfo]:
        """Detect image-based CAPTCHA"""
        for selector in self.IMAGE_CAPTCHA_SELECTORS:
            try:
                element = await self._query_selector(page, selector)
                if element:
                    image_data = await self._capture_element_image(page, element)
                    return CaptchaInfo(
                        captcha_type=CaptchaType.IMAGE,
                        page_url=page_url,
                        image_data=image_data,
                    )
            except Exception:
                continue

        # Check for Cloudflare challenge page
        try:
            is_cf_challenge = await page.evaluate("""
                () => {
                    return document.title.includes('Just a moment') ||
                           document.title.includes('Attention Required') ||
                           !!document.querySelector('#challenge-running') ||
                           !!document.querySelector('#challenge-stage');
                }
            """)
            if is_cf_challenge:
                return CaptchaInfo(
                    captcha_type=CaptchaType.IMAGE,
                    page_url=page_url,
                    extra={"cloudflare_challenge": True},
                )
        except Exception:
            pass

        return None

    async def _capture_element_image(self, page, element) -> Optional[bytes]:
        """Capture screenshot of a specific element (returns bytes)"""
        try:
            # browser-use 0.11.8: screenshot() returns base64 str
            return base64.b64decode(await element.screenshot())
        except Exception:
            try:
                return base64.b64decode(await page.screenshot())
            except Exception as e:
                logger.error(f"Element screenshot failed: {e}")
                return None

    async def _get_recaptcha_sitekey(self, page, element) -> Optional[str]:
        """Extract reCAPTCHA site key"""
        try:
            # Try data-sitekey attribute
            site_key = await page.evaluate("""
                () => {
                    const el = document.querySelector('[data-sitekey]');
                    return el ? el.getAttribute('data-sitekey') : null;
                }
            """)
            if site_key:
                return site_key

            # Try iframe src
            site_key = await page.evaluate("""
                () => {
                    const iframe = document.querySelector("iframe[src*='recaptcha']");
                    if (iframe) {
                        const match = iframe.src.match(/[?&]k=([a-zA-Z0-9_-]+)/);
                        return match ? match[1] : null;
                    }
                    return null;
                }
            """)
            return site_key

        except Exception:
            return None

    async def _get_hcaptcha_sitekey(self, page, element) -> Optional[str]:
        """Extract hCaptcha site key"""
        try:
            site_key = await page.evaluate("""
                () => {
                    const el = document.querySelector('[data-hcaptcha-sitekey]') ||
                               document.querySelector('.h-captcha[data-sitekey]');
                    return el ? (el.getAttribute('data-hcaptcha-sitekey') ||
                                el.getAttribute('data-sitekey')) : null;
                }
            """)
            return site_key
        except Exception:
            return None


class CaptchaMiddleware:
    """
    Middleware for automatic CAPTCHA detection and solving.

    Example:
        solver = TwoCaptchaSolver(api_key="...")
        middleware = CaptchaMiddleware(solver)

        # Attach to browser context
        await middleware.attach(context)

        # Navigate - CAPTCHA will be auto-solved
        await page.goto("https://example.com")
    """

    def __init__(
        self,
        solver: CaptchaSolver,
        solvers: Optional[list[CaptchaSolver]] = None,
        auto_solve: bool = True,
        max_retries: int = 3,
        on_captcha_detected: Optional[Callable[[CaptchaInfo], None]] = None,
        on_captcha_solved: Optional[Callable[[CaptchaSolution], None]] = None,
    ):
        self._solver = solver
        self._solvers = solvers or [solver]
        self._detector = CaptchaDetector()
        self._auto_solve = auto_solve
        self._max_retries = max_retries
        self._on_detected = on_captcha_detected
        self._on_solved = on_captcha_solved

    async def attach(self, context) -> None:
        """Attach middleware to browser context"""
        context.on("page", self._on_page_created)

    async def _on_page_created(self, page) -> None:
        """Handle new page creation"""
        page.on("load", lambda: asyncio.create_task(self._check_for_captcha(page)))

    async def _check_for_captcha(self, page) -> None:
        """Check page for CAPTCHA and solve if found"""
        try:
            captcha = await self._detector.detect(page)

            if captcha:
                logger.info(f"CAPTCHA detected: {captcha.captcha_type.value}")

                if self._on_detected:
                    self._on_detected(captcha)

                if self._auto_solve:
                    await self._solve_and_submit(page, captcha)

        except Exception as e:
            logger.error(f"CAPTCHA check error: {e}")

    async def _solve_and_submit(self, page, captcha: CaptchaInfo) -> bool:
        """Solve CAPTCHA and submit token using solver chain"""
        for attempt in range(self._max_retries):
            logger.info(f"Solving CAPTCHA attempt {attempt + 1}/{self._max_retries}")

            # Try each solver in chain
            for solver in self._solvers:
                if not solver.supports(captcha.captcha_type):
                    continue

                logger.info(f"Trying solver: {solver.__class__.__name__}")
                solution = await solver.solve(captcha)

                if self._on_solved:
                    self._on_solved(solution)

                if solution.success:
                    logger.info(
                        f"CAPTCHA solved by {solution.provider} in {solution.solve_time_ms}ms"
                    )
                    success = await self._submit_token(page, captcha, solution)
                    if success:
                        return True
                else:
                    logger.warning(
                        f"Solver {solver.__class__.__name__} failed: {solution.error}"
                    )

        return False

    async def _submit_token(
        self,
        page,
        captcha: CaptchaInfo,
        solution: CaptchaSolution,
    ) -> bool:
        """Submit CAPTCHA token to page"""
        try:
            if captcha.captcha_type in (CaptchaType.RECAPTCHA_V2, CaptchaType.RECAPTCHA_V3):
                await page.evaluate(f"""
                    (token) => {{
                        // Set response in textarea
                        const textarea = document.querySelector('#g-recaptcha-response') ||
                                        document.querySelector('[name="g-recaptcha-response"]');
                        if (textarea) {{
                            textarea.value = token;
                            textarea.style.display = 'block';
                        }}

                        // Call callback if exists
                        if (typeof ___grecaptcha_cfg !== 'undefined') {{
                            const clients = ___grecaptcha_cfg.clients;
                            if (clients) {{
                                for (const client of Object.values(clients)) {{
                                    const callback = client?.callback;
                                    if (typeof callback === 'function') {{
                                        callback(token);
                                        return true;
                                    }}
                                }}
                            }}
                        }}

                        // Try global callback
                        if (typeof captchaCallback === 'function') {{
                            captchaCallback(token);
                            return true;
                        }}

                        return false;
                    }}
                """, solution.token)

            elif captcha.captcha_type == CaptchaType.HCAPTCHA:
                await page.evaluate(f"""
                    (token) => {{
                        const textarea = document.querySelector('[name="h-captcha-response"]') ||
                                        document.querySelector('[name="g-recaptcha-response"]');
                        if (textarea) {{
                            textarea.value = token;
                        }}

                        // Call hcaptcha callback
                        if (typeof hcaptcha !== 'undefined' && hcaptcha.execute) {{
                            // Trigger form submission
                            const form = document.querySelector('form');
                            if (form) form.submit();
                        }}
                    }}
                """, solution.token)

            elif captcha.captcha_type == CaptchaType.TURNSTILE:
                await page.evaluate(f"""
                    (token) => {{
                        const input = document.querySelector('[name="cf-turnstile-response"]');
                        if (input) {{
                            input.value = token;
                        }}

                        // Trigger Turnstile callback
                        if (typeof turnstile !== 'undefined') {{
                            const widgets = turnstile.getWidgetIds();
                            if (widgets.length > 0) {{
                                turnstile.render(widgets[0], {{ callback: () => {{}} }});
                            }}
                        }}
                    }}
                """, solution.token)

            logger.info("CAPTCHA token submitted")
            return True

        except Exception as e:
            logger.error(f"Token submit error: {e}")
            return False

    async def detect(self, page) -> Optional[CaptchaInfo]:
        """Manually detect CAPTCHA on page"""
        return await self._detector.detect(page)

    async def solve(self, page, captcha: Optional[CaptchaInfo] = None) -> CaptchaSolution:
        """Manually solve CAPTCHA"""
        if captcha is None:
            captcha = await self._detector.detect(page)

        if captcha is None:
            return CaptchaSolution(
                success=False,
                error="No CAPTCHA detected",
            )

        solution = await self._solver.solve(captcha)

        if solution.success:
            await self._submit_token(page, captcha, solution)

        return solution


def create_captcha_solver(
    provider: str = "2captcha",
    api_key: str = "",
    **kwargs,
) -> CaptchaSolver:
    """
    Factory function to create CAPTCHA solver.

    Args:
        provider: "2captcha", "anti-captcha", or "vision"
        api_key: API key for the service
        **kwargs: Provider-specific options

    Returns:
        CaptchaSolver instance
    """
    if provider == "2captcha":
        return TwoCaptchaSolver(api_key=api_key, **kwargs)
    elif provider in ("anti-captcha", "anticaptcha"):
        return AntiCaptchaSolver(api_key=api_key, **kwargs)
    elif provider == "vision":
        from .vision_captcha_solver import VisionCaptchaSolver
        return VisionCaptchaSolver(api_key=api_key, **kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}")
