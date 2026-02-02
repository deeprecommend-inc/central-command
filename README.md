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
src/
├── ccp.py                   # CCPOrchestrator
├── sense/                   # Sense層
│   ├── event_bus.py
│   ├── metrics_collector.py
│   └── state_snapshot.py
├── think/                   # Think層
│   ├── strategy.py
│   ├── rules_engine.py
│   └── decision_context.py
├── control/                 # Control層
│   ├── executor.py
│   ├── state_machine.py
│   └── feedback_loop.py
├── learn/                   # Learn層
│   ├── knowledge_store.py
│   ├── pattern_detector.py
│   └── performance_analyzer.py
├── web_agent.py            # Command層
├── proxy_manager.py
├── browser_worker.py
├── parallel_controller.py
├── ua_manager.py
├── rate_limiter.py
├── session_manager.py
└── logging_config.py
```

---

## 依存関係

- Python 3.10+
- playwright
- fake-useragent
- aiohttp
- python-dotenv
- loguru
- pydantic
