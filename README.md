# Web Agent - プロキシ & ユーザーエージェント管理付きブラウザ自動化

プロンプトからWeb操作エージェントを実行する際に、プロキシローテーションとユーザーエージェントを使用するPythonフレームワーク。

## 機能

- **プロキシローテーション** - BrightData連携による自動IPローテーション
- **住宅IP (Residential)** - デフォルトで住宅IPを使用
- **ユーザーエージェント管理** - セッションごとに一貫したUA/フィンガープリント
- **並列処理** - 最大5並列のブラウザセッション
- **Playwright** - 高速で安定したブラウザ自動化

## プロジェクト構造

```
sns-agent/
├── .env.example              # 環境変数テンプレート
├── requirements.txt          # 依存関係
├── main.py                   # エントリーポイント
├── config/
│   └── settings.py           # 設定管理
└── src/
    ├── proxy_manager.py      # プロキシローテーション
    ├── ua_manager.py         # ユーザーエージェント管理
    ├── browser_worker.py     # ブラウザワーカー
    ├── parallel_controller.py # 並列処理コントローラー
    └── web_agent.py          # メインエージェント
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

# 5. 環境変数を設定
cp .env.example .env
# .envファイルを編集してBrightDataの認証情報を設定
```

## 設定

`.env`ファイルを編集:

```env
# BrightData Proxy Settings
BRIGHTDATA_USERNAME=your_username
BRIGHTDATA_PASSWORD=your_password
BRIGHTDATA_HOST=brd.superproxy.io
BRIGHTDATA_PORT=22225
BRIGHTDATA_PROXY_TYPE=residential  # residential, datacenter, mobile, isp

# Browser Settings
HEADLESS=true
PARALLEL_SESSIONS=5

# OpenAI API (browser-use使用時)
OPENAI_API_KEY=your_openai_api_key
```

### プロキシタイプ

| タイプ | 説明 |
|-------|------|
| `residential` | 住宅IP（デフォルト・推奨） |
| `datacenter` | データセンターIP |
| `mobile` | モバイルIP |
| `isp` | ISP IP |

## 使用方法

### コマンドライン

```bash
# 単一URL
python main.py https://example.com

# デモ（複数URL並列）
python main.py
```

### Pythonコード

```python
import asyncio
from src import WebAgent
from src.web_agent import AgentConfig

async def main():
    # 設定
    config = AgentConfig(
        brightdata_username="your_username",
        brightdata_password="your_password",
        proxy_type="residential",  # 住宅IP
        parallel_sessions=5,
        headless=True,
    )

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

## 依存関係

- Python 3.10+
- playwright
- fake-useragent
- aiohttp
- python-dotenv
- loguru
- pydantic
