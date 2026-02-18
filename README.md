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

## Quick Start

### Prerequisites

- Python 3.10+

### Setup

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

pip install -r requirements.txt
playwright install
playwright install-deps  # Linux only
```

### Environment Variables

```bash
cp .env.example .env
# Edit .env with your values
```

## Use Cases

### 1. Navigate a site with residential proxy rotation

Rotate through residential IPs to avoid rate limiting or geo-restrictions.

```bash
python run.py url -r https://example.com
```

### 2. Scrape multiple sites in parallel

Process multiple targets concurrently (up to 5 parallel sessions by default).

```bash
python run.py url https://site-a.com https://site-b.com https://site-c.com
```

### 3. Access geo-restricted content via mobile IP

Use mobile carrier IPs for content that blocks datacenter traffic.

```bash
python run.py url -m https://mobile-only-site.com
```

### 4. Automate browser tasks with AI

Give a natural language instruction and let the AI agent operate the browser.

```bash
python run.py ai "Go to https://example.com, fill in the contact form, and submit" --no-proxy
```

### 5. Solve CAPTCHAs automatically during automation

AI agent detects and solves CAPTCHAs using Vision AI, with fallback to token-based services.

```bash
# Vision AI solver (GPT-4o)
python run.py ai --captcha-solver vision "Log in to https://protected-site.com"

# 2captcha fallback
python run.py ai --captcha-solver 2captcha "Submit the registration form"
```

### 6. Run a simple browser task with a specific LLM

Use browser-use directly with your preferred model, without proxy or UA management.

```bash
python browse.py "Go to google.com and search for python"
python browse.py --model claude-sonnet-4-20250514 "Search for AI news"
python browse.py --show "Open https://example.com"  # visible browser
```

Supported models: gpt-4o, gpt-4o-mini, o1, o3-mini, claude-sonnet-4-20250514, claude-opus-4-20250514

### 7. Send alerts to Slack, Teams, Email, or Webhooks

Dispatch notifications to one or multiple channels at once.

```bash
# List configured channels
python run.py channels

# Send to Slack
python run.py notify --channel slack --to "#ops" "CPU usage exceeded 90%"

# Send to a webhook endpoint
python run.py notify --channel webhook --to "https://your-endpoint.com/alert" "Disk full on node-3"
```

### 8. Run a workflow with human-in-the-loop approval

Submit a task via API. When the AI confidence is below the threshold, it pauses and waits for human approval before executing.

```bash
# Start the API server
python server.py

# Submit a workflow that requires approval
curl -X POST http://localhost:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"target": "https://example.com", "task_type": "navigate", "enable_approval": true, "confidence_threshold": 0.7}'

# Check pending approvals
curl http://localhost:8000/approvals

# Approve
curl -X POST http://localhost:8000/approvals/{request_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "admin@example.com", "reason": "Verified safe"}'
```

### 9. Monitor events in real time

Connect via WebSocket to receive live events from the CCP pipeline.

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

### 10. Evaluate and compare decision policies with past data

Replay recorded experiences against different policies to find the best strategy.

```bash
# View experience statistics
python simulate.py stats experiences.json

# Replay with a policy
python simulate.py replay experiences.json --episodes 20

# Compare multiple policies
python simulate.py compare experiences.json --episodes 10
```

### 11. Check proxy health before running tasks

Verify that your proxy pool is healthy and responsive.

```bash
python run.py health
```

### 12. Encrypt credentials with PQC vault

Store API keys and secrets encrypted with post-quantum cryptography. Keys never touch `.env` in plaintext.

```bash
# Initialize vault
python run.py vault init

# Store a secret
python run.py vault set OPENAI_API_KEY sk-your-key-here

# Retrieve
python run.py vault get OPENAI_API_KEY

# List stored keys
python run.py vault list

# Rotate encryption keys
python run.py vault rotate
```

### 13. Tamper-proof decision audit trail

Every LLM call and decision is logged with a cryptographic signature. Verify integrity at any time.

```python
from src.security import PQCEngine, AuditLogger

engine = PQCEngine()
signing_kp = engine.generate_signing_keypair()
audit = AuditLogger(pqc_engine=engine, signing_keypair=signing_kp, log_file="audit.jsonl")

# Entries are signed automatically
audit.log_event("deployment", input_hash="abc", output_hash="def")

# Verify all entries
valid, invalid = audit.verify_all()
print(f"{valid} valid, {invalid} invalid")
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `python run.py url <urls...>` | Navigate to one or more URLs |
| `python run.py ai "<instruction>"` | Run AI browser agent |
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
| `--residential` | `-r` | Residential IP (default) |
| `--mobile` | `-m` | Mobile IP |
| `--datacenter` | `-d` | Datacenter IP |
| `--isp` | `-i` | ISP IP |
| `--no-proxy` | | Direct connection |
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

### Proxy

| Variable | Required | Description |
|----------|----------|-------------|
| `BRIGHTDATA_USERNAME` | No | BrightData username (direct connection if unset) |
| `BRIGHTDATA_PASSWORD` | No | BrightData password |
| `BRIGHTDATA_PROXY_TYPE` | No | residential / datacenter / mobile / isp |
| `PARALLEL_SESSIONS` | No | Parallel sessions (default: 5) |
| `HEADLESS` | No | Headless mode (default: true) |

### AI / CAPTCHA

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | For AI agent / Vision CAPTCHA | OpenAI API key |
| `ANTHROPIC_API_KEY` | For Claude models | Anthropic API key |
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
| `CCP_VAULT_DIR` | Vault storage directory (default: .ccp_vault) |

## Testing

```bash
pytest tests/ -v              # Run all tests
pytest tests/ --cov=src       # With coverage
pytest tests/test_security/ -v  # Security tests only
```
