# User-Agent 更新ガイド

## 概要

このシステムは**3ヶ月ごと**にUser-Agentを更新します。

- **現在のバージョン**: 2025-11
- **次回更新日**: 2026-02-01
- **更新サイクル**: 3ヶ月（四半期ごと）

## 現在のUser-Agent一覧

### デスクトップ (12種類)

#### Chrome - Windows
- Chrome 131.0.0.0 (最新)
- Chrome 130.0.0.0

#### Chrome - Mac
- Chrome 131.0.0.0 on macOS 10.15.7 (最新)
- Chrome 130.0.0.0 on macOS 10.15.7

#### Safari - Mac
- Safari 18.1 on macOS 10.15.7 (最新)
- Safari 18.0 on macOS 10.15.7

#### Edge - Windows
- Edge 131.0.0.0 (最新)
- Edge 130.0.0.0

#### Firefox - Windows
- Firefox 132.0 (最新)
- Firefox 131.0

#### Chrome - Linux
- Chrome 131.0.0.0 on Linux (最新)
- Chrome 130.0.0.0 on Linux

### モバイル (8種類)

#### Safari - iOS
- iOS 17.7
- iOS 17.6.1
- iOS 18.1 (最新)

#### Chrome - Android
- Android 14 (Samsung S23, Pixel 8) - Chrome 131 (最新)
- Android 13 (Samsung S22) - Chrome 130

#### Safari - iPad
- iPadOS 17.7
- iPadOS 18.1 (最新)

---

## 更新手順（3ヶ月ごと）

### 1. 最新バージョンの調査

更新時期が来たら、以下のサイトで最新バージョンを確認:

- **Chrome**: https://chromereleases.googleblog.com/
- **Safari/iOS**: https://developer.apple.com/documentation/safari-release-notes
- **Firefox**: https://www.mozilla.org/en-US/firefox/releases/
- **Edge**: https://docs.microsoft.com/en-us/deployedge/microsoft-edge-relnote-stable-channel

### 2. `user_agent_manager.py` を更新

ファイル: `backend/app/services/user_agent_manager.py`

```python
# 次回更新日を3ヶ月後に設定
NEXT_UPDATE_DATE = "2026-05-01"  # 例: 2026年2月 → 2026年5月
CURRENT_VERSION = "2026-02"      # バージョンを年-月で更新

# USER_AGENTSディクショナリを最新バージョンに更新
USER_AGENTS = {
    "desktop": {
        "chrome_windows": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",  # 例: 最新版に更新
            # ... 他のバージョン
        ],
        # ... 他のブラウザ
    },
    "mobile": {
        # ... モバイル版も同様に更新
    }
}
```

### 3. テスト

```bash
# Backendを再起動
docker-compose restart backend

# User-Agent情報を確認
curl http://localhost:8006/user-agents/info | python3 -m json.tool

# ランダムUser-Agentをテスト
curl "http://localhost:8006/user-agents/random?device_type=desktop" | python3 -m json.tool
curl "http://localhost:8006/user-agents/random?device_type=mobile" | python3 -m json.tool
```

### 4. コミット & デプロイ

```bash
git add backend/app/services/user_agent_manager.py
git commit -m "Update User-Agents to [VERSION] (scheduled quarterly update)"
git push
```

---

## API使用例

### 更新情報を取得

```bash
GET /user-agents/info
```

```json
{
  "current_version": "2025-11",
  "next_update_date": "2026-02-01",
  "days_until_update": 74,
  "update_required": false,
  "total_user_agents": 20,
  "desktop_count": 12,
  "mobile_count": 8
}
```

### ランダムUser-Agentを取得

```bash
# デスクトップ
GET /user-agents/random?device_type=desktop

# モバイル
GET /user-agents/random?device_type=mobile

# ブラウザ指定
GET /user-agents/random?device_type=desktop&browser=chrome

# OS指定
GET /user-agents/random?device_type=desktop&os=mac
```

### 全User-Agentリスト

```bash
GET /user-agents/list
GET /user-agents/list?device_type=desktop
```

### ペルソナでテスト

```bash
POST /user-agents/test
Content-Type: application/json

{
  "preferred_device": "desktop",
  "preferred_browser": "chrome",
  "preferred_os": "windows"
}
```

---

## 更新スケジュール

| 更新日 | バージョン | ステータス |
|--------|-----------|-----------|
| 2025-11-18 | 2025-11 | ✅ 現行 |
| 2026-02-01 | 2026-02 | 📅 予定 |
| 2026-05-01 | 2026-05 | 📅 予定 |
| 2026-08-01 | 2026-08 | 📅 予定 |
| 2026-11-01 | 2026-11 | 📅 予定 |

---

## 自動チェック

システム起動時に自動的に更新状況がログ出力されます:

```
✅ User-Agent最新バージョン: 2025-11 次回更新まで: 74日 (2026-02-01)
```

更新が必要な場合:

```
⚠️  User-Agent更新が必要です！ 現在のバージョン: 2025-11 次回更新予定: 2026-02-01
```

---

## 注意事項

1. **検知リスク**: 古いUser-Agentは検知されやすいため、定期更新を必ず実施してください
2. **バリエーション**: 各カテゴリに複数のバージョンを含めることで、指紋の多様性を確保
3. **ペルソナ連携**: Muloginプロファイル作成時に自動的に最新User-Agentが適用されます
4. **後方互換性**: 既存のアカウントは次回ブラウザ起動時に新しいUser-Agentを使用

---

## トラブルシューティング

### User-Agentが古いまま

```bash
# Backendを再起動
docker-compose restart backend

# キャッシュをクリア
docker-compose down && docker-compose up -d
```

### 更新リマインダーが表示される

`user_agent_manager.py` の `NEXT_UPDATE_DATE` を確認し、現在日時と比較してください。
