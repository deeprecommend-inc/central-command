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
        "captcha_solver": "vision",
        "llm_provider": get_env("LLM_PROVIDER", "openai"),
        "llm_base_url": get_env("LLM_BASE_URL", ""),
        "llm_model": get_env("LLM_MODEL", ""),
    }

    i = 0
    while i < len(args):
        arg = args[i]
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
        elif arg == "--captcha-solver" and i + 1 < len(args):
            i += 1
            options["captcha_solver"] = args[i]
        elif arg == "--local":
            options["llm_provider"] = "local"
            if not options["llm_base_url"]:
                options["llm_base_url"] = "http://localhost:11434/v1"
            if not options["llm_model"]:
                options["llm_model"] = "dolphin3"
        elif arg == "--llm-base-url" and i + 1 < len(args):
            i += 1
            options["llm_base_url"] = args[i]
            if options["llm_provider"] == "openai":
                options["llm_provider"] = "local"
        elif arg == "--llm-model" and i + 1 < len(args):
            i += 1
            options["llm_model"] = args[i]
        else:
            remaining_args.append(arg)
        i += 1

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


async def run_ai_agent(
    task: str,
    proxy_type: str = "residential",
    captcha_solver: str = "vision",
    llm_provider: str = "openai",
    llm_base_url: str = "",
    llm_model: str = "",
):
    """Run AI-driven browser-use agent with CAPTCHA support"""
    from src.browser_use_agent import BrowserUseAgent, BrowserUseConfig

    # Resolve API key
    api_key = get_env("LLM_API_KEY") or get_env("OPENAI_API_KEY")
    if not api_key and llm_provider != "local":
        logger.error("API key required (set LLM_API_KEY or OPENAI_API_KEY, or use --local for local LLM)")
        sys.exit(1)

    model = llm_model or get_env("OPENAI_MODEL", "gpt-4o")

    config = BrowserUseConfig(
        brightdata_username=get_env("BRIGHTDATA_USERNAME"),
        brightdata_password=get_env("BRIGHTDATA_PASSWORD"),
        brightdata_host=get_env("BRIGHTDATA_HOST", "brd.superproxy.io"),
        brightdata_port=int(get_env("BRIGHTDATA_PORT", "22225")),
        proxy_type=proxy_type,
        llm_provider=llm_provider,
        llm_api_key=api_key,
        llm_base_url=llm_base_url,
        openai_api_key=api_key,
        model=model,
        headless=get_env("HEADLESS", "true").lower() == "true",
        captcha_solver=captcha_solver,
    )

    agent = BrowserUseAgent(config)
    result = await agent.run(task)

    if result.get("success"):
        logger.info(f"Task completed successfully")
    else:
        logger.error(f"Task failed: {result.get('error')}")

    # Display human score
    hs = result.get("human_score")
    if hs:
        _print_human_score(hs)

    if not result.get("success"):
        sys.exit(1)


async def run_parallel_ai(
    tasks: list[str],
    proxy_type: str = "residential",
    captcha_solver: str = "vision",
    llm_provider: str = "openai",
    llm_base_url: str = "",
    llm_model: str = "",
):
    """Run multiple AI tasks in parallel with CAPTCHA support"""
    from src.browser_use_agent import BrowserUseAgent, BrowserUseConfig

    api_key = get_env("LLM_API_KEY") or get_env("OPENAI_API_KEY")
    if not api_key and llm_provider != "local":
        logger.error("API key required (set LLM_API_KEY or OPENAI_API_KEY, or use --local for local LLM)")
        sys.exit(1)

    model = llm_model or get_env("OPENAI_MODEL", "gpt-4o")

    config = BrowserUseConfig(
        brightdata_username=get_env("BRIGHTDATA_USERNAME"),
        brightdata_password=get_env("BRIGHTDATA_PASSWORD"),
        brightdata_host=get_env("BRIGHTDATA_HOST", "brd.superproxy.io"),
        brightdata_port=int(get_env("BRIGHTDATA_PORT", "22225")),
        proxy_type=proxy_type,
        llm_provider=llm_provider,
        llm_api_key=api_key,
        llm_base_url=llm_base_url,
        openai_api_key=api_key,
        model=model,
        headless=get_env("HEADLESS", "true").lower() == "true",
        captcha_solver=captcha_solver,
    )

    agent = BrowserUseAgent(config)
    max_sessions = int(get_env("PARALLEL_SESSIONS", "5"))
    results = await agent.run_parallel(tasks, max_concurrent=max_sessions)

    success_count = sum(1 for r in results if r.get("success"))
    logger.info(f"Completed: {success_count}/{len(tasks)} tasks successful")


def _print_human_score(hs: dict) -> None:
    """Print human-likeness score summary"""
    score = hs.get("score", 0)
    max_score = hs.get("max", 100)
    is_human = hs.get("is_human", False)
    verdict = "PASS" if is_human else "FAIL"
    print(f"\nHuman Score: {score}/{max_score} [{verdict}]")
    metrics = hs.get("metrics", {})
    if metrics:
        for mid, m in metrics.items():
            flag = "OK" if m.get("pass") else "NG"
            print(f"  {mid}: {m.get('value', 0):.4f} [{flag}] +{m.get('points', 0)}")


async def run_score_demo():
    """Run a human-likeness score demo with synthetic data"""
    import random
    from src.human_score import HumanScoreTracker

    tracker = HumanScoreTracker()
    base = tracker._start

    # Simulate 30 actions over 10 minutes with natural variation
    action_types = ["click", "scroll", "type", "navigate", "search", "hover", "wait"]
    t = base
    for i in range(30):
        t += random.uniform(5, 45)  # 5-45 seconds between actions
        action = random.choice(action_types)
        tracker.record_action(action, timestamp=t)

    # Simulate 8 page visits
    for i in range(8):
        tracker.record_page_visit(
            url=f"https://example.com/page{i}",
            dwell_sec=random.uniform(3, 120),
            completed=random.random() < 0.5,
            bounced=random.random() < 0.15,
            clicked=random.random() < 0.4,
        )

    # Simulate IP/fingerprint
    tracker.record_ip(ip="203.0.113.1", country="us", fingerprint_hash="abc123")
    tracker.record_ip(ip="203.0.113.2", country="us", fingerprint_hash="def456")

    # Simulate outcomes
    for _ in range(5):
        tracker.record_outcome(random.choice(["success", "partial", "skip"]))

    report = tracker.compute()
    print(report)


def print_usage():
    print("""
Web Agent CLI

Usage:
  python run.py <command> [options] [args...]

Commands:
  url <url> [url2...]     Navigate to URL(s) with proxy/UA rotation
  health                  Check proxy health status
  ai <task>               Run AI-driven task with CAPTCHA support
  score                   Run human-likeness score demo with synthetic data
  notify <text>           Send notification via channel
  channels                List registered notification channels
  vault <subcmd>          Manage encrypted credential vault
  demo                    Run demo with test URLs
  test                    Test basic functionality

Proxy Options:
  --residential, -r       Use residential IP (default)
  --mobile, -m            Use mobile IP
  --datacenter, -d        Use datacenter IP
  --isp, -i               Use ISP IP
  --no-proxy              Disable proxy (direct connection)

LLM Options:
  --local                 Use local LLM (Ollama/LM Studio/vLLM, no API key needed)
  --llm-base-url <url>    Local LLM server URL (default: http://localhost:11434/v1)
  --llm-model <model>     LLM model name (e.g. dolphin3, hermes3, mythomax)

CAPTCHA Options:
  --captcha-solver <type> CAPTCHA solver: vision (default), 2captcha, anti-captcha

Other Options:
  --json                  Output in JSON format
  --verbose, -v           Verbose logging

Notify Options:
  --channel <id>          Channel ID (default: webhook)
  --to <recipient>        Recipient (channel name, email, URL)

Examples:
  python run.py url https://httpbin.org/ip
  python run.py url --mobile https://example.com
  python run.py url --no-proxy https://example.com
  python run.py health --mobile
  python run.py demo --no-proxy

  # Cloud LLM
  python run.py ai "Go to example.com and solve the CAPTCHA" --no-proxy
  python run.py ai --captcha-solver 2captcha "Navigate to site and login"

  # Local LLM (no API key required)
  python run.py ai --local "Go to example.com and get the page title"
  python run.py ai --local --llm-model hermes3 "Search google for AI news"
  python run.py ai --llm-base-url http://localhost:1234/v1 --llm-model dolphin3 "Navigate to github.com"
  python run.py parallel --local "task 1" "task 2" "task 3"

  # Notifications
  python run.py channels
  python run.py notify --channel slack --to "#general" "Alert message"
  python run.py notify --channel webhook --to "https://httpbin.org/post" "Test"

  # Vault
  python run.py vault init
  python run.py vault set API_KEY sk-12345
  python run.py vault get API_KEY

Environment Variables:
  LLM_PROVIDER            LLM provider: openai, anthropic, local (default: openai)
  LLM_BASE_URL            Local LLM server URL (for local provider)
  LLM_MODEL               LLM model name
  LLM_API_KEY             LLM API key (not needed for local)
  OPENAI_API_KEY          OpenAI API key (legacy, fallback for LLM_API_KEY)
  OPENAI_MODEL            OpenAI model (legacy, fallback for LLM_MODEL)
  ANTHROPIC_API_KEY       Anthropic API key (for Claude models)
  BRIGHTDATA_USERNAME     BrightData proxy username (optional)
  BRIGHTDATA_PASSWORD     BrightData proxy password (optional)
  BRIGHTDATA_PROXY_TYPE   residential (default), datacenter, mobile, isp
  PARALLEL_SESSIONS       Max parallel sessions (default: 5)
  HEADLESS                Run headless (default: true)
  LOG_FORMAT              Logging format: json or text (default: text)
  LOG_LEVEL               Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)
  TWOCAPTCHA_API_KEY      2captcha API key (optional fallback)
  ANTICAPTCHA_API_KEY     Anti-Captcha API key (optional fallback)
  SLACK_WEBHOOK_URL       Slack Incoming Webhook URL
  SLACK_BOT_TOKEN         Slack Bot Token
  SLACK_DEFAULT_CHANNEL   Slack default channel
  TEAMS_WEBHOOK_URL       Teams Incoming Webhook URL
  EMAIL_SMTP_HOST         SMTP server host
  EMAIL_SMTP_PORT         SMTP port (default: 587)
  EMAIL_SMTP_USER         SMTP username
  EMAIL_SMTP_PASSWORD     SMTP password
  EMAIL_FROM              Sender email address
  WEBHOOK_URLS            Comma-separated webhook URLs

Supported Local LLM Servers:
  Ollama          http://localhost:11434/v1   ollama serve
  LM Studio       http://localhost:1234/v1    Start server in LM Studio
  vLLM            http://localhost:8000/v1    vllm serve <model>
  llama.cpp       http://localhost:8080/v1    llama-server -m <model>
  LocalAI         http://localhost:8080/v1    local-ai

Note: BRIGHTDATA and LLM API keys are optional. Use --local for API-key-free operation.
""")


async def run_notify(channel_id: str, to: str, text: str):
    """Send notification via a channel"""
    from src.command.channels import ChannelRegistry, WebhookChannel, SlackChannel, TeamsChannel, EmailChannel

    registry = ChannelRegistry()

    # Auto-register channels from settings
    try:
        from config.settings import settings

        if settings.slack_webhook_url or settings.slack_bot_token:
            registry.register(SlackChannel(
                webhook_url=settings.slack_webhook_url,
                bot_token=settings.slack_bot_token,
                default_channel=settings.slack_default_channel,
            ))
        if settings.teams_webhook_url:
            registry.register(TeamsChannel(webhook_url=settings.teams_webhook_url))
        if settings.email_smtp_host:
            registry.register(EmailChannel(
                smtp_host=settings.email_smtp_host,
                smtp_port=settings.email_smtp_port,
                smtp_user=settings.email_smtp_user,
                smtp_password=settings.email_smtp_password,
                from_address=settings.email_from,
            ))
        if settings.webhook_urls:
            for i, url in enumerate(settings.webhook_urls.split(",")):
                url = url.strip()
                if url:
                    registry.register(WebhookChannel(
                        url=url, channel_id=f"webhook_{i}", label=f"Webhook {i}",
                    ))
    except Exception:
        pass

    # If channel not found, try to use it as a webhook
    try:
        registry.get(channel_id)
    except KeyError:
        registry.register(WebhookChannel(channel_id=channel_id, label=channel_id))

    result = await registry.send_to(channel_id, to, text)
    if result.success:
        logger.info(f"Sent to {channel_id}: {result.message_id}")
    else:
        logger.error(f"Failed: {result.error}")


async def run_list_channels():
    """List registered channels"""
    from src.command.channels import ChannelRegistry, WebhookChannel, SlackChannel, TeamsChannel, EmailChannel

    registry = ChannelRegistry()

    try:
        from config.settings import settings

        if settings.slack_webhook_url or settings.slack_bot_token:
            registry.register(SlackChannel(
                webhook_url=settings.slack_webhook_url,
                bot_token=settings.slack_bot_token,
                default_channel=settings.slack_default_channel,
            ))
        if settings.teams_webhook_url:
            registry.register(TeamsChannel(webhook_url=settings.teams_webhook_url))
        if settings.email_smtp_host:
            registry.register(EmailChannel(
                smtp_host=settings.email_smtp_host,
                smtp_port=settings.email_smtp_port,
                smtp_user=settings.email_smtp_user,
                smtp_password=settings.email_smtp_password,
                from_address=settings.email_from,
            ))
        if settings.webhook_urls:
            for i, url in enumerate(settings.webhook_urls.split(",")):
                url = url.strip()
                if url:
                    registry.register(WebhookChannel(
                        url=url, channel_id=f"webhook_{i}", label=f"Webhook {i}",
                    ))
    except Exception:
        pass

    channels = registry.list_channels()
    if not channels:
        print("No channels registered. Set environment variables to configure channels.")
        return

    print(f"\nRegistered Channels ({len(channels)}):")
    for ch in channels:
        print(f"  [{ch['id']}] {ch['label']} - {ch['description']}")


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
        asyncio.run(run_ai_agent(
            task, proxy_type, options["captcha_solver"],
            options["llm_provider"], options["llm_base_url"], options["llm_model"],
        ))

    elif command == "parallel":
        if len(args) < 1:
            print("Error: Tasks required")
            sys.exit(1)
        asyncio.run(run_parallel_ai(
            args, proxy_type, options["captcha_solver"],
            options["llm_provider"], options["llm_base_url"], options["llm_model"],
        ))

    elif command == "score":
        asyncio.run(run_score_demo())

    elif command == "notify":
        # Parse --channel and --to
        channel_id = "webhook"
        to = ""
        text_parts = []
        i = 0
        while i < len(args):
            if args[i] == "--channel" and i + 1 < len(args):
                channel_id = args[i + 1]
                i += 2
            elif args[i] == "--to" and i + 1 < len(args):
                to = args[i + 1]
                i += 2
            else:
                text_parts.append(args[i])
                i += 1
        text = " ".join(text_parts)
        if not text:
            print("Error: Message text required")
            sys.exit(1)
        asyncio.run(run_notify(channel_id, to, text))

    elif command == "channels":
        asyncio.run(run_list_channels())

    elif command == "vault":
        run_vault(args)

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


def run_vault(args: list[str]):
    """Manage encrypted credential vault"""
    from src.security.vault import SecureVault
    from config.settings import settings

    vault = SecureVault(vault_dir=settings.vault_dir)

    if not args:
        print("Usage: python run.py vault <init|set|get|list|delete|rotate>")
        sys.exit(1)

    subcmd = args[0].lower()

    if subcmd == "init":
        vault.init()
        print(f"Vault initialized at {settings.vault_dir}")

    elif subcmd == "set":
        if len(args) < 3:
            print("Usage: python run.py vault set <key> <value>")
            sys.exit(1)
        vault.init()
        vault.set(args[1], args[2])
        print(f"Set: {args[1]}")

    elif subcmd == "get":
        if len(args) < 2:
            print("Usage: python run.py vault get <key>")
            sys.exit(1)
        vault.init()
        value = vault.get(args[1])
        if value is None:
            print(f"Key not found: {args[1]}")
            sys.exit(1)
        print(value)

    elif subcmd == "list":
        vault.init()
        keys = vault.list_keys()
        if not keys:
            print("Vault is empty")
        else:
            for k in keys:
                print(f"  {k}")

    elif subcmd == "delete":
        if len(args) < 2:
            print("Usage: python run.py vault delete <key>")
            sys.exit(1)
        vault.init()
        if vault.delete(args[1]):
            print(f"Deleted: {args[1]}")
        else:
            print(f"Key not found: {args[1]}")
            sys.exit(1)

    elif subcmd == "rotate":
        vault.init()
        vault.rotate_keys()
        print("Key rotation complete")

    else:
        print(f"Unknown vault command: {subcmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
