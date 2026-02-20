# CCP - Central Command Post

An AI-powered command center that automates decision-making and execution for industrial operations.

CCP integrates scattered data, fragmented decisions, and manual operations into a unified pipeline:
**Sense -> Think -> Command -> Control -> Learn**

## What CCP Does

- Aggregates real-time data from IoT, sensors, databases, and AI inference results
- Makes prioritized decisions based on rules, AI, and simulation
- Dispatches instructions to people (Slack, Teams, Email) and systems (API, webhooks)
- Monitors execution and automatically escalates when needed
- Learns from outcomes to continuously improve decisions
- Works with local LLMs (Ollama, LM Studio, vLLM) -- no cloud API key required

## Quick Start

### Prerequisites

- Python 3.10+
- A local LLM server (Ollama, LM Studio, vLLM, etc.) **or** a cloud API key (OpenAI / Anthropic)

### Install

```bash
pip install -r requirements.txt
playwright install
playwright install-deps  # Linux only
cp .env.example .env
```

### Option A: Run with a local LLM (no API key)

```bash
# 1. Install and start Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama serve

# 2. Pull a model
ollama pull dolphin3        # Dolphin 3.0 (8B) -- recommended
ollama pull hermes3         # Nous Hermes 3 (8B)
ollama pull mythomax        # MythoMax-L2 (13B)

# 3. Run
python run.py ai --local --no-proxy "Go to example.com and get the page title"
```

### Option B: Run with a cloud LLM

```bash
# Set your API key in .env
echo "OPENAI_API_KEY=sk-your-key" >> .env

# Run
python run.py ai --no-proxy "Go to example.com and get the page title"
```

## Usage

### Local LLM

All `ai` and `parallel` commands accept `--local` to use a local LLM server with no API key.

```bash
# Default: Ollama + dolphin3
python run.py ai --local "Fill in the contact form on example.com" --no-proxy

# Specify model
python run.py ai --local --llm-model hermes3 "Search google for AI news" --no-proxy

# Specify server URL (LM Studio, vLLM, etc.)
python run.py ai --llm-base-url http://localhost:1234/v1 --llm-model mythomax "Navigate to github.com" --no-proxy

# Parallel tasks
python run.py parallel --local "task one" "task two" "task three" --no-proxy

# browse.py (lightweight runner)
python browse.py --local "Go to google.com and search for python"
python browse.py --local --model dolphin3 "Open https://example.com"
python browse.py --base-url http://localhost:8000/v1 --model hermes3 "Search for news"
```

You can also set local LLM as the default in `.env` so `--local` is not needed:

```bash
LLM_PROVIDER=local
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=dolphin3
```

Supported local LLM servers:

| Server | Default URL | Start Command |
|--------|------------|---------------|
| Ollama | `http://localhost:11434/v1` | `ollama serve` |
| LM Studio | `http://localhost:1234/v1` | Start in GUI |
| vLLM | `http://localhost:8000/v1` | `vllm serve <model>` |
| llama.cpp | `http://localhost:8080/v1` | `llama-server -m <model>` |
| LocalAI | `http://localhost:8080/v1` | `local-ai` |

Tested local models:

| Model | Size | Pull Command |
|-------|------|-------------|
| Dolphin 3.0 | 8B | `ollama pull dolphin3` |
| Nous Hermes 3 | 8B | `ollama pull hermes3` |
| Chronos-Hermes 13B v2 | 13B | `ollama pull chronos-hermes:13b` |
| MythoMax-L2 | 13B | `ollama pull mythomax` |
| LLaMA 3 Dark (MoE) | 18.4B | `ollama pull llama3-dark` |
| Llama 2 Uncensored | 7B-13B | `ollama pull llama2-uncensored` |
| WizardLM Uncensored | 13B | `ollama pull wizardlm-uncensored:13b` |

### Cloud LLM

```bash
# OpenAI (default)
python run.py ai "Go to example.com, fill in the form, and submit" --no-proxy

# Anthropic Claude
python browse.py --model claude-sonnet-4-20250514 "Search for AI news"

# Specific OpenAI model
python browse.py --model gpt-4o-mini "Open https://example.com"
python browse.py --show "Open https://example.com"  # visible browser
```

Supported cloud models: gpt-4o, gpt-4o-mini, o1, o3-mini, claude-sonnet-4-20250514, claude-opus-4-20250514

### Proxy Rotation

Rotate through residential, mobile, datacenter, or ISP IPs via BrightData. Optional -- runs with direct connection if not configured.

```bash
# Residential IP (default)
python run.py url -r https://example.com

# Mobile IP
python run.py url -m https://mobile-only-site.com

# Multiple URLs in parallel
python run.py url https://site-a.com https://site-b.com https://site-c.com

# No proxy
python run.py url --no-proxy https://example.com

# Health check
python run.py health
```

### CAPTCHA Solving

AI agent detects and solves CAPTCHAs using Vision AI, with fallback to token-based services.

```bash
# Vision solver (default, uses the configured LLM)
python run.py ai --captcha-solver vision "Log in to https://protected-site.com"

# 2captcha fallback
python run.py ai --captcha-solver 2captcha "Submit the registration form"

# Local LLM + CAPTCHA (if model supports vision)
python run.py ai --local --captcha-solver vision "Solve the CAPTCHA on example.com" --no-proxy
```

### Notifications

Dispatch alerts to Slack, Teams, Email, or webhooks.

```bash
python run.py channels
python run.py notify --channel slack --to "#ops" "CPU usage exceeded 90%"
python run.py notify --channel webhook --to "https://your-endpoint.com/alert" "Disk full on node-3"
```

### Workflow with Human-in-the-Loop

Submit a task via API. When AI confidence is below the threshold, it pauses for human approval.

```bash
python server.py

curl -X POST http://localhost:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"target": "https://example.com", "task_type": "navigate", "enable_approval": true, "confidence_threshold": 0.7}'

curl http://localhost:8000/approvals

curl -X POST http://localhost:8000/approvals/{request_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "admin@example.com", "reason": "Verified safe"}'
```

### Real-time Event Stream

```bash
python server.py
```

```python
import asyncio, websockets

async def listen():
    async with websockets.connect("ws://localhost:8000/ws/events") as ws:
        while True:
            print(await ws.recv())

asyncio.run(listen())
```

### Replay and Policy Comparison

Replay recorded experiences against different policies to find the best strategy.

```bash
python simulate.py stats experiences.json
python simulate.py replay experiences.json --episodes 20
python simulate.py compare experiences.json --episodes 10
```

### Credential Vault (PQC)

Store secrets encrypted with post-quantum cryptography.

```bash
python run.py vault init
python run.py vault set OPENAI_API_KEY sk-your-key-here
python run.py vault get OPENAI_API_KEY
python run.py vault list
python run.py vault rotate
```

### Audit Trail

Every LLM call and decision is logged with a cryptographic signature.

```python
from src.security import PQCEngine, AuditLogger

engine = PQCEngine()
signing_kp = engine.generate_signing_keypair()
audit = AuditLogger(pqc_engine=engine, signing_keypair=signing_kp, log_file="audit.jsonl")

audit.log_event("deployment", input_hash="abc", output_hash="def")

valid, invalid = audit.verify_all()
print(f"{valid} valid, {invalid} invalid")
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `python run.py url <urls...>` | Navigate to one or more URLs |
| `python run.py ai "<instruction>"` | Run AI browser agent |
| `python run.py parallel "<t1>" "<t2>"` | Run multiple AI tasks in parallel |
| `python run.py demo` | Run demo |
| `python run.py health` | Proxy health check |
| `python run.py channels` | List notification channels |
| `python run.py notify` | Send notification |
| `python run.py vault <cmd>` | Manage encrypted vault |
| `python browse.py "<instruction>"` | Run browser-use directly |
| `python simulate.py stats <file>` | Experience statistics |
| `python simulate.py replay <file>` | Replay with policy |
| `python simulate.py compare <file>` | Compare policies |

### CLI Options

| Option | Short | Description |
|--------|-------|-------------|
| `--local` | | Use local LLM (no API key needed) |
| `--llm-base-url <url>` | | Local LLM server URL (default: `http://localhost:11434/v1`) |
| `--llm-model <name>` | | LLM model name (e.g. `dolphin3`, `hermes3`) |
| `--residential` | `-r` | Residential IP (default) |
| `--mobile` | `-m` | Mobile IP |
| `--datacenter` | `-d` | Datacenter IP |
| `--isp` | `-i` | ISP IP |
| `--no-proxy` | | Direct connection (no BrightData) |
| `--captcha-solver <type>` | | `vision` (default), `2captcha`, `anti-captcha` |
| `--json` | | JSON log output |
| `-v` | | Verbose logging (DEBUG) |

## API Server

```bash
python server.py                # Start on default port
python server.py --port 8080    # Custom port
python server.py --reload       # Development mode
python server.py --workers 4    # Multiple workers
```

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health check |
| GET | `/stats` | Statistics |
| POST | `/tasks` | Create task |
| POST | `/workflow` | Run workflow |
| GET | `/approvals` | List pending approvals |
| POST | `/approvals/{id}/approve` | Approve |
| POST | `/approvals/{id}/reject` | Reject |
| GET | `/thoughts` | List thought chains |
| GET | `/experiences` | List experiences |
| GET | `/channels` | List channels |
| POST | `/channels/{id}/send` | Send to channel |
| POST | `/channels/broadcast` | Broadcast to all |
| GET | `/channels/health` | Channel health |
| WS | `/ws/events` | Real-time event stream |

OpenAPI Docs: `http://localhost:8000/docs`

## Docker

```bash
docker-compose up -d                       # Basic (with ChromaDB)
docker-compose --profile qdrant up -d      # With Qdrant
docker-compose --profile full up -d        # Full stack (including Redis)
docker-compose logs -f ccp-api             # View logs
```

## Environment Variables

### LLM

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_PROVIDER` | No | `openai`, `anthropic`, or `local` (default: `openai`) |
| `LLM_BASE_URL` | For local | Local LLM server URL (e.g. `http://localhost:11434/v1`) |
| `LLM_MODEL` | No | Model name (default: `gpt-4o`) |
| `LLM_API_KEY` | For cloud | API key (not needed for local) |
| `OPENAI_API_KEY` | No | Legacy fallback for `LLM_API_KEY` |
| `ANTHROPIC_API_KEY` | No | For Claude models |

### Proxy

| Variable | Required | Description |
|----------|----------|-------------|
| `BRIGHTDATA_USERNAME` | No | BrightData username (direct connection if unset) |
| `BRIGHTDATA_PASSWORD` | No | BrightData password |
| `BRIGHTDATA_PROXY_TYPE` | No | `residential` / `datacenter` / `mobile` / `isp` |
| `PARALLEL_SESSIONS` | No | Parallel sessions (default: 5) |
| `HEADLESS` | No | Headless mode (default: true) |

### CAPTCHA

| Variable | Required | Description |
|----------|----------|-------------|
| `TWOCAPTCHA_API_KEY` | No | 2captcha fallback |
| `ANTICAPTCHA_API_KEY` | No | Anti-Captcha fallback |

### Notification Channels

| Variable | Description |
|----------|-------------|
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |
| `SLACK_BOT_TOKEN` | Slack Bot Token |
| `SLACK_DEFAULT_CHANNEL` | Default Slack channel |
| `TEAMS_WEBHOOK_URL` | Teams Incoming Webhook URL |
| `EMAIL_SMTP_HOST` | SMTP server host |
| `EMAIL_SMTP_PORT` | SMTP port (default: 587) |
| `EMAIL_SMTP_USER` | SMTP username |
| `EMAIL_SMTP_PASSWORD` | SMTP password |
| `EMAIL_FROM` | Sender email address |
| `WEBHOOK_URLS` | Comma-separated webhook URLs |

### Security

| Variable | Description |
|----------|-------------|
| `CCP_VAULT_ENABLED` | Enable credential vault (default: false) |
| `CCP_VAULT_DIR` | Vault storage directory (default: `.ccp_vault`) |

## Testing

```bash
pytest tests/ -v              # Run all tests
pytest tests/ --cov=src       # With coverage
pytest tests/test_security/ -v  # Security tests only
```
