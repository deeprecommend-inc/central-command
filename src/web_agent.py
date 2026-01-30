"""
Web Agent - Main interface for web automation with proxy and UA rotation
"""
import asyncio
from typing import Optional, Any
from loguru import logger
from pydantic import BaseModel, Field, field_validator, ConfigDict

from .proxy_manager import ProxyManager, ProxyType
from .ua_manager import UserAgentManager
from .browser_worker import BrowserWorker, WorkerResult
from .parallel_controller import ParallelController, TaskResult


class AgentConfig(BaseModel):
    """Configuration for WebAgent with validation"""

    brightdata_username: str = ""
    brightdata_password: str = ""
    brightdata_host: str = "brd.superproxy.io"
    brightdata_port: int = Field(default=22225, ge=1, le=65535)
    proxy_type: str = "residential"
    parallel_sessions: int = Field(default=5, ge=1, le=50)
    headless: bool = True
    max_retries: int = Field(default=3, ge=0, le=10)

    @field_validator("proxy_type")
    @classmethod
    def validate_proxy_type(cls, v: str) -> str:
        valid_types = {"residential", "datacenter", "mobile", "isp"}
        if v.lower() not in valid_types:
            raise ValueError(f"proxy_type must be one of: {valid_types}")
        return v.lower()

    @field_validator("brightdata_host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if v and not v.replace(".", "").replace("-", "").replace("_", "").isalnum():
            raise ValueError("Invalid host format")
        return v

    model_config = ConfigDict(extra="forbid")


class WebAgent:
    """
    Web automation agent with proxy rotation and user agent management.

    Supports async context manager for automatic cleanup:

        async with WebAgent(config) as agent:
            result = await agent.navigate("https://example.com")

    Or manual cleanup:

        agent = WebAgent(config)
        try:
            result = await agent.navigate("https://example.com")
        finally:
            await agent.cleanup()
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self._closed = False

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
            proxy_label = f"{proxy_type.value}" if proxy_type != ProxyType.RESIDENTIAL else f"{proxy_type.value} (default)"
            logger.info(f"Proxy enabled: type={proxy_label}")
        else:
            logger.info("Proxy disabled: BRIGHTDATA credentials not set (direct connection)")

        self.ua_manager = UserAgentManager()
        self.controller = ParallelController(
            proxy_manager=self.proxy_manager,
            ua_manager=self.ua_manager,
            max_workers=self.config.parallel_sessions,
            headless=self.config.headless,
            max_retries=self.config.max_retries,
        )

    async def __aenter__(self) -> "WebAgent":
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit with cleanup"""
        await self.cleanup()
        return None

    async def navigate(self, url: str) -> TaskResult:
        """Navigate to URL with single worker"""
        self._check_closed()

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
        self._check_closed()

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
        self._check_closed()
        return await self.controller.run_task(task_id, task_fn)

    async def run_custom_tasks_parallel(
        self,
        tasks: list[tuple[str, Any]],
    ) -> list[TaskResult]:
        """Run multiple custom tasks in parallel"""
        self._check_closed()
        return await self.controller.run_parallel(tasks)

    async def cleanup(self) -> None:
        """Clean up all resources"""
        if not self._closed:
            await self.controller.cleanup_all()
            self.ua_manager.clear_all()
            self._closed = True
            logger.info("WebAgent cleanup complete")

    def _check_closed(self) -> None:
        """Check if agent is closed"""
        if self._closed:
            raise RuntimeError("WebAgent is closed")

    @property
    def is_closed(self) -> bool:
        """Check if agent has been closed"""
        return self._closed

    def get_proxy_stats(self) -> dict:
        """Get proxy usage statistics"""
        if self.proxy_manager:
            return {
                k: {"success_rate": v.success_rate, "total": v.total_requests}
                for k, v in self.proxy_manager.get_stats().items()
            }
        return {}

    def get_proxy_health(self) -> dict:
        """Get proxy health summary"""
        if self.proxy_manager:
            return self.proxy_manager.get_health_summary()
        return {}

    async def health_check(self) -> dict:
        """Run health check on all proxies"""
        if self.proxy_manager:
            return await self.proxy_manager.health_check_all()
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
