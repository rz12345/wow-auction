# API 與資料路徑映射

> 列出所有外部 API endpoint、Firebase 資料路徑、通知 payload 格式，供故障排查與擴充功能參考。

## 1. Battle.net API

### 1.1 OAuth2 Token

| 項目 | 值 |
|------|-----|
| Endpoint | `POST https://us.battle.net/oauth/token` |
| 認證方式 | HTTP Basic Auth（`client_id` : `client_secret`） |
| Params | `grant_type=client_credentials` |
| Timeout | 10 秒 |
| 呼叫位置 | `app/services/battle_net.py:9` |

**Token 用途**：存於 `AuctionController.access_token`，附於後續 Game Data API 的 `Authorization: Bearer <token>` header。

> ⚠️ 註：endpoint 是 `us.battle.net` 而非 `tw.battle.net`。OAuth 端點全球共用，但 Game Data 端點區分區域。

### 1.2 Game Data Endpoints

所有 Game Data 呼叫通過 `WowGameData._get()`（`wow_game_data.py:16`）統一處理 timeout、JSON 解析、錯誤記錄。

| 用途 | Method | URL | Params | 呼叫者 |
|------|--------|-----|--------|--------|
| 取得連結伺服器索引 | GET | `https://tw.api.blizzard.com/data/wow/connected-realm/index` | `namespace=dynamic-tw` | `fetchRealmsData` |
| 取得單一連結伺服器詳情 | GET | `<href from index>` | `namespace=dynamic-tw` | `fetchRealmsList` |
| 取得伺服器拍賣資料 | GET | `https://tw.api.blizzard.com/data/wow/connected-realm/{realm_id}/auctions` | `namespace=dynamic-tw, locale=zh_TW` | `fetchAuctionData` |
| **取得全球商品價格** | GET | `https://tw.api.blizzard.com/data/wow/auctions/commodities` | `namespace=dynamic-tw, locale=zh_TW` | `fetchCommoditiesData` |
| 取得物品 metadata | GET | `https://tw.api.blizzard.com/data/wow/item/{item_id}` | `namespace=static-tw, locale=zh_TW` | `fetchItemInfo`（含 1 秒 sleep） |

**Namespace 說明**：
- `dynamic-tw`：頻繁變動的資料（伺服器、拍賣）
- `static-tw`：靜態資料（物品、品質、職業）

### 1.3 Commodities 回應格式（精簡示意）

```json
{
    "_links": { ... },
    "auctions": [
        {
            "id": 12345678,
            "item": { "id": 238365 },
            "quantity": 5,
            "unit_price": 50000,
            "time_left": "VERY_LONG"
        },
        ...
    ]
}
```

驗證邏輯：`app/helpers/validators.py::validate_auction_record()`（`unit_price` 必為非負 int、`quantity` 必為正 int）。

### 1.4 Item Info 回應格式（用到的欄位）

```json
{
    "id": 238365,
    "name": "物品中文名",
    "level": 600,
    "required_level": 60,
    "quality": { "type": "EPIC", "name": "史詩" },
    "item_class": { "id": 8, "name": "寶石" },
    "item_subclass": { "id": 0, "name": "寶石" }
}
```

對應到 SQLite `items` 資料表（`auction_controller.py:256`）。

## 2. Firebase 路徑映射

Project ID：`jojocat-wow-f72a5`（`storage_firebase.py:20`）

### 2.1 Realtime Database

Database URL：`https://jojocat-wow-f72a5-default-rtdb.asia-southeast1.firebasedatabase.app`

| 路徑 | 寫入時機 | Method | 內容結構 |
|------|---------|--------|---------|
| `/wow/auction` | `update_statics()` 每次執行末尾 | PUT（全量覆蓋） | `{ item_id: [{min, max, median, qty, date}, ...] }` 28 天每天一筆 |
| `/wow/auction_realtime` | `fetch_commodities_data()` 末尾 | PUT | `{ item_id: [{min, max, median, qty, date}] }` 當日即時 |
| `/wow/item_focus_list` | `update_item_list()` 末尾 | PUT | `{ item_id: { id, name, level, required_level, quality_type, quality_name, item_class_name, item_class_id, item_subclass_name, item_subclass_id } }` |

REST URL 格式：`<DATABASE_URL>/<path>.json`（`storage_firebase.py:39`）

### 2.2 Cloud Firestore

Base：`https://firestore.googleapis.com/v1/projects/jojocat-wow-f72a5/databases/(default)/documents`

| 操作 | Method | URL Pattern | 呼叫者 |
|------|--------|-------------|--------|
| 寫入單一文件 | PATCH | `.../{collection_name}/{document_id}` | `updateCollection` |
| 列出 collection 內所有 doc id | GET | `.../{collection_name}` | `getCollectionDocIdList` |
| 讀取近 28 天文件 | GET | `.../{collection_name}` | `getDocuments`（過濾近 28 天） |
| 刪除文件 | DELETE | `.../{collection_name}/{document_id}` | `deleteDocument` |

**型別轉換**：Firestore REST 需要 typed value 包裝（`integerValue`、`doubleValue`、`mapValue` 等），由 `_to_fs_value` / `_from_fs_value` 遞迴處理（`storage_firebase.py:75-106`）。

### 2.3 Cloud Storage

Bucket：`jojocat-wow-f72a5.appspot.com`（`storage_firebase.py:22`）

| 操作 | Method | URL | 呼叫者 |
|------|--------|-----|--------|
| 上傳 JSON | POST | `https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o?uploadType=media&name={filename}` | `uploadJsonByDict` |
| 列出物件 | GET | `https://storage.googleapis.com/storage/v1/b/{bucket}/o?prefix={path}` | `getStorageFileList` |
| 下載 JSON | GET | `https://storage.googleapis.com/storage/v1/b/{bucket}/o/{filename}?alt=media` | `getStorageJsonFileContent` |
| 刪除物件 | DELETE | `https://storage.googleapis.com/storage/v1/b/{bucket}/o/{filename}` | `deleteStorageFile` |

**filename URL encoding**：所有 filename 通過 `urllib.parse.quote(name, safe='')` 處理，斜線會被 encode 為 `%2F`（`storage_firebase.py:159`）。

## 3. 通知 API

### 3.1 Discord Webhook

| 項目 | 值 |
|------|-----|
| Endpoint | `POST <webhook_url from discord-webhook.json>` |
| Headers | `Content-Type: application/json` |
| Body | `{"content": "<msg text>"}` |
| 字元限制 | 2000 字元/則 |
| 預期狀態碼 | 200 或 204 |
| Timeout | 10 秒 |
| 呼叫位置 | `app/controllers/auction_controller.py:387` |

**分批策略**（`auction_controller.py:406-426`）：
1. 若 `len(msg) > 2000`，按 `\n` 切分
2. 累加每一行直到下一行會超過 2000，封存當前 chunk 開新 chunk
3. 每個 chunk 獨立 POST

### 3.2 Telegram Bot

| 項目 | 值 |
|------|-----|
| Endpoint | `POST https://api.telegram.org/bot{bot_token}/sendMessage` |
| Headers | `Content-Type: application/json` |
| Body | `{"chat_id": "<chat_id>", "text": "<msg text>"}` |
| 字元限制 | 4096 字元/則 |
| 預期狀態碼 | 200 |
| Timeout | 10 秒 |
| 呼叫位置 | `app/controllers/auction_controller.py:490` |

**分批策略**：與 Discord 相同邏輯，上限改為 4096（`auction_controller.py:505-515`）。

### 3.3 通知訊息格式

`check_cheap_goods` 產生的 msg 結構：

```
📢商品(三星或無星)比過去 7 天的價格下跌
{物品名} {⭐⭐⭐ 或 無星} / {現價/10000}G / 📉{ratio}%，https://rz12345.github.io/wow-auction/#/{class_id}/{subclass_id}/{item_id}
{物品名} ⭐⭐⭐ / {現價}G / 📉{ratio}%，<url>
...
---------------
📢商品(三星或無星)比過去 7 天的價格上漲
{物品名} ⭐⭐⭐ / {現價}G / 📈+{ratio}%，<url>
...
---------------
```

URL 指向外部 GitHub Pages 看板：`https://rz12345.github.io/wow-auction/#/{item_class_id}/{item_subclass_id}/{item_id}`

## 4. Google Sheets API（可選）

| 項目 | 值 |
|------|-----|
| 套件 | `gspread` 2.49.1 |
| Scope | `https://www.googleapis.com/auth/spreadsheets` |
| 認證 | service account（`google-auth.json`） |
| 呼叫位置 | `app/services/google_sheet.py` |

| 操作 | 方法 | gspread 對應 |
|------|------|--------------|
| 讀取整份工作表為 DataFrame | `getData()` | `worksheet.get_all_records()` |
| 讀取單欄 | `getColumnVals(col_idx)` | `worksheet.col_values(col_idx)` |
| 附加單列 | `addRow(list_data)` | `worksheet.append_row(..., table_range='A1')` |
| 附加多列 | `addRows(list_data)` | `worksheet.append_rows(..., table_range='A1')` |

**初始化方式**：

```python
gs = GoogleSheet(sheet_url='https://docs.google.com/spreadsheets/d/...', worksheet_name='Sheet1')
df = gs.getData()
gs.addRow(['col_a', 'col_b', 'col_c'])
```

> 目前 `GoogleSheet` 並未在 `start.py` 流程中使用，僅供臨時報表或 ad-hoc 查詢。

## 5. SQLite 查詢索引

主要 SQL 查詢位置（供調整通知範圍時參考）：

| 用途 | 位置 | 說明 |
|------|------|------|
| 撈取追蹤物品清單 | `auction_controller.py:74` | `id >= threshold AND class IN (...)` |
| 寫入歷史統計 | `auction_controller.py:162` | `df_stat.to_sql('auction_statistics', ...)` |
| 寫入即時統計 | `auction_controller.py:224` | `df_stat.to_sql('auction_statistics_realtime', ...)` |
| **降價偵測核心 SQL** | `auction_controller.py:307-350` | 含 hardcoded 通知範圍過濾 |
| 物品星級查詢 | `auction_controller.py:537-552` | 同名物品按 ID 排序映射為 1/2/3 星 |

## 6. 外部端點清單（防火牆白名單）

| Domain | 用途 |
|--------|------|
| `us.battle.net` | OAuth token |
| `tw.api.blizzard.com` | Battle.net Game Data |
| `*-default-rtdb.asia-southeast1.firebasedatabase.app` | Firebase RT DB |
| `firestore.googleapis.com` | Firestore |
| `storage.googleapis.com` | Cloud Storage |
| `oauth2.googleapis.com` | Google service account token 刷新 |
| `discord.com` | Discord Webhook |
| `api.telegram.org` | Telegram Bot |
| `sheets.googleapis.com` | Google Sheets（如使用） |
