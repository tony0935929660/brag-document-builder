# Brag Document Builder

以本地優先為核心的 CLI 工具，協助你把零散工作紀錄整理成可確認的成就，並產出可直接使用的職涯內容。

## 特色

- Markdown 權威模型：已確認事實與 AI 生成措辭分離保存。
- 安全優先分析流程：送出前預覽、警示、明確 YES 確認、最大位元組限制。
- 已完成 Slice 1 到 Slice 10。
- 內建 MVP 評估流程，支援可重現的 deterministic 驗證與門檻報告。

## 目前版本

- 最新標籤：v0.10.0
- Python 需求：3.12 以上

## 快速開始

建立並啟用虛擬環境。

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

執行核心流程。

```bash
python -m src.brag_cli init-vault --path /path/to/vault
python -m src.brag_cli capture-text --text "Reduced p95 latency by 28% in checkout flow"
python -m src.brag_cli analyze-inbox --model gpt-4o-mini
python -m src.brag_cli review-candidate --mode immediate
python -m src.brag_cli confirm-candidate --candidate-id <candidate-id>
python -m src.brag_cli generate-outputs --achievement-id <achievement-id> --output-types star,resume-bullet,performance-summary --language en
```

## Docker 即開即用（Windows）

第一次設定（只做一次）：

```powershell
Copy-Item .env.example .env
```

編輯 `.env`，填入你的值：

```dotenv
OPENAI_API_KEY=sk-your-key
VAULT_PATH=C:\Users\你的帳號\Documents\Obsidian Vault
```

之後每次開機只要 Docker Desktop 有啟動，在專案根目錄執行：

```powershell
.\brag.ps1 show-config
.\brag.ps1 capture-text --text "test entry from docker" --vault /vault
.\brag.ps1 analyze-inbox --vault /vault --model gpt-4o-mini
```

如果不帶參數：

```powershell
.\brag.ps1
```

會直接顯示 CLI help。

## 本機 Web 介面（極簡三欄）

先安裝依賴：

```powershell
python -m pip install -e .
```

啟動本機頁面：

```powershell
python -m src.web_app --host 127.0.0.1 --port 8765
```

開啟瀏覽器到：

- http://127.0.0.1:8765

目前 Web 版支援：

- 手動輸入（自由文字或結構化欄位）
- 送出到 Inbox
- 直接分析當日 Inbox

結構化欄位主框架（建議預設使用）：

- context：場景與問題
- action：你做了什麼
- impact：結果與量化
- evidence：可驗證證據

介面內建三個可套用範例：

- 效能優化
- 穩定性修復
- 協作與交付

快捷鍵：

- Ctrl+Enter：送出記錄
- Ctrl+S：儲存草稿（瀏覽器 localStorage）
- Ctrl+Shift+A：分析 Inbox

## MVP 評估（Slice 10）

Deterministic 端到端檢查：

```bash
python -m src.brag_cli mvp-eval --fixtures-file tests/fixtures/mvp_eval_cases.json --deterministic
```

模擬 OpenAI 失敗模式：

```bash
python -m src.brag_cli mvp-eval --fixtures-file tests/fixtures/mvp_eval_cases.json --deterministic --simulate-openai-failure
```

評估報告會包含分群接受率、值得保留項目漏抓率、輕微改寫率、平均處理時間，以及每個案例的追溯資訊。

## 指令分組

- Vault 與設定：init-vault、show-config
- 擷取與分析：capture-text、capture-prompted、analyze-inbox、review-candidate
- 決策流程：confirm-candidate、attach-candidate
- 內容產出：generate-outputs
- Repo 匯入：repo-register、repo-list、repo-remove、changelog-import、import-ledger-rebuild
- 評估：mvp-eval

## 測試

```bash
python -m unittest discover -s tests
```

## 文件

- [docs/SPEC.md](docs/SPEC.md)
- [docs/PLAN.md](docs/PLAN.md)
- [CHANGELOG.md](CHANGELOG.md)
- English version: [README.en.md](README.en.md)
