#!/usr/bin/env python3
"""
Run Web Agent - Main CLI entry point
"""
import asyncio
import sys
import os
from loguru import logger
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="INFO",
)


def get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


async def run_basic_agent(urls: list[str]):
    """Run basic Playwright agent without AI"""
    from src import WebAgent
    from src.web_agent import AgentConfig

    config = AgentConfig(
        brightdata_username=get_env("BRIGHTDATA_USERNAME"),
        brightdata_password=get_env("BRIGHTDATA_PASSWORD"),
        brightdata_host=get_env("BRIGHTDATA_HOST", "brd.superproxy.io"),
        brightdata_port=int(get_env("BRIGHTDATA_PORT", "22225")),
        proxy_type=get_env("BRIGHTDATA_PROXY_TYPE", "residential"),
        parallel_sessions=int(get_env("PARALLEL_SESSIONS", "5")),
        headless=get_env("HEADLESS", "true").lower() == "true",
    )

    agent = WebAgent(config)

    try:
        if len(urls) == 1:
            logger.info(f"Navigating to: {urls[0]}")
            result = await agent.navigate(urls[0])
            if result.success:
                logger.info(f"Success: {result.data.get('url')}")
                logger.info(f"Title: {result.data.get('title', 'N/A')}")
            else:
                logger.error(f"Failed: {result.error}")
        else:
            logger.info(f"Navigating to {len(urls)} URLs in parallel...")
            results = await agent.parallel_navigate(urls)
            for i, result in enumerate(results):
                if result.success:
                    logger.info(f"[{i+1}] Success: {result.data.get('title', 'N/A')}")
                else:
                    logger.error(f"[{i+1}] Failed: {result.error}")

        # Show proxy stats
        stats = agent.get_proxy_stats()
        if stats:
            logger.info(f"Proxy stats: {stats}")

    finally:
        await agent.cleanup()


async def run_ai_agent(task: str):
    """Run AI-driven browser-use agent"""
    from src.browser_use_agent import BrowserUseAgent, BrowserUseConfig

    openai_key = get_env("OPENAI_API_KEY")
    if not openai_key:
        logger.error("OPENAI_API_KEY is required for AI agent")
        logger.info("Set OPENAI_API_KEY in .env or environment")
        sys.exit(1)

    config = BrowserUseConfig(
        brightdata_username=get_env("BRIGHTDATA_USERNAME"),
        brightdata_password=get_env("BRIGHTDATA_PASSWORD"),
        brightdata_host=get_env("BRIGHTDATA_HOST", "brd.superproxy.io"),
        brightdata_port=int(get_env("BRIGHTDATA_PORT", "22225")),
        proxy_type=get_env("BRIGHTDATA_PROXY_TYPE", "residential"),
        openai_api_key=openai_key,
        model=get_env("OPENAI_MODEL", "gpt-4o"),
        headless=get_env("HEADLESS", "true").lower() == "true",
    )

    agent = BrowserUseAgent(config)

    logger.info(f"Running AI task: {task}")
    result = await agent.run(task)

    if result["success"]:
        logger.info("Task completed successfully")
        logger.info(f"Result: {result.get('result')}")
    else:
        logger.error(f"Task failed: {result.get('error')}")


async def run_parallel_ai(tasks: list[str]):
    """Run multiple AI tasks in parallel"""
    from src.browser_use_agent import BrowserUseAgent, BrowserUseConfig

    openai_key = get_env("OPENAI_API_KEY")
    if not openai_key:
        logger.error("OPENAI_API_KEY is required for AI agent")
        sys.exit(1)

    config = BrowserUseConfig(
        brightdata_username=get_env("BRIGHTDATA_USERNAME"),
        brightdata_password=get_env("BRIGHTDATA_PASSWORD"),
        proxy_type=get_env("BRIGHTDATA_PROXY_TYPE", "residential"),
        openai_api_key=openai_key,
        headless=get_env("HEADLESS", "true").lower() == "true",
    )

    agent = BrowserUseAgent(config)

    max_concurrent = int(get_env("PARALLEL_SESSIONS", "5"))
    results = await agent.run_parallel(tasks, max_concurrent=max_concurrent)

    for result in results:
        idx = result.get("index", "?")
        if result["success"]:
            logger.info(f"[{idx}] Success")
        else:
            logger.error(f"[{idx}] Failed: {result.get('error')}")


def print_usage():
    print("""
Web Agent CLI

Usage:
  python run.py <command> [args...]

Commands:
  url <url> [url2...]     Navigate to URL(s) with proxy/UA rotation
  ai <task>               Run AI-driven task with natural language
  parallel <task1> <task2>...  Run multiple AI tasks in parallel
  demo                    Run demo with test URLs
  test                    Test basic functionality

Examples:
  python run.py url https://httpbin.org/ip
  python run.py url https://example.com https://google.com
  python run.py ai "Go to google.com and search for python"
  python run.py demo

Environment Variables:
  BRIGHTDATA_USERNAME     BrightData proxy username
  BRIGHTDATA_PASSWORD     BrightData proxy password
  BRIGHTDATA_PROXY_TYPE   residential (default), datacenter, mobile, isp
  OPENAI_API_KEY          OpenAI API key (required for AI agent)
  PARALLEL_SESSIONS       Max parallel sessions (default: 5)
  HEADLESS                Run headless (default: true)
""")


async def run_demo():
    """Run demo"""
    urls = [
        "https://httpbin.org/ip",
        "https://httpbin.org/user-agent",
        "https://httpbin.org/headers",
    ]
    await run_basic_agent(urls)


async def run_test():
    """Quick test"""
    await run_basic_agent(["https://httpbin.org/ip"])


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    command = sys.argv[1].lower()

    if command == "url":
        if len(sys.argv) < 3:
            print("Error: URL required")
            sys.exit(1)
        urls = sys.argv[2:]
        asyncio.run(run_basic_agent(urls))

    elif command == "ai":
        if len(sys.argv) < 3:
            print("Error: Task description required")
            sys.exit(1)
        task = " ".join(sys.argv[2:])
        asyncio.run(run_ai_agent(task))

    elif command == "parallel":
        if len(sys.argv) < 3:
            print("Error: Tasks required")
            sys.exit(1)
        tasks = sys.argv[2:]
        asyncio.run(run_parallel_ai(tasks))

    elif command == "demo":
        asyncio.run(run_demo())

    elif command == "test":
        asyncio.run(run_test())

    elif command in ["-h", "--help", "help"]:
        print_usage()

    else:
        print(f"Unknown command: {command}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
