# CCP - Central Command Platform

産業現場の「判断」と「指示」を担うAI中央指揮所

## コンセプト

CCPは、点在するデータ、分断された判断、属人化した運用を統合し、
「状況把握 → 判断 → 指示 → 実行監視」をAIで自動化・高速化する。

## 解決する産業課題

- 現場データはあるが判断が遅い
- 異常は検知できても次の一手が決まらない
- 指示が人に依存し、再現性・スケールがない
- 拠点・設備・システムが分断され、全体最適ができない
- 緊急時に司令塔が不在

## CCPの役割

1. 全体状況の統合把握（Common Operating Picture）
2. 優先順位付け・意思決定
3. 人・設備・システムへの指示生成
4. 実行状況の監視と再判断
5. 判断ログの蓄積と再学習

## 機能構成

```text
[Sense] → [Think] → [Command] → [Control] → [Learn]
   ↓         ↓          ↓           ↓          ↓
 状況認識   判断      指示生成    実行監視    学習・知識化
```

### Sense（状況認識）
- IoT / 設備 / センサー / 業務DB / AI推論結果を統合
- 異常・兆候・リスクを単一ダッシュボードに可視化

### Think（判断）
- ルール x AI x シミュレーションのハイブリッド判断
- 重要度・緊急度・影響範囲で自動優先順位付け
- 「何が問題か」ではなく「何をすべきか」まで決定

### Command（指示）
- 人向け：Teams / Slack / メール / アラート
- システム向け：API / 制御信号 / ワークフロー起動

### Control（実行監視）
- 指示が実行されたかをリアルタイム監視
- 未実行・遅延・逸脱を即検知
- 必要に応じて再指示・エスカレーション

### Learn（学習）
- 判断・指示・結果を全てログ化
- 成功・失敗パターンを学習
- 属人判断を組織知へ変換

## CCPの本質的価値

- AIは分析係ではなく「指揮官」
- データを見るAIではなく、動かすAI
- 単体AIではなく、全体を統べるOS
- 現場・経営・システムを貫く意思決定中枢

---

# 実装方針

- スローガンは「無駄がない、全てがある。」
- 並列実装し、嘘は排除すること
- 常に最小構成でシンプルにしようと心がけること
- 不要になったフォルダやファイルは随時削除すること
- 絵文字は使わない
- 全ての操作をコマンドで完結するように
- 常にREADME.mdを最新の状態に保つこと
- README.mdは英語で表記し、技術内部的なことは書かず、ユースケースや使い方だけ記載すること

---

# Web操作エージェント（Command層の実装）

## 目的
プロンプトからWeb操作エージェントを実行する際に、プロキシローテーションとユーザーエージェントを使用する

## 達成すること
- プロキシローテーション（BrightData）※オプション
- IPタイプ選択（住宅IP / モバイルIP）
- ユーザーエージェント管理
- 並列ブラウザセッション管理（5並列）

## CLI使用方法

```bash
# 基本
python run.py url https://example.com

# ローカルLLM（API Key不要）
python run.py ai --local "Go to example.com and get the title" --no-proxy
python run.py ai --local --llm-model hermes3 "Search for AI news" --no-proxy

# クラウドLLM
python run.py ai "Go to example.com" --no-proxy

# 住宅IP
python run.py url -r https://example.com

# モバイルIP
python run.py url -m https://example.com

# プロキシなし
python run.py url --no-proxy https://example.com

# デモ
python run.py demo --no-proxy
```

## CLIオプション

| オプション | 短縮 | 説明 |
|-----------|------|------|
| `--residential` | `-r` | 住宅IP（デフォルト） |
| `--mobile` | `-m` | モバイルIP |
| `--datacenter` | `-d` | データセンターIP |
| `--isp` | `-i` | ISP IP |
| `--no-proxy` | - | 直接接続 |
| `--local` | - | ローカルLLM使用（API Key不要） |
| `--llm-base-url` | - | ローカルLLMサーバーURL |
| `--llm-model` | - | LLMモデル名 |

## 環境変数

| 変数 | 必須 | 説明 |
|------|------|------|
| LLM_PROVIDER | No | openai/anthropic/local（デフォルト: openai） |
| LLM_BASE_URL | No | ローカルLLMサーバーURL |
| LLM_MODEL | No | LLMモデル名 |
| LLM_API_KEY | No | LLM APIキー（local時は不要） |
| OPENAI_API_KEY | No | OpenAI APIキー（レガシー、LLM_API_KEYのフォールバック） |
| BRIGHTDATA_USERNAME | No | BrightDataユーザー名（未設定時は直接接続） |
| BRIGHTDATA_PASSWORD | No | BrightDataパスワード |
| BRIGHTDATA_PROXY_TYPE | No | residential/datacenter/mobile/isp |
| PARALLEL_SESSIONS | No | 並列数（デフォルト: 5） |
| HEADLESS | No | ヘッドレス実行（デフォルト: true） |

## システムアーキテクチャ

```text
[ CLI ] → [ WebAgent ] → [ ParallelController ] → [ BrowserWorker ]
   ↓            ↓                ↓                      ↓
[ 設定 ]  [ ProxyManager ]  [ リトライ機構 ]    [ Playwright ]
```

## コアコンポーネント

### ProxyManager
- プロキシプールの初期化
- プロキシヘルスチェック
- ローテーションロジック（使用回数、応答時間、成功率）

### BrowserWorker
- プロキシ設定適用
- ユーザーエージェント設定
- ページナビゲーション
- 要素操作（クリック、入力、スクロール）
- スクリーンショット取得

### ParallelController
- 5並列のブラウザセッション制御
- 指数バックオフによる再試行（1s → 2s → 4s、最大30s）
- プロキシ切断時の自動切り替え

## 技術スタック

- 自動化: Playwright
- プロキシ: BrightData
- 設定: python-dotenv

```bash
pip install playwright fake-useragent aiohttp python-dotenv loguru pydantic
```
