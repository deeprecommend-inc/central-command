# SNS-Agent セキュリティ分析レポート
## 防御的セキュリティ研究用

---

## 1. エグゼクティブサマリー

本レポートは、SNS自動化システム「Shaka AI (釈迦AI)」のコードベースを分析し、同様の攻撃からプラットフォームを防御するための知見を提供する。

### 攻撃概要

| カテゴリ | 手法 | リスクレベル |
|----------|------|--------------|
| アカウント生成 | 電話認証バイパス、大量Gmail作成 | 高 |
| ブラウザ指紋偽装 | Mulogin統合、Canvas/WebGL偽装 | 高 |
| IPローテーション | BrightDataレジデンシャルプロキシ | 中〜高 |
| 自動エンゲージメント | Playwright/Browser-use | 中 |
| スケーリング | 100万アカウント対応設計 | 極高 |

---

## 2. 攻撃ベクトル詳細分析

### 2.1 アカウント大量生成（`gmail_generator.py`）

#### 攻撃手法
```
1. モバイルUser-Agent偽装（iPhone/Android）
2. シークレットモード（Cookie永続化回避）
3. レジデンシャルプロキシによるIP変更
4. ランダム化された個人情報
5. モバイルビューポートエミュレーション
```

#### 検出ポイント
| 信号 | 詳細 | 検出優先度 |
|------|------|------------|
| タイミングパターン | `asyncio.sleep(0.5〜3)` - 固定待機時間 | 高 |
| 入力パターン | プログラム的な`fill()`呼び出し | 高 |
| ブラウザ設定 | `--disable-blink-features=AutomationControlled` | 極高 |
| 位置情報 | 固定座標（40.7128, -74.0060 = NYC） | 中 |
| デバイス一貫性 | iPhone UA + NYC位置 + en-US = 不自然な組み合わせ | 高 |

#### コード証拠 (`gmail_generator.py:66-71`)
```python
browser_args = [
    '--disable-blink-features=AutomationControlled',
    '--disable-features=IsolateOrigins,site-per-process',
    '--disable-site-isolation-trials',
]
```

### 2.2 ブラウザ指紋偽装（`mulogin_service.py`）

#### 偽装対象
| 指紋要素 | 偽装方法 | 検出回避率 |
|----------|----------|------------|
| Canvas | `"random"` - ランダムノイズ注入 | 中 |
| WebGL | `"random"` - レンダラー情報偽装 | 中 |
| ClientRects | `"random"` - DOMRect偽装 | 低〜中 |
| AudioContext | `"random"` - オーディオ指紋偽装 | 中 |
| Fonts | `"random"` - フォント列挙偽装 | 低 |
| MediaDevices | `"random"` - カメラ/マイク偽装 | 低 |

#### 脆弱性（検出可能）
```python
# mulogin_service.py:69-75
"platform": "Win32",           # 固定値 - 検出可能
"hardwareConcurrency": 8,      # 固定値 - 検出可能
"deviceMemory": 8,             # 固定値 - 検出可能
"doNotTrack": "1",             # 常に1 - 統計的異常
```

### 2.3 プロキシローテーション（`brightdata_service.py`）

#### プロキシタイプ
| タイプ | 特徴 | 検出難易度 |
|--------|------|------------|
| Residential | 一般家庭IP | 高（検出困難） |
| Mobile | モバイルキャリアIP | 高（検出困難） |
| Datacenter | データセンターIP | 低（容易） |
| ISP | ハイブリッド | 中 |

#### 検出ポイント
```python
# brightdata_service.py:40-51
# セッションIDパターン
username = f"{self.username}-zone-{self.zone}"
username += f"-country-{country.lower()}"
username += f"-session-{session_id}"
```

**検出信号**: 同一`session_id`からの複数リクエストはBrightData経由の可能性

### 2.4 YouTube自動エンゲージメント（`youtube_automation.py`）

#### 自動化アクション
| アクション | セレクタ | 検出ポイント |
|------------|----------|--------------|
| いいね | `button[aria-label*="like this video"]` | クリック速度、マウス軌跡なし |
| コメント | `#contenteditable-root` | 入力速度が一定 |
| 登録 | `yt-subscribe-button-view-model button` | 即時クリック |

#### 行動パターン（検出可能）
```python
# youtube_automation.py:200-221
await page.goto(video_url)
await asyncio.sleep(3)        # 固定3秒待機
# ... いいねボタンクリック
await asyncio.sleep(2)        # 固定2秒待機
```

---

## 3. データベース設計分析

### 3.1 スケーリング設計（`database.py`）

#### 大量アカウント対応
```python
# database.py:287
target_count = Column(Integer, nullable=False)  # 最大1,000,000
batch_size = Column(Integer, default=100)       # 同時100件
```

#### 追跡情報
| テーブル | 目的 | 保存データ |
|----------|------|------------|
| GeneratedAccount | 生成アカウント管理 | username, email, password_encrypted |
| ProxyIP | プロキシプール | 品質メトリクス、ブロック状況 |
| UserAgent | UA管理 | 使用回数、最終使用時刻 |
| TaskLog | 実行ログ | リアルタイム進捗 |

### 3.2 観測回避設計

#### 16カテゴリ監視システム（`ObservabilityMetric`）
```
1. IP構造        9. 操作テンポ
2. リズム        10. ナビゲーションパターン
3. 暗号/プロトコル 11. ヘッダー
4. User-Agent一貫性 12. データ送信
5. 指紋          13. CAPTCHA応答
6. Cookie/ストレージ 14. 一貫性
7. JavaScript    15. 分布
8. マウス/ポインタ  16. その他
```

---

## 4. 防御システム設計

### 4.1 検出レイヤー

```
┌─────────────────────────────────────────────────────────┐
│                    防御アーキテクチャ                    │
├─────────────────────────────────────────────────────────┤
│  Layer 1: ネットワーク分析                              │
│  ├── IP評価（ASN, レジデンシャル判定）                  │
│  ├── TLSフィンガープリント（JA3/JA4）                  │
│  └── リクエスト頻度分析                                │
├─────────────────────────────────────────────────────────┤
│  Layer 2: ブラウザ検証                                  │
│  ├── 自動化フラグ検出                                  │
│  ├── 指紋一貫性検証                                    │
│  └── JavaScript実行環境検査                            │
├─────────────────────────────────────────────────────────┤
│  Layer 3: 行動分析                                      │
│  ├── マウス軌跡分析                                    │
│  ├── 入力パターン分析                                  │
│  └── ナビゲーション分析                                │
├─────────────────────────────────────────────────────────┤
│  Layer 4: 機械学習                                      │
│  ├── 異常検出モデル                                    │
│  ├── クラスタリング分析                                │
│  └── 時系列パターン認識                                │
└─────────────────────────────────────────────────────────┘
```

### 4.2 具体的検出ロジック

#### 4.2.1 自動化検出（JavaScript）
```javascript
// 検出スクリプト例
const detectAutomation = () => {
  const signals = [];

  // 1. navigator.webdriver検出
  if (navigator.webdriver === true) {
    signals.push('WEBDRIVER_ENABLED');
  }

  // 2. Playwright/Puppeteer検出
  if (window.__playwright || window.__puppeteer) {
    signals.push('AUTOMATION_FRAMEWORK');
  }

  // 3. Chrome DevTools Protocol検出
  if (window.cdc_adoQpoasnfa76pfcZLmcfl_) {
    signals.push('CDP_DETECTED');
  }

  // 4. 不自然なプロパティ
  if (navigator.plugins.length === 0) {
    signals.push('NO_PLUGINS');
  }

  // 5. Canvas指紋の一貫性
  const canvas1 = getCanvasFingerprint();
  setTimeout(() => {
    const canvas2 = getCanvasFingerprint();
    if (canvas1 !== canvas2) {
      signals.push('CANVAS_INCONSISTENT');
    }
  }, 1000);

  return signals;
};
```

#### 4.2.2 行動分析
```python
# 検出ロジック例
class BehaviorAnalyzer:
    def analyze_mouse_movement(self, events: List[MouseEvent]) -> float:
        """
        マウス移動パターンを分析

        ボット特徴:
        - 直線的な移動（ベジェ曲線なし）
        - 一定速度
        - 目標に直接移動
        """

        if len(events) < 2:
            return 1.0  # 高リスク

        # 角度変化の分散
        angles = self._calculate_angles(events)
        angle_variance = np.var(angles)

        # 速度の分散
        speeds = self._calculate_speeds(events)
        speed_variance = np.var(speeds)

        # 人間: 高分散、ボット: 低分散
        human_score = min(angle_variance, speed_variance) / 100

        return 1.0 - min(human_score, 1.0)

    def analyze_typing_pattern(self, keystrokes: List[KeyEvent]) -> float:
        """
        タイピングパターンを分析

        ボット特徴:
        - 一定のキー間隔
        - ミスタイプなし
        - 超高速入力
        """

        intervals = []
        for i in range(1, len(keystrokes)):
            interval = keystrokes[i].timestamp - keystrokes[i-1].timestamp
            intervals.append(interval)

        if not intervals:
            return 1.0

        # 間隔の分散
        variance = np.var(intervals)
        mean_interval = np.mean(intervals)

        # 人間: 50-200ms平均、高分散
        # ボット: 10-50ms平均、低分散

        if mean_interval < 30:
            return 0.9  # 高リスク: 超高速
        if variance < 100:
            return 0.7  # 中リスク: 一定速度

        return 0.2  # 低リスク
```

#### 4.2.3 プロキシ検出
```python
class ProxyDetector:
    def __init__(self):
        self.known_proxy_asns = self._load_proxy_asns()
        self.residential_asns = self._load_residential_asns()

    def analyze_ip(self, ip: str, headers: dict) -> dict:
        """
        IPアドレスを分析
        """

        result = {
            'ip': ip,
            'risk_score': 0.0,
            'signals': []
        }

        # 1. ASN分析
        asn_info = self._get_asn_info(ip)
        if asn_info['asn'] in self.known_proxy_asns:
            result['risk_score'] += 0.5
            result['signals'].append('KNOWN_PROXY_ASN')

        # 2. ヘッダー分析
        proxy_headers = [
            'X-Forwarded-For',
            'X-Real-IP',
            'Via',
            'X-Proxy-ID'
        ]
        for header in proxy_headers:
            if header.lower() in [h.lower() for h in headers.keys()]:
                result['risk_score'] += 0.2
                result['signals'].append(f'PROXY_HEADER_{header}')

        # 3. 地理的一貫性
        ip_location = self._get_ip_location(ip)
        timezone = headers.get('X-Timezone')
        if timezone and not self._location_matches_timezone(ip_location, timezone):
            result['risk_score'] += 0.3
            result['signals'].append('GEO_TIMEZONE_MISMATCH')

        return result
```

### 4.3 レート制限設計

```python
class AdaptiveRateLimiter:
    """
    適応型レート制限

    ボットファーム対策:
    - 新規アカウントに厳しい制限
    - 信頼スコアに基づく動的制限
    - 異常パターン検出時の即座の制限
    """

    def __init__(self):
        self.base_limits = {
            'like': {'hourly': 50, 'daily': 200},
            'comment': {'hourly': 10, 'daily': 50},
            'subscribe': {'hourly': 20, 'daily': 100},
        }

    def get_limit(self, user: User, action: str) -> dict:
        base = self.base_limits[action].copy()

        # アカウント年齢による調整
        account_age_days = (datetime.now() - user.created_at).days
        if account_age_days < 7:
            base['hourly'] = base['hourly'] // 5
            base['daily'] = base['daily'] // 5
        elif account_age_days < 30:
            base['hourly'] = base['hourly'] // 2
            base['daily'] = base['daily'] // 2

        # 信頼スコアによる調整
        if user.trust_score < 0.3:
            base['hourly'] = base['hourly'] // 3
            base['daily'] = base['daily'] // 3

        return base
```

---

## 5. 攻撃検出チェックリスト

### 5.1 即座に検出可能な信号

| 信号 | 検出方法 | 対応 |
|------|----------|------|
| `navigator.webdriver = true` | JavaScript | 即時ブロック |
| 固定待機パターン | 時系列分析 | スコア加算 |
| CDP接続 | グローバル変数検査 | 即時ブロック |
| プラグイン数0 | JavaScript | スコア加算 |
| 自動化フラグ | ブラウザ設定検査 | 即時ブロック |

### 5.2 統計的に検出可能な信号

| 信号 | 検出方法 | 閾値 |
|------|----------|------|
| 同一IPからの複数アカウント作成 | IPトラッキング | 24h内3件以上 |
| 類似User-Agent | パターンマッチング | 類似度80%以上 |
| 直線的マウス移動 | 軌跡分析 | 角度分散 < 10 |
| 一定速度タイピング | キーストローク分析 | 分散 < 100ms |
| 時間帯集中 | 時系列分析 | 特定時間に90%以上 |

### 5.3 機械学習検出

| モデル | 入力特徴 | 出力 |
|--------|----------|------|
| Isolation Forest | 行動パターンベクトル | 異常スコア |
| LSTM | 時系列アクション | ボット確率 |
| Random Forest | 複合特徴 | 分類ラベル |

---

## 6. 推奨対策

### 6.1 短期対策（即時実装可能）

1. **自動化検出JavaScript導入**
   - `navigator.webdriver`チェック
   - Playwright/Puppeteer検出
   - CDP変数検出

2. **レート制限強化**
   - 新規アカウントへの厳格な制限
   - IPベースの制限

3. **CAPTCHA強化**
   - reCAPTCHA v3スコア監視
   - 行動分析ベースのチャレンジ

### 6.2 中期対策（1-3ヶ月）

1. **行動分析システム構築**
   - マウス軌跡収集・分析
   - キーストロークダイナミクス
   - ナビゲーションパターン

2. **機械学習モデル導入**
   - 異常検出モデル
   - リアルタイムスコアリング

3. **デバイス指紋検証**
   - Canvas/WebGL一貫性
   - フォント列挙検証

### 6.3 長期対策（3-6ヶ月）

1. **リアルタイム脅威インテリジェンス**
   - 攻撃パターンデータベース
   - 自動更新ルール

2. **分散型検出システム**
   - エッジでの検出
   - 中央集権型分析

3. **ゼロトラストアーキテクチャ**
   - 継続的認証
   - コンテキストベースアクセス

---

## 7. 結論

このシステムは以下の特徴を持つ高度なボットファームインフラである：

1. **スケーラビリティ**: 100万アカウント対応設計
2. **検出回避**: 16カテゴリの観測回避機構
3. **分散化**: プロキシローテーション、指紋偽装
4. **自動化**: LLM駆動のブラウザ操作

防御側は多層防御アプローチを採用し、単一の検出メカニズムに依存しないことが重要である。

---

*レポート作成日: 2025-12-24*
*分析者: セキュリティ研究チーム*
*分類: 防御的セキュリティ研究用*
