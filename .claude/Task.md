# 已完成任務

## 核心基礎建設

- [x] **外部化硬編碼常數**（2026-04-05）— 建立 `app/configs/settings.json`；將 `item_id_threshold`、`tracked_item_classes`、`custom_tracked_items`、`history_days`、`price_compare_days`、`price_drop_threshold`、`min_gold_threshold`、`notify_batch_size` 全數移出 controller，`__init__` 載入後以 `self.*` 引用
- [x] **新增 `requirements.txt`**（2026-04-05）— 列出所有相依套件與固定版本：pandas==2.3.3、requests==2.32.5、firebase-admin==7.3.0、gspread==2.49.1、google-auth==2.49.1、py7zr==1.1.0
- [x] **Windows 工作排程器**（2026-04-05）— 排程建立於 `\WowAuction\WowAuctionMonitor`；每 4 小時執行 `start.py`，log 輸出至 `logs/scheduler.log`
- [x] **自動封存腳本**（2026-04-05）— 新增 `auction_controller.py::archive_old_files()`；超過 28 天的 JSON 快照依年月壓縮為 `data/auction/archived/auction-{YYYYMM}.7z`，壓縮成功後自動刪除原始檔；`start.py` 每次執行結尾自動呼叫
- [x] **MVC 專案結構** — 建立 `controllers/`、`services/`、`repositories/`、`configs/`、`data/` 目錄
- [x] **SQLite 資料表結構** — 建立 `items`、`auction_statistics`、`auction_statistics_realtime` 資料表
- [x] **Windows 批次執行器** — `start.bat` 啟動 Anaconda 環境並執行 `start.py`

## Battle.net 整合

- [x] **OAuth2 Token 取得** — `services/battle_net.py` 實作 Client Credentials 流程，向 `https://oauth.battle.net/token` 取得存取 Token
- [x] **商品資料抓取** — `wow_game_data.py::fetchCommoditiesData()` 從台灣伺服器 API 抓取即時全球商品價格
- [x] **物品詳細資料抓取** — `wow_game_data.py::fetchItemInfo()` 從 Battle.net 取得物品名稱、等級、品質、分類
- [x] **伺服器資料抓取** — `fetchRealmsData()` 和 `fetchRealmsList()` 用於查詢連結伺服器

## 資料管道

- [x] **快照儲存為本地 JSON** — `fetch_commodities_data()` 將帶有時間戳記的 `data/auction/commodities-{ts}.json` 存至本地（每份約 10 MB）
- [x] **28 天滾動封存** — 超過 28 天的檔案自動移至 `data/auction/archived/`（7z 壓縮格式）
- [x] **統計彙整** — `update_statics()` 讀取 28 天視窗內的 JSON 檔案，透過 pandas groupby 計算每個物品的最低/最高/中位數/數量
- [x] **SQLite 持久化** — 彙整後的統計寫入 `auction_statistics` 資料表；即時統計寫入 `auction_statistics_realtime`

## Firebase 同步

- [x] **Realtime Database 同步** — 價格統計推送至 `/wow/auction` 和 `/wow/auction_realtime` 節點
- [x] **Cloud Firestore 同步** — 每次執行時維護 28 天滾動文件集合
- [x] **Cloud Storage 整合** — JSON 匯出檔可上傳至 Firebase Storage，支援列表/下載/刪除操作
- [x] **物品追蹤清單** — `update_item_list()` 將新發現的物品同步至 Firebase `/wow/item_focus_list`

## 通知功能

- [x] **Discord 降價警示** — `check_cheap_goods()` 偵測相較 7 天均價降幅 >= 10% 的物品，發送格式化的 Discord 訊息
- [x] **Discord 訊息分批** — `notify_message()` 在超過 Discord 2000 字元限制時自動分批發送
- [x] **物品品質星級顯示** — `query_item_quality()` 將稀有度等級對應為星級字串

## 通知功能異動（2026-04-05）

- [x] **移除 LINE Notify** — 刪除 `app/configs/line-notify-token.json`，LINE Notify 從未實作，正式廢棄
- [x] **新增 Telegram Bot 通知** — 建立 `app/configs/telegram-bot.json`（含 `bot_token`、`chat_id` 欄位）；在 `auction_controller.py` 新增 `TELEGRAM_CRED_PATH` 常數與 `notify_telegram()` 方法（支援超過 4096 字元自動分批）；`check_cheap_goods()` 現在同時呼叫 Discord 與 Telegram 發送通知
- [x] **填寫 Telegram Bot 憑證** — `bot_token` 與 `chat_id` 已填入 `app/configs/telegram-bot.json`，Telegram 通知功能已可正常使用

## 報表功能

- [x] **Google Sheets 整合** — `services/google_sheet.py` 支援讀取（`getData`、`getColumnVals`）和寫入（`addRow`、`addRows`）操作

## 物品分類

- [x] **類別篩選** — 僅追蹤 交易技能/物品附魔/寶石/消耗品 類別且 ID >= 210796 的物品
- [x] **自訂物品追蹤** — 硬編碼特殊物品：123918（脈石礦石）、132514（自動鐵鎚）
- [x] **物品分類參考資料** — 載入 `data/item_class.json` 解析分類名稱
