# Brag Document Builder Web 完整版規格

## 1. 文件狀態

本文件記錄 Brag Document Builder `v1.1` 至 `v1.5` Web 完整版的已確認產品決策。

- `docs/SPEC.md` 繼續代表原始 CLI MVP 規格。
- 本文件擴充既有產品，不取代 Markdown 權威模型或既有 CLI 能力。
- 本文件描述產品行為與邊界；實作順序由 `PLAN2.md` 定義。

## 2. 產品目標

Web 完整版將既有 CLI 的 Slice 1 至 Slice 10 能力整合為本機工作台，讓單一使用者不必記憶命令即可完成：

1. 快速記錄工作。
2. 找出尚未分析的輸入。
3. 安全地送出 AI 分析。
4. 篩選並逐筆補強候選成果。
5. 分階段確認事實與生成措辭。
6. 建立、合併、封存或拒絕成果。
7. 產生 STAR、履歷條列與績效摘要。
8. 管理 Repository、Changelog 匯入與處理狀態。
9. 執行 MVP 評估與檢視報告。

## 3. 使用者與運行模式

- 單一使用者、本機優先。
- Web 服務只監聽 `127.0.0.1`。
- 不提供區域網路或網際網路存取。
- 不實作登入、多租戶或權限系統。
- Web 與 CLI 共用相同 Vault、Markdown 格式及操作設定。
- Docker 與本機 Python 啟動皆必須支援相同主要流程。

## 4. 核心產品原則

### 4.1 Markdown 權威

- Inbox、Achievements、Rejected 與 Outputs Markdown 是內容的唯一權威來源。
- Web 不能把瀏覽器狀態或操作 JSON 當成已確認成果。
- 使用者直接在 Obsidian 修改的確認事實優先於舊的分析或生成結果。
- 權威 Markdown 更新必須維持 atomic write 與格式驗證。

### 4.2 本機操作狀態

Web 可保存可重建狀態，例如：

- Capture ID 與內容 hash。
- 是否已分析、最後分析時間與模型。
- AI 候選結果與來源參照。
- 待補件、待確認與延後狀態。
- Repository 根目錄、註冊資訊與匯入 ledger。

操作狀態不是權威成果；刪除後可由 Markdown 與已註冊來源重建。API Key 不得寫入此狀態。

### 4.3 使用者控制

- AI 只能提出分群、評估、補件問題與措辭。
- 推論不能自動變成已確認事實。
- Confirm、Reject、Merge、Separate、Ignore、Archive 等決策由使用者明確執行。
- Web 不提供永久刪除；清理使用封存或拒絕。

## 5. 資訊架構

### 5.1 首頁待辦

首頁預設顯示：

- 今日新增 Capture 數量。
- 今日尚未分析數量。
- 全部待補件候選。
- 全部待確認候選。
- 最近確認成果。
- 來源已變更、需要重新分析或複查的項目。

首頁以待辦導向，不以 CLI 指令名稱作為主要導航。

### 5.2 主導航

建議功能區：

1. 首頁。
2. 收集。
3. 分析。
4. 審核。
5. 成果。
6. 輸出。
7. 匯入。
8. 工具與設定。

每個功能仍可對應既有 CLI 能力，但 UI 使用工作流程語言。

## 6. 介面方向

### 6.1 視覺風格

- 主風格為 C：極簡專注風。
- 三欄工作台：左側流程與主要動作、中間主操作、右側上下文與狀態。
- 支援專注模式，可隱藏左右欄。
- 不使用卡片堆疊或行銷式版面。
- 資料管理頁可依內容使用表格，但維持相同視覺語言。
- 介面需支援桌面與窄視窗，不得發生文字或控制項重疊。

### 6.2 快捷鍵

第一階段只支援 Web 頁面內快捷鍵：

- `Ctrl+Enter`：送出目前主要表單。
- `Ctrl+S`：儲存草稿。
- `Ctrl+Shift+A`：開啟或執行分析流程。

快捷鍵不得略過安全預覽或權威寫入確認。

## 7. Capture 流程

### 7.1 輸入模式

支援：

- 自由文字。
- 結構化欄位。
- Changelog 匯入。

結構化欄位固定使用：

- `context`：場景與問題。
- `action`：使用者做了什麼。
- `impact`：結果與量化。
- `evidence`：可驗證證據。

內建效能優化、穩定性修復、協作與交付範例。

### 7.2 Capture ID

- 新 Capture 具有不可變、穩定的 Capture ID。
- Capture ID 與來源參照必須能在後續分析、候選與成果間追溯。
- 既有未帶 ID 的 Inbox 區塊不改寫；讀取時依內容與來源位置產生可重建 ID。
- 新 Capture 必須先寫入 Inbox，才可進行 AI 分析。

### 7.3 草稿

- 草稿儲存在瀏覽器 `localStorage`。
- 草稿不是 Inbox 紀錄，也不會送往 OpenAI。
- Capture 成功後清空表單，但不影響其他未送出草稿。

## 8. Analyze 流程

### 8.1 預設範圍

- 預設分析今日尚未分析的 Capture。
- 使用者可改選今日全部、指定 Capture 或自訂 Inbox 範圍。
- Web 不應每次自動重送整份當日 Inbox。

### 8.2 Hash 與重複分析

- 每個分析來源保存內容 hash。
- 相同 hash 的已分析內容預設略過。
- 來源修改後顯示「內容已變更」，由使用者決定是否重新分析。
- 重新分析保留舊結果與時間，不能靜默覆蓋已確認事實。

### 8.3 AI 安全預覽

每次送 OpenAI 前必須開啟不可略過的確認視窗，顯示：

- 完整傳送內容。
- 估算 bytes。
- 使用模型。
- 敏感資訊警告。
- 明確取消與確認送出動作。

不得用工作階段記憶跳過確認。

### 8.4 分析結果

每筆輸入保留：

- Project/topic 分群。
- Classification：new candidate、supporting evidence 或 retained raw activity。
- Impact、difficulty、leadership/ownership、evidence strength、reusability 評分。
- 簡短 reason。
- Provider、model 與分析時間。
- Capture ID 與來源 hash。

OpenAI 回應需經 JSON 驗證與安全正規化；格式錯誤不得破壞 Inbox。

## 9. Review 流程

### 9.1 候選列表

列表提供：

- 狀態篩選。
- Project/topic 篩選。
- 搜尋。
- 來源變更提示。
- 批次選取後進入逐筆模式。

列表只負責總覽與篩選，不在表格內完成高風險事實確認。

### 9.2 逐筆工作台

逐筆審核時：

- 中欄顯示候選、評分、reason 與確認事實。
- 右欄顯示來源 Capture、既有成果、缺少欄位與歷史。
- 每輪最多提出三個補件問題。
- 問題可回答、略過或延後。
- AI 建議與使用者確認答案需清楚分離。

候選狀態包含：

- `needs-detail`。
- `ready-for-confirmation`。
- `confirmed`。
- `rejected`。
- `ignored`。

## 10. Confirm 與 Reject

確認維持四階段：

1. 確認分群與拆分。
2. 確認是否值得保留。
3. 逐項確認事實。
4. 確認生成措辭。

Web 需顯示目前階段與尚未完成步驟。返回上一步不得視為確認。

拒絕時：

- 必須輸入理由。
- 保留來源參照。
- 寫入 Rejected Markdown。
- 後續分析應能辨識既有拒絕決策，避免重複提案。

## 11. Attach、Merge 與衝突

當候選可能屬於既有成果時，Web 提供：

- Merge：合併來源或事實。
- Separate：建立獨立成果。
- Ignore：保留追溯但不建立成果。

Merge 前必須顯示：

- 目標 achievement ID 與檔案。
- 既有與新來源。
- 每個衝突欄位的舊值與新值。
- 將被更新的生成區塊。

任何確認事實替換都需逐項同意；不能自動解決衝突。

## 12. Achievements

成果頁支援：

- 搜尋與狀態篩選。
- 依 immutable ID 讀取成果，不依檔名判定身分。
- 顯示確認事實、來源、生成內容與缺少證據。
- 封存成果。
- 重新產生指定 generated 區塊。

Web 不提供永久刪除。使用者仍可直接在 Obsidian 編輯 Markdown。

## 13. Outputs

支援：

- STAR story。
- Resume bullet。
- Performance summary。
- 中文與英文。
- 單一成果或多成果聚合。

產生後直接寫入既有 Markdown/Outputs 模型，再於 Web 顯示結果與路徑。

- 只能使用確認事實。
- 缺少數字時只能使用明確 placeholder，如 `[X%]`。
- 不得把推論呈現為已確認結果。
- 重新生成不得修改確認事實。

## 14. Repository 與 Changelog

### 14.1 多個允許根目錄

- 使用者在 Web 設定頁新增或移除多個 Repository 根目錄。
- 系統不得自動掃描所有子目錄或自動註冊 Repository。
- 根目錄僅限制檔案選擇器可瀏覽範圍。
- 註冊仍需明確選擇 repo 路徑與 changelog 路徑。

### 14.2 註冊與匯入

Web 支援：

- Register、list、remove。
- 選取 Changelog heading/range。
- 預覽精確匯入文字。
- 明確確認後寫入 Inbox。
- 選擇是否接續 Analyze。

### 14.3 增量處理

- 保存來源 hash 與 range ledger。
- 相同內容略過。
- 修改內容顯示 diff 與可能受影響成果。
- 需要使用者確認後才重新匯入或重新分析。
- 提供 ledger rebuild 工具與結果摘要。

## 15. MVP Eval

工具頁提供：

- 選擇 fixture JSON。
- deterministic 模式。
- simulate OpenAI failure 模式。
- 執行狀態與報告路徑。
- 門檻結果、missed achievements、false positives 與逐案例 traceability。

評估不得將 API Key、完整秘密或非必要私密資料寫入報告。

## 16. 設定中心

設定頁可管理：

- Vault 狀態與路徑。
- 預設模型。
- Max bytes。
- Repository 根目錄。
- 已註冊 Repository。
- 操作狀態與 ledger rebuild。

`OPENAI_API_KEY`：

- 不顯示。
- 不提供 Web 編輯。
- 不回傳遮罩片段。
- 缺少時僅顯示可操作的設定說明。

## 17. 錯誤與恢復

- 所有錯誤需顯示可操作說明，不得靜默失敗。
- Capture 寫入成功與 AI 分析失敗需分開呈現。
- 網路、認證、格式、檔案、衝突與驗證錯誤需有不同訊息。
- 長時間操作需顯示進度與防止重複送出。
- 重試不能重複寫入 Capture 或成果。
- Malformed authoritative Markdown 必須拒絕修改並提供檔案路徑與修復方向。

## 18. 非目標

`v1.1` 至 `v1.5` 不包含：

- 多使用者與登入。
- 公開網路部署。
- Windows 全域快捷鍵或常駐托盤程式。
- 自動匿名化。
- 語音輸入。
- Git commit history 或 GitHub API ingestion。
- Jira、Calendar 等外部整合。
- 多 AI provider。
- 永久刪除權威資料。
- 自動掃描所有 Repository。
- 自動修改確認事實。

## 19. 成功標準

完整版成功需滿足：

- 使用者可不開終端完成所有既有 CLI 主要能力。
- 新 Capture 不會因 AI 失敗而遺失。
- 預設只分析尚未處理內容，避免不必要重複費用。
- 所有 AI 呼叫都經完整安全預覽確認。
- 所有權威寫入都能追溯 Capture 與 candidate。
- Confirm/Attach 不會靜默修改事實。
- Web 與 CLI 對相同 Markdown 產生一致結果。
- 主要工作流程可在桌面與窄視窗使用。
- 自動測試覆蓋成功、取消、重試、衝突、malformed Markdown 與秘密不外洩。
- 原 MVP 評估門檻繼續通過。
