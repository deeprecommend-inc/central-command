#!/usr/bin/env python3
"""
Simple browser-use runner - No proxy, no UA rotation
Uses Playwright's Chromium with CDP connection
"""
import asyncio
import sys
import os
import subprocess
import time
import signal
import requests
from dotenv import load_dotenv

load_dotenv()

CHROME_PATH = "/root/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome"
CDP_PORT = 9222


def launch_browser(headless: bool = True) -> tuple[subprocess.Popen, str]:
    """Launch Chrome with CDP and return process + websocket URL"""
    headless_arg = "--headless=new" if headless else ""
    args = [
        CHROME_PATH,
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-debugging-address=127.0.0.1",
    ]
    if headless:
        args.insert(1, "--headless=new")

    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Wait for CDP to be ready
    for _ in range(30):
        try:
            resp = requests.get(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=1)
            data = resp.json()
            ws_url = data.get("webSocketDebuggerUrl", "")
            if ws_url:
                return proc, ws_url
        except Exception:
            pass
        time.sleep(0.5)

    proc.terminate()
    raise RuntimeError("Failed to start Chrome with CDP")


def get_llm(model: str = "gpt-4o", base_url: str = ""):
    """Get LLM based on model name and optional base_url for local models"""
    if base_url:
        # Local LLM via OpenAI-compatible API (Ollama, LM Studio, vLLM, etc.)
        from browser_use import ChatOpenAI
        return ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key=os.getenv("LLM_API_KEY", "not-needed"),
        )
    elif model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        from browser_use.llm.openai.chat import ChatOpenAI
        return ChatOpenAI(model=model)
    elif model.startswith("claude"):
        from browser_use.llm.anthropic.chat import ChatAnthropic
        return ChatAnthropic(model=model)
    else:
        # Treat unknown model names as local if LLM_BASE_URL is set
        env_base_url = os.getenv("LLM_BASE_URL", "")
        if env_base_url:
            from browser_use import ChatOpenAI
            return ChatOpenAI(
                model=model,
                base_url=env_base_url,
                api_key=os.getenv("LLM_API_KEY", "not-needed"),
            )
        from browser_use.llm.openai.chat import ChatOpenAI
        return ChatOpenAI(model=model)


async def run(task: str, headless: bool = True, model: str = "gpt-4o", base_url: str = ""):
    from browser_use import Agent
    from browser_use.browser.profile import BrowserProfile

    # Launch browser with CDP
    print(f"Launching browser (headless={headless})...")
    proc, ws_url = launch_browser(headless)
    print(f"Browser ready: {ws_url[:50]}...")

    try:
        llm = get_llm(model, base_url)
        profile = BrowserProfile(cdp_url=ws_url)
        agent = Agent(task=task, llm=llm, browser_profile=profile)

        result = await agent.run()
        print(f"\nResult: {result}")
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def main():
    if len(sys.argv) < 2:
        print("""
browser-use simple runner

Usage:
  python browse.py "<task>"
  python browse.py --show "<task>"
  python browse.py --model claude-sonnet-4-20250514 "<task>"
  python browse.py --local "<task>"
  python browse.py --local --model dolphin3 "<task>"

Options:
  --show              Show browser window (not headless)
  --model <model>     LLM model (default: gpt-4o)
  --local             Use local LLM (Ollama/LM Studio/vLLM)
  --base-url <url>    Local LLM base URL (default: http://localhost:11434/v1)

Cloud Models:
  gpt-4o, gpt-4o-mini, o1, o3-mini
  claude-sonnet-4-20250514, claude-opus-4-20250514

Local Models (via Ollama, LM Studio, vLLM, etc.):
  dolphin3, hermes3, mythomax, llama3.1, wizardlm2, etc.

Environment:
  OPENAI_API_KEY      Required for GPT/o1/o3 models
  ANTHROPIC_API_KEY   Required for Claude models
  LLM_BASE_URL        Local LLM server URL (alternative to --base-url)
  LLM_API_KEY         API key for local server (if required)

Examples:
  python browse.py "Go to google.com and search for python"
  python browse.py --show "Open https://example.com"
  python browse.py --model claude-sonnet-4-20250514 "Search for AI news"
  python browse.py --local "Go to example.com and get the title"
  python browse.py --local --model dolphin3 "Search google for AI"
  python browse.py --base-url http://localhost:1234/v1 --model hermes3 "Navigate to github.com"
""")
        sys.exit(0)

    headless = True
    model = "gpt-4o"
    base_url = ""
    args = sys.argv[1:]

    # Parse options
    filtered_args = []
    i = 0
    while i < len(args):
        if args[i] == "--show":
            headless = False
        elif args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]
            i += 1
        elif args[i] == "--local":
            base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
            if model == "gpt-4o":
                model = "dolphin3"
        elif args[i] == "--base-url" and i + 1 < len(args):
            base_url = args[i + 1]
            i += 1
        else:
            filtered_args.append(args[i])
        i += 1

    task = " ".join(filtered_args)
    if not task:
        print("Error: task required")
        sys.exit(1)

    asyncio.run(run(task, headless, model, base_url))


if __name__ == "__main__":
    main()
