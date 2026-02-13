"""
Browser-Use Agent - AI-driven browser automation with proxy, UA rotation, and CAPTCHA handling

Launches Chrome manually via CDP to avoid timeout issues in WSL/Docker environments.
Proxy authentication handled via Chrome extension for reliable headless operation.
"""
import asyncio
import base64
import json
import os
import shutil
import signal
import socket
import sys
import tempfile
import time
from typing import Optional, Any
from dataclasses import dataclass
from loguru import logger

import subprocess
from browser_use import Agent, BrowserProfile, BrowserSession, Tools, ActionResult, ChatOpenAI

from .proxy_manager import ProxyManager, ProxyType
from .ua_manager import UserAgentManager
from .command.captcha_solver import (
    CaptchaDetector,
    CaptchaType,
    CaptchaSolver,
    TwoCaptchaSolver,
    AntiCaptchaSolver,
    CaptchaMiddleware,
)
from .command.vision_captcha_solver import VisionCaptchaSolver


CAPTCHA_SYSTEM_PROMPT = """
When you encounter a CAPTCHA on a page, use the solve_captcha action to detect and solve it automatically.
The solver uses Vision AI for image recognition and falls back to token-based services if available.
After solving, verify the page has progressed past the CAPTCHA before continuing with the original task.

IMPORTANT dropdown handling:
- For <select> elements: use the built-in select_dropdown(index, text) action.
- For custom combobox (div role="combobox", like Google's month/gender selectors):
  use select_custom_dropdown(dropdown_id, option_text).
  Example: select_custom_dropdown(dropdown_id="month", option_text="January")
  Example: select_custom_dropdown(dropdown_id="gender", option_text="Male")
- Use the actual visible text of the option (match the page language).
- If both fail: click the combobox to open it, then in the NEXT step click the specific option.
"""

# Default Chromium path from Playwright installation
_DEFAULT_CHROME_PATH = "/root/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome"


def _find_free_port() -> int:
    """Find a free TCP port"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get_chrome_path() -> str:
    """Get Chromium executable path"""
    if os.path.exists(_DEFAULT_CHROME_PATH):
        return _DEFAULT_CHROME_PATH
    # Fallback: resolve via Playwright
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "from playwright.sync_api import sync_playwright; "
             "p = sync_playwright().start(); "
             "print(p.chromium.executable_path); "
             "p.stop()"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    raise RuntimeError("Chromium not found. Run: playwright install chromium")


def _create_proxy_auth_extension(username: str, password: str) -> str:
    """
    Create a temporary Chrome extension for proxy authentication.

    Chrome's --proxy-server flag does not support credentials.
    This extension handles 407 Proxy Authentication Required responses
    by providing credentials via webRequest.onAuthRequired.

    Returns:
        Path to the temporary extension directory (caller must clean up)
    """
    ext_dir = tempfile.mkdtemp(prefix="proxy_auth_")

    manifest = {
        "version": "1.0",
        "manifest_version": 2,
        "name": "Proxy Auth",
        "permissions": [
            "proxy",
            "tabs",
            "webRequest",
            "webRequestBlocking",
            "<all_urls>",
        ],
        "background": {
            "scripts": ["background.js"],
            "persistent": True,
        },
    }

    background_js = f"""
chrome.webRequest.onAuthRequired.addListener(
    function(details) {{
        return {{
            authCredentials: {{
                username: {json.dumps(username)},
                password: {json.dumps(password)}
            }}
        }};
    }},
    {{urls: ["<all_urls>"]}},
    ["blocking"]
);
"""

    with open(os.path.join(ext_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)

    with open(os.path.join(ext_dir, "background.js"), "w") as f:
        f.write(background_js)

    return ext_dir


def launch_browser_cdp(
    headless: bool = True,
    proxy_server: Optional[str] = None,
    user_agent: Optional[str] = None,
    extension_dir: Optional[str] = None,
) -> tuple[subprocess.Popen, str, int]:
    """
    Launch Chrome with CDP and return (process, websocket_url, port).

    Uses a free port to avoid conflicts with concurrent sessions.
    """
    chrome_path = _get_chrome_path()
    port = _find_free_port()

    args = [
        chrome_path,
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
    ]

    if extension_dir:
        # Extensions require non-headless or --headless=new (Chrome 109+)
        # --disable-extensions-except allows only our extension
        args.append(f"--load-extension={extension_dir}")
        args.append(f"--disable-extensions-except={extension_dir}")
        if headless:
            args.append("--headless=new")
    elif headless:
        args.append("--headless=new")

    if proxy_server:
        args.append(f"--proxy-server={proxy_server}")
    if user_agent:
        args.append(f"--user-agent={user_agent}")

    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Wait for CDP to be ready (max 30 retries, 0.5s each = 15s)
    import requests
    for _ in range(30):
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=1)
            data = resp.json()
            ws_url = data.get("webSocketDebuggerUrl", "")
            if ws_url:
                logger.info(f"Chrome CDP ready on port {port}")
                return proc, ws_url, port
        except Exception:
            pass
        time.sleep(0.5)

    proc.terminate()
    raise RuntimeError(f"Chrome failed to start CDP on port {port}")


@dataclass
class BrowserUseConfig:
    """Configuration for BrowserUseAgent"""

    # Proxy settings
    brightdata_username: str = ""
    brightdata_password: str = ""
    brightdata_host: str = "brd.superproxy.io"
    brightdata_port: int = 22225
    proxy_type: str = "residential"

    # OpenAI settings
    openai_api_key: str = ""
    model: str = "gpt-4o"

    # Browser settings
    headless: bool = True

    # CAPTCHA solver preference
    captcha_solver: str = "vision"


class BrowserUseAgent:
    """
    AI-driven browser automation with proxy rotation, user agent management,
    and CAPTCHA solving capabilities.

    Launches Chrome manually via CDP for reliable startup in all environments.
    Proxy auth is handled via a temporary Chrome extension.

    CAPTCHA solver chain (in priority order):
    1. Vision LLM (GPT-4o) - for image/text CAPTCHAs
    2. 2captcha - token-based fallback
    3. anti-captcha - token-based fallback
    """

    def __init__(self, config: BrowserUseConfig):
        self.config = config

        # Initialize proxy manager (with connectivity test)
        self.proxy_manager: Optional[ProxyManager] = None
        if config.brightdata_username and config.brightdata_password:
            if self._test_proxy_connectivity(config):
                proxy_type_map = {
                    "residential": ProxyType.RESIDENTIAL,
                    "datacenter": ProxyType.DATACENTER,
                    "mobile": ProxyType.MOBILE,
                    "isp": ProxyType.ISP,
                }
                proxy_type = proxy_type_map.get(config.proxy_type.lower(), ProxyType.RESIDENTIAL)

                self.proxy_manager = ProxyManager(
                    username=config.brightdata_username,
                    password=config.brightdata_password,
                    host=config.brightdata_host,
                    port=config.brightdata_port,
                    proxy_type=proxy_type,
                )
                logger.info(f"Proxy enabled: type={proxy_type.value}")
            else:
                logger.warning("Proxy connectivity test failed, falling back to direct connection")
        else:
            logger.info("Proxy disabled: direct connection")

        # Initialize UA manager
        self.ua_manager = UserAgentManager()

        # Initialize LLM
        self.llm = ChatOpenAI(
            model=config.model,
            api_key=config.openai_api_key,
        )

        self._session_counter = 0

        # Initialize CAPTCHA components
        self._init_captcha_solvers()

        # Create custom tools with CAPTCHA actions
        self.tools = self._create_tools()

    @staticmethod
    def _test_proxy_connectivity(config: BrowserUseConfig) -> bool:
        """Test proxy connectivity before using it. Returns True if proxy works."""
        import requests as req
        proxy_url = (
            f"http://{config.brightdata_username}:{config.brightdata_password}"
            f"@{config.brightdata_host}:{config.brightdata_port}"
        )
        try:
            resp = req.get(
                "http://httpbin.org/ip",
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"Proxy test OK: {resp.json().get('origin', 'unknown')}")
                return True
            logger.warning(f"Proxy test failed: HTTP {resp.status_code}")
            return False
        except Exception as e:
            logger.warning(f"Proxy test failed: {e}")
            return False

    def _init_captcha_solvers(self):
        """Initialize CAPTCHA detector and solver chain"""
        self.captcha_detector = CaptchaDetector()
        self.captcha_solvers: list[CaptchaSolver] = []

        # Vision LLM (priority)
        if self.config.openai_api_key:
            self.captcha_solvers.append(
                VisionCaptchaSolver(api_key=self.config.openai_api_key)
            )
            logger.info("CAPTCHA solver: Vision (GPT-4o) enabled")

        # 2captcha (fallback)
        twocaptcha_key = os.getenv("TWOCAPTCHA_API_KEY", "")
        if twocaptcha_key:
            self.captcha_solvers.append(
                TwoCaptchaSolver(api_key=twocaptcha_key)
            )
            logger.info("CAPTCHA solver: 2captcha enabled")

        # anti-captcha (fallback)
        anticaptcha_key = os.getenv("ANTICAPTCHA_API_KEY", "")
        if anticaptcha_key:
            self.captcha_solvers.append(
                AntiCaptchaSolver(api_key=anticaptcha_key)
            )
            logger.info("CAPTCHA solver: anti-captcha enabled")

        if not self.captcha_solvers:
            logger.warning("No CAPTCHA solvers configured (set OPENAI_API_KEY for Vision solver)")

    def _create_tools(self) -> Tools:
        """Create custom Tools with CAPTCHA-related actions"""
        tools = Tools()
        agent_ref = self

        @tools.action("Detect and solve CAPTCHA on the current page")
        async def solve_captcha(browser_session: BrowserSession) -> ActionResult:
            page = await browser_session.get_current_page()
            captcha = await agent_ref.captcha_detector.detect(page)

            if not captcha:
                return ActionResult(extracted_content="No CAPTCHA detected on page")

            logger.info(f"CAPTCHA detected: {captcha.captcha_type.value}")

            # Capture image if needed for image CAPTCHA
            # browser-use 0.11.8: screenshot() returns base64 str, not bytes
            if captcha.captcha_type == CaptchaType.IMAGE and not captcha.image_data:
                captcha.image_data = base64.b64decode(await page.screenshot())

            # Try each solver in chain
            for solver in agent_ref.captcha_solvers:
                if not solver.supports(captcha.captcha_type):
                    continue

                logger.info(f"Attempting solver: {solver.__class__.__name__}")
                solution = await solver.solve(captcha)

                if solution.success:
                    logger.info(
                        f"CAPTCHA solved by {solution.provider} in {solution.solve_time_ms}ms"
                    )

                    # Submit token/text to page
                    middleware = CaptchaMiddleware(solver=solver)
                    await middleware._submit_token(page, captcha, solution)

                    return ActionResult(
                        extracted_content=f"CAPTCHA solved: type={captcha.captcha_type.value}, provider={solution.provider}"
                    )
                else:
                    logger.warning(f"{solver.__class__.__name__} failed: {solution.error}")

            return ActionResult(error="All CAPTCHA solvers failed")

        @tools.action(
            "Select option from a custom dropdown (div role=combobox, NOT <select>). "
            "For native <select> elements, use the built-in select_dropdown action instead. "
            "Parameters: dropdown_id (e.g. 'month', 'gender'), option_text (e.g. 'January', 'Male')"
        )
        async def select_custom_dropdown(dropdown_id: str, option_text: str, browser_session: BrowserSession) -> ActionResult:
            page = await browser_session.get_current_page()
            if not page:
                return ActionResult(error="No page available")
            try:
                # Step 1: Open dropdown using native browser-use CSS selector API
                dropdowns = await page.get_elements_by_css_selector(f'#{dropdown_id}')
                if not dropdowns:
                    return ActionResult(error=f"Dropdown #{dropdown_id} not found on page")
                await dropdowns[0].click()
                await asyncio.sleep(0.5)

                # Step 2: Find options and click matching one
                options = await page.get_elements_by_css_selector('div[role="option"]')
                if not options:
                    options = await page.get_elements_by_css_selector('div[data-value], li[role="option"]')

                for opt in options:
                    text = await opt.evaluate("() => this.textContent.trim()")
                    if text == option_text or option_text in text:
                        await opt.click()
                        await asyncio.sleep(0.3)
                        logger.info(f"select_custom_dropdown: selected '{text}' from #{dropdown_id}")
                        return ActionResult(
                            extracted_content=f"Selected '{text}' from dropdown '{dropdown_id}'"
                        )

                # Report available options for debugging
                available = []
                for opt in options[:12]:
                    t = await opt.evaluate("() => this.textContent.trim()")
                    available.append(t)

                return ActionResult(
                    error=f"Option '{option_text}' not found in #{dropdown_id}. Available options: {available}"
                )
            except Exception as e:
                logger.warning(f"select_custom_dropdown error: {e}")
                return ActionResult(error=f"select_custom_dropdown failed: {e}")

        @tools.action("Detect CAPTCHA type on the current page without solving")
        async def detect_captcha(browser_session: BrowserSession) -> ActionResult:
            page = await browser_session.get_current_page()
            captcha = await agent_ref.captcha_detector.detect(page)

            if captcha:
                return ActionResult(
                    extracted_content=f"CAPTCHA found: type={captcha.captcha_type.value}, site_key={captcha.site_key or 'N/A'}"
                )
            return ActionResult(extracted_content="No CAPTCHA detected")

        @tools.action("Take a screenshot of a CAPTCHA element on the page")
        async def screenshot_captcha(browser_session: BrowserSession) -> ActionResult:
            page = await browser_session.get_current_page()
            captcha = await agent_ref.captcha_detector.detect(page)

            if not captcha:
                return ActionResult(extracted_content="No CAPTCHA element found to screenshot")

            if captcha.image_data:
                return ActionResult(
                    extracted_content=f"CAPTCHA screenshot captured: {len(captcha.image_data)} bytes"
                )

            screenshot_b64 = await page.screenshot()
            screenshot = base64.b64decode(screenshot_b64)
            return ActionResult(
                extracted_content=f"Page screenshot captured: {len(screenshot)} bytes"
            )

        return tools

    def _get_launch_params(self) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Get proxy server URL, user agent, and proxy auth extension dir
        for Chrome launch args.

        Returns:
            (proxy_server, user_agent, extension_dir)
        """
        self._session_counter += 1
        session_id = f"session_{self._session_counter}"

        # Proxy
        proxy_server = None
        extension_dir = None
        if self.proxy_manager:
            proxy = self.proxy_manager.get_proxy(new_session=True)
            proxy_server = f"http://{self.config.brightdata_host}:{self.config.brightdata_port}"
            proxy_username = proxy.username + (f"-country-{proxy.country}" if proxy.country else "")
            proxy_password = proxy.password

            # Create Chrome extension for proxy auth
            extension_dir = _create_proxy_auth_extension(proxy_username, proxy_password)
            logger.info(f"Using proxy: country={proxy.country}, type={proxy.proxy_type.value}")

        # User agent
        profile = self.ua_manager.get_random_profile(session_id=session_id)
        user_agent = profile.user_agent
        logger.info(f"Using UA: {user_agent[:60]}...")

        return proxy_server, user_agent, extension_dir

    async def run(self, task: str) -> dict[str, Any]:
        """
        Run a task using natural language prompt with CAPTCHA support.

        Launches Chrome via CDP for reliable startup, then runs browser-use Agent.
        Proxy auth is handled via a temporary Chrome extension.
        """
        logger.info(f"Running task: {task[:100]}...")

        proxy_server, user_agent, extension_dir = self._get_launch_params()
        proc = None

        try:
            # Launch Chrome with CDP
            proc, ws_url, port = launch_browser_cdp(
                headless=self.config.headless,
                proxy_server=proxy_server,
                user_agent=user_agent,
                extension_dir=extension_dir,
            )

            # Create browser profile with CDP URL
            # headless=True を明示 (upstream #3207: headless動作差異対応)
            browser_profile = BrowserProfile(cdp_url=ws_url, headless=self.config.headless)

            agent = Agent(
                task=task,
                llm=self.llm,
                browser_profile=browser_profile,
                tools=self.tools,
                extend_system_message=CAPTCHA_SYSTEM_PROMPT,
                use_vision=True,
            )

            result = await agent.run()

            return {
                "success": True,
                "result": result,
                "task": task,
            }

        except Exception as e:
            logger.error(f"Task failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "task": task,
            }
        finally:
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            # Clean up proxy auth extension
            if extension_dir and os.path.isdir(extension_dir):
                shutil.rmtree(extension_dir, ignore_errors=True)

    async def run_parallel(self, tasks: list[str], max_concurrent: int = 5) -> list[dict]:
        """
        Run multiple tasks in parallel. Each task gets its own Chrome instance.
        """
        logger.info(f"Running {len(tasks)} tasks in parallel (max {max_concurrent})")

        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_with_semaphore(task: str, index: int) -> dict:
            async with semaphore:
                logger.info(f"Starting task {index + 1}/{len(tasks)}")
                result = await self.run(task)
                result["index"] = index
                return result

        results = await asyncio.gather(
            *[run_with_semaphore(task, i) for i, task in enumerate(tasks)],
            return_exceptions=True,
        )

        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append({
                    "success": False,
                    "error": str(result),
                    "task": tasks[i],
                    "index": i,
                })
            else:
                final_results.append(result)

        success_count = sum(1 for r in final_results if r.get("success"))
        logger.info(f"Completed: {success_count}/{len(tasks)} successful")

        return final_results
