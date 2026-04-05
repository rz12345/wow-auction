# 魔獸世界拍賣場價格監控系統

## 專案目的

監控魔獸世界拍賣場（台灣伺服器）的商品價格。從 Blizzard Battle.net API 抓取即時資料，將 28 天滾動歷史存入 SQLite，同步統計資料至 Firebase，並在偵測到顯著降價時透過 Discord 發送通知。

## 技術棧

| 層級 | 技術 |
|------|------|
| 程式語言 | Python 3.8+ |
| 資料處理 | pandas |
| 本地儲存 | SQLite（`data/db.sqlite`） |
| 雲端同步 | Firebase（Realtime DB、Firestore、Cloud Storage） |
| 資料來源 | Blizzard Battle.net API（tw.api.blizzard.com） |
| 通知 | Discord Webhook、Telegram Bot |
| 報表 | Google Sheets API |
| 執行器 | Windows 批次檔（`start.bat`）+ Anaconda 環境 |

## 目錄結構

```
wow-auction/
├── start.py                        # 進入點 — 執行抓取 + 統計更新
├── start.bat                       # Windows 執行器（啟動 Anaconda 環境）
│
├── app/
│   ├── controllers/
│   │   └── auction_controller.py   # 核心業務邏輯（409 行）
│   ├── services/
│   │   ├── battle_net.py           # OAuth2 Token 取得
│   │   ├── storage_firebase.py     # Firebase RT DB / Firestore / Storage
│   │   └── google_sheet.py         # Google Sheets 讀寫
│   ├── repositories/
│   │   └── wow_game_data.py        # Battle.net API 呼叫（物品、拍賣資料）
│   └── configs/                    # JSON 憑證檔案（已加入 .gitignore）
│       ├── battle-net-cred.json
│       ├── discord-webhook.json
│       ├── firebase-cred.json
│       ├── google-auth.json
│       └── telegram-bot.json
│
└── data/
    ├── db.sqlite                   # SQLite — items + auction_statistics 資料表
    ├── item_class.json             # 物品分類參考資料
    └── auction/
        ├── commodities-*.json      # 每日快照（每份約 10 MB）
        └── archived/               # 壓縮的舊快照（7z 格式）
```

## 架構

MVC 風格的分層架構：

```
start.py
  └── AuctionController（controllers/auction_controller.py）
        ├── WowGameData（repositories/wow_game_data.py）     ← Battle.net API 呼叫
        ├── BattleNet（services/battle_net.py）               ← OAuth Token
        ├── StorageFirebase（services/storage_firebase.py）   ← Firebase
        └── GoogleSheet（services/google_sheet.py）           ← Google Sheets
```

## 資料流

```
Battle.net API
  → fetch_commodities_data()  → data/auction/commodities-{ts}.json
                               → Firebase RT DB（/wow/auction_realtime）

data/auction/*.json（28 天視窗）
  → update_statics()          → SQLite（auction_statistics）
                               → Firebase RT DB（/wow/auction）
                               → Firebase Firestore

SQLite + Firebase
  → check_cheap_goods()       → Discord Webhook（降價警示通知）
```

## 核心方法（`auction_controller.py`）

| 方法 | 用途 |
|------|------|
| `fetch_commodities_data()` | 抓取即時價格、儲存 JSON、更新 Firebase |
| `update_statics()` | 彙整 28 天統計（最低/最高/中位數）至 SQLite + Firebase |
| `update_item_list()` | 同步新物品至 Firebase 物品追蹤清單 |
| `check_cheap_goods()` | 偵測相較 7 天均價降幅 >= 10% 的物品，通知 Discord |
| `notify_message()` | 發送 Discord Webhook（超過 2000 字元自動分批） |
| `query_item_quality()` | 將物品稀有度對應為星級顯示 |

## 追蹤物品類別

- 交易技能、物品附魔、寶石、消耗品
- 上述類別中 ID >= 210796 的物品
- 自訂追蹤：123918（脈石礦石）、132514（自動鐵鎚）

## 價格警示條件

- 相較 7 天均價降幅 >= 10%
- 歷史最低價格 >= 10,000 金幣
- 價格顯著上漲或下跌皆會發送通知

## SQLite 資料表結構

```sql
-- 物品主檔
items (id, name, level, required_level, quality_type, quality_name,
       item_class_name, item_class_id, item_subclass_name, item_subclass_id)

-- 歷史每日統計（28 天滾動視窗）
auction_statistics (item_id, min, max, median, qty, date)

-- 當日即時統計（每次執行後清除）
auction_statistics_realtime (item_id, min, max, median, qty, date)
```

## 檔案職責

| 檔案 | 用途 |
|------|------|
| `Todo.md` | 未完成項目，含做法說明與優先序 |
| `Task.md` | 已完成項目的歷史紀錄，依日期分段 |
| `CLAUDE.md` | 專案規範，本身的變動也需記錄至 `Task.md` |

> 已完成的項目**不留在 `Todo.md`**，一律移至 `Task.md`。

## 任務管理規則

每次工作階段遵循以下流程：

1. **開始前** — 讀取 `Todo.md` 了解待辦項目，讀取 `Task.md` 了解已完成的歷史
2. **進行中** — 完成的項目從 `Todo.md` 移除
3. **結束時** — 將本次完成的項目整理後**移入 `Task.md`**，標註日期與分類

## 程式碼規範

- 不可變性：回傳新物件，不直接修改原有物件
- 小而專一的檔案：每個模組維持在 400 行以內
- 每一層都要明確處理錯誤，不可靜默吞掉例外
- 驗證所有外部資料（API 回應）再進行處理
- 不可在程式碼中硬編碼機密資訊，所有憑證放在 `app/configs/*.json`（已加入 .gitignore）
- 常數（閾值、日期範圍、物品 ID）應放在設定檔中，不可直接寫死在程式裡
