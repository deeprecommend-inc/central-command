# CCP - Central Command Platform

産業現場の「判断」と「指示」を担うAI中央指揮所

## コンセプト

CCPは、点在するデータ、分断された判断、属人化した運用を統合し、
「状況把握 → 判断 → 指示 → 実行監視」をAIで自動化・高速化する。

```
[Sense] → [Think] → [Command] → [Control] → [Learn]
   ↓         ↓          ↓           ↓          ↓
 状況認識   判断      指示生成    実行監視    学習・知識化
```

## CCPの本質的価値

- AIは分析係ではなく「指揮官」
- データを見るAIではなく、動かすAI
- 単体AIではなく、全体を統べるOS
- 現場・経営・システムを貫く意思決定中枢

---

# Web操作エージェント（Command層の実装）

プロンプトからWeb操作エージェントを実行するPythonフレームワーク。

## 機能

- **プロキシローテーション** - BrightData連携による自動IPローテーション（オプション）
- **住宅IP (Residential)** - デフォルトで住宅IPを使用
- **ユーザーエージェント管理** - セッションごとに一貫したUA/フィンガープリント
- **並列処理** - 最大5並列のブラウザセッション
- **自動リトライ** - 指数バックオフによる再試行
- **プロキシ自動切替** - 接続エラー時に新しいプロキシへ自動切替
- **AI駆動** - browser-useによる自然言語Web操作

## プロジェクト構造

```
sns-agent/
├── .env.example              # 環境変数テンプレート
├── requirements.txt          # 依存関係
├── run.py                    # CLIエントリーポイント
├── main.py                   # Pythonエントリーポイント
├── config/
│   └── settings.py           # 設定管理
└── src/
    ├── proxy_manager.py      # プロキシローテーション
    ├── ua_manager.py         # ユーザーエージェント管理
    ├── browser_worker.py     # ブラウザワーカー
    ├── parallel_controller.py # 並列処理コントローラー
    ├── web_agent.py          # メインエージェント
    └── browser_use_agent.py  # AI駆動エージェント
```

## インストール

```bash
# 1. リポジトリをクローン
git clone <repository-url>
cd sns-agent

# 2. 仮想環境を作成
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# または
.\venv\Scripts\activate   # Windows

# 3. 依存関係をインストール
pip install -r requirements.txt

# 4. Playwrightブラウザをインストール
playwright install chromium
playwright install-deps chromium  # Linux: システム依存関係

# 5. 環境変数を設定（オプション）
cp .env.example .env
```

## 環境変数

| 変数 | 必須 | 説明 |
|------|------|------|
| BRIGHTDATA_USERNAME | No | BrightDataユーザー名（未設定時は直接接続） |
| BRIGHTDATA_PASSWORD | No | BrightDataパスワード |
| BRIGHTDATA_HOST | No | プロキシホスト（デフォルト: brd.superproxy.io） |
| BRIGHTDATA_PORT | No | プロキシポート（デフォルト: 22225） |
| BRIGHTDATA_PROXY_TYPE | No | residential/datacenter/mobile/isp |
| OPENAI_API_KEY | AIモードのみ | OpenAI APIキー |
| PARALLEL_SESSIONS | No | 並列数（デフォルト: 5） |
| HEADLESS | No | ヘッドレス実行（デフォルト: true） |

### プロキシタイプ

| タイプ | 説明 |
|-------|------|
| `residential` | 住宅IP（デフォルト） |
| `datacenter` | データセンターIP |
| `mobile` | モバイルIP |
| `isp` | ISP IP |

## 使用方法

### CLI

```bash
# 単一URL（プロキシなしでも動作）
python run.py url https://httpbin.org/ip

# 複数URL並列
python run.py url https://example.com https://google.com https://github.com

# AI駆動タスク（OPENAI_API_KEY必須）
python run.py ai "Go to google.com and search for python"

# 複数AIタスク並列
python run.py parallel "Search for python" "Search for javascript"

# デモ
python run.py demo

# テスト
python run.py test

# ヘルプ
python run.py --help
```

### Pythonコード

```python
import asyncio
from src import WebAgent
from src.web_agent import AgentConfig

async def main():
    # プロキシなしで動作
    config = AgentConfig(
        parallel_sessions=5,
        headless=True,
    )

    # プロキシありの場合
    # config = AgentConfig(
    #     brightdata_username="your_username",
    #     brightdata_password="your_password",
    #     proxy_type="residential",  # 住宅IP
    #     parallel_sessions=5,
    #     headless=True,
    # )

    agent = WebAgent(config)

    try:
        # 単一URLにアクセス
        result = await agent.navigate("https://httpbin.org/ip")
        if result.success:
            print(f"Title: {result.data.get('title')}")
            print(f"URL: {result.data.get('url')}")

        # 複数URLに並列アクセス
        urls = [
            "https://httpbin.org/ip",
            "https://httpbin.org/user-agent",
            "https://httpbin.org/headers",
        ]
        results = await agent.parallel_navigate(urls)

        for i, r in enumerate(results):
            print(f"URL {i+1}: {'Success' if r.success else r.error}")

        # プロキシ統計
        print(agent.get_proxy_stats())

    finally:
        await agent.cleanup()

asyncio.run(main())
```

### カスタムタスク

```python
from src.browser_worker import BrowserWorker, WorkerResult

async def custom_task(worker: BrowserWorker) -> WorkerResult:
    # ページにアクセス
    await worker.navigate("https://example.com")

    # 要素をクリック
    await worker.click("button#submit")

    # フォームに入力
    await worker.fill("input#search", "検索ワード")

    # スクリーンショット
    await worker.screenshot("/tmp/screenshot.png")

    # JavaScript実行
    result = await worker.evaluate("document.title")

    return WorkerResult(success=True, data={"title": result.data})

# 実行
result = await agent.run_custom_task("my_task", custom_task)
```

### AI駆動タスク

```python
from src.browser_use_agent import BrowserUseAgent, BrowserUseConfig

config = BrowserUseConfig(
    openai_api_key="your_key",
    model="gpt-4o",
    headless=True,
)

agent = BrowserUseAgent(config)

# 自然言語でタスク実行
result = await agent.run("Go to google.com and search for 'python programming'")

# 複数タスク並列実行
results = await agent.run_parallel([
    "Search for python on google",
    "Search for javascript on google",
], max_concurrent=5)
```

## API リファレンス

### WebAgent

| メソッド | 説明 |
|---------|------|
| `navigate(url)` | 単一URLにアクセス |
| `parallel_navigate(urls)` | 複数URLに並列アクセス |
| `run_custom_task(task_id, task_fn)` | カスタムタスクを実行 |
| `run_custom_tasks_parallel(tasks)` | カスタムタスクを並列実行 |
| `get_proxy_stats()` | プロキシ統計を取得 |
| `cleanup()` | リソースを解放 |

### BrowserWorker

| メソッド | 説明 |
|---------|------|
| `navigate(url)` | URLにアクセス |
| `get_content()` | ページコンテンツを取得 |
| `click(selector)` | 要素をクリック |
| `fill(selector, value)` | 入力フィールドに値を設定 |
| `screenshot(path)` | スクリーンショットを保存 |
| `evaluate(script)` | JavaScriptを実行 |
| `wait_for_selector(selector)` | 要素の出現を待機 |

### BrowserUseAgent

| メソッド | 説明 |
|---------|------|
| `run(task)` | 自然言語タスクを実行 |
| `run_parallel(tasks, max_concurrent)` | 複数タスクを並列実行 |

### ParallelController

| 設定 | デフォルト | 説明 |
|------|-----------|------|
| `max_workers` | 5 | 最大並列数 |
| `max_retries` | 3 | 最大リトライ回数 |
| `BASE_DELAY` | 1.0s | リトライ基本待機時間 |
| `MAX_DELAY` | 30.0s | リトライ最大待機時間 |

## エラーハンドリング

### 自動リトライ

プロキシ関連のエラー時に自動的にリトライ:

- 指数バックオフ: 1s → 2s → 4s → ... (最大30s)
- 新しいプロキシで再試行
- 最大3回リトライ

### 対象エラー

- connection refused
- connection reset
- timeout
- proxy errors

## 依存関係

- Python 3.10+
- playwright
- browser-use
- fake-useragent
- aiohttp
- python-dotenv
- loguru
- pydantic
- pydantic-settings
