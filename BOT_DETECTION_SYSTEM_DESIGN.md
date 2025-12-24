# ボット検出システム設計書
## 防御側アーキテクチャ

---

## 1. システム概要

### 1.1 目的
SNS-Agentのような大規模ボットファーム攻撃を検出・防御するためのシステム設計。

### 1.2 設計原則
- **多層防御**: 単一検出メカニズムに依存しない
- **適応型**: 攻撃パターンの進化に対応
- **低レイテンシ**: ユーザー体験を損なわない
- **高精度**: 偽陽性を最小化

---

## 2. アーキテクチャ

```
                    ┌─────────────────────────────────────┐
                    │            Load Balancer             │
                    └──────────────────┬──────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │        Edge Detection Layer          │
                    │  ┌─────────────────────────────────┐│
                    │  │ TLS Fingerprint (JA3/JA4)       ││
                    │  │ IP Reputation Check             ││
                    │  │ Rate Limiting (Token Bucket)    ││
                    │  └─────────────────────────────────┘│
                    └──────────────────┬──────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │       Browser Detection Layer        │
                    │  ┌─────────────────────────────────┐│
                    │  │ Automation Flag Detection       ││
                    │  │ Fingerprint Consistency         ││
                    │  │ JavaScript Environment Check    ││
                    │  └─────────────────────────────────┘│
                    └──────────────────┬──────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │       Behavior Analysis Layer        │
                    │  ┌─────────────────────────────────┐│
                    │  │ Mouse Movement Analysis         ││
                    │  │ Keystroke Dynamics              ││
                    │  │ Navigation Pattern Analysis     ││
                    │  │ Timing Analysis                 ││
                    │  └─────────────────────────────────┘│
                    └──────────────────┬──────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │        ML Detection Layer            │
                    │  ┌─────────────────────────────────┐│
                    │  │ Anomaly Detection (Isolation F) ││
                    │  │ Sequence Analysis (LSTM)        ││
                    │  │ Classification (Random Forest)  ││
                    │  └─────────────────────────────────┘│
                    └──────────────────┬──────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │       Decision & Response Layer      │
                    │  ┌─────────────────────────────────┐│
                    │  │ Risk Score Aggregation          ││
                    │  │ Adaptive Response Selection     ││
                    │  │ CAPTCHA / Block / Allow         ││
                    │  └─────────────────────────────────┘│
                    └──────────────────┬──────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │            Application               │
                    └─────────────────────────────────────┘
```

---

## 3. 検出モジュール詳細

### 3.1 Edge Detection Layer

#### 3.1.1 TLS Fingerprint (JA3/JA4)

```python
# ja3_detector.py

import hashlib
from typing import Optional, Dict

class JA3Detector:
    """
    JA3/JA4 TLS Fingerprint Detector

    Playwright/Puppeteer/Seleniumは特徴的なTLSハンドシェイクを持つ
    """

    def __init__(self):
        # 既知のボットJA3ハッシュ
        self.known_bot_ja3 = {
            # Playwright Chromium
            "cd08e31494f9531f560d64c695473da9",
            # Puppeteer
            "3b5074b1b5d032e5620f69f9f700ff0e",
            # Selenium ChromeDriver
            "bd0bf25947d4a37404f0424edf4db9ad",
        }

        # 正常ブラウザのJA3
        self.known_browser_ja3 = {
            # Chrome 120
            "773906b0efdefa24a7f2b8eb6985bf37",
            # Firefox 120
            "b32309a26951912be7dba376398abc3b",
        }

    def analyze(self, ja3_hash: str, ja3_full: str) -> Dict:
        """
        JA3ハッシュを分析

        Returns:
            {
                'is_bot': bool,
                'confidence': float,
                'matched_pattern': str
            }
        """
        result = {
            'is_bot': False,
            'confidence': 0.0,
            'matched_pattern': None
        }

        # 既知のボットパターン
        if ja3_hash in self.known_bot_ja3:
            result['is_bot'] = True
            result['confidence'] = 0.95
            result['matched_pattern'] = 'KNOWN_BOT_JA3'
            return result

        # 正常ブラウザ
        if ja3_hash in self.known_browser_ja3:
            result['confidence'] = 0.1
            return result

        # 未知のパターン - 詳細分析
        result['confidence'] = self._analyze_ja3_components(ja3_full)

        return result

    def _analyze_ja3_components(self, ja3_full: str) -> float:
        """
        JA3コンポーネントを詳細分析

        JA3形式: TLSVersion,Ciphers,Extensions,EllipticCurves,EllipticCurvePointFormats
        """
        try:
            parts = ja3_full.split(',')
            if len(parts) != 5:
                return 0.5  # 不正形式

            tls_version = parts[0]
            ciphers = parts[1].split('-')
            extensions = parts[2].split('-')

            # TLS 1.3未使用は古いボット
            if tls_version not in ['771', '772']:  # TLS 1.2, 1.3
                return 0.7

            # 暗号スイートが少なすぎる
            if len(ciphers) < 10:
                return 0.6

            # 拡張機能が少なすぎる
            if len(extensions) < 8:
                return 0.6

            return 0.3

        except Exception:
            return 0.5
```

#### 3.1.2 IP Reputation

```python
# ip_reputation.py

from dataclasses import dataclass
from typing import Dict, List, Optional
import asyncio
import aiohttp

@dataclass
class IPReputation:
    ip: str
    is_proxy: bool
    is_vpn: bool
    is_tor: bool
    is_datacenter: bool
    is_residential: bool
    risk_score: float
    country: str
    asn: int
    asn_name: str

class IPReputationService:
    """
    IPレピュテーションチェック

    複数データソースを統合:
    - MaxMind GeoIP
    - IPinfo.io
    - AbuseIPDB
    - 内部データベース
    """

    def __init__(self):
        self.cache = {}
        self.cache_ttl = 3600  # 1時間

        # 既知の悪意あるASN
        self.malicious_asns = {
            # BrightData ASN
            9009,   # M247
            16276,  # OVH
            # その他のプロキシプロバイダ
        }

        # レジデンシャルプロキシプロバイダのIPレンジ
        self.proxy_ranges = []

    async def check(self, ip: str) -> IPReputation:
        """
        IPのレピュテーションをチェック
        """
        # キャッシュチェック
        if ip in self.cache:
            cached = self.cache[ip]
            if cached['expires'] > asyncio.get_event_loop().time():
                return cached['data']

        # 並列でチェック
        results = await asyncio.gather(
            self._check_geoip(ip),
            self._check_ipinfo(ip),
            self._check_abuseipdb(ip),
            self._check_internal_db(ip),
            return_exceptions=True
        )

        # 結果を統合
        reputation = self._merge_results(ip, results)

        # キャッシュに保存
        self.cache[ip] = {
            'data': reputation,
            'expires': asyncio.get_event_loop().time() + self.cache_ttl
        }

        return reputation

    def _merge_results(self, ip: str, results: List) -> IPReputation:
        """
        複数ソースの結果を統合
        """
        is_proxy = False
        is_vpn = False
        is_tor = False
        is_datacenter = False
        is_residential = True
        risk_score = 0.0
        country = "XX"
        asn = 0
        asn_name = ""

        for result in results:
            if isinstance(result, Exception):
                continue

            if result.get('is_proxy'):
                is_proxy = True
                risk_score += 0.3

            if result.get('is_vpn'):
                is_vpn = True
                risk_score += 0.2

            if result.get('is_tor'):
                is_tor = True
                risk_score += 0.4

            if result.get('is_datacenter'):
                is_datacenter = True
                is_residential = False
                risk_score += 0.1

            if result.get('country'):
                country = result['country']

            if result.get('asn'):
                asn = result['asn']
                if asn in self.malicious_asns:
                    risk_score += 0.3

            if result.get('asn_name'):
                asn_name = result['asn_name']

        return IPReputation(
            ip=ip,
            is_proxy=is_proxy,
            is_vpn=is_vpn,
            is_tor=is_tor,
            is_datacenter=is_datacenter,
            is_residential=is_residential and not is_datacenter,
            risk_score=min(risk_score, 1.0),
            country=country,
            asn=asn,
            asn_name=asn_name
        )

    async def _check_geoip(self, ip: str) -> Dict:
        # MaxMind GeoIPデータベース照会
        pass

    async def _check_ipinfo(self, ip: str) -> Dict:
        # IPinfo.io API照会
        pass

    async def _check_abuseipdb(self, ip: str) -> Dict:
        # AbuseIPDB照会
        pass

    async def _check_internal_db(self, ip: str) -> Dict:
        # 内部ブラックリスト/ホワイトリスト照会
        pass
```

### 3.2 Browser Detection Layer

#### 3.2.1 Automation Detection Script

```javascript
// automation_detector.js
// クライアントサイドで実行される検出スクリプト

(function() {
    'use strict';

    const signals = [];

    // 1. WebDriver検出
    const checkWebDriver = () => {
        if (navigator.webdriver === true) {
            signals.push('WEBDRIVER_ENABLED');
        }

        // webdriverプロパティが削除されていないか確認
        const descriptor = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
        if (descriptor && descriptor.get && descriptor.get.toString().includes('native code')) {
            // 正常
        } else {
            signals.push('WEBDRIVER_MODIFIED');
        }
    };

    // 2. 自動化フレームワーク検出
    const checkAutomationFrameworks = () => {
        // Playwright
        if (window.__playwright) signals.push('PLAYWRIGHT');

        // Puppeteer
        if (window.__puppeteer) signals.push('PUPPETEER');

        // Selenium
        if (document.$cdc_asdjflasutopfhvcZLmcfl_) signals.push('SELENIUM_CDC');
        if (window._selenium) signals.push('SELENIUM');
        if (window.callSelenium) signals.push('SELENIUM_CALL');

        // PhantomJS
        if (window._phantom || window.callPhantom) signals.push('PHANTOMJS');

        // Nightmare
        if (window.__nightmare) signals.push('NIGHTMARE');
    };

    // 3. Chrome DevTools Protocol検出
    const checkCDP = () => {
        // CDPが有効な場合に存在する変数
        const cdpVariables = [
            'cdc_adoQpoasnfa76pfcZLmcfl_',
            'cdc_asdjflasutopfhvcZLmcfl_'
        ];

        for (const v of cdpVariables) {
            if (window[v] || document[v]) {
                signals.push('CDP_DETECTED');
                break;
            }
        }
    };

    // 4. プラグイン検出
    const checkPlugins = () => {
        if (navigator.plugins.length === 0) {
            signals.push('NO_PLUGINS');
        }

        // MimeTypesも確認
        if (navigator.mimeTypes.length === 0) {
            signals.push('NO_MIMETYPES');
        }
    };

    // 5. 言語設定の一貫性
    const checkLanguages = () => {
        if (!navigator.languages || navigator.languages.length === 0) {
            signals.push('NO_LANGUAGES');
        }

        if (navigator.languages && navigator.language &&
            !navigator.languages.includes(navigator.language)) {
            signals.push('LANGUAGE_INCONSISTENT');
        }
    };

    // 6. 権限API検出
    const checkPermissions = async () => {
        try {
            const notificationPermission = await navigator.permissions.query({name: 'notifications'});
            // 自動化環境では通常'denied'または'prompt'のまま
            // 実際のブラウザでは'granted'が多い
        } catch (e) {
            signals.push('PERMISSIONS_API_ERROR');
        }
    };

    // 7. Canvas指紋一貫性チェック
    const checkCanvasConsistency = () => {
        const getFingerprint = () => {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            ctx.textBaseline = 'top';
            ctx.font = '14px Arial';
            ctx.fillText('Bot detection test', 2, 2);
            return canvas.toDataURL();
        };

        const fp1 = getFingerprint();

        // 100ms後に再度取得
        setTimeout(() => {
            const fp2 = getFingerprint();
            if (fp1 !== fp2) {
                signals.push('CANVAS_INCONSISTENT');
            }
        }, 100);
    };

    // 8. 画面解像度の一貫性
    const checkScreenConsistency = () => {
        if (window.outerWidth === 0 || window.outerHeight === 0) {
            signals.push('ZERO_OUTER_DIMENSIONS');
        }

        if (window.innerWidth > window.screen.width ||
            window.innerHeight > window.screen.height) {
            signals.push('INVALID_SCREEN_DIMENSIONS');
        }

        // ヘッドレスモード検出
        if (window.outerWidth === window.innerWidth &&
            window.outerHeight === window.innerHeight) {
            signals.push('POSSIBLE_HEADLESS');
        }
    };

    // 9. タイミング精度
    const checkTimingPrecision = () => {
        const times = [];
        for (let i = 0; i < 10; i++) {
            times.push(performance.now());
        }

        // 精度が低すぎる（プライバシー保護）または高すぎる場合
        const precision = times[1] - times[0];
        if (precision === 0) {
            signals.push('ZERO_TIMING_PRECISION');
        }
    };

    // 10. WebGL検出
    const checkWebGL = () => {
        try {
            const canvas = document.createElement('canvas');
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');

            if (!gl) {
                signals.push('NO_WEBGL');
                return;
            }

            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            if (debugInfo) {
                const vendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL);
                const renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);

                // 仮想環境/ヘッドレス検出
                if (renderer.includes('SwiftShader')) {
                    signals.push('SWIFTSHADER_DETECTED');
                }
                if (renderer.includes('llvmpipe')) {
                    signals.push('LLVMPIPE_DETECTED');
                }
            }
        } catch (e) {
            signals.push('WEBGL_ERROR');
        }
    };

    // 実行
    const runDetection = async () => {
        checkWebDriver();
        checkAutomationFrameworks();
        checkCDP();
        checkPlugins();
        checkLanguages();
        await checkPermissions();
        checkCanvasConsistency();
        checkScreenConsistency();
        checkTimingPrecision();
        checkWebGL();

        // 結果をサーバーに送信
        if (signals.length > 0) {
            navigator.sendBeacon('/api/bot-detection', JSON.stringify({
                signals: signals,
                timestamp: Date.now(),
                url: window.location.href
            }));
        }
    };

    // ページロード時に実行
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runDetection);
    } else {
        runDetection();
    }
})();
```

### 3.3 Behavior Analysis Layer

#### 3.3.1 Mouse Movement Analyzer

```python
# mouse_analyzer.py

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple
import math

@dataclass
class MouseEvent:
    x: float
    y: float
    timestamp: float
    event_type: str  # 'move', 'click', 'scroll'

class MouseMovementAnalyzer:
    """
    マウス移動パターン分析

    人間とボットの違い:
    - 人間: 曲線的、速度変化あり、オーバーシュートあり
    - ボット: 直線的、一定速度、正確な目標到達
    """

    def __init__(self):
        # 閾値設定
        self.min_events = 10  # 最小イベント数
        self.angle_variance_threshold = 0.1  # 角度分散閾値
        self.speed_variance_threshold = 0.2  # 速度分散閾値

    def analyze(self, events: List[MouseEvent]) -> dict:
        """
        マウスイベントを分析

        Returns:
            {
                'is_bot': bool,
                'confidence': float,
                'features': dict,
                'signals': list
            }
        """
        result = {
            'is_bot': False,
            'confidence': 0.0,
            'features': {},
            'signals': []
        }

        if len(events) < self.min_events:
            result['signals'].append('INSUFFICIENT_EVENTS')
            result['confidence'] = 0.5
            return result

        # 特徴抽出
        features = self._extract_features(events)
        result['features'] = features

        # 分析
        signals = []
        bot_score = 0.0

        # 1. 角度分散チェック
        if features['angle_variance'] < self.angle_variance_threshold:
            signals.append('LOW_ANGLE_VARIANCE')
            bot_score += 0.25

        # 2. 速度分散チェック
        if features['speed_variance'] < self.speed_variance_threshold:
            signals.append('LOW_SPEED_VARIANCE')
            bot_score += 0.25

        # 3. 直線性チェック
        if features['linearity'] > 0.9:
            signals.append('HIGH_LINEARITY')
            bot_score += 0.2

        # 4. 加速度パターン
        if features['acceleration_changes'] < 3:
            signals.append('LOW_ACCELERATION_CHANGES')
            bot_score += 0.15

        # 5. ジッター（微小な揺れ）の欠如
        if features['jitter'] < 0.5:
            signals.append('LOW_JITTER')
            bot_score += 0.15

        result['signals'] = signals
        result['confidence'] = min(bot_score, 1.0)
        result['is_bot'] = result['confidence'] > 0.6

        return result

    def _extract_features(self, events: List[MouseEvent]) -> dict:
        """
        特徴量を抽出
        """
        # 座標と時間を配列に
        positions = [(e.x, e.y) for e in events]
        timestamps = [e.timestamp for e in events]

        # 角度計算
        angles = self._calculate_angles(positions)

        # 速度計算
        speeds = self._calculate_speeds(positions, timestamps)

        # 加速度計算
        accelerations = self._calculate_accelerations(speeds, timestamps)

        # 直線性計算
        linearity = self._calculate_linearity(positions)

        # ジッター計算
        jitter = self._calculate_jitter(positions)

        return {
            'angle_variance': np.var(angles) if angles else 0,
            'angle_mean': np.mean(angles) if angles else 0,
            'speed_variance': np.var(speeds) if speeds else 0,
            'speed_mean': np.mean(speeds) if speeds else 0,
            'acceleration_changes': self._count_sign_changes(accelerations),
            'linearity': linearity,
            'jitter': jitter,
            'total_distance': self._calculate_total_distance(positions),
            'event_count': len(events)
        }

    def _calculate_angles(self, positions: List[Tuple[float, float]]) -> List[float]:
        """
        連続する3点間の角度を計算
        """
        angles = []
        for i in range(1, len(positions) - 1):
            p1 = positions[i - 1]
            p2 = positions[i]
            p3 = positions[i + 1]

            # ベクトル
            v1 = (p1[0] - p2[0], p1[1] - p2[1])
            v2 = (p3[0] - p2[0], p3[1] - p2[1])

            # 角度計算
            dot = v1[0] * v2[0] + v1[1] * v2[1]
            mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
            mag2 = math.sqrt(v2[0]**2 + v2[1]**2)

            if mag1 > 0 and mag2 > 0:
                cos_angle = max(-1, min(1, dot / (mag1 * mag2)))
                angle = math.acos(cos_angle)
                angles.append(angle)

        return angles

    def _calculate_speeds(
        self,
        positions: List[Tuple[float, float]],
        timestamps: List[float]
    ) -> List[float]:
        """
        速度を計算
        """
        speeds = []
        for i in range(1, len(positions)):
            dx = positions[i][0] - positions[i-1][0]
            dy = positions[i][1] - positions[i-1][1]
            dt = timestamps[i] - timestamps[i-1]

            if dt > 0:
                distance = math.sqrt(dx**2 + dy**2)
                speed = distance / dt
                speeds.append(speed)

        return speeds

    def _calculate_accelerations(
        self,
        speeds: List[float],
        timestamps: List[float]
    ) -> List[float]:
        """
        加速度を計算
        """
        accelerations = []
        for i in range(1, len(speeds)):
            dt = timestamps[i+1] - timestamps[i] if i+1 < len(timestamps) else 1
            if dt > 0:
                acc = (speeds[i] - speeds[i-1]) / dt
                accelerations.append(acc)

        return accelerations

    def _calculate_linearity(self, positions: List[Tuple[float, float]]) -> float:
        """
        軌跡の直線性を計算 (0-1, 1が完全な直線)
        """
        if len(positions) < 2:
            return 0

        # 始点と終点の直線距離
        start = positions[0]
        end = positions[-1]
        direct_distance = math.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)

        # 実際の移動距離
        total_distance = self._calculate_total_distance(positions)

        if total_distance == 0:
            return 0

        return direct_distance / total_distance

    def _calculate_jitter(self, positions: List[Tuple[float, float]]) -> float:
        """
        微小な揺れ（ジッター）を計算
        """
        if len(positions) < 3:
            return 0

        # 移動平均からの偏差
        window_size = 3
        deviations = []

        for i in range(window_size, len(positions)):
            # 移動平均
            avg_x = np.mean([p[0] for p in positions[i-window_size:i]])
            avg_y = np.mean([p[1] for p in positions[i-window_size:i]])

            # 現在位置との偏差
            deviation = math.sqrt(
                (positions[i][0] - avg_x)**2 +
                (positions[i][1] - avg_y)**2
            )
            deviations.append(deviation)

        return np.mean(deviations) if deviations else 0

    def _calculate_total_distance(self, positions: List[Tuple[float, float]]) -> float:
        """
        総移動距離を計算
        """
        total = 0
        for i in range(1, len(positions)):
            dx = positions[i][0] - positions[i-1][0]
            dy = positions[i][1] - positions[i-1][1]
            total += math.sqrt(dx**2 + dy**2)
        return total

    def _count_sign_changes(self, values: List[float]) -> int:
        """
        符号変化の回数をカウント
        """
        if not values:
            return 0

        changes = 0
        prev_sign = None
        for v in values:
            current_sign = 1 if v >= 0 else -1
            if prev_sign is not None and current_sign != prev_sign:
                changes += 1
            prev_sign = current_sign

        return changes
```

#### 3.3.2 Keystroke Dynamics Analyzer

```python
# keystroke_analyzer.py

import numpy as np
from dataclasses import dataclass
from typing import List

@dataclass
class KeyEvent:
    key: str
    event_type: str  # 'keydown', 'keyup'
    timestamp: float

class KeystrokeDynamicsAnalyzer:
    """
    キーストロークダイナミクス分析

    人間とボットの違い:
    - 人間: 不規則な間隔、タイプミスあり、ホールド時間にばらつき
    - ボット: 一定間隔、ミスなし、一定のホールド時間
    """

    def __init__(self):
        # 人間の典型的な値
        self.human_avg_interval = 120  # ms
        self.human_interval_variance = 50  # ms
        self.min_events = 10

    def analyze(self, events: List[KeyEvent]) -> dict:
        """
        キーストロークイベントを分析

        Returns:
            {
                'is_bot': bool,
                'confidence': float,
                'features': dict,
                'signals': list
            }
        """
        result = {
            'is_bot': False,
            'confidence': 0.0,
            'features': {},
            'signals': []
        }

        if len(events) < self.min_events:
            result['signals'].append('INSUFFICIENT_EVENTS')
            result['confidence'] = 0.5
            return result

        # 特徴抽出
        features = self._extract_features(events)
        result['features'] = features

        # 分析
        signals = []
        bot_score = 0.0

        # 1. 間隔の分散チェック
        if features['interval_variance'] < 20:
            signals.append('LOW_INTERVAL_VARIANCE')
            bot_score += 0.3

        # 2. 平均間隔チェック（人間は通常50-200ms）
        if features['interval_mean'] < 30:
            signals.append('TOO_FAST_TYPING')
            bot_score += 0.25
        elif features['interval_mean'] > 500:
            signals.append('TOO_SLOW_TYPING')
            bot_score += 0.1

        # 3. ホールド時間の分散
        if features['hold_variance'] < 10:
            signals.append('LOW_HOLD_VARIANCE')
            bot_score += 0.2

        # 4. タイプミス/修正の欠如
        if features['backspace_ratio'] < 0.01:
            signals.append('NO_CORRECTIONS')
            bot_score += 0.15

        # 5. ダイグラフパターン（2文字連続）
        if features['digraph_consistency'] > 0.95:
            signals.append('HIGH_DIGRAPH_CONSISTENCY')
            bot_score += 0.1

        result['signals'] = signals
        result['confidence'] = min(bot_score, 1.0)
        result['is_bot'] = result['confidence'] > 0.6

        return result

    def _extract_features(self, events: List[KeyEvent]) -> dict:
        """
        特徴量を抽出
        """
        # キーダウンイベントのみ抽出
        keydowns = [e for e in events if e.event_type == 'keydown']
        keyups = [e for e in events if e.event_type == 'keyup']

        # 間隔計算
        intervals = []
        for i in range(1, len(keydowns)):
            interval = keydowns[i].timestamp - keydowns[i-1].timestamp
            intervals.append(interval)

        # ホールド時間計算
        hold_times = self._calculate_hold_times(events)

        # バックスペース率
        backspace_count = sum(1 for e in keydowns if e.key in ['Backspace', 'Delete'])
        backspace_ratio = backspace_count / len(keydowns) if keydowns else 0

        # ダイグラフ分析
        digraph_times = self._calculate_digraph_times(keydowns)
        digraph_consistency = self._calculate_consistency(digraph_times)

        return {
            'interval_mean': np.mean(intervals) if intervals else 0,
            'interval_variance': np.var(intervals) if intervals else 0,
            'interval_min': np.min(intervals) if intervals else 0,
            'interval_max': np.max(intervals) if intervals else 0,
            'hold_mean': np.mean(hold_times) if hold_times else 0,
            'hold_variance': np.var(hold_times) if hold_times else 0,
            'backspace_ratio': backspace_ratio,
            'digraph_consistency': digraph_consistency,
            'event_count': len(events)
        }

    def _calculate_hold_times(self, events: List[KeyEvent]) -> List[float]:
        """
        キーホールド時間を計算
        """
        hold_times = []
        key_press_times = {}

        for event in events:
            if event.event_type == 'keydown':
                key_press_times[event.key] = event.timestamp
            elif event.event_type == 'keyup':
                if event.key in key_press_times:
                    hold_time = event.timestamp - key_press_times[event.key]
                    hold_times.append(hold_time)
                    del key_press_times[event.key]

        return hold_times

    def _calculate_digraph_times(self, keydowns: List[KeyEvent]) -> dict:
        """
        ダイグラフ（2文字連続）の入力時間を計算
        """
        digraph_times = {}

        for i in range(1, len(keydowns)):
            digraph = f"{keydowns[i-1].key}{keydowns[i].key}"
            interval = keydowns[i].timestamp - keydowns[i-1].timestamp

            if digraph not in digraph_times:
                digraph_times[digraph] = []
            digraph_times[digraph].append(interval)

        return digraph_times

    def _calculate_consistency(self, digraph_times: dict) -> float:
        """
        ダイグラフ時間の一貫性を計算
        """
        consistencies = []

        for digraph, times in digraph_times.items():
            if len(times) >= 2:
                variance = np.var(times)
                mean = np.mean(times)
                if mean > 0:
                    cv = variance / mean  # 変動係数
                    consistency = 1 / (1 + cv)
                    consistencies.append(consistency)

        return np.mean(consistencies) if consistencies else 0
```

---

## 4. 機械学習モデル

### 4.1 Isolation Forest

```python
# ml_detector.py

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib

class BotDetectionModel:
    """
    Isolation Forestベースの異常検出モデル
    """

    def __init__(self, model_path: str = None):
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            n_estimators=100,
            contamination=0.1,  # 10%がボットと想定
            random_state=42
        )
        self.is_fitted = False

        if model_path:
            self.load(model_path)

    def fit(self, features: np.ndarray):
        """
        モデルを訓練
        """
        scaled_features = self.scaler.fit_transform(features)
        self.model.fit(scaled_features)
        self.is_fitted = True

    def predict(self, features: np.ndarray) -> np.ndarray:
        """
        予測

        Returns:
            array of -1 (anomaly/bot) or 1 (normal)
        """
        if not self.is_fitted:
            raise RuntimeError("Model not fitted")

        scaled_features = self.scaler.transform(features)
        return self.model.predict(scaled_features)

    def score(self, features: np.ndarray) -> np.ndarray:
        """
        異常スコアを取得

        Returns:
            array of scores (lower = more anomalous)
        """
        if not self.is_fitted:
            raise RuntimeError("Model not fitted")

        scaled_features = self.scaler.transform(features)
        return self.model.score_samples(scaled_features)

    def save(self, path: str):
        """
        モデルを保存
        """
        joblib.dump({
            'model': self.model,
            'scaler': self.scaler,
            'is_fitted': self.is_fitted
        }, path)

    def load(self, path: str):
        """
        モデルを読み込み
        """
        data = joblib.load(path)
        self.model = data['model']
        self.scaler = data['scaler']
        self.is_fitted = data['is_fitted']
```

---

## 5. 統合サービス

```python
# bot_detection_service.py

from dataclasses import dataclass
from typing import Dict, List, Optional
import asyncio

@dataclass
class DetectionResult:
    is_bot: bool
    confidence: float
    risk_score: float
    signals: List[str]
    recommended_action: str  # 'allow', 'challenge', 'block'
    details: Dict

class BotDetectionService:
    """
    統合ボット検出サービス
    """

    def __init__(self):
        self.ip_reputation = IPReputationService()
        self.ja3_detector = JA3Detector()
        self.mouse_analyzer = MouseMovementAnalyzer()
        self.keystroke_analyzer = KeystrokeDynamicsAnalyzer()
        self.ml_model = BotDetectionModel()

        # 重み設定
        self.weights = {
            'ip_reputation': 0.2,
            'ja3': 0.15,
            'browser_detection': 0.25,
            'mouse_behavior': 0.15,
            'keystroke': 0.1,
            'ml_model': 0.15
        }

    async def detect(
        self,
        ip: str,
        ja3_hash: str,
        browser_signals: List[str],
        mouse_events: List[MouseEvent],
        keystroke_events: List[KeyEvent],
        additional_features: Dict = None
    ) -> DetectionResult:
        """
        総合的なボット検出を実行
        """

        all_signals = []
        scores = {}

        # 1. IP評価
        ip_result = await self.ip_reputation.check(ip)
        scores['ip_reputation'] = ip_result.risk_score
        if ip_result.is_proxy:
            all_signals.append('PROXY_IP')
        if ip_result.is_vpn:
            all_signals.append('VPN_IP')

        # 2. JA3分析
        ja3_result = self.ja3_detector.analyze(ja3_hash, "")
        scores['ja3'] = ja3_result['confidence']
        if ja3_result['matched_pattern']:
            all_signals.append(ja3_result['matched_pattern'])

        # 3. ブラウザ検出
        browser_score = len(browser_signals) * 0.15
        scores['browser_detection'] = min(browser_score, 1.0)
        all_signals.extend(browser_signals)

        # 4. マウス行動分析
        mouse_result = self.mouse_analyzer.analyze(mouse_events)
        scores['mouse_behavior'] = mouse_result['confidence']
        all_signals.extend(mouse_result['signals'])

        # 5. キーストローク分析
        keystroke_result = self.keystroke_analyzer.analyze(keystroke_events)
        scores['keystroke'] = keystroke_result['confidence']
        all_signals.extend(keystroke_result['signals'])

        # 6. ML分析
        if additional_features:
            features = np.array([list(additional_features.values())])
            ml_score = self.ml_model.score(features)[0]
            scores['ml_model'] = 1 - (ml_score + 1) / 2  # -1,1 -> 0,1
        else:
            scores['ml_model'] = 0.5

        # 総合スコア計算
        total_score = sum(
            score * self.weights[key]
            for key, score in scores.items()
        )

        # 判定
        if total_score > 0.7:
            is_bot = True
            action = 'block'
        elif total_score > 0.4:
            is_bot = False
            action = 'challenge'
        else:
            is_bot = False
            action = 'allow'

        return DetectionResult(
            is_bot=is_bot,
            confidence=total_score,
            risk_score=total_score,
            signals=all_signals,
            recommended_action=action,
            details={
                'scores': scores,
                'ip_info': {
                    'ip': ip,
                    'is_proxy': ip_result.is_proxy,
                    'country': ip_result.country
                }
            }
        )
```

---

## 6. 運用ガイドライン

### 6.1 モニタリングダッシュボード

追跡すべきメトリクス:
- 検出率（Detection Rate）
- 偽陽性率（False Positive Rate）
- レスポンスタイム
- ブロック/チャレンジ/許可の分布
- シグナル別検出数

### 6.2 アラート設定

| 条件 | 重要度 | アクション |
|------|--------|------------|
| 検出率 > 20% | 高 | 攻撃調査開始 |
| 偽陽性率 > 5% | 高 | 閾値調整 |
| 同一IP/UA組み合わせ > 100件/時 | 中 | 自動ブロック |
| 新規JA3パターン > 10% | 低 | パターン調査 |

### 6.3 継続的改善

1. **週次レビュー**: 偽陽性/偽陰性の分析
2. **月次更新**: MLモデルの再訓練
3. **四半期**: 検出ルールの見直し

---

*設計書作成日: 2025-12-24*
*バージョン: 1.0*
