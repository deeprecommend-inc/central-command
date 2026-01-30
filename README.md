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
- **IPタイプ選択** - 住宅IP / モバイルIP / データセンターIP / ISP IP
- **ユーザーエージェント管理** - セッションごとに一貫したUA/フィンガープリント
- **並列処理** - 最大5並列のブラウザセッション
- **自動リトライ** - 指数バックオフによる再試行
- **プロキシ自動切替** - 接続エラー時に新しいプロキシへ自動切替

## インストール

```bash
# 1. リポジトリをクローン
git clone <repository-url>
cd sns-agent

# 2. 仮想環境を作成
python3 -m venv venv
source venv/bin/activate

# 3. 依存関係をインストール
pip install -r requirements.txt

# 4. Playwrightブラウザをインストール
playwright install chromium
playwright install-deps chromium

# 5. 環境変数を設定（オプション）
cp .env.example .env
```

## 使用方法

### CLI

```bash
# 基本的なURL操作
python run.py url https://example.com

# 複数URL並列
python run.py url https://example.com https://google.com https://github.com

# デモ
python run.py demo

# ヘルプ
python run.py --help
```

### プロキシタイプ選択

```bash
# 住宅IP（デフォルト）
python run.py url https://example.com
python run.py url -r https://example.com
python run.py url --residential https://example.com

# モバイルIP
python run.py url -m https://example.com
python run.py url --mobile https://example.com

# データセンターIP
python run.py url -d https://example.com
python run.py url --datacenter https://example.com

# ISP IP
python run.py url -i https://example.com
python run.py url --isp https://example.com

# プロキシなし（直接接続）
python run.py url --no-proxy https://example.com
python run.py demo --no-proxy
```

### 複数プロキシ・UAで並列実行

```bash
# 5つのURLを異なるプロキシ・UAで並列実行（住宅IP）
python run.py url -r https://site1.com https://site2.com https://site3.com https://site4.com https://site5.com

# モバイルIPで並列実行
python run.py url -m https://site1.com https://site2.com https://site3.com
```

各ブラウザセッションは自動的に:
- 異なるプロキシ（国ローテーション）
- 異なるユーザーエージェント
- 異なるフィンガープリント

を使用します。

### AI駆動ブラウザ操作（browser-use）

自然言語でWeb操作を実行できます。

```bash
# 単一タスク（住宅IP）
python run.py ai "Googleで'Python'を検索してトップ3の結果を取得"

# モバイルIPでAIタスク
python run.py ai -m "Amazonで'laptop'を検索して価格を比較"

# 複数タスクを並列実行（異なるプロキシ・UA）
python run.py parallel "サイトAでログイン" "サイトBでデータ取得" "サイトCでスクリーンショット"

# 異なるIPタイプで並列AI
python run.py parallel -d "タスク1" "タスク2" "タスク3"
```

**注意**: AI機能（browser-use）はWSL環境では現在無効です。ネイティブLinux/Mac環境で使用してください。

### CLIオプション

| オプション | 短縮 | 説明 |
|-----------|------|------|
| `--residential` | `-r` | 住宅IP（デフォルト） |
| `--mobile` | `-m` | モバイルIP |
| `--datacenter` | `-d` | データセンターIP |
| `--isp` | `-i` | ISP IP |
| `--no-proxy` | - | 直接接続（プロキシ無効） |

## 環境変数

| 変数 | 必須 | 説明 |
|------|------|------|
| BRIGHTDATA_USERNAME | No | BrightDataユーザー名（未設定時は直接接続） |
| BRIGHTDATA_PASSWORD | No | BrightDataパスワード |
| BRIGHTDATA_PROXY_TYPE | No | residential/datacenter/mobile/isp |
| PARALLEL_SESSIONS | No | 並列数（デフォルト: 5） |
| HEADLESS | No | ヘッドレス実行（デフォルト: true） |
| OPENAI_API_KEY | No | OpenAI APIキー（AI機能使用時のみ必須） |

## Pythonコード

```python
import asyncio
from src import WebAgent
from src.web_agent import AgentConfig

async def main():
    config = AgentConfig(
        parallel_sessions=5,
        headless=True,
    )

    # コンテキストマネージャーで自動クリーンアップ
    async with WebAgent(config) as agent:
        result = await agent.navigate("https://httpbin.org/ip")
        if result.success:
            print(f"Title: {result.data.get('title')}")

        # 複数URLに並列アクセス
        results = await agent.parallel_navigate([
            "https://httpbin.org/ip",
            "https://httpbin.org/user-agent",
        ])

asyncio.run(main())
```

### プロキシ使用時

```python
async def main():
    config = AgentConfig(
        brightdata_username="your_username",
        brightdata_password="your_password",
        proxy_type="mobile",  # residential/mobile/datacenter/isp
    )

    async with WebAgent(config) as agent:
        # プロキシヘルスチェック
        health = await agent.health_check()
        print(f"Proxy health: {health}")

        result = await agent.navigate("https://httpbin.org/ip")
        print(f"IP: {result.data}")
```

### AI駆動ブラウザ操作（Pythonコード）

```python
import asyncio
from src.browser_use_agent import BrowserUseAgent, BrowserUseConfig

async def main():
    config = BrowserUseConfig(
        brightdata_username="your_username",
        brightdata_password="your_password",
        proxy_type="mobile",  # residential/mobile/datacenter/isp
        openai_api_key="your_openai_key",
        model="gpt-4o",
        headless=True,
    )

    agent = BrowserUseAgent(config)

    # 単一タスク実行
    result = await agent.run("Googleで'AI'を検索してトップ5の結果を取得")
    print(result)

    # 複数タスクを並列実行（各タスクは異なるプロキシ・UAを使用）
    tasks = [
        "サイトAでログインしてダッシュボードを開く",
        "サイトBで商品価格を取得",
        "サイトCでニュースヘッドラインを収集",
    ]
    results = await agent.run_parallel(tasks, max_concurrent=3)
    for r in results:
        print(f"Task {r['index']}: {'Success' if r['success'] else r['error']}")

asyncio.run(main())
```

## API リファレンス

### WebAgent

| メソッド | 説明 |
|---------|------|
| `navigate(url)` | 単一URLにアクセス |
| `parallel_navigate(urls)` | 複数URLに並列アクセス |
| `run_custom_task(task_id, task_fn)` | カスタムタスクを実行 |
| `get_proxy_stats()` | プロキシ統計を取得 |
| `cleanup()` | リソースを解放 |

### BrowserUseAgent（AI駆動）

| メソッド | 説明 |
|---------|------|
| `run(task)` | 自然言語タスクを実行 |
| `run_parallel(tasks, max_concurrent)` | 複数タスクを並列実行 |

### BrowserWorker

| メソッド | 説明 |
|---------|------|
| `navigate(url)` | URLにアクセス |
| `get_content()` | ページコンテンツを取得 |
| `click(selector)` | 要素をクリック |
| `fill(selector, value)` | 入力フィールドに値を設定 |
| `type(selector, text)` | テキストを1文字ずつ入力 |
| `screenshot(path)` | スクリーンショットを保存 |
| `evaluate(script)` | JavaScriptを実行 |
| `scroll(direction, amount)` | ページをスクロール |
| `hover(selector)` | 要素にホバー |
| `select(selector, value)` | ドロップダウンから選択 |
| `get_text(selector)` | 要素のテキストを取得 |
| `wait_for_selector(selector)` | 要素の出現を待機 |
| `wait_for_navigation()` | ナビゲーション完了を待機 |
| `press(key)` | キーボードキーを押下 |

### ParallelController

| 設定 | デフォルト | 説明 |
|------|-----------|------|
| `max_workers` | 5 | 最大並列数 |
| `max_retries` | 3 | 最大リトライ回数 |
| `BASE_DELAY` | 1.0s | リトライ基本待機時間 |
| `MAX_DELAY` | 30.0s | リトライ最大待機時間 |

## エラーハンドリング

プロキシ関連のエラー時に自動的にリトライ:

- 指数バックオフ: 1s → 2s → 4s → ... (最大30s)
- 新しいプロキシで再試行
- 最大3回リトライ

## 依存関係

- Python 3.10+
- playwright
- fake-useragent
- aiohttp
- python-dotenv
- loguru
- pydantic
