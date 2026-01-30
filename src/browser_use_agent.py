"""
Browser-Use Agent - AI-driven browser automation with proxy and UA rotation
"""
import asyncio
from typing import Optional, Any
from dataclasses import dataclass
from loguru import logger

import subprocess
from browser_use import Agent
from browser_use.browser.profile import BrowserProfile, ProxySettings
from browser_use.llm import ChatOpenAI

from .proxy_manager import ProxyManager, ProxyType
from .ua_manager import UserAgentManager


def get_playwright_chromium_path() -> str:
    """Get Playwright's chromium executable path"""
    try:
        result = subprocess.run(
            ["python", "-c",
             "from playwright.sync_api import sync_playwright; "
             "p = sync_playwright().start(); "
             "print(p.chromium.executable_path); "
             "p.stop()"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "/root/.cache/ms-playwright/chromium-1200/chrome-linux64/chrome"


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


class BrowserUseAgent:
    """
    AI-driven browser automation with proxy rotation and user agent management.

    Uses browser-use for natural language web automation.
    """

    def __init__(self, config: BrowserUseConfig):
        self.config = config

        # Initialize proxy manager
        self.proxy_manager: Optional[ProxyManager] = None
        if config.brightdata_username and config.brightdata_password:
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
            proxy_label = f"{proxy_type.value} (住宅IP)" if proxy_type == ProxyType.RESIDENTIAL else proxy_type.value
            logger.info(f"Proxy enabled: type={proxy_label}")
        else:
            logger.info("Proxy disabled: BRIGHTDATA credentials not set (direct connection)")

        # Initialize UA manager
        self.ua_manager = UserAgentManager()

        # Initialize LLM (browser-use native)
        self.llm = ChatOpenAI(
            model=config.model,
            api_key=config.openai_api_key,
        )

        self._session_counter = 0

    def _create_browser_profile(self) -> BrowserProfile:
        """Create browser profile with proxy and UA"""
        self._session_counter += 1
        session_id = f"session_{self._session_counter}"

        # Get proxy settings
        proxy_settings = None
        if self.proxy_manager:
            proxy = self.proxy_manager.get_proxy(new_session=True)
            proxy_settings = ProxySettings(
                server=f"http://{self.config.brightdata_host}:{self.config.brightdata_port}",
                username=proxy.username + (f"-country-{proxy.country}" if proxy.country else ""),
                password=proxy.password,
            )
            logger.info(f"Using proxy: country={proxy.country}, type={proxy.proxy_type.value}")

        # Get UA profile
        profile = self.ua_manager.get_random_profile(session_id=session_id)
        logger.info(f"Using UA: {profile.user_agent[:60]}...")

        # Create browser profile with explicit chromium path
        browser_profile = BrowserProfile(
            headless=self.config.headless,
            proxy=proxy_settings,
            user_agent=profile.user_agent,
            viewport={"width": profile.viewport_width, "height": profile.viewport_height},
            executable_path=get_playwright_chromium_path(),
        )

        return browser_profile

    async def run(self, task: str) -> dict[str, Any]:
        """
        Run a task using natural language prompt.

        Args:
            task: Natural language description of the task
                  e.g., "Go to google.com and search for 'python'"

        Returns:
            dict with result information
        """
        logger.info(f"Running task: {task[:100]}...")

        browser_profile = self._create_browser_profile()

        try:
            agent = Agent(
                task=task,
                llm=self.llm,
                browser_profile=browser_profile,
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

    async def run_parallel(self, tasks: list[str], max_concurrent: int = 5) -> list[dict]:
        """
        Run multiple tasks in parallel with different proxies/UAs.

        Args:
            tasks: List of task descriptions
            max_concurrent: Maximum concurrent browsers

        Returns:
            List of results
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

        # Handle exceptions
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
