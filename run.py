#!/usr/bin/env python3
"""
Run Web Agent - Main CLI entry point
"""
import asyncio
import sys
import os
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Configure logging
from src.logging_config import configure_logging

json_logging = os.getenv("LOG_FORMAT", "").lower() == "json"
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
configure_logging(level=log_level, json_format=json_logging)

from loguru import logger


def get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def parse_args(args: list[str]) -> tuple[str, list[str], dict]:
    """Parse command line arguments"""
    proxy_type = get_env("BRIGHTDATA_PROXY_TYPE", "residential")
    remaining_args = []
    options = {
        "json": False,
        "verbose": False,
    }

    for arg in args:
        if arg in ["--residential", "-r"]:
            proxy_type = "residential"
        elif arg in ["--mobile", "-m"]:
            proxy_type = "mobile"
        elif arg in ["--datacenter", "-d"]:
            proxy_type = "datacenter"
        elif arg in ["--isp", "-i"]:
            proxy_type = "isp"
        elif arg == "--no-proxy":
            os.environ["BRIGHTDATA_USERNAME"] = ""
            os.environ["BRIGHTDATA_PASSWORD"] = ""
        elif arg == "--json":
            options["json"] = True
        elif arg in ["--verbose", "-v"]:
            options["verbose"] = True
        else:
            remaining_args.append(arg)

    return proxy_type, remaining_args, options


async def run_basic_agent(urls: list[str], proxy_type: str = "residential"):
    """Run basic Playwright agent without AI"""
    from src import WebAgent
    from src.web_agent import AgentConfig

    config = AgentConfig(
        brightdata_username=get_env("BRIGHTDATA_USERNAME"),
        brightdata_password=get_env("BRIGHTDATA_PASSWORD"),
        brightdata_host=get_env("BRIGHTDATA_HOST", "brd.superproxy.io"),
        brightdata_port=int(get_env("BRIGHTDATA_PORT", "22225")),
        proxy_type=proxy_type,
        parallel_sessions=int(get_env("PARALLEL_SESSIONS", "5")),
        headless=get_env("HEADLESS", "true").lower() == "true",
    )

    async with WebAgent(config) as agent:
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


async def run_health_check(proxy_type: str = "residential"):
    """Run proxy health check"""
    from src import WebAgent
    from src.web_agent import AgentConfig
    import json

    username = get_env("BRIGHTDATA_USERNAME")
    password = get_env("BRIGHTDATA_PASSWORD")

    if not username or not password:
        logger.warning("BRIGHTDATA credentials not set. Health check requires proxy configuration.")
        print("\nProxy Status: Not configured (direct connection mode)")
        return

    config = AgentConfig(
        brightdata_username=username,
        brightdata_password=password,
        brightdata_host=get_env("BRIGHTDATA_HOST", "brd.superproxy.io"),
        brightdata_port=int(get_env("BRIGHTDATA_PORT", "22225")),
        proxy_type=proxy_type,
    )

    async with WebAgent(config) as agent:
        logger.info(f"Running health check for {proxy_type} proxies...")

        # Get health summary
        health = agent.get_proxy_health()
        print(f"\nProxy Health Summary ({proxy_type}):")
        print(f"  Total: {health.get('total_proxies', 0)}")
        print(f"  Healthy: {health.get('healthy', 0)}")
        print(f"  Unhealthy: {health.get('unhealthy', 0)}")

        print("\nCountry Status:")
        for country, status in health.get("countries", {}).items():
            health_icon = "[OK]" if status.get("healthy") else "[NG]"
            print(f"  {country.upper()}: {health_icon} score={status.get('health_score')} rate={status.get('success_rate')}")

        # Run actual health check
        print("\nRunning live health check...")
        results = await agent.health_check()
        healthy = sum(1 for v in results.values() if v)
        print(f"Live check: {healthy}/{len(results)} healthy")


async def run_ai_agent(task: str, proxy_type: str = "residential"):
    """Run AI-driven browser-use agent"""
    logger.warning("AI agent (browser-use) is currently not supported in WSL environment")
    logger.info("Use 'python run.py url <URL>' for basic web operations")
    logger.info("browser-use requires native Linux/Mac environment")
    sys.exit(1)


async def run_parallel_ai(tasks: list[str], proxy_type: str = "residential"):
    """Run multiple AI tasks in parallel"""
    logger.warning("AI agent (browser-use) is currently not supported in WSL environment")
    logger.info("Use 'python run.py url <URL1> <URL2>' for parallel web operations")
    sys.exit(1)


def print_usage():
    print("""
Web Agent CLI

Usage:
  python run.py <command> [options] [args...]

Commands:
  url <url> [url2...]     Navigate to URL(s) with proxy/UA rotation
  health                  Check proxy health status
  ai <task>               Run AI-driven task (not supported in WSL)
  demo                    Run demo with test URLs
  test                    Test basic functionality

Proxy Options:
  --residential, -r       Use residential IP (default)
  --mobile, -m            Use mobile IP
  --datacenter, -d        Use datacenter IP
  --isp, -i               Use ISP IP
  --no-proxy              Disable proxy (direct connection)

Other Options:
  --json                  Output in JSON format
  --verbose, -v           Verbose logging

Examples:
  python run.py url https://httpbin.org/ip
  python run.py url --mobile https://example.com
  python run.py url -r https://google.com https://github.com
  python run.py url --no-proxy https://example.com
  python run.py health --mobile
  python run.py demo --no-proxy

Environment Variables:
  BRIGHTDATA_USERNAME     BrightData proxy username (optional)
  BRIGHTDATA_PASSWORD     BrightData proxy password (optional)
  BRIGHTDATA_PROXY_TYPE   residential (default), datacenter, mobile, isp
  PARALLEL_SESSIONS       Max parallel sessions (default: 5)
  HEADLESS                Run headless (default: true)
  LOG_FORMAT              Logging format: json or text (default: text)
  LOG_LEVEL               Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)

Note: BRIGHTDATA settings are optional. Without them, the agent runs with direct connection.
""")


async def run_demo(proxy_type: str = "residential"):
    """Run demo"""
    urls = [
        "https://httpbin.org/ip",
        "https://httpbin.org/user-agent",
        "https://httpbin.org/headers",
    ]
    await run_basic_agent(urls, proxy_type)


async def run_test(proxy_type: str = "residential"):
    """Quick test"""
    await run_basic_agent(["https://httpbin.org/ip"], proxy_type)


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    command = sys.argv[1].lower()

    # Parse arguments
    proxy_type, args, options = parse_args(sys.argv[2:])

    # Reconfigure logging if --json flag is set
    if options["json"]:
        configure_logging(level="INFO", json_format=True)
    elif options["verbose"]:
        configure_logging(level="DEBUG", json_format=False)

    if command == "url":
        if len(args) < 1:
            print("Error: URL required")
            sys.exit(1)
        asyncio.run(run_basic_agent(args, proxy_type))

    elif command == "health":
        asyncio.run(run_health_check(proxy_type))

    elif command == "ai":
        if len(args) < 1:
            print("Error: Task description required")
            sys.exit(1)
        task = " ".join(args)
        asyncio.run(run_ai_agent(task, proxy_type))

    elif command == "parallel":
        if len(args) < 1:
            print("Error: Tasks required")
            sys.exit(1)
        asyncio.run(run_parallel_ai(args, proxy_type))

    elif command == "demo":
        asyncio.run(run_demo(proxy_type))

    elif command == "test":
        asyncio.run(run_test(proxy_type))

    elif command in ["-h", "--help", "help"]:
        print_usage()

    else:
        print(f"Unknown command: {command}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
