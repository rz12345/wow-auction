# 設定文件

> 涵蓋 `app/configs/` 下所有設定檔的欄位、合法值範圍、調整建議。

## 1. 設定檔總表

| 檔案 | 性質 | 是否進 git | 用途 |
|------|------|-----------|------|
| `settings.json` | 操作參數 | ✅ 是 | 歷史天數、通知門檻、批次大小 |
| `tracked_items.json` | 物品追蹤策略 | ✅ 是 | 追蹤哪些類別、ID threshold、自訂物品 |
| `battle-net-cred.json` | 憑證 | ❌ `.gitignore` | Battle.net OAuth client |
| `firebase-cred.json` | 憑證 | ❌ `.gitignore` | Firebase service account |
| `discord-webhook.json` | 憑證 | ❌ `.gitignore` | Discord webhook URL |
| `telegram-bot.json` | 憑證 | ❌ `.gitignore` | Telegram bot token + chat |
| `google-auth.json` | 憑證 | ❌ `.gitignore` | Google Sheets service account |

`.gitignore` 規則來源：

```
app/configs/*
!app/configs/settings.json
!app/configs/tracked_items.json
```

## 2. `settings.json` — 操作參數

當前內容（`app/configs/settings.json`）：

```json
{
    "history_days": 28,
    "price_compare_days": 7,
    "price_drop_threshold": -10,
    "min_gold_threshold": 10000,
    "notify_batch_size": 20
}
```

驗證邏輯：`app/helpers/validators.py::validate_settings()`

| 欄位 | 型別 | 合法範圍 | 預設 | 說明 |
|------|------|---------|------|------|
| `history_days` | int | 1 - 365 | 28 | 統計視窗天數。`update_statics` 只會處理 `[今天 - history_days, 今天]` 範圍的快照；`archive_old_files` 也以這個天數判斷「過期」 |
| `price_compare_days` | int | 1 - 365 | 7 | 降價比較基準天數。`check_cheap_goods` 取 N 天內最低價作為比較基線 |
| `price_drop_threshold` | int / float | ≤ 0 | -10 | 降幅百分比門檻（**負數**）。-10 代表跌幅 ≥ 10% 才通知 |
| `min_gold_threshold` | int / float | ≥ 0 | 10000 | 7 天最低價（單位：銅幣）下限。低於此值的物品不通知（避免低價垃圾物品洗版） |
| `notify_batch_size` | int | 1 - 200 | 20 | 一次通知最多包含幾筆物品。Discord 2000 字元上限會再二次切分，這只是行數層級的批次 |

### 調整建議

- **降低通知量**：調 `price_drop_threshold` → -20（要跌更多才通知），或調高 `min_gold_threshold` → 50000
- **更靈敏**：調 `price_compare_days` → 3（與更近期相比）
- **延長歷史**：調 `history_days` → 60（注意：pandas 記憶體會線性增加，60 天可能需 1-2 GB）

## 3. `tracked_items.json` — 物品追蹤策略

當前內容：

```json
{
    "item_id_threshold": 236761,
    "tracked_item_classes": ["交易技能", "物品附魔", "寶石", "消耗品"],
    "custom_tracked_items": [123918, 132514]
}
```

驗證邏輯：`app/helpers/validators.py::validate_tracked_items()`

| 欄位 | 型別 | 限制 | 說明 |
|------|------|------|------|
| `item_id_threshold` | int | ≥ 1 | ID 門檻。配合 `tracked_item_classes` 使用：`(id >= threshold AND class IN classes) OR id IN custom` |
| `tracked_item_classes` | list[str] | 不可為空 | 物品大類中文名（對應 `data/item_class.json`）。實際生效的篩選見 `auction_controller.py:69` |
| `custom_tracked_items` | list[int] | 元素必為 int | 不受 threshold / class 限制的長期關注物品 ID |

### 為何要 `item_id_threshold`？

魔獸世界每次資料片更新會跳一個 ID 區間。設 `item_id_threshold = 236761` 等於「只追蹤地心戰役（11.x）以後的物品」，避免歷史舊物品（已無人交易）干擾。

### 調整情境

| 情境 | 操作 |
|------|------|
| 想追蹤新增的「珠寶設計」類別 | 在 `tracked_item_classes` 加 `"珠寶設計"`（注意必須是 `data/item_class.json` 內的中文名） |
| 想關注某個低 ID 物品 | 加入 `custom_tracked_items` 陣列 |
| 新版資料片開放後想剔除舊物品 | 提高 `item_id_threshold` 到新版本起始 ID |

> ⚠️ `check_cheap_goods` 的通知範圍另有 SQL 層級的 hardcoded 過濾（只通知 `item_class_id = 0` 子類 1/3/5/9 與 `item_class_id = 8`），詳見 [ARCHITECTURE.md §6.5](ARCHITECTURE.md)。修改 `tracked_item_classes` 不會影響通知範圍，只影響資料抓取與統計。

## 4. 5 份憑證檔範例

### 4.1 `battle-net-cred.json`

```json
{
    "client_id": "abcdef1234567890abcdef1234567890",
    "client_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

| 欄位 | 取得方式 |
|------|---------|
| `client_id` | [Battle.net Developer Portal](https://develop.battle.net/) → Manage API Access → 建立 Client → 複製 Client ID |
| `client_secret` | 同上頁面，建立後一次顯示，**請立即備份** |

讀取位置：`app/services/battle_net.py:13`

### 4.2 `firebase-cred.json`

整份從 Firebase Console 下載的 service account JSON，欄位包含 `type`、`project_id`、`private_key_id`、`private_key`、`client_email`、`client_id`、`auth_uri`、`token_uri` 等：

```json
{
    "type": "service_account",
    "project_id": "jojocat-wow-f72a5",
    "private_key_id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n",
    "client_email": "firebase-adminsdk-xxxx@jojocat-wow-f72a5.iam.gserviceaccount.com",
    "client_id": "123456789012345678901",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "..."
}
```

取得方式：Firebase Console → 專案設定 → 服務帳戶 → 產生新私密金鑰 → 下載 JSON

讀取位置：`app/services/storage_firebase.py:23`

**所需 IAM 角色**（對應 `storage_firebase.py:11-16` 的 scope）：
- Firebase Realtime Database Admin
- Cloud Datastore User（Firestore）
- Storage Object Admin

### 4.3 `discord-webhook.json`

```json
{
    "webhook_url": "https://discord.com/api/webhooks/1234567890123456789/AbCdEfGhIjKlMnOpQrStUvWxYz_1234567890_AbCdEfGhIjKlMnOpQrStUvWxYz"
}
```

取得方式：Discord 伺服器 → 頻道設定（齒輪）→ 整合 → Webhooks → 新建 Webhook → 複製 URL

讀取位置：`app/controllers/auction_controller.py:394`

### 4.4 `telegram-bot.json`

```json
{
    "bot_token": "1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ_abcdefghi",
    "chat_id": "123456789"
}
```

| 欄位 | 取得方式 |
|------|---------|
| `bot_token` | Telegram 中找 `@BotFather` → `/newbot` → 設定名稱 → 取得 token |
| `chat_id` | 1) 用瀏覽器先發一則訊息給你的 bot；2) 開啟 `https://api.telegram.org/bot<TOKEN>/getUpdates`；3) 回應中 `result[0].message.chat.id` 即為你的 chat_id |

讀取位置：`app/controllers/auction_controller.py:495`

### 4.5 `google-auth.json`（可選）

僅當你使用 `app/services/google_sheet.py` 寫入 Google Sheets 時才需要。格式與 `firebase-cred.json` 相同（service account JSON）。

取得方式：Google Cloud Console → IAM 與管理 → 服務帳戶 → 建立 → 啟用 Google Sheets API → 建立金鑰 → 下載 JSON

讀取位置：`app/services/google_sheet.py:9`

**權限**：在目標試算表「共用」中加入 service account 的 `client_email`（編輯者）。

## 5. 常見調整情境速查

| 想做的事 | 改哪個檔 | 改哪個欄位 |
|---------|---------|-----------|
| 通知變嚴格 | `settings.json` | `price_drop_threshold` 改更負（如 -20） |
| 通知變敏感 | `settings.json` | `price_drop_threshold` 改較大值（如 -5） |
| 過濾低價物品更嚴 | `settings.json` | `min_gold_threshold` 調高 |
| 比較基準縮短 | `settings.json` | `price_compare_days` 改 3 |
| 拉長歷史視窗 | `settings.json` | `history_days` 改 60（注意記憶體） |
| 通知一次給更多筆 | `settings.json` | `notify_batch_size` 改 50 |
| 追蹤新類別 | `tracked_items.json` | `tracked_item_classes` 加類名 |
| 新增/移除自訂物品 | `tracked_items.json` | `custom_tracked_items` 增刪 ID |
| 排除舊資料片物品 | `tracked_items.json` | `item_id_threshold` 提高 |
| 換 Discord 頻道 | `discord-webhook.json` | `webhook_url` 換新 |
| 換 Telegram chat | `telegram-bot.json` | `chat_id` 換新 |
| 變更通知策略（類別/子類） | **改 SQL** `auction_controller.py:346` | hardcoded，無法用 JSON 設定調整 |
