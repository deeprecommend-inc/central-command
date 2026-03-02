# CCP - Central Command Post

<p align="center">
  <img src="public/logo.png" alt="CCP Logo" width="200">
</p>

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

### Install (macOS / Ubuntu / WSL2)

```bash
# One-command setup: installs all dependencies, Ollama, default model, and Playwright
./setup.sh

# Options
./setup.sh --model hermes3     # Pull a different model
./setup.sh --skip-model        # Skip model download
```

Or install manually:

```bash
pip install -r requirements.txt
playwright install
playwright install-deps  # Linux only
cp .env.example .env
```

### Option A: Run with a local LLM (no API key)

```bash
# If you used setup.sh, Ollama and dolphin3 are already installed.
# Otherwise:
#   macOS:        brew install ollama
#   Ubuntu/WSL2:  curl -fsSL https://ollama.com/install.sh | sh
ollama serve

# Pull additional models (optional)
ollama pull hermes3         # Nous Hermes 3 (8B)
ollama pull mythomax        # MythoMax-L2 (13B)

# Run
python run.py --no-proxy "Go to example.com and get the page title"
```

### Option B: Run with a cloud LLM

```bash
# Set your API key in .env
echo "LLM_PROVIDER=openai" >> .env
echo "LLM_API_KEY=sk-your-key" >> .env

# Run
python run.py --no-proxy "Go to example.com and get the page title"
```

## Usage

```bash
python run.py [options] "<prompt>"
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--model <name>` | `-m` | LLM model (default: `dolphin3`) |
| `--parallel <n>` | `-p` | Parallel workers (default: 1) |
| `--area <code>` | `-a` | Country code for proxy (default: `us`) |
| `--timezone <tz>` | `-t` | Timezone override (default: auto from area) |
| `--mode <mode>` | `-M` | Execution mode: `browser-use` (default) or `scrapling` |
| `--no-proxy` | | Direct connection (no proxy) |
| `--verbose` | `-v` | Debug logging |

### Examples

```bash
# No proxy, default local LLM
python run.py --no-proxy "Go to example.com and get the page title"

# Specify model
python run.py -m hermes3 --no-proxy "Search google for AI news"

# With SmartProxy ISP (Japan IP)
python run.py -a jp "Go to https://httpbin.org/ip and get the IP"

# Parallel execution (3 workers, US area)
python run.py -p 3 -a us "Go to https://httpbin.org/ip and get the IP"
```

### Scrapling Stealth Mode

Scrapling provides anti-bot stealth (TLS fingerprint spoofing, CDP runtime patches, Cloudflare bypass) for single-page fetching.

```bash
# Install scrapling
pip install "scrapling[fetchers]" && scrapling install

# Stealth fetch
python run.py -M scrapling --no-proxy "https://example.com"

# With proxy (Japan IP)
python run.py -M scrapling -a jp "https://httpbin.org/ip"

# Cloudflare bypass
SOLVE_CLOUDFLARE=true python run.py -M scrapling "https://target.com"
```

### Local LLM

Set local LLM as the default in `.env`:

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
# OpenAI
LLM_PROVIDER=openai LLM_API_KEY=sk-xxx python run.py --no-proxy "Go to example.com"

# Anthropic Claude
LLM_PROVIDER=anthropic LLM_API_KEY=sk-ant-xxx python run.py -m claude-sonnet-4-20250514 --no-proxy "Search for AI news"
```

Supported cloud models: gpt-4o, gpt-4o-mini, o1, o3-mini, claude-sonnet-4-20250514, claude-opus-4-20250514

### Proxy (SmartProxy ISP)

Each parallel worker automatically gets a unique sticky IP + user agent via SmartProxy ISP (Decodo). Optional -- runs with direct connection if not configured.

```bash
# Set credentials in .env
SMARTPROXY_USERNAME=your-username
SMARTPROXY_PASSWORD=your-password
SMARTPROXY_AREA=us

# Single task with proxy
python run.py "Go to https://httpbin.org/ip and get the IP"

# Japan IP
python run.py -a jp "Go to https://httpbin.org/ip and get the IP"

# 5 parallel workers, each with unique IP
python run.py -p 5 -a us "Go to https://httpbin.org/ip and get the IP"

# No proxy
python run.py --no-proxy "Go to example.com"
```

Supported area codes (60+ countries):

| Region | Codes |
|--------|-------|
| North America | `us`, `ca`, `mx` |
| South America | `br`, `ar`, `cl`, `co`, `pe` |
| Europe - Western | `gb`, `de`, `fr`, `es`, `it`, `pt`, `nl`, `be`, `ch`, `at`, `ie` |
| Europe - Northern | `se`, `no`, `dk`, `fi` |
| Europe - Eastern | `pl`, `cz`, `ro`, `hu`, `ua`, `bg`, `hr`, `sk`, `rs`, `gr` |
| Europe - Other | `ru`, `tr` |
| Middle East | `il`, `ae`, `sa`, `qa` |
| Africa | `za`, `ng`, `eg`, `ke`, `ma`, `gh` |
| East Asia | `jp`, `kr`, `cn`, `tw`, `hk`, `mn` |
| Southeast Asia | `sg`, `th`, `vn`, `id`, `my`, `ph` |
| South Asia | `in`, `pk`, `bd`, `lk` |
| Oceania | `au`, `nz` |

Each area automatically sets the correct locale and timezone for the browser profile.

### Browser Fingerprints (GoLogin)

For realistic browser fingerprints (user agent, viewport, platform), configure GoLogin API:

1. Create a GoLogin account at https://gologin.com
2. Go to Settings -> API Documentation -> Generate New Token
3. Set the token in `.env`:

```bash
GOLOGIN_API_TOKEN=your-token-here
```

When configured, each browser session gets a realistic fingerprint from the GoLogin API.
When not configured (or if the API is unavailable), falls back to random user agent generation.

### CAPTCHA Solving

AI agent detects and solves CAPTCHAs using Vision AI, with fallback to token-based services.

```bash
# Vision solver (default, uses the configured LLM)
python run.py --no-proxy "Log in to https://protected-site.com"
```

### Notifications

Dispatch alerts to Slack, Teams, Email, or webhooks (via API server).

### Lightweight Browser Runner

```bash
python browse.py "Go to google.com and search for python"
python browse.py --model dolphin3 "Open https://example.com"
```

### Session Persistence (Login Once, Stay Logged In)

Chrome sessions are persisted to disk so you can log in once and stay logged in across runs.

```bash
# Set SESSION_DIR in .env
SESSION_DIR=./sessions/default
```

### Workflow with Human-in-the-Loop

```bash
python server.py

curl -X POST http://localhost:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"target": "https://example.com", "task_type": "navigate", "enable_approval": true, "confidence_threshold": 0.7}'
```

### Replay and Policy Comparison

```bash
python simulate.py stats experiences.json
python simulate.py replay experiences.json --episodes 20
python simulate.py compare experiences.json --episodes 10
```

### Credential Vault (PQC)

Store secrets encrypted with post-quantum cryptography.

```bash
python -c "from src.security.vault import SecureVault; v = SecureVault(); v.init(); v.set('KEY', 'value'); print(v.get('KEY'))"
```

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
| `LLM_PROVIDER` | No | `openai`, `anthropic`, or `local` (default: `local`) |
| `LLM_BASE_URL` | For local | Local LLM server URL (e.g. `http://localhost:11434/v1`) |
| `LLM_MODEL` | No | Model name (default: `dolphin3`) |
| `LLM_API_KEY` | For cloud | API key (not needed for local) |
| `OPENAI_API_KEY` | No | Legacy fallback for `LLM_API_KEY` |
| `ANTHROPIC_API_KEY` | No | For Claude models |

### Browser Fingerprint (GoLogin)

| Variable | Required | Description |
|----------|----------|-------------|
| `GOLOGIN_API_TOKEN` | No | GoLogin API token for realistic browser fingerprints (fallback: random UA) |

### Proxy (SmartProxy ISP)

| Variable | Required | Description |
|----------|----------|-------------|
| `SMARTPROXY_USERNAME` | No | SmartProxy ISP username (direct connection if empty) |
| `SMARTPROXY_PASSWORD` | No | SmartProxy ISP password |
| `SMARTPROXY_HOST` | No | SmartProxy host (default: `isp.decodo.com`) |
| `SMARTPROXY_PORT` | No | SmartProxy port (default: `10001`) |
| `SMARTPROXY_AREA` | No | Default country code (default: `us`) |
| `SMARTPROXY_TIMEZONE` | No | Timezone override (default: auto from area) |
| `HEADLESS` | No | Headless mode (default: true) |
| `SOLVE_CLOUDFLARE` | No | Enable Cloudflare bypass in scrapling mode (default: false) |

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
