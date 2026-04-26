# 部署文件

> 目標讀者：個人維護者（重灌、換機、調整排程時的操作手冊）

## 1. 環境需求

| 項目 | 需求 |
|------|------|
| OS | Windows 10 / 11（測試於 Windows 11 Pro 26200） |
| Python | 3.8+（生產環境用 Anaconda 3.11 / 3.12） |
| 磁碟 | 至少 5 GB 空間（28 天 JSON 快照約 280 MB；archived 7z 累計約 2 GB） |
| 網路 | 可連 `tw.api.blizzard.com`、`oauth.battle.net`、`firebase.googleapis.com`、`api.telegram.org`、`discord.com` |

## 2. 安裝步驟

### 2.1 取得程式碼

```bash
git clone <repo-url> wow-auction
cd wow-auction
```

### 2.2 建立 Python 環境

```bash
# 建立 Anaconda 環境
conda create -n wow-auction python=3.11
conda activate wow-auction

# 安裝相依
pip install -r requirements.txt
```

`requirements.txt` 目前內容：

```
pandas==2.3.3
requests==2.32.5
gspread==2.49.1
google-auth==2.49.1
py7zr==1.1.0
```

> 註：`firebase-admin` 已於 2026-04-05 移除，所有 Firebase 操作改用 REST API + `google-auth`（見 [ARCHITECTURE.md §6.1](ARCHITECTURE.md)）。

### 2.3 建立資料夾

```bash
mkdir -p data/auction/archived logs
```

## 3. 憑證準備

於 `app/configs/` 放入下列 5 份 JSON。**所有檔案皆已加入 `.gitignore`**（除了 `settings.json` / `tracked_items.json`）。

| 檔案 | 取得管道 | 必要欄位 |
|------|---------|---------|
| `battle-net-cred.json` | [Battle.net Developer Portal](https://develop.battle.net/) → 建立 Client | `client_id`、`client_secret` |
| `firebase-cred.json` | Firebase Console → 專案設定 → 服務帳戶 → 產生新私密金鑰 | 整份 service account JSON（含 `private_key` 等 10+ 欄位） |
| `discord-webhook.json` | Discord 伺服器 → 頻道設定 → 整合 → Webhooks → 新建 | `webhook_url` |
| `telegram-bot.json` | Telegram BotFather → `/newbot` 取得 token；發送一則訊息給 bot 後從 `getUpdates` 取得 chat_id | `bot_token`、`chat_id` |
| `google-auth.json`（可選，僅 Sheets 報表用） | Google Cloud Console → IAM → Service Account → 建立金鑰 | 整份 service account JSON |

**詳細欄位範例**請見 [CONFIGURATION.md](CONFIGURATION.md)。

## 4. 首次執行

### 4.1 直接以 Python 執行

```bash
conda activate wow-auction
cd <專案目錄>
python start.py
```

### 4.2 建立 Windows 批次檔（推薦）

於專案根目錄建立 `start.bat`：

```bat
@echo off
call C:\ProgramData\anaconda3\Scripts\activate.bat wow-auction
cd /d C:\projects\wow-auction
python ./start.py
```

> ⚠️ 將 `C:\ProgramData\anaconda3` 與 `C:\projects\wow-auction` 替換為你機器上的實際路徑。

執行：

```bash
start.bat
```

### 4.3 預期輸出

成功執行會在 `logs/app.log` 看到（同步輸出至 console）：

```
2026-XX-XX XX:XX:XX [INFO] app.controllers.auction_controller - 統計完成 2026-XX-XX：[...]
2026-XX-XX XX:XX:XX [INFO] app.services.storage_firebase - RT DB 寫入完成：/wow/auction
2026-XX-XX XX:XX:XX [INFO] app.controllers.auction_controller - archive_old_files: 2026XX → auction-2026XX.7z（N 個檔案）
```

### 4.4 首次執行會做什麼

1. 建立 SQLite 三張表（首次執行時隱式建立，因為 `INSERT` 自動建表）
2. 抓取一份完整的 commodities 資料（單檔約 10 MB）寫入 `data/auction/commodities-{ts}.json`
3. 對所有新出現的物品（資料庫中沒有的）逐一呼叫 `fetchItemInfo`（每物品 sleep 1 秒，避免被 rate limit；首次跑可能耗 5-15 分鐘）
4. 寫入 Firebase RT DB 三個節點：`/wow/auction_realtime`、`/wow/auction`、`/wow/item_focus_list`
5. 觸發 `check_cheap_goods` — 但首次跑因無歷史資料，不會發出通知

## 5. Windows 工作排程器設定

### 5.1 建立排程（GUI）

1. 開啟「工作排程器」
2. 動作 → 建立工作（注意：不是「建立基本工作」）
3. **一般** 分頁：
   - 名稱：`WowAuctionMonitor`
   - 位置：`\WowAuction\`（可手動輸入建立資料夾）
   - 勾選「不論使用者登入與否均執行」
   - 勾選「以最高權限執行」
4. **觸發程序** 分頁 → 新增：
   - 開始工作：依排程
   - 重複每隔：4 小時，持續時間：1 天
5. **動作** 分頁 → 新增：
   - 動作：啟動程式
   - 程式或指令碼：`C:\projects\wow-auction\start.bat`
   - 開始位置：`C:\projects\wow-auction\`
6. **設定** 分頁：
   - 勾選「如果工作執行超過時間則停止」設為 1 小時

### 5.2 將排程輸出導向 log

修改 `start.bat`：

```bat
@echo off
call C:\ProgramData\anaconda3\Scripts\activate.bat wow-auction
cd /d C:\projects\wow-auction
python ./start.py >> logs\scheduler.log 2>&1
```

### 5.3 驗證排程

```powershell
# PowerShell 列出排程
Get-ScheduledTask -TaskPath "\WowAuction\" -TaskName "WowAuctionMonitor"

# 手動觸發一次
Start-ScheduledTask -TaskPath "\WowAuction\" -TaskName "WowAuctionMonitor"
```

## 6. 日誌與資料維護

### 6.1 日誌位置

| 路徑 | 內容 | 輪替 |
|------|------|------|
| `logs/app.log` | Python `logging` 模組輸出（INFO/WARNING/ERROR） | **無自動輪替**，建議定期 truncate 或外掛 `logrotate` |
| `logs/scheduler.log` | `start.bat` 的 stdout/stderr（包含 conda activate 訊息） | 同上 |

### 6.2 資料目錄

| 路徑 | 用途 | 維護建議 |
|------|------|---------|
| `data/db.sqlite` | 主資料庫 | 每月手動備份 1 份至外部位置；單檔通常 < 100 MB |
| `data/auction/*.json` | 28 天內的快照 | 自動由 `archive_old_files()` 處理，毋須手動介入 |
| `data/auction/archived/auction-{YYYYMM}.7z` | 月封存檔 | 累積到一定大小可手動轉移至外部備份；**勿刪除**，內含長期歷史 |
| `data/item_class.json` | 物品分類參考表 | 靜態資料，毋須維護（除非 Battle.net 新增物品大類） |

### 6.3 SQLite 備份指令

```bash
# 線上備份（不會鎖表）
sqlite3 data/db.sqlite ".backup data/db_backup_$(date +%Y%m%d).sqlite"
```

## 7. 故障排查

### 7.1 啟動立即失敗 — `RuntimeError: 找不到設定檔`

- 檢查 `app/configs/settings.json` 與 `tracked_items.json` 是否存在
- 確認 `start.bat` 的 `cd /d` 路徑正確

### 7.2 `RuntimeError: 無法取得 Battle.net access token`

- 檢查 `app/configs/battle-net-cred.json` 的 `client_id` / `client_secret` 是否填寫
- 至 [Battle.net Developer Portal](https://develop.battle.net/) 確認 Client 仍有效（未被停用）
- 檢查網路：`curl https://us.battle.net/oauth/token`（注意：endpoint 是 us 不是 tw，見 `battle_net.py:9`）

### 7.3 `RuntimeError: 無法取得拍賣場資料`

- Battle.net API 偶有維護，先重試一次
- 檢查 `tw.api.blizzard.com` 是否可達

### 7.4 Firebase 寫入 403

- service account 缺少 scope，確認 `firebase-cred.json` 對應的 IAM 角色含：
  - `Firebase Realtime Database Admin`
  - `Cloud Datastore User`（Firestore）
  - `Storage Object Admin`（Cloud Storage）
- 對照 `storage_firebase.py:11-16` 的 `_SCOPES` 清單

### 7.5 Discord 通知不發

- 即使有降價物品，若不符 SQL 條件（`item_class_id = 0 AND item_subclass_id IN (1, 3, 5, 9) OR item_class_id = 8`）也不會通知
- 檢查 `min_gold_threshold`（預設 10000）— 7 天最低價低於此值的物品會被排除
- 檢查 `app/configs/discord-webhook.json` 的 `webhook_url` 是否仍有效（Discord 頻道刪除/重建會失效）
- 看 `logs/app.log` 是否有 `Discord 發送失敗，狀態碼：` 字樣

### 7.6 Telegram 通知不發

- 確認 `app/configs/telegram-bot.json` 的 `bot_token` 與 `chat_id` 正確
- 用瀏覽器測試：`https://api.telegram.org/bot{bot_token}/getMe`
- 確認 bot 已被加入目標 chat（個人 chat 需先主動發訊息給 bot）

### 7.7 `UnicodeDecodeError: 'cp950'` 讀取 settings 時

- 已修正（commit `835ae00`）— 所有 `open()` 含 `encoding='utf-8'`
- 若舊版本仍報此錯，pull 最新 main 即可

### 7.8 `update_statics` 寫入後 Firebase RT DB 沒更新

- `/wow/auction` 節點寫入是「全量覆蓋」（`PUT`），檢查資料是否真的有變化
- 看 `logs/app.log` 是否有 `RT DB 寫入完成：/wow/auction`

### 7.9 7z 封存失敗

- 檢查 `data/auction/archived/` 資料夾是否存在且可寫
- `py7zr` 對單檔最大支援足夠，但**多次 append** 同一個 7z 可能導致檔案損毀；若發現異常可手動刪除當月 7z 後重跑（會重建）

## 8. 升級與遷移

### 8.1 套件升級

```bash
# 升級單一套件
pip install --upgrade pandas
# 凍結新版本至 requirements.txt
pip freeze | grep -E "pandas|requests|gspread|google-auth|py7zr" > requirements.txt
```

### 8.2 換機

1. 複製整個專案目錄（含 `data/`、`logs/`、`app/configs/`）
2. 在新機重建 conda 環境（步驟 §2.2）
3. 編輯 `start.bat` 中的路徑
4. 重新建立 Windows 排程器（步驟 §5）
