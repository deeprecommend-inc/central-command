"""
Web Agent - Main interface for web automation with proxy and UA rotation
"""
import asyncio
from typing import Optional, Any
from dataclasses import dataclass
from loguru import logger

from .proxy_manager import ProxyManager, ProxyType
from .ua_manager import UserAgentManager
from .browser_worker import BrowserWorker, WorkerResult
from .parallel_controller import ParallelController, TaskResult


@dataclass
class AgentConfig:
    """Configuration for WebAgent"""

    brightdata_username: str = ""
    brightdata_password: str = ""
    brightdata_host: str = "brd.superproxy.io"
    brightdata_port: int = 22225
    # Proxy type: residential (住宅IP), datacenter, mobile, isp
    proxy_type: str = "residential"
    parallel_sessions: int = 5
    headless: bool = True


class WebAgent:
    """
    Web automation agent with proxy rotation and user agent management.

    Example usage:
        agent = WebAgent(config)
        result = await agent.navigate("https://example.com")
        results = await agent.parallel_navigate(["https://a.com", "https://b.com"])
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()

        # Initialize proxy manager if credentials provided
        self.proxy_manager = None
        if self.config.brightdata_username and self.config.brightdata_password:
            # Convert string to ProxyType enum
            proxy_type_map = {
                "residential": ProxyType.RESIDENTIAL,
                "datacenter": ProxyType.DATACENTER,
                "mobile": ProxyType.MOBILE,
                "isp": ProxyType.ISP,
            }
            proxy_type = proxy_type_map.get(
                self.config.proxy_type.lower(), ProxyType.RESIDENTIAL
            )

            self.proxy_manager = ProxyManager(
                username=self.config.brightdata_username,
                password=self.config.brightdata_password,
                host=self.config.brightdata_host,
                port=self.config.brightdata_port,
                proxy_type=proxy_type,
            )
            logger.info(f"Proxy manager initialized: type={proxy_type.value} (住宅IP)" if proxy_type == ProxyType.RESIDENTIAL else f"Proxy manager initialized: type={proxy_type.value}")
        else:
            logger.warning("No proxy credentials provided - running without proxy")

        self.ua_manager = UserAgentManager()
        self.controller = ParallelController(
            proxy_manager=self.proxy_manager,
            ua_manager=self.ua_manager,
            max_workers=self.config.parallel_sessions,
            headless=self.config.headless,
        )

    async def navigate(self, url: str) -> TaskResult:
        """Navigate to URL with single worker"""

        async def task(worker: BrowserWorker) -> WorkerResult:
            result = await worker.navigate(url)
            if result.success:
                content = await worker.get_content()
                if content.success:
                    result.data = {**result.data, **content.data}
            return result

        return await self.controller.run_task("single", task)

    async def parallel_navigate(self, urls: list[str]) -> list[TaskResult]:
        """Navigate to multiple URLs in parallel"""

        def make_task(url: str):
            async def task(worker: BrowserWorker) -> WorkerResult:
                result = await worker.navigate(url)
                if result.success:
                    content = await worker.get_content()
                    if content.success:
                        result.data = {**result.data, **content.data}
                return result

            return task

        tasks = [(f"nav_{i}", make_task(url)) for i, url in enumerate(urls)]
        return await self.controller.run_parallel(tasks)

    async def run_custom_task(
        self,
        task_id: str,
        task_fn,
    ) -> TaskResult:
        """Run custom task with worker"""
        return await self.controller.run_task(task_id, task_fn)

    async def run_custom_tasks_parallel(
        self,
        tasks: list[tuple[str, Any]],
    ) -> list[TaskResult]:
        """Run multiple custom tasks in parallel"""
        return await self.controller.run_parallel(tasks)

    async def cleanup(self) -> None:
        """Clean up all resources"""
        await self.controller.cleanup_all()

    def get_proxy_stats(self) -> dict:
        """Get proxy usage statistics"""
        if self.proxy_manager:
            return {
                k: {"success_rate": v.success_rate, "total": v.total_requests}
                for k, v in self.proxy_manager.get_stats().items()
            }
        return {}


# Convenience function for quick usage
async def create_agent(
    brightdata_username: str = "",
    brightdata_password: str = "",
    parallel_sessions: int = 5,
    headless: bool = True,
) -> WebAgent:
    """Create and return a configured WebAgent"""
    config = AgentConfig(
        brightdata_username=brightdata_username,
        brightdata_password=brightdata_password,
        parallel_sessions=parallel_sessions,
        headless=headless,
    )
    return WebAgent(config)
