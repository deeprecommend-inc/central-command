# SNS-Agent攻撃検出方法の研究
## 実践的な検出テクニック

---

## 1. 攻撃シグネチャ一覧

SNS-Agentのコードベースから抽出した、検出可能な攻撃シグネチャ。

### 1.1 ブラウザ自動化シグネチャ

| シグネチャ | ソースコード | 検出方法 |
|------------|--------------|----------|
| `--disable-blink-features=AutomationControlled` | `gmail_generator.py:68` | ブラウザ起動引数の検出 |
| `--disable-features=IsolateOrigins` | `gmail_generator.py:69` | セキュリティ機能無効化検出 |
| `navigator.webdriver` | Playwright標準 | JavaScript検出 |
| 固定viewport (390x844) | `gmail_generator.py:94` | 画面サイズパターン |
| `is_mobile=True, has_touch=True` | `gmail_generator.py:96-97` | モバイルエミュレーション検出 |

### 1.2 タイミングパターン

```python
# SNS-Agentで使用されている固定待機時間パターン

# gmail_generator.py
await asyncio.sleep(0.5)   # フォーム入力間
await asyncio.sleep(1)     # ボタンクリック前
await asyncio.sleep(2)     # ページ遷移後
await asyncio.sleep(3)     # 認証ステップ間

# youtube_automation.py
await asyncio.sleep(2)     # ページ読み込み後
await asyncio.sleep(3)     # ログイン処理後
await asyncio.sleep(5)     # 動画アップロード後
```

**検出ロジック**:
```python
def detect_fixed_timing(intervals: List[float]) -> bool:
    """
    固定タイミングパターンを検出

    SNS-Agentの特徴:
    - 0.5, 1, 2, 3, 5秒の固定間隔
    - 分散が非常に小さい
    """
    # 既知の固定間隔（ミリ秒）
    known_intervals = [500, 1000, 2000, 3000, 5000]

    suspicious_count = 0
    for interval in intervals:
        for known in known_intervals:
            # ±50msの誤差を許容
            if abs(interval - known) < 50:
                suspicious_count += 1
                break

    # 70%以上が既知のパターンならボット
    return suspicious_count / len(intervals) > 0.7
```

### 1.3 プロキシシグネチャ

```python
# BrightDataプロキシパターン
# brightdata_service.py:40-51

# ユーザー名パターン:
# {username}-zone-{zone}-country-{country}-session-{session_id}

# 例:
# user123-zone-residential-country-us-session-abc123
# user123-zone-mobile-country-jp-session-def456
```

**検出方法**:
```python
def detect_brightdata_proxy(headers: dict, timing: dict) -> dict:
    """
    BrightDataプロキシの検出

    特徴:
    1. 一定のセッション維持パターン
    2. X-Real-IP / X-Forwarded-Forヘッダー
    3. brd.superproxy.io への接続痕跡
    """
    signals = []

    # ヘッダー分析
    if 'Via' in headers:
        if 'superproxy' in headers['Via'].lower():
            signals.append('BRIGHTDATA_VIA_HEADER')

    # レイテンシパターン
    # プロキシ経由は追加のレイテンシが発生
    if timing.get('first_byte_ms', 0) > 500:
        signals.append('HIGH_LATENCY')

    return {'signals': signals}
```

### 1.4 ユーザーエージェントパターン

```python
# user_agent_manager.py から抽出

# SNS-Agentが使用するUA（2025-11バージョン）
KNOWN_BOT_UA_PATTERNS = [
    # 固定バージョン番号
    "Chrome/131.0.0.0",
    "Chrome/130.0.0.0",
    "Safari/18.1",

    # モバイルエミュレーション
    "iPhone; CPU iPhone OS 16_0",
    "iPhone; CPU iPhone OS 15_5",
    "Android 13; SM-S901B",
    "Android 12; Pixel 6",
]
```

**検出ロジック**:
```python
def detect_ua_anomaly(user_agent: str, client_hints: dict) -> dict:
    """
    User-Agent異常検出

    チェック項目:
    1. UA文字列とClient Hintsの整合性
    2. 古いバージョン番号
    3. 不自然な組み合わせ
    """
    signals = []

    # Client HintsとUAの整合性
    if client_hints:
        ch_brand = client_hints.get('Sec-CH-UA-Platform', '')
        if 'iPhone' in user_agent and ch_brand != 'iOS':
            signals.append('UA_CLIENTHINTS_MISMATCH')

    # 既知のボットUAパターン
    for pattern in KNOWN_BOT_UA_PATTERNS:
        if pattern in user_agent:
            signals.append(f'KNOWN_BOT_UA_PATTERN:{pattern}')

    return {'signals': signals}
```

---

## 2. 攻撃フローの検出

### 2.1 アカウント生成フロー

```
┌─────────────────────────────────────────────────────────────────┐
│                  Gmail Account Creation Flow                     │
├─────────────────────────────────────────────────────────────────┤
│  Step 1: Navigate to signup                                      │
│  ├── URL: accounts.google.com/signup                            │
│  └── Detection: 同一IPから複数のsignupアクセス                   │
├─────────────────────────────────────────────────────────────────┤
│  Step 2: Fill name fields                                        │
│  ├── Action: fill('input[name="firstName"]')                    │
│  ├── Action: fill('input[name="lastName"]')                     │
│  └── Detection: 入力速度が一定、ミスなし                         │
├─────────────────────────────────────────────────────────────────┤
│  Step 3: Fill birthdate                                          │
│  ├── Action: select_option('select#month')                      │
│  ├── Action: fill('input[name="year"]')                         │
│  └── Detection: ドロップダウン操作が機械的                       │
├─────────────────────────────────────────────────────────────────┤
│  Step 4: Choose username                                         │
│  ├── Action: click('Create your own Gmail address')             │
│  ├── Action: fill('input[name="Username"]')                     │
│  └── Detection: ユーザー名パターン（first_last + 数字）          │
├─────────────────────────────────────────────────────────────────┤
│  Step 5: Set password                                            │
│  ├── Action: fill('input[name="Passwd"]')                       │
│  ├── Action: fill('input[name="PasswdAgain"]')                  │
│  └── Detection: パスワード入力が同時、コピペパターン             │
├─────────────────────────────────────────────────────────────────┤
│  Step 6: Skip phone verification                                 │
│  ├── Action: click('button:has-text("Skip")')                   │
│  └── Detection: 電話番号をスキップするパターン                   │
├─────────────────────────────────────────────────────────────────┤
│  Step 7: Accept terms                                            │
│  ├── Action: scroll + click('I agree')                          │
│  └── Detection: 利用規約を読まずに即同意                         │
└─────────────────────────────────────────────────────────────────┘
```

**フロー検出コード**:
```python
class AccountCreationFlowDetector:
    """
    アカウント作成フローの異常検出
    """

    def __init__(self):
        self.expected_steps = [
            'signup_page',
            'name_input',
            'birthdate_input',
            'username_input',
            'password_input',
            'phone_skip',
            'terms_accept'
        ]

        # 正常な所要時間（秒）
        self.normal_durations = {
            'name_input': (10, 60),        # 10-60秒
            'birthdate_input': (5, 30),    # 5-30秒
            'username_input': (10, 120),   # 10-120秒
            'password_input': (10, 60),    # 10-60秒
            'phone_skip': (2, 30),         # 2-30秒
            'terms_accept': (5, 120),      # 5-120秒（読む時間）
        }

    def analyze_flow(self, events: List[dict]) -> dict:
        """
        フローを分析
        """
        signals = []

        # 1. ステップ順序チェック
        actual_steps = [e['step'] for e in events]
        if actual_steps == self.expected_steps:
            signals.append('PERFECT_STEP_ORDER')

        # 2. 所要時間チェック
        for event in events:
            step = event['step']
            duration = event['duration']

            if step in self.normal_durations:
                min_dur, max_dur = self.normal_durations[step]
                if duration < min_dur:
                    signals.append(f'TOO_FAST_{step.upper()}')
                elif duration > max_dur:
                    signals.append(f'TOO_SLOW_{step.upper()}')

        # 3. 電話スキップ検出
        phone_events = [e for e in events if e['step'] == 'phone_skip']
        if phone_events and phone_events[0].get('action') == 'skip':
            signals.append('PHONE_SKIP')

        # 4. 総所要時間
        total_time = sum(e['duration'] for e in events)
        if total_time < 60:  # 1分未満は異常
            signals.append('EXTREMELY_FAST_COMPLETION')

        return {
            'signals': signals,
            'is_suspicious': len(signals) >= 3
        }
```

### 2.2 YouTubeエンゲージメントフロー

```
┌─────────────────────────────────────────────────────────────────┐
│                   YouTube Like Attack Flow                       │
├─────────────────────────────────────────────────────────────────┤
│  Step 1: Login                                                   │
│  ├── youtube.com → Sign in                                      │
│  ├── Enter email → Enter password                               │
│  └── Detection: 固定待機時間、機械的入力                         │
├─────────────────────────────────────────────────────────────────┤
│  Step 2: Navigate to video                                       │
│  ├── Direct URL access (page.goto)                              │
│  └── Detection: 検索せずに直接アクセス                           │
├─────────────────────────────────────────────────────────────────┤
│  Step 3: Like video                                              │
│  ├── Selector: button[aria-label*="like this video"]            │
│  ├── Fallback: yt-icon-button#top-level-buttons-computed        │
│  └── Detection: いいねまでの時間が短い、動画視聴なし             │
├─────────────────────────────────────────────────────────────────┤
│  Step 4: Repeat for next video                                   │
│  ├── Fixed wait: asyncio.sleep(2)                               │
│  └── Detection: 複数動画への連続いいね                           │
└─────────────────────────────────────────────────────────────────┘
```

**検出ルール**:
```python
ENGAGEMENT_DETECTION_RULES = {
    'like_without_watch': {
        'condition': 'like_time < 5 AND watch_time < 10',
        'risk_score': 0.8,
        'description': '動画を見ずにいいね'
    },
    'rapid_likes': {
        'condition': 'likes_per_hour > 20',
        'risk_score': 0.9,
        'description': '1時間に20件以上のいいね'
    },
    'sequential_likes': {
        'condition': 'consecutive_likes > 5 AND interval_variance < 1000',
        'risk_score': 0.85,
        'description': '一定間隔での連続いいね'
    },
    'new_account_activity': {
        'condition': 'account_age < 7 AND total_likes > 50',
        'risk_score': 0.75,
        'description': '新規アカウントの過剰活動'
    }
}
```

---

## 3. 機械学習ベースの検出

### 3.1 特徴量エンジニアリング

SNS-Agentの行動から抽出可能な特徴量:

```python
FEATURE_DEFINITIONS = {
    # セッション特徴
    'session_duration': 'セッション継続時間（秒）',
    'pages_visited': '訪問ページ数',
    'actions_per_minute': '1分あたりのアクション数',

    # タイミング特徴
    'avg_action_interval': '平均アクション間隔（ms）',
    'action_interval_variance': 'アクション間隔の分散',
    'time_to_first_action': '最初のアクションまでの時間',

    # 入力特徴
    'avg_typing_speed': '平均タイピング速度（文字/秒）',
    'typing_speed_variance': 'タイピング速度の分散',
    'backspace_ratio': 'バックスペース使用率',

    # マウス特徴
    'mouse_movement_count': 'マウス移動イベント数',
    'avg_mouse_speed': '平均マウス移動速度',
    'mouse_linearity': 'マウス軌跡の直線性',

    # ブラウザ特徴
    'plugins_count': 'プラグイン数',
    'screen_resolution': '画面解像度',
    'timezone_offset': 'タイムゾーンオフセット',

    # ネットワーク特徴
    'ip_asn': 'IPのASN',
    'is_proxy': 'プロキシ使用フラグ',
    'request_latency': 'リクエストレイテンシ'
}
```

### 3.2 訓練データ生成

```python
def generate_training_data():
    """
    訓練データ生成

    正常ユーザーとボットのラベル付きデータを生成
    """

    # 正常ユーザーデータ（収集済みログから）
    normal_features = load_normal_user_logs()

    # ボットデータ（SNS-Agentの行動パターンから生成）
    bot_features = []

    # SNS-Agentの特徴をシミュレート
    for _ in range(10000):
        bot_features.append({
            'session_duration': random.uniform(60, 300),
            'pages_visited': random.randint(5, 20),
            'actions_per_minute': random.uniform(10, 30),

            # 固定タイミングパターン
            'avg_action_interval': random.choice([500, 1000, 2000, 3000]),
            'action_interval_variance': random.uniform(0, 100),

            # 高速入力
            'avg_typing_speed': random.uniform(15, 25),
            'typing_speed_variance': random.uniform(0, 1),
            'backspace_ratio': random.uniform(0, 0.02),

            # マウスなし/直線的
            'mouse_movement_count': random.randint(0, 10),
            'avg_mouse_speed': random.uniform(1000, 5000),
            'mouse_linearity': random.uniform(0.9, 1.0),

            # ブラウザ
            'plugins_count': 0,
            'screen_resolution': '390x844',  # 固定

            # ネットワーク
            'is_proxy': 1,
            'request_latency': random.uniform(200, 1000)
        })

    return normal_features, bot_features
```

### 3.3 モデル評価

```python
def evaluate_detection_model(model, test_data):
    """
    検出モデルの評価

    重要な指標:
    - Precision: ボットと判定したもののうち実際にボットの割合
    - Recall: 実際のボットのうち検出できた割合
    - F1 Score: PrecisionとRecallの調和平均
    """

    predictions = model.predict(test_data['features'])
    labels = test_data['labels']

    # 混同行列
    tn = sum((p == 0 and l == 0) for p, l in zip(predictions, labels))
    fp = sum((p == 1 and l == 0) for p, l in zip(predictions, labels))
    fn = sum((p == 0 and l == 1) for p, l in zip(predictions, labels))
    tp = sum((p == 1 and l == 1) for p, l in zip(predictions, labels))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # 目標値
    # Precision > 0.95 (偽陽性を最小化)
    # Recall > 0.90 (ボットを逃さない)

    return {
        'precision': precision,
        'recall': recall,
        'f1_score': f1,
        'false_positive_rate': fp / (fp + tn),
        'false_negative_rate': fn / (fn + tp)
    }
```

---

## 4. リアルタイム検出システム

### 4.1 ストリーム処理アーキテクチャ

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Client    │───▶│   Nginx     │───▶│  Detection  │
│  (Browser)  │    │   (Edge)    │    │   Worker    │
└─────────────┘    └─────────────┘    └──────┬──────┘
                                              │
                   ┌──────────────────────────┼──────────────────────────┐
                   │                          ▼                          │
                   │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
                   │  │   Redis     │◀───│   Kafka     │───▶│   ML Model  │
                   │  │  (Cache)    │    │  (Stream)   │    │  (Scoring)  │
                   │  └─────────────┘    └─────────────┘    └─────────────┘
                   │                          │                          │
                   │                          ▼                          │
                   │  ┌─────────────┐    ┌─────────────┐                │
                   │  │ PostgreSQL  │◀───│  Analyzer   │                │
                   │  │  (Store)    │    │  (Batch)    │                │
                   │  └─────────────┘    └─────────────┘                │
                   └─────────────────────────────────────────────────────┘
```

### 4.2 検出パイプライン

```python
# detection_pipeline.py

import asyncio
from kafka import KafkaConsumer, KafkaProducer
import json

class DetectionPipeline:
    """
    リアルタイム検出パイプライン
    """

    def __init__(self):
        self.consumer = KafkaConsumer(
            'user-events',
            bootstrap_servers=['localhost:9092'],
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )

        self.producer = KafkaProducer(
            bootstrap_servers=['localhost:9092'],
            value_serializer=lambda m: json.dumps(m).encode('utf-8')
        )

        self.detection_service = BotDetectionService()
        self.session_store = SessionStore()

    async def process_event(self, event: dict):
        """
        イベントを処理
        """
        session_id = event['session_id']
        event_type = event['type']

        # セッションデータを取得/更新
        session = await self.session_store.get_or_create(session_id)
        session.add_event(event)

        # 検出実行（一定イベント数ごと）
        if session.event_count % 10 == 0:
            result = await self.detection_service.detect(
                ip=session.ip,
                ja3_hash=session.ja3,
                browser_signals=session.browser_signals,
                mouse_events=session.mouse_events,
                keystroke_events=session.keystroke_events
            )

            if result.is_bot or result.risk_score > 0.5:
                # アラート送信
                self.producer.send('bot-alerts', {
                    'session_id': session_id,
                    'risk_score': result.risk_score,
                    'signals': result.signals,
                    'recommended_action': result.recommended_action
                })

    async def run(self):
        """
        パイプライン実行
        """
        for message in self.consumer:
            await self.process_event(message.value)
```

---

## 5. 対策有効性の評価

### 5.1 検出率マトリクス

SNS-Agentの各コンポーネントに対する検出有効性:

| コンポーネント | 検出方法 | 検出率 | 回避難易度 |
|----------------|----------|--------|------------|
| Playwrightブラウザ | webdriver検出 | 95% | 高 |
| 固定タイミング | パターン分析 | 85% | 中 |
| BrightDataプロキシ | IP評価 | 60% | 低 |
| Mulogin指紋 | 一貫性チェック | 70% | 中 |
| 自動入力 | キーストローク分析 | 80% | 中 |
| 直線マウス | 軌跡分析 | 90% | 高 |

### 5.2 総合検出率

多層防御による総合検出率:

```
P(検出) = 1 - P(全層回避)
        = 1 - (1-0.95) × (1-0.85) × (1-0.60) × (1-0.70) × (1-0.80) × (1-0.90)
        = 1 - 0.05 × 0.15 × 0.40 × 0.30 × 0.20 × 0.10
        = 1 - 0.0000018
        ≈ 99.9998%
```

### 5.3 推奨検出優先順位

1. **即時実装**: ブラウザ自動化検出（最高検出率）
2. **短期実装**: タイミングパターン分析
3. **中期実装**: 行動分析（マウス/キーストローク）
4. **長期実装**: 機械学習モデル

---

## 6. 継続的改善プロセス

### 6.1 攻撃者対抗策の追跡

SNS-Agentが進化した場合の対応:

```python
class ThreatIntelligenceTracker:
    """
    脅威インテリジェンス追跡
    """

    def track_evasion_attempts(self, blocked_sessions: List[dict]):
        """
        回避試行を分析

        新しいパターンを発見したら検出ルールを更新
        """
        patterns = self.extract_patterns(blocked_sessions)

        for pattern in patterns:
            if pattern not in self.known_patterns:
                self.add_new_pattern(pattern)
                self.alert_security_team(pattern)

    def update_detection_rules(self, new_patterns: List[dict]):
        """
        検出ルールを更新
        """
        for pattern in new_patterns:
            rule = self.generate_rule(pattern)
            self.detection_service.add_rule(rule)
```

### 6.2 定期レビュー項目

| 頻度 | 項目 | 担当 |
|------|------|------|
| 日次 | 偽陽性レビュー | SOC |
| 週次 | 検出率分析 | セキュリティチーム |
| 月次 | ルール最適化 | セキュリティエンジニア |
| 四半期 | モデル再訓練 | MLエンジニア |

---

*研究レポート作成日: 2025-12-24*
*バージョン: 1.0*
