# 待辦任務

## 高優先度

## 品質與穩定性

- [ ] **將 `print` 替換為 `logging`** — 目前所有除錯/資訊輸出均使用 `print`；改用 Python `logging` 模組，支援可設定的日誌等級與檔案輸出
- [ ] **改善錯誤處理** — 部分 `try/except` 區塊過於寬泛或靜默吞掉例外；應加入具體的例外類型並在失敗時記錄完整上下文
- [ ] **輸入資料驗證** — 在處理前驗證 Battle.net API 回應（檢查缺少的欄位、非預期的型別）

## 測試

- [ ] **單元測試** — 目前測試覆蓋率為零；應為以下功能新增測試：
  - `statics_auction_records()` 統計彙整邏輯
  - `check_cheap_goods()` 降價偵測邏輯
  - `query_item_quality()` 星級對應邏輯
  - `notify_message()` / `notify_telegram()` 訊息分批邏輯
- [ ] **整合測試** — 模擬 Firebase 和 Battle.net 呼叫，端對端測試完整資料管道

## 自動化


## 架構與維護

- [ ] **修正 Firebase 服務拼字錯誤** — `storage_firebase.py` 中的 `getDocuemnts()` 應改為 `getDocuments()`
- [ ] **評估更輕量的 Firebase 客戶端** — `firebase-admin` 套件較重；評估直接使用 Firebase REST API 以簡化部署
- [ ] **分離物品 ID 設定** — 將追蹤物品 ID 和類別篩選條件從 `auction_controller.py` 移至 `app/configs/tracked_items.json`
