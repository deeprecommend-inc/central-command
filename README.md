# CCP - Central Command Post

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

## アーキテクチャ

```
                    +-----------------------------+
                    |     CCP Orchestrator        |
                    |   (Central Coordinator)     |
                    +-------------+---------------+
                                  |
     +------------+---------------+---------------+------------+
     |            |               |               |            |
+----v----+ +-----v-----+ +-------v-------+ +----v----+ +-----v-----+
|  Sense  | |   Think   | |    Command    | | Control | |   Learn   |
| (認識)  | |  (判断)   | |   (指示)      | | (監視)  | |  (学習)   |
+---------+ +-----------+ +---------------+ +---------+ +-----------+
     |            |               |               |            |
 EventBus     RulesEngine     WebAgent       Executor    KnowledgeStore
 Metrics      Strategy        Browser        StateMachine PatternDetector
 Snapshot     Decision        Proxy/UA       FeedbackLoop Analyzer
```

---

## CCP統合使用

```python
import asyncio
from src import CCPOrchestrator, AgentConfig

async def main():
    config = AgentConfig(parallel_sessions=5)

    async with CCPOrchestrator(config) as ccp:
        # 単一タスク実行
        result = await ccp.run("https://example.com")
        print(f"Success: {result.success}")
        print(f"Decision: {result.decision.action}")
        print(f"Duration: {result.duration:.2f}s")

        # 複数タスク並列実行
        results = await ccp.run_parallel([
            "https://example.com",
            "https://httpbin.org/ip",
        ])

        # 統計取得
        stats = ccp.get_stats()
        print(f"Cycles: {stats['cycle_count']}")

        # パフォーマンスレポート
        report = ccp.get_report()
        print(f"Success rate: {report.success_rate:.1%}")

asyncio.run(main())
```

---

## 各レイヤーの詳細

### Sense層 - 状況認識

システム内外の状態を収集・正規化する。

```python
from src import EventBus, Event, MetricsCollector, StateSnapshot

# イベントバス（Pub/Sub）
bus = EventBus()

async def on_error(event: Event):
    print(f"Error: {event.data}")

bus.subscribe("proxy.failure", on_error)
await bus.publish(Event("proxy.failure", "proxy_manager", {"reason": "timeout"}))

# メトリクス収集
metrics = MetricsCollector()
metrics.record("request.duration", 0.5, {"endpoint": "/api"})

from datetime import timedelta
stats = metrics.get_aggregated("request.duration", timedelta(minutes=5))
print(f"Avg: {stats.avg}, Count: {stats.count}")

# 状態スナップショット
snapshot = StateSnapshot(event_bus=bus, metrics_collector=metrics)
state = snapshot.get_current_state()
print(f"Success rate: {state.success_rate}")
```

### Think層 - 判断

収集した情報から戦略を決定する。

```python
from src import RulesEngine, Rule, DecisionContext, TaskContext, RetryStrategy
from src.sense import SystemState

# ルールエンジン
engine = RulesEngine.create_default()

# カスタムルール追加
engine.add_rule(Rule(
    name="high_error_rate",
    condition=lambda ctx: ctx.get_error_frequency() > 0.5,
    action="reduce_parallelism",
    params={"factor": 0.5},
    priority=100,
))

# 判断実行
context = DecisionContext(
    system_state=SystemState(),
    task_context=TaskContext(task_id="t1", task_type="nav", last_error_type="timeout"),
)
decision = engine.evaluate_first(context)
print(f"Action: {decision.action}, Confidence: {decision.confidence}")

# リトライ戦略
strategy = RetryStrategy(max_retries=3, backoff_base=1.0)
decision = strategy.evaluate(context)
```

### Command層 - 指示生成・実行

Web操作エージェントによる実行。

```python
from src import WebAgent, AgentConfig

config = AgentConfig(
    parallel_sessions=5,
    headless=True,
    proxy_type="residential",
)

async with WebAgent(config) as agent:
    result = await agent.navigate("https://example.com")
    if result.success:
        print(f"Title: {result.data.get('title')}")
```

### Control層 - 実行監視

タスクの状態管理とフィードバック収集。

```python
from src import Executor, Task, FeedbackLoop, TaskState

# エグゼキュータ
executor = Executor()
task = Task(task_id="t1", task_type="navigate", target="https://example.com")

async def my_task(t: Task):
    # 実行ロジック
    return ExecutionResult(task_id=t.task_id, success=True)

result = await executor.execute(task, my_task)
print(f"State: {result.state}")

# タスク制御
await executor.pause("t1")
await executor.resume("t1")
await executor.cancel("t1")

# フィードバックループ
feedback = FeedbackLoop()
await feedback.on_result(result)

adjustments = feedback.get_adjustments()
for adj in adjustments:
    print(f"Adjust {adj.parameter}: {adj.recommended_value}")
```

### Learn層 - 学習・知識化

実行結果から学習し知識を蓄積する。

```python
from src import KnowledgeStore, KnowledgeEntry, PatternDetector, PerformanceAnalyzer

# 知識ストア
store = KnowledgeStore(max_entries=1000)
store.store(KnowledgeEntry(
    key="proxy.us.success_rate",
    value=0.95,
    confidence=0.9,
    source="analyzer",
))

entry = store.query("proxy.us.success_rate")
print(f"Value: {entry.value}, Confidence: {entry.confidence}")

# パターン検出
detector = PatternDetector()
patterns = detector.analyze_events(events)
for p in patterns:
    print(f"Pattern: {p.pattern_type}, Confidence: {p.confidence}")

# 異常検出
anomaly = detector.detect_metric_anomaly(metrics)
if anomaly:
    print(f"Anomaly: {anomaly.severity} - {anomaly.description}")

# パフォーマンス分析
analyzer = PerformanceAnalyzer(metrics_collector=metrics)
report = analyzer.generate_report()
print(f"Success rate: {report.success_rate:.1%}")
print(f"Recommendations: {report.recommendations}")
```

---

## API Server

FastAPIベースのREST/WebSocket APIサーバー。

### サーバー起動

```bash
# 基本起動
python server.py

# ポート指定
python server.py --port 8080

# 開発モード（自動リロード）
python server.py --reload

# 複数ワーカー
python server.py --workers 4
```

### API使用例

```python
import httpx

# タスク実行
response = httpx.post("http://localhost:8000/tasks", json={
    "target": "https://example.com",
    "task_type": "navigate",
})
task = response.json()
print(f"Task ID: {task['task_id']}")

# LangGraphワークフロー実行
response = httpx.post("http://localhost:8000/workflow", json={
    "target": "https://example.com",
    "task_type": "navigate",
    "enable_approval": True,
    "confidence_threshold": 0.7,
})
workflow = response.json()
print(f"Workflow: {workflow['cycle_id']}")

# 承認待ちリスト取得
response = httpx.get("http://localhost:8000/approvals")
approvals = response.json()
for req in approvals["requests"]:
    print(f"Pending: {req['request_id']} - {req['decision_action']}")

# 承認
httpx.post(f"http://localhost:8000/approvals/{request_id}/approve", json={
    "approved_by": "user@example.com",
    "reason": "Looks safe",
})

# 思考チェーン取得
response = httpx.get("http://localhost:8000/thoughts")
thoughts = response.json()
for chain in thoughts["chains"]:
    print(f"Chain: {chain['cycle_id']} - {len(chain['steps'])} steps")
```

### WebSocket（リアルタイムイベント）

```python
import asyncio
import websockets

async def listen_events():
    async with websockets.connect("ws://localhost:8000/ws/events") as ws:
        while True:
            event = await ws.recv()
            print(f"Event: {event}")

asyncio.run(listen_events())
```

### 主要エンドポイント

| Method | Path | 説明 |
|--------|------|------|
| GET | `/` | API情報 |
| GET | `/health` | ヘルスチェック |
| GET | `/stats` | 統計情報 |
| POST | `/tasks` | タスク作成 |
| POST | `/workflow` | ワークフロー実行 |
| GET | `/approvals` | 承認待ちリスト |
| POST | `/approvals/{id}/approve` | 承認 |
| POST | `/approvals/{id}/reject` | 拒否 |
| GET | `/thoughts` | 思考チェーン一覧 |
| GET | `/experiences` | 経験一覧 |
| WS | `/ws/events` | イベントストリーム |

OpenAPI Docs: `http://localhost:8000/docs`

---

## CLI

### 基本コマンド

```bash
# URL操作
python run.py url https://example.com

# 複数URL並列
python run.py url https://example.com https://google.com https://github.com

# プロキシヘルスチェック
python run.py health

# デモ
python run.py demo

# ヘルプ
python run.py --help
```

### プロキシタイプ選択

```bash
# 住宅IP（デフォルト）
python run.py url -r https://example.com

# モバイルIP
python run.py url -m https://example.com

# データセンターIP
python run.py url -d https://example.com

# ISP IP
python run.py url -i https://example.com

# プロキシなし（直接接続）
python run.py url --no-proxy https://example.com
```

### ロギングオプション

```bash
# JSON形式でログ出力
python run.py url --json https://example.com

# 詳細ログ（DEBUG）
python run.py url -v https://example.com
```

### AI Agent（CAPTCHA対応ブラウザ操作）

プロキシ/UA/CAPTCHA自動突破を統合したAIブラウザエージェント。

```bash
# AIタスク実行（CAPTCHA自動突破付き）
python run.py ai "https://example.com にアクセスしてCAPTCHAを解く" --no-proxy

# CAPTCHAソルバー指定
python run.py ai --captcha-solver vision "サイトにログインする"
python run.py ai --captcha-solver 2captcha "フォームを送信する"

# プロキシ+AI
python run.py ai -m "モバイルIPでサイトにアクセスする"
```

CAPTCHAソルバー:
- `vision` - GPT-4o Vision（デフォルト）
- `2captcha` - 2captchaサービス
- `anti-captcha` - Anti-Captchaサービス

環境変数:
- `OPENAI_API_KEY` - 必須（AIエージェント + Vision CAPTCHA）
- `TWOCAPTCHA_API_KEY` - 2captchaフォールバック用（オプション）
- `ANTICAPTCHA_API_KEY` - Anti-Captchaフォールバック用（オプション）

### browser-use（シンプル実行）

プロキシ/UA設定なしでbrowser-useを直接実行する。

```bash
# 基本（GPT-4o）
python browse.py "Go to google.com and search for python"

# ブラウザ表示（headlessオフ）
python browse.py --show "Open https://example.com"

# モデル指定
python browse.py --model claude-sonnet-4-20250514 "Search for AI news"
python browse.py --model gpt-4o-mini "Get the title of https://example.com"
```

オプション:
- `--show` - ブラウザ表示（headlessオフ）
- `--model <model>` - LLMモデル指定（デフォルト: gpt-4o）

対応モデル:
- GPT: gpt-4o, gpt-4o-mini, o1, o3-mini
- Claude: claude-sonnet-4-20250514, claude-opus-4-20250514

環境変数:
- `OPENAI_API_KEY` - GPT/o1/o3モデル使用時
- `ANTHROPIC_API_KEY` - Claudeモデル使用時

---

## API リファレンス

### CCPOrchestrator

| メソッド | 説明 |
|---------|------|
| `run(target, task_type)` | CCPサイクルを実行 |
| `run_parallel(targets)` | 複数タスクを並列実行 |
| `get_stats()` | 統計を取得 |
| `get_report()` | パフォーマンスレポートを生成 |
| `cleanup()` | リソースを解放 |

### Sense Layer

| クラス | 説明 |
|--------|------|
| `EventBus` | Pub/Subイベントシステム |
| `MetricsCollector` | 時系列メトリクス収集 |
| `StateSnapshot` | システム状態スナップショット |

### Think Layer

| クラス | 説明 |
|--------|------|
| `RulesEngine` | ルールベース判断エンジン |
| `RetryStrategy` | リトライ判断戦略 |
| `ProxySelectionStrategy` | プロキシ選択戦略 |
| `DecisionContext` | 判断コンテキスト |

### Control Layer

| クラス | 説明 |
|--------|------|
| `Executor` | タスク実行管理 |
| `StateMachine` | 状態遷移管理 |
| `FeedbackLoop` | フィードバック収集・調整 |

### Learn Layer

| クラス | 説明 |
|--------|------|
| `KnowledgeStore` | インメモリ知識ストア |
| `PatternDetector` | パターン・異常検出 |
| `PerformanceAnalyzer` | パフォーマンス分析 |

### Command Layer (WebAgent)

| メソッド | 説明 |
|---------|------|
| `navigate(url)` | 単一URLにアクセス |
| `parallel_navigate(urls)` | 複数URLに並列アクセス |
| `run_custom_task(task_id, task_fn)` | カスタムタスクを実行 |
| `get_proxy_stats()` | プロキシ統計を取得 |
| `health_check()` | ライブヘルスチェック実行 |

---

## エラーハンドリング

### ErrorType

| タイプ | リトライ | 説明 |
|--------|---------|------|
| `TIMEOUT` | Yes | タイムアウト |
| `CONNECTION` | Yes | 接続エラー |
| `PROXY` | Yes | プロキシエラー |
| `ELEMENT_NOT_FOUND` | No | 要素が見つからない |
| `VALIDATION` | No | バリデーションエラー |
| `BROWSER_CLOSED` | No | ブラウザが閉じた |

### 自動リトライ

- 指数バックオフ: 1s → 2s → 4s → ... (最大30s)
- 新しいプロキシで再試行
- 最大3回リトライ（設定可能）

---

## CCP v2 機能

### Experience Store（経験ストア）

学習の基盤となる(State, Action, Outcome, Reward)タプルを保存。

```python
from src.learn import ExperienceStore, StateSnapshot, Action, Outcome, OutcomeStatus
from datetime import datetime

store = ExperienceStore(max_size=10000)

# 経験を記録
state = StateSnapshot(timestamp=datetime.now(), features={"cpu": 0.5})
action = Action(action_type="navigate", params={"url": "https://example.com"})
outcome = Outcome(status=OutcomeStatus.SUCCESS, result={"title": "Example"}, duration_ms=150)

exp = store.record(state, action, outcome)

# 統計取得
stats = store.get_statistics()
print(f"Success rate: {stats['success_rate']:.1%}")

# ファイルに保存/読み込み
store.save_to_file("experiences.json")
store.load_from_file("experiences.json")
```

### Replay Engine（リプレイエンジン）

過去の経験を使ってポリシーを評価・比較。

```python
from src.learn import ReplayEngine, ReplayConfig

engine = ReplayEngine(experience_store)

# ポリシー評価
result = await engine.replay(my_policy, episodes=10)
print(f"Avg reward: {result.avg_reward}")

# 複数ポリシー比較
results = await engine.compare_policies([policy_a, policy_b])
print(f"Best: {results[0].policy_id}")
```

### シミュレーションCLI

```bash
# 経験ファイルの統計
python simulate.py stats experiences.json

# ポリシーでリプレイ
python simulate.py replay experiences.json --episodes 20

# 複数ポリシー比較
python simulate.py compare experiences.json --episodes 10
```

### Protocol Interfaces（v2用インターフェース）

ドメイン横断のための抽象インターフェース。

```python
from src.protocols import SafetyPolicy, DomainAdapter, RewardModel, Policy, Planner

# ドメインアダプター（軍事/プラント/金融で差し替え）
class MyDomainAdapter:
    async def execute(self, action: Action) -> Outcome: ...
    async def observe(self) -> StateSnapshot: ...
    def capabilities(self) -> list[str]: ...

# 安全ポリシー
class MySafetyPolicy:
    def authorize(self, plan, state) -> Authorization: ...
    def risk_score(self, plan, state) -> float: ...
    def kill_switch(self) -> bool: ...
```

### LangGraph Workflow（v2 Think層）

LangGraphベースのステートフルワークフロー。LLMが判断し、低信頼度時はHuman-in-the-Loopで承認を待つ。

```python
from src.think import CCPGraphWorkflow, LLMConfig, ApprovalConfig

# ワークフロー作成
workflow = CCPGraphWorkflow(
    llm_config=LLMConfig(provider="openai", model="gpt-4o"),
    approval_config=ApprovalConfig(confidence_threshold=0.7),
    thought_log_dir="logs/thoughts",
)

# 承認ハンドラ登録（Slack/Teams通知など）
async def approval_handler(request):
    print(f"Approval needed: {request.decision.action}")

workflow.on_approval_request(approval_handler)

# レイヤー実行関数を設定
workflow.set_sense_executor(my_sense_fn)
workflow.set_command_executor(my_command_fn)

# ワークフロー実行
result = await workflow.run(
    task_id="task_001",
    task_type="navigate",
    target="https://example.com",
)

print(f"Success: {result['final_success']}")
print(f"Thought steps: {len(result['thought_chain'])}")
```

### Human-in-the-Loop（承認ワークフロー）

低信頼度の判断に対して人間の承認を待つ。

```python
from src.think import HumanApprovalManager, ApprovalConfig, Decision

manager = HumanApprovalManager(ApprovalConfig(
    confidence_threshold=0.7,
    auto_approve_above=0.9,
    default_timeout=300.0,
))

# 承認が必要か確認
decision = Decision(action="proceed", confidence=0.5)
if manager.needs_approval(decision):
    request = manager.create_request("task_001", decision, state)

    # 非同期で承認を待つ
    status = await manager.wait_for_approval(request)

    if status == ApprovalStatus.APPROVED:
        # 実行続行
        pass

# 外部から承認/拒否
manager.approve(request_id, "user@example.com", "Looks good")
manager.reject(request_id, "user@example.com", "Risk too high")
```

### Chain of Thought Logging

全ての思考プロセスを記録し、後から分析可能。

```python
from src.think import ThoughtLogger, ThoughtChain

logger = ThoughtLogger(log_dir="logs/thoughts", auto_save=True)

# チェーン開始
chain = logger.start_chain(task_id="task_001")

# ステップ記録（ワークフロー内で自動）
logger.log_step(chain.cycle_id, thought_step)
logger.log_transition(chain.cycle_id, CCPPhase.SENSE, CCPPhase.THINK, "data_collected")

# 完了
logger.complete_chain(chain.cycle_id, decision_dict, outcome_dict)

# 統計
stats = logger.get_stats()
print(f"Avg duration: {stats['avg_duration_ms']:.0f}ms")
```

### Vector Store & RAG（v3 Learn層）

ベクトルデータベースによる意味的検索とRAG（Retrieval Augmented Generation）。

```python
from src.learn import (
    VectorKnowledgeStore,
    RAGRetriever,
    RAGConfig,
    create_vector_store,
)

# ベクトル対応KnowledgeStore
store = VectorKnowledgeStore(
    vector_backend="chroma",  # memory, chroma, qdrant
    persist_directory="./knowledge_db",
)

# 知識を保存（自動的にベクトル化）
store.store(KnowledgeEntry(
    key="proxy.residential.best_country",
    value="us",
    metadata={"description": "US has highest success rate"},
))

# 意味的検索
results = store.semantic_search("best proxy for scraping")
for entry, score in results:
    print(f"{entry.key}: {entry.value} (similarity: {score:.2f})")

# RAGリトリーバー（経験ベース学習）
retriever = RAGRetriever(RAGConfig(
    vector_backend="chroma",
    top_k=5,
    min_score=0.3,
))

# 経験をインデックス
retriever.index_experiences(experience_store)

# 類似経験を取得
result = retriever.retrieve(
    query="Navigate to https://example.com",
    filter={"task_type": "navigate"},
)

# LLMプロンプトにコンテキスト注入
print(result.context_text)
```

### Redis分散化（v4 Sense/Control層）

Redis Pub/Subによる分散イベントバスと状態キャッシュ。

```python
from src.sense import RedisEventBus, Event, create_event_bus
from src.control import RedisStateCache, CachedTaskState, CacheTaskState, create_state_cache

# 分散イベントバス
bus = create_event_bus(backend="redis", redis_url="redis://localhost:6379")

async def on_task_complete(event: Event):
    print(f"Task completed: {event.data}")

bus.subscribe("task.completed", on_task_complete)

# リスナー開始（バックグラウンド）
asyncio.create_task(bus.start_listening())

# イベント発行（全インスタンスに配信）
await bus.publish(Event("task.completed", "worker", {"task_id": "123"}))

# 状態キャッシュ（クラッシュリカバリ対応）
cache = create_state_cache(backend="redis", redis_url="redis://localhost:6379")

# タスク状態を保存
state = CachedTaskState(
    task_id="task_001",
    state=CacheTaskState.RUNNING,
    target="https://example.com",
    task_type="navigate",
    worker_id="worker_1",
)
await cache.save(state)

# クラッシュ後のリカバリ
recovered = await cache.recover_running_tasks(worker_id="worker_1")
for task in recovered:
    print(f"Recovering: {task.task_id}")

# 分散ロック
if await cache.acquire_lock("task_001", "worker_1", ttl=60):
    try:
        # 排他処理
        pass
    finally:
        await cache.release_lock("task_001", "worker_1")
```

### Stealth Browser（v5 Command層）

アンチディテクト対策のステルスブラウザ。

```python
from src.command import StealthConfig, StealthBrowser

# ステルス設定
config = StealthConfig(
    canvas_noise=True,           # Canvas指紋ランダム化
    webgl_spoof=True,           # WebGL偽装
    audio_noise=True,           # Audio指紋ノイズ
    navigator_spoof=True,       # Navigator偽装
    webrtc_block=True,          # WebRTCリーク防止
    timezone="America/New_York", # タイムゾーン偽装
)

stealth = StealthBrowser(config)

async with async_playwright() as p:
    browser = await p.chromium.launch(
        args=stealth.get_launch_args()
    )
    context = await browser.new_context(
        **stealth.get_context_options()
    )

    # ステルススクリプト適用
    await stealth.apply_to_context(context)

    page = await context.new_page()
    await page.goto("https://example.com")
```

### Human-like Behavior（v5 Command層）

人間らしい操作を模倣するマウス/キーボード/スクロール動作。

```python
from src.command import HumanBehaviorConfig, HumanBehavior

config = HumanBehaviorConfig(
    mouse_speed="normal",      # slow, normal, fast
    typing_speed="normal",
    typo_rate=0.02,            # タイポ率
    enable_typos=True,         # タイポ有効化
)

behavior = HumanBehavior(config)

# 人間らしいマウス移動（ベジェ曲線）
await behavior.mouse.move_to(page, 500, 300)
await behavior.mouse.click(page, 500, 300)

# 要素へ移動してクリック
await behavior.mouse.move_to_element(page, "button#submit")
await behavior.mouse.click_element(page, "button#submit")

# 人間らしいタイピング（タイポ＋修正込み）
await behavior.typing.type_text(page, "Hello World", "input#name")

# 自然なスクロール
await behavior.scroll.scroll_to_bottom(page)
await behavior.scroll.scroll_to_element(page, "#footer")
```

### CAPTCHA Solver（v5 Command層）

CAPTCHA自動検出と解決サービス連携。Vision AI（GPT-4o）による画像CAPTCHA解析に対応。

```python
from src.command import (
    CaptchaDetector,
    CaptchaMiddleware,
    TwoCaptchaSolver,
    VisionCaptchaSolver,
    create_captcha_solver,
)

# Vision AIソルバー（GPT-4o画像認識）
vision_solver = create_captcha_solver(
    provider="vision",
    api_key="your_openai_api_key",
)

# トークンベースソルバー
token_solver = create_captcha_solver(
    provider="2captcha",  # or "anti-captcha"
    api_key="your_api_key",
)

# 残高確認
balance = await token_solver.get_balance()
print(f"Balance: ${balance}")

# 手動検出と解決
detector = CaptchaDetector()
captcha = await detector.detect(page)

if captcha:
    print(f"Found: {captcha.captcha_type}")
    solution = await vision_solver.solve(captcha)
    if solution.success:
        print(f"Text: {solution.text}")

# 自動ミドルウェア（フォールバックチェーン対応）
middleware = CaptchaMiddleware(
    solver=vision_solver,
    solvers=[vision_solver, token_solver],  # Vision -> 2captcha
    auto_solve=True,
    max_retries=3,
)

await middleware.attach(context)

# 以降、CAPTCHAが自動解決される
await page.goto("https://protected-site.com")
```

対応CAPTCHAタイプ:
- reCAPTCHA v2/v3
- hCaptcha
- Cloudflare Turnstile
- 画像CAPTCHA（Vision AI）
- テキストCAPTCHA（Vision AI）
- FunCaptcha

ソルバー優先順位:
1. Vision LLM (GPT-4o) - 画像/テキストCAPTCHA
2. 2captcha - トークンベースフォールバック
3. anti-captcha - トークンベースフォールバック

### Docker Compose

```bash
# 基本起動（ChromaDB）
docker-compose up -d

# Qdrantを使用
docker-compose --profile qdrant up -d

# フルスタック（Redis含む）
docker-compose --profile full up -d

# ログ確認
docker-compose logs -f ccp-api
```

---

## テスト

```bash
# 全テスト実行
pytest tests/ -v

# カバレッジ付き
pytest tests/ --cov=src

# 特定レイヤーのテスト
pytest tests/test_sense/ -v
pytest tests/test_think/ -v
pytest tests/test_control/ -v
pytest tests/test_learn/ -v
pytest tests/test_ccp.py -v
```

---

## ファイル構成

```
run.py                       # CLI エントリポイント
browse.py                    # browser-use シンプル実行
simulate.py                  # v2 シミュレーションCLI
server.py                    # API Server エントリポイント
src/
├── ccp.py                   # CCPOrchestrator
├── protocols.py             # v2 Protocol Interfaces
├── api/                     # API Server
│   ├── models.py            # Pydantic Models
│   └── server.py            # FastAPI Server
├── sense/                   # Sense層
│   ├── event_bus.py         # + RedisEventBus (v4)
│   ├── metrics_collector.py
│   └── state_snapshot.py
├── think/                   # Think層
│   ├── strategy.py
│   ├── rules_engine.py
│   ├── decision_context.py
│   ├── agent_state.py       # v2 LangGraph State
│   ├── llm_decision.py      # v2 LLM Decision Maker
│   ├── human_in_loop.py     # v2 Human-in-the-Loop
│   ├── thought_log.py       # v2 Chain of Thought Log
│   └── graph_workflow.py    # v2 LangGraph Workflow
├── command/                 # Command層
│   ├── stealth.py           # v5 Stealth Browser
│   ├── human_behavior.py    # v5 Human-like Behavior
│   ├── captcha_solver.py    # v5 CAPTCHA Solver
│   └── vision_captcha_solver.py  # v6 Vision AI CAPTCHA Solver
├── control/                 # Control層
│   ├── executor.py
│   ├── state_machine.py
│   ├── state_cache.py       # v4 Redis State Cache
│   └── feedback_loop.py
├── learn/                   # Learn層
│   ├── knowledge_store.py   # + VectorKnowledgeStore
│   ├── pattern_detector.py
│   ├── performance_analyzer.py
│   ├── experience_store.py  # v2 Experience Store
│   ├── replay_engine.py     # v2 Replay Engine
│   ├── vector_store.py      # v3 Vector Store
│   └── rag_retriever.py     # v3 RAG Retriever
├── web_agent.py
├── proxy_manager.py
├── browser_worker.py
├── parallel_controller.py
├── ua_manager.py
├── rate_limiter.py
├── session_manager.py
└── logging_config.py
```

---

## セットアップ

### 仮想環境の作成

```bash
# venv作成
python -m venv venv

# 有効化（Linux/macOS）
source venv/bin/activate

# 有効化（Windows）
venv\Scripts\activate
```

### 依存関係のインストール

```bash
# パッケージインストール
pip install playwright browser-use langchain-openai langchain-anthropic fake-useragent aiohttp python-dotenv loguru pydantic

# Playwrightブラウザのインストール
playwright install

# システム依存関係（Linux）
playwright install-deps
```

### 環境変数の設定

```bash
cp .env.example .env
# .envを編集して必要な値を設定
```

---

## 依存関係

- Python 3.10+
- playwright
- browser-use
- langchain-openai
- langchain-anthropic
- fake-useragent
- aiohttp
- python-dotenv
- loguru
- pydantic
