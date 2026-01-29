"""
Main entry point for Web Agent
"""
import asyncio
import sys
from loguru import logger
from dotenv import load_dotenv

from config.settings import settings
from src import WebAgent
from src.web_agent import AgentConfig

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="INFO",
)


async def demo():
    """Demo: Navigate to multiple URLs with proxy rotation"""
    load_dotenv()

    config = AgentConfig(
        brightdata_username=settings.brightdata_username,
        brightdata_password=settings.brightdata_password,
        brightdata_host=settings.brightdata_host,
        brightdata_port=settings.brightdata_port,
        proxy_type=settings.brightdata_proxy_type,  # 住宅IP (residential) がデフォルト
        parallel_sessions=settings.parallel_sessions,
        headless=settings.headless,
    )

    agent = WebAgent(config)

    try:
        # Demo URLs
        urls = [
            "https://httpbin.org/ip",
            "https://httpbin.org/user-agent",
            "https://httpbin.org/headers",
        ]

        logger.info(f"Navigating to {len(urls)} URLs in parallel...")
        results = await agent.parallel_navigate(urls)

        for i, result in enumerate(results):
            if result.success:
                logger.info(f"URL {i+1}: Success - {result.data.get('title', 'No title')}")
            else:
                logger.error(f"URL {i+1}: Failed - {result.error}")

        # Show proxy stats
        stats = agent.get_proxy_stats()
        if stats:
            logger.info(f"Proxy stats: {stats}")

    finally:
        await agent.cleanup()


async def single_navigation(url: str):
    """Navigate to a single URL"""
    load_dotenv()

    config = AgentConfig(
        brightdata_username=settings.brightdata_username,
        brightdata_password=settings.brightdata_password,
        proxy_type=settings.brightdata_proxy_type,  # 住宅IP
        headless=settings.headless,
    )

    agent = WebAgent(config)

    try:
        result = await agent.navigate(url)
        if result.success:
            print(f"Title: {result.data.get('title', 'N/A')}")
            print(f"URL: {result.data.get('url', 'N/A')}")
        else:
            print(f"Error: {result.error}")
        return result
    finally:
        await agent.cleanup()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
        asyncio.run(single_navigation(url))
    else:
        asyncio.run(demo())
