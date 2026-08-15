from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from flask import Flask, jsonify, render_template_string, request

from src.brag_cli import (
    append_inbox_entry,
    build_cloud_payload_preview,
    estimate_bytes,
    flatten_analysis_items,
    format_prompted_entry,
    format_text_entry,
    inbox_file_for_today,
    read_inbox_for_analysis,
    request_openai_analysis,
    resolve_vault_path,
    validate_analysis_result,
)


MAX_BYTES_DEFAULT = 12000


def load_dotenv_if_present(dotenv_path: Path) -> None:
    if not dotenv_path.exists() or not dotenv_path.is_file():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def build_app() -> Flask:
    app = Flask(__name__)

    @app.get("/api/config")
    def api_config():
        vault_path = resolve_vault_path(None)
        inbox_path = inbox_file_for_today(vault_path)
        inbox_text = ""
        if inbox_path.exists() and inbox_path.is_file():
            inbox_text = inbox_path.read_text(encoding="utf-8")
        return jsonify(
            {
                "vault_path": str(vault_path),
                "inbox_path": str(inbox_path),
                "inbox_exists": inbox_path.exists(),
                "inbox_tail": inbox_text[-2000:],
            }
        )

    @app.post("/api/capture")
    def api_capture():
        payload = request.get_json(silent=True) or {}
        mode = str(payload.get("mode", "text"))
        vault_path = resolve_vault_path(None)
        inbox_path = inbox_file_for_today(vault_path)

        if mode == "prompted":
            args = SimpleNamespace(
                context=str(payload.get("context", "")).strip(),
                action=str(payload.get("action", "")).strip(),
                impact=str(payload.get("impact", "")).strip(),
                evidence=str(payload.get("evidence", "")).strip(),
            )
            if not any([args.context, args.action, args.impact, args.evidence]):
                return jsonify({"error": "請至少填寫一個結構化欄位。"}), 400
            entry = format_prompted_entry(args)
        else:
            text = str(payload.get("text", "")).strip()
            if not text:
                return jsonify({"error": "請輸入要記錄的內容。"}), 400
            entry = format_text_entry(text)

        append_inbox_entry(inbox_path, entry)
        return jsonify(
            {
                "message": "已寫入 Inbox。",
                "inbox_path": str(inbox_path),
                "entry_preview": entry,
            }
        )

    @app.post("/api/analyze")
    def api_analyze():
        payload = request.get_json(silent=True) or {}
        model = str(payload.get("model", "gpt-4o-mini")).strip() or "gpt-4o-mini"
        max_bytes = int(payload.get("max_bytes", MAX_BYTES_DEFAULT))
        confirmed = bool(payload.get("confirm_send", False))
        if not confirmed:
            return jsonify({"error": "請先勾選已檢查送出內容。"}), 400

        vault_path = resolve_vault_path(None)
        inbox_path, outbound_content = read_inbox_for_analysis(vault_path, None)
        size = estimate_bytes(outbound_content)
        if size > max_bytes:
            return jsonify({"error": f"送出內容超過上限 ({size} > {max_bytes})。"}), 400

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return jsonify({"error": "缺少 OPENAI_API_KEY。"}), 400

        analysis = request_openai_analysis(api_key=api_key, model=model, outbound_content=outbound_content)
        validate_analysis_result(analysis)
        items = flatten_analysis_items(analysis)
        preview = build_cloud_payload_preview("Outbound content preview (exact payload):", outbound_content)
        return jsonify(
            {
                "message": "分析完成。",
                "inbox_path": str(inbox_path),
                "byte_size": size,
                "preview": preview,
                "analysis": analysis,
                "items": items,
            }
        )

    @app.get("/")
    def index():
        return render_template_string(PAGE_TEMPLATE)

    @app.errorhandler(ValueError)
    def handle_value_error(exc: ValueError):
        return jsonify({"error": str(exc)}), 400

    @app.errorhandler(OSError)
    def handle_os_error(exc: OSError):
        return jsonify({"error": str(exc)}), 500

    return app


PAGE_TEMPLATE = """
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Brag Capture Studio</title>
  <style>
    :root {
      --bg: #f5f4ef;
      --surface: #fffdf8;
      --surface-alt: #f1eee6;
      --text: #1f1d1a;
      --muted: #6f6a63;
      --line: #dbd4c8;
      --accent: #3e6b5f;
      --accent-2: #b27246;
      --ok: #2d6a4f;
      --err: #a3322a;
      --shadow: 0 8px 28px rgba(35, 29, 22, 0.08);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      background:
        radial-gradient(circle at 8% 10%, #f8f0dd 0, #f8f0dd 14%, transparent 15%),
        radial-gradient(circle at 90% 84%, #e8f0e9 0, #e8f0e9 12%, transparent 13%),
        linear-gradient(180deg, #f4f2ec 0%, #efeae0 100%);
      font-family: "IBM Plex Sans", "Noto Sans TC", sans-serif;
      min-height: 100vh;
    }

    .layout {
      display: grid;
      grid-template-columns: 260px minmax(520px, 1fr) 360px;
      gap: 14px;
      padding: 14px;
    }

    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
      padding: 18px;
      animation: rise 220ms ease-out;
    }

    @keyframes rise {
      from { transform: translateY(8px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }

    h1 {
      margin: 0 0 8px;
      letter-spacing: 0.02em;
      font-size: 24px;
      font-weight: 650;
    }

    h2 {
      margin: 0 0 10px;
      font-size: 17px;
      font-weight: 640;
    }

    .muted {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }

    .left-actions {
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }

    button {
      border: 1px solid var(--line);
      background: var(--surface-alt);
      color: var(--text);
      border-radius: 12px;
      padding: 10px 12px;
      font-family: inherit;
      font-size: 14px;
      cursor: pointer;
      transition: transform 120ms ease, background 120ms ease;
    }

    button:hover { transform: translateY(-1px); }
    button:active { transform: translateY(1px); }

    .primary {
      background: var(--accent);
      color: #fff;
      border-color: transparent;
    }

    .ghost {
      background: transparent;
    }

    label {
      display: block;
      margin: 10px 0 6px;
      font-size: 13px;
      color: var(--muted);
    }

    textarea,
    input[type="text"] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px;
      font-family: "IBM Plex Sans", "Noto Sans TC", sans-serif;
      font-size: 14px;
      background: #fff;
      color: var(--text);
    }

    textarea { min-height: 160px; resize: vertical; }

    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }

    .inline {
      display: flex;
      gap: 10px;
      align-items: center;
      margin: 10px 0;
      flex-wrap: wrap;
    }

    .status {
      margin-top: 10px;
      border-radius: 12px;
      padding: 10px;
      font-size: 13px;
      border: 1px solid transparent;
      white-space: pre-wrap;
      line-height: 1.45;
    }

    .status.ok {
      background: #edf8f1;
      border-color: #b8deca;
      color: var(--ok);
    }

    .status.err {
      background: #ffefed;
      border-color: #f0c0bc;
      color: var(--err);
    }

    .chip {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      background: #f3eee4;
      border: 1px solid var(--line);
      font-size: 12px;
      margin: 0 6px 6px 0;
    }

    .analysis-list {
      max-height: 360px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 8px;
      background: #fffcf7;
    }

    .analysis-item {
      border-bottom: 1px dashed var(--line);
      padding: 8px 4px;
    }

    .analysis-item:last-child { border-bottom: 0; }

    .kbd {
      font-family: "IBM Plex Mono", monospace;
      font-size: 12px;
      background: #f0ebe0;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 2px 6px;
    }

    @media (max-width: 1180px) {
      .layout {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="layout">
    <aside class="panel">
      <h1>Capture Studio</h1>
      <p class="muted">極簡三欄工作台。先輸入、再分析、最後挑重點。</p>

      <div class="left-actions">
        <button id="btnCapture" class="primary">送出記錄</button>
        <button id="btnAnalyze">分析 Inbox</button>
        <button id="btnSaveDraft" class="ghost">儲存草稿</button>
      </div>

      <h2 style="margin-top:16px;">快捷鍵</h2>
      <p class="muted"><span class="kbd">Ctrl+Enter</span> 送出記錄</p>
      <p class="muted"><span class="kbd">Ctrl+S</span> 儲存草稿</p>
      <p class="muted"><span class="kbd">Ctrl+Shift+A</span> 分析 Inbox</p>
    </aside>

    <main class="panel">
      <h2>輸入</h2>
      <div class="inline">
        <label><input type="radio" name="mode" value="text" checked> 自由文字</label>
        <label><input type="radio" name="mode" value="prompted"> 結構化欄位</label>
      </div>

      <label for="textInput">自由文字</label>
      <textarea id="textInput" placeholder="今天完成的成果、困難與影響..."></textarea>

      <div id="promptedFields" style="display:none;">
        <div class="inline" style="margin-top:4px;">
          <label for="promptedPreset" style="margin:0;">套用範例</label>
          <select id="promptedPreset" style="max-width:280px;">
            <option value="">請選擇範例...</option>
            <option value="performance">效能優化</option>
            <option value="reliability">穩定性修復</option>
            <option value="collaboration">協作與交付</option>
          </select>
        </div>
        <div class="row">
          <div>
            <label for="context">context（場景與問題）</label>
            <input id="context" type="text" placeholder="哪個系統遇到什麼問題，影響到誰" />
          </div>
          <div>
            <label for="action">action（你做了什麼）</label>
            <input id="action" type="text" placeholder="你實際採取的改善動作" />
          </div>
        </div>
        <div class="row">
          <div>
            <label for="impact">impact（結果與量化）</label>
            <input id="impact" type="text" placeholder="盡量含數字，如 p95 -28% 或錯誤率 -70%" />
          </div>
          <div>
            <label for="evidence">evidence（可驗證證據）</label>
            <input id="evidence" type="text" placeholder="報表、ticket、監控截圖、PR 連結" />
          </div>
        </div>
      </div>

      <div class="inline" style="margin-top:12px;">
        <label for="model" style="margin:0;">模型</label>
        <input id="model" type="text" value="gpt-4o-mini" style="max-width:240px;" />
        <label style="margin:0;"><input id="confirmSend" type="checkbox" /> 我已檢查送出內容</label>
      </div>

      <div id="statusBox" class="status" style="display:none;"></div>
    </main>

    <section class="panel">
      <h2>狀態</h2>
      <p class="muted" id="cfg"></p>
      <div style="margin:8px 0;">
        <span class="chip" id="byteSizeChip">bytes: -</span>
        <span class="chip" id="countChip">items: -</span>
      </div>

      <h2>分析結果</h2>
      <div id="analysisList" class="analysis-list"></div>

      <h2 style="margin-top:14px;">Inbox 片段</h2>
      <textarea id="inboxTail" readonly style="min-height:140px;"></textarea>
    </section>
  </div>

  <script>
    const STORAGE_KEY = "brag-web-draft-v1";

    const textInput = document.getElementById("textInput");
    const contextInput = document.getElementById("context");
    const actionInput = document.getElementById("action");
    const impactInput = document.getElementById("impact");
    const evidenceInput = document.getElementById("evidence");
    const promptedPreset = document.getElementById("promptedPreset");
    const modeRadios = Array.from(document.querySelectorAll('input[name="mode"]'));
    const promptedFields = document.getElementById("promptedFields");
    const statusBox = document.getElementById("statusBox");
    const cfg = document.getElementById("cfg");
    const inboxTail = document.getElementById("inboxTail");
    const byteSizeChip = document.getElementById("byteSizeChip");
    const countChip = document.getElementById("countChip");
    const analysisList = document.getElementById("analysisList");

    const structuredPresets = {
      performance: {
        context: "Checkout API 在高峰時段 p95 過高，影響下單體驗。",
        action: "重構查詢路徑，加入索引與快取策略，移除重複序列化。",
        impact: "p95 由 820ms 降到 590ms（約 -28%），尖峰錯誤率下降。",
        evidence: "APM dashboard 截圖、壓測報告、部署前後指標對照。",
      },
      reliability: {
        context: "排程任務偶發 timeout，導致每日同步中斷。",
        action: "加入重試與退避策略，拆分長交易，補上 timeout 與告警。",
        impact: "連續 14 天零失敗，夜間告警量下降 70%。",
        evidence: "監控告警紀錄、任務成功率趨勢、incident ticket 關閉紀錄。",
      },
      collaboration: {
        context: "跨團隊需求不一致，造成前後端反覆修改。",
        action: "建立共用規格模板，主持每週對齊會議，定義驗收清單。",
        impact: "需求返工次數由每次平均 3 次降到 1 次，交付時間縮短 20%。",
        evidence: "會議紀錄、PR 迭代次數統計、Sprint 回顧數據。",
      },
    };

    function showStatus(msg, ok = true) {
      statusBox.style.display = "block";
      statusBox.className = ok ? "status ok" : "status err";
      statusBox.textContent = msg;
    }

    function selectedMode() {
      return modeRadios.find((r) => r.checked)?.value || "text";
    }

    function refreshModeUI() {
      promptedFields.style.display = selectedMode() === "prompted" ? "block" : "none";
    }

    function clearCaptureInputs() {
      textInput.value = "";
      contextInput.value = "";
      actionInput.value = "";
      impactInput.value = "";
      evidenceInput.value = "";
      if (promptedPreset) {
        promptedPreset.value = "";
      }
    }

    function applyPreset(presetKey) {
      const preset = structuredPresets[presetKey];
      if (!preset) {
        return;
      }
      contextInput.value = preset.context;
      actionInput.value = preset.action;
      impactInput.value = preset.impact;
      evidenceInput.value = preset.evidence;
      showStatus("已套用結構化範例，可直接修改後送出。", true);
    }

    function saveDraft() {
      const data = {
        mode: selectedMode(),
        text: textInput.value,
        context: contextInput.value,
        action: actionInput.value,
        impact: impactInput.value,
        evidence: evidenceInput.value,
        model: document.getElementById("model").value,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      showStatus("草稿已儲存。", true);
    }

    function loadDraft() {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      try {
        const d = JSON.parse(raw);
        modeRadios.forEach((r) => {
          r.checked = r.value === (d.mode || "text");
        });
        textInput.value = d.text || "";
        contextInput.value = d.context || "";
        actionInput.value = d.action || "";
        impactInput.value = d.impact || "";
        evidenceInput.value = d.evidence || "";
        document.getElementById("model").value = d.model || "gpt-4o-mini";
      } catch (_) {
      }
      refreshModeUI();
    }

    async function fetchConfig() {
      try {
        const resp = await fetch("/api/config");
        const data = await resp.json();
        cfg.textContent = "Vault: " + data.vault_path + "\\nInbox: " + data.inbox_path;
        inboxTail.value = data.inbox_tail || "";
      } catch (err) {
        showStatus("讀取設定失敗：" + String(err), false);
      }
    }

    async function capture() {
      try {
        const payload = {
          mode: selectedMode(),
          text: textInput.value,
          context: contextInput.value,
          action: actionInput.value,
          impact: impactInput.value,
          evidence: evidenceInput.value,
        };
        const resp = await fetch("/api/capture", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok) {
          showStatus(data.error || "送出失敗。", false);
          return;
        }
        showStatus(data.message + "\\n" + data.inbox_path, true);
        clearCaptureInputs();
        await fetchConfig();
      } catch (err) {
        showStatus("送出失敗：" + String(err), false);
      }
    }

    function renderItems(items) {
      if (!items.length) {
        analysisList.innerHTML = "<div class='muted'>目前沒有可顯示項目。</div>";
        return;
      }
      analysisList.innerHTML = items
        .slice(0, 30)
        .map((it) => {
          const score = it.value_assessment || {};
          return (
            "<div class='analysis-item'>" +
            "<div><strong>" + (it.project_or_topic || "(no-topic)") + "</strong></div>" +
            "<div class='muted'>" + (it.classification || "") + "</div>" +
            "<div>impact=" + (score.impact ?? "-") +
            ", evidence=" + (score.evidence_strength ?? "-") + "</div>" +
            "<div class='muted'>" + (it.reason || "") + "</div>" +
            "</div>"
          );
        })
        .join("");
    }

    async function analyze() {
      try {
        const payload = {
          model: document.getElementById("model").value,
          confirm_send: document.getElementById("confirmSend").checked,
        };
        const resp = await fetch("/api/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok) {
          showStatus(data.error || "分析失敗。", false);
          return;
        }
        byteSizeChip.textContent = "bytes: " + data.byte_size;
        countChip.textContent = "items: " + (data.items || []).length;
        renderItems(data.items || []);
        showStatus(data.message, true);
      } catch (err) {
        showStatus("分析失敗：" + String(err), false);
      }
    }

    document.getElementById("btnCapture").addEventListener("click", capture);
    document.getElementById("btnAnalyze").addEventListener("click", analyze);
    document.getElementById("btnSaveDraft").addEventListener("click", saveDraft);
    if (promptedPreset) {
      promptedPreset.addEventListener("change", (evt) => {
        applyPreset(evt.target.value);
      });
    }
    modeRadios.forEach((r) => r.addEventListener("change", refreshModeUI));

    document.addEventListener("keydown", (evt) => {
      if (evt.ctrlKey && evt.key === "Enter") {
        evt.preventDefault();
        capture();
        return;
      }
      if (evt.ctrlKey && (evt.key === "s" || evt.key === "S")) {
        evt.preventDefault();
        saveDraft();
        return;
      }
      if (evt.ctrlKey && evt.shiftKey && (evt.key === "A" || evt.key === "a")) {
        evt.preventDefault();
        analyze();
      }
    });

    loadDraft();
    refreshModeUI();
    fetchConfig();
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="brag-web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> int:
    load_dotenv_if_present(Path(".env"))
    args = parse_args()
    app = build_app()
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
