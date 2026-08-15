from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest


REQUIRED_VAULT_DIRS = [
    Path("Brag/Inbox"),
    Path("Brag/Achievements"),
    Path("Brag/Archive/Rejected"),
    Path("Brag/Outputs"),
]

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
ANALYSIS_REQUIRED_SCORES = [
    "impact",
    "difficulty",
    "leadership_ownership",
    "evidence_strength",
    "reusability",
]
CLASSIFICATION_VALUES = {
    "new_candidate",
    "supporting_evidence",
    "retained_raw_activity",
}
FOLLOWUP_KEYS = [
    "context",
    "contribution",
    "scope",
    "constraints",
    "outcome",
    "evidence",
]
READY_KEYS = ["context", "contribution", "outcome", "evidence"]


def config_file_path() -> Path:
    config_root = os.getenv("BRAG_CONFIG_DIR")
    if config_root:
        return Path(config_root) / "config.json"
    return Path.home() / ".brag-document-builder" / "config.json"


def ensure_existing_directory(path_text: str) -> Path:
    path = Path(path_text).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"Vault path does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"Vault path is not a directory: {path}")
    return path


def initialize_vault(vault_path: Path) -> None:
    for rel_dir in REQUIRED_VAULT_DIRS:
        (vault_path / rel_dir).mkdir(parents=True, exist_ok=True)


def write_config_atomic(config_path: Path, content: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(config_path.parent),
        delete=False,
    ) as tmp:
        json.dump(content, tmp, ensure_ascii=True, indent=2)
        tmp.flush()
        temp_name = tmp.name
    Path(temp_name).replace(config_path)


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise ValueError("No configuration found. Run `init-vault --path <vault_path>` first.")
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def review_state_file_path() -> Path:
    config_root = os.getenv("BRAG_CONFIG_DIR")
    if config_root:
        return Path(config_root) / "review_state.json"
    return Path.home() / ".brag-document-builder" / "review_state.json"


def load_review_state() -> dict:
    path = review_state_file_path()
    if not path.exists():
        return {"candidates": {}}
    with path.open("r", encoding="utf-8") as f:
        parsed = json.load(f)
    if not isinstance(parsed, dict) or "candidates" not in parsed:
        return {"candidates": {}}
    return parsed


def save_review_state(state: dict) -> None:
    write_config_atomic(review_state_file_path(), state)


def find_candidate_state(state: dict, candidate_id: str) -> dict:
    candidate = state.get("candidates", {}).get(candidate_id)
    if not isinstance(candidate, dict):
        raise ValueError(f"Candidate not found: {candidate_id}")
    return candidate


def confirm_stage(prompt: str) -> bool:
    return input(f"{prompt} Type YES to confirm: ").strip() == "YES"


def markdown_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def safe_file_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-").lower()
    return stem or "achievement"


def validate_achievement_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("achievement-id may contain only letters, numbers, underscores, and hyphens.")
    return value


def validate_authoritative_achievement(content: str) -> None:
    required_parts = [
        "id:",
        "state:",
        "date:",
        "source_references:",
        "## Confirmed Facts",
        "### Context",
        "### Contribution",
        "### Outcome",
        "### Evidence",
        "## Source Material",
        "## Generated Wording",
    ]
    if not content.startswith("---\n") or "\n---\n" not in content[4:]:
        raise ValueError("Malformed authoritative achievement Markdown: invalid frontmatter.")
    missing = [part for part in required_parts if part not in content]
    if missing:
        raise ValueError(
            "Malformed authoritative achievement Markdown: missing " + ", ".join(missing)
        )


def render_achievement_markdown(
    *,
    achievement_id: str,
    candidate: dict,
    wording: str,
    language: str,
    model: str,
) -> str:
    answers = candidate["confirmed_answers"]
    generated_at = datetime.now(timezone.utc).isoformat()
    achievement_date = datetime.now(timezone.utc).date().isoformat()
    source_reference = candidate["candidate_id"]
    project = candidate.get("project_or_topic", "")
    return (
        "---\n"
        f"id: {markdown_string(achievement_id)}\n"
        "state: confirmed\n"
        f"date: {markdown_string(achievement_date)}\n"
        f"project: {markdown_string(project)}\n"
        "source_references:\n"
        f"  - {markdown_string(source_reference)}\n"
        "ai_provider: openai\n"
        f"ai_model: {markdown_string(model)}\n"
        f"generated_at_utc: {markdown_string(generated_at)}\n"
        f"generated_language: {markdown_string(language)}\n"
        "---\n\n"
        "## Confirmed Facts\n\n"
        f"### Context\n\n{answers.get('context', '')}\n\n"
        f"### Contribution\n\n{answers.get('contribution', '')}\n\n"
        f"### Outcome\n\n{answers.get('outcome', '')}\n\n"
        f"### Evidence\n\n{answers.get('evidence', '')}\n\n"
        "## Source Material\n\n"
        f"- {source_reference}\n\n"
        "## Generated Wording\n\n"
        f"{wording}\n"
    )


def render_rejection_markdown(candidate: dict, reason: str) -> str:
    rejected_at = datetime.now(timezone.utc).isoformat()
    return (
        "---\n"
        f"candidate_id: {markdown_string(candidate['candidate_id'])}\n"
        f"rejected_at_utc: {markdown_string(rejected_at)}\n"
        "---\n\n"
        "## Source Reference\n\n"
        f"{candidate['candidate_id']}\n\n"
        "## Rejection Reason\n\n"
        f"{reason}\n"
    )


def parse_frontmatter(text: str) -> dict:
    lines = text.splitlines()
    data: dict = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value == "":
            i += 1
            values: list[str] = []
            while i < len(lines) and lines[i].lstrip().startswith("- "):
                item = lines[i].lstrip()[2:].strip()
                try:
                    values.append(json.loads(item))
                except json.JSONDecodeError:
                    values.append(item)
                i += 1
            data[key] = values
            continue
        try:
            data[key] = json.loads(raw_value)
        except json.JSONDecodeError:
            data[key] = raw_value
        i += 1
    return data


def render_frontmatter(data: dict) -> str:
    ordered_keys = [
        "id",
        "state",
        "date",
        "project",
        "source_references",
        "ai_provider",
        "ai_model",
        "generated_at_utc",
        "generated_language",
    ]
    keys = ordered_keys + [k for k in data.keys() if k not in ordered_keys]
    out = ["---"]
    for key in keys:
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, list):
            out.append(f"{key}:")
            for item in value:
                out.append(f"  - {markdown_string(str(item))}")
            continue
        if key in {"state", "ai_provider"}:
            out.append(f"{key}: {value}")
        else:
            out.append(f"{key}: {markdown_string(str(value))}")
    out.append("---")
    return "\n".join(out)


def parse_confirmed_facts_block(block_text: str) -> dict:
    def get_value(title: str, next_title: str | None) -> str:
        start_token = f"### {title}\n\n"
        start = block_text.find(start_token)
        if start == -1:
            return ""
        start += len(start_token)
        if next_title is None:
            end = len(block_text)
        else:
            end_token = f"\n\n### {next_title}\n\n"
            end = block_text.find(end_token, start)
            if end == -1:
                end = len(block_text)
        return block_text[start:end].strip()

    return {
        "context": get_value("Context", "Contribution"),
        "contribution": get_value("Contribution", "Outcome"),
        "outcome": get_value("Outcome", "Evidence"),
        "evidence": get_value("Evidence", None),
    }


def render_confirmed_facts_block(facts: dict) -> str:
    return (
        "## Confirmed Facts\n\n"
        f"### Context\n\n{facts.get('context', '')}\n\n"
        f"### Contribution\n\n{facts.get('contribution', '')}\n\n"
        f"### Outcome\n\n{facts.get('outcome', '')}\n\n"
        f"### Evidence\n\n{facts.get('evidence', '')}"
    )


def parse_source_material_block(block_text: str) -> list[str]:
    body = block_text.replace("## Source Material", "", 1).strip()
    lines: list[str] = []
    for line in body.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("- "):
            lines.append(trimmed[2:].strip())
    return lines


def parse_generated_wording_block(block_text: str) -> str:
    return block_text.replace("## Generated Wording", "", 1).strip()


def parse_authoritative_achievement_file(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    validate_authoritative_achievement(content)
    end_frontmatter = content.find("\n---\n", 4)
    if end_frontmatter == -1:
        raise ValueError("Malformed authoritative achievement Markdown: invalid frontmatter.")
    frontmatter_text = content[4:end_frontmatter]
    body = content[end_frontmatter + 5 :]
    idx_cf = body.find("## Confirmed Facts")
    idx_sm = body.find("## Source Material")
    idx_gw = body.find("## Generated Wording")
    if min(idx_cf, idx_sm, idx_gw) == -1 or not (idx_cf < idx_sm < idx_gw):
        raise ValueError("Malformed authoritative achievement Markdown: invalid section order.")

    confirmed_block = body[idx_cf:idx_sm].rstrip()
    source_block = body[idx_sm:idx_gw].rstrip()
    generated_block = body[idx_gw:].rstrip()
    frontmatter = parse_frontmatter(frontmatter_text)
    achievement_id = str(frontmatter.get("id", "")).strip()
    if not achievement_id:
        raise ValueError("Malformed authoritative achievement Markdown: missing id.")

    source_refs = frontmatter.get("source_references", [])
    if not isinstance(source_refs, list):
        raise ValueError("Malformed authoritative achievement Markdown: source_references must be a list.")

    return {
        "path": path,
        "content": content,
        "frontmatter": frontmatter,
        "id": achievement_id,
        "project": str(frontmatter.get("project", "")),
        "source_references": [str(x) for x in source_refs],
        "confirmed_facts": parse_confirmed_facts_block(confirmed_block),
        "confirmed_block": confirmed_block,
        "source_lines": parse_source_material_block(source_block),
        "generated_wording": parse_generated_wording_block(generated_block),
    }


def scan_achievements(vault_path: Path) -> tuple[dict, list[str]]:
    achievement_root = vault_path / "Brag" / "Achievements"
    entries: dict[str, dict] = {}
    warnings: list[str] = []
    for path in achievement_root.rglob("*.md"):
        try:
            parsed = parse_authoritative_achievement_file(path)
        except ValueError as e:
            warnings.append(f"Skipped malformed achievement file: {path} ({e})")
            continue
        entries[parsed["id"]] = parsed
    return entries, warnings


def choose_target_achievement(achievements: dict, candidate: dict, achievement_id: str | None) -> dict | None:
    if achievement_id:
        key = validate_achievement_id(achievement_id)
        return achievements.get(key)
    project = str(candidate.get("project_or_topic", "")).strip().lower()
    matches = [a for a in achievements.values() if str(a.get("project", "")).strip().lower() == project]
    if len(matches) == 1:
        return matches[0]
    return None


def compose_authoritative_markdown(
    *,
    frontmatter: dict,
    confirmed_block: str,
    source_lines: list[str],
    generated_wording: str,
) -> str:
    source_body = "\n".join(f"- {line}" for line in source_lines)
    source_block = "## Source Material\n\n"
    if source_body:
        source_block += source_body + "\n"
    generated_block = "## Generated Wording\n\n" + generated_wording.strip() + "\n"
    return (
        render_frontmatter(frontmatter)
        + "\n\n"
        + confirmed_block.strip()
        + "\n\n"
        + source_block
        + "\n"
        + generated_block
    )


def default_wording_from_facts(facts: dict) -> str:
    return f"{facts.get('contribution', '')}; {facts.get('outcome', '')}".strip("; ")


def has_explicit_metric(text: str) -> bool:
    return re.search(r"\d+(?:\.\d+)?\s*%?", text) is not None


def extract_resume_themes(facts: dict) -> list[str]:
    haystack = " ".join(
        [
            str(facts.get("context", "")).lower(),
            str(facts.get("contribution", "")).lower(),
            str(facts.get("outcome", "")).lower(),
            str(facts.get("evidence", "")).lower(),
        ]
    )
    themes: list[str] = []
    if any(k in haystack for k in ["led", "lead", "mentor", "帶領", "協作", "coordina"]):
        themes.append("leadership")
    if any(k in haystack for k in ["pipeline", "automation", "deploy", "ci/cd", "自動化"]):
        themes.append("delivery-excellence")
    if any(k in haystack for k in ["security", "reliability", "stability", "品質", "可靠"]):
        themes.append("reliability-security")
    if any(k in haystack for k in ["cost", "efficiency", "time", "效能", "效率", "%"]):
        themes.append("impact-efficiency")
    if not themes:
        themes.append("execution")
    return themes


def strongest_statement(facts: dict, language: str) -> str:
    contribution = str(facts.get("contribution", "")).strip()
    outcome = str(facts.get("outcome", "")).strip()
    if not outcome:
        outcome = "[X%]" if language == "en" else "[X%]"
    if language == "en":
        return f"{contribution}; delivered {outcome}".strip("; ")
    return f"{contribution}；帶來成果：{outcome}".strip("；")


def generate_outputs_from_facts(facts: dict, language: str) -> dict:
    context = str(facts.get("context", "")).strip()
    contribution = str(facts.get("contribution", "")).strip()
    outcome = str(facts.get("outcome", "")).strip()
    evidence = str(facts.get("evidence", "")).strip()
    if not has_explicit_metric(outcome):
        outcome = (outcome + " " if outcome else "") + "[X%]"

    if language == "en":
        star = (
            f"Situation: {context}\n"
            f"Task: Improve the target outcome.\n"
            f"Action: {contribution}\n"
            f"Result: {outcome}; evidence: {evidence}"
        )
        resume = f"{contribution}, resulting in {outcome}."
        summary = f"Delivered {outcome} by {contribution}. Evidence: {evidence}."
    else:
        star = (
            f"Situation: {context}\n"
            "Task: 改善目標結果。\n"
            f"Action: {contribution}\n"
            f"Result: {outcome}；證據：{evidence}"
        )
        resume = f"{contribution}，帶來 {outcome}。"
        summary = f"透過 {contribution} 達成 {outcome}；證據：{evidence}。"

    return {
        "star": star,
        "resume-bullet": resume,
        "performance-summary": summary,
    }


def parse_output_types(value: str) -> list[str]:
    allowed = {"star", "resume-bullet", "performance-summary"}
    selected = [x.strip() for x in value.split(",") if x.strip()]
    if not selected:
        raise ValueError("At least one output type is required.")
    for item in selected:
        if item not in allowed:
            raise ValueError(f"Unsupported output type: {item}")
    return selected


def render_generated_section(existing: str, language: str, model: str, outputs: dict, output_types: list[str]) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        "## Generated Wording",
        "",
        f"Generated-Language: {language}",
        f"Generated-At-UTC: {generated_at}",
        f"Generated-Model: {model}",
        "",
    ]
    labels = {
        "star": "STAR",
        "resume-bullet": "Resume Bullet",
        "performance-summary": "Performance Summary",
    }
    for output_type in output_types:
        lines.append(f"### {labels[output_type]}")
        lines.append("")
        lines.append(outputs[output_type])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def split_authoritative_sections(content: str) -> tuple[str, str, str, str]:
    end_frontmatter = content.find("\n---\n", 4)
    if end_frontmatter == -1:
        raise ValueError("Malformed authoritative achievement Markdown: invalid frontmatter.")
    frontmatter_text = content[4:end_frontmatter]
    body = content[end_frontmatter + 5 :]
    idx_cf = body.find("## Confirmed Facts")
    idx_sm = body.find("## Source Material")
    idx_gw = body.find("## Generated Wording")
    if min(idx_cf, idx_sm, idx_gw) == -1 or not (idx_cf < idx_sm < idx_gw):
        raise ValueError("Malformed authoritative achievement Markdown: invalid section order.")
    confirmed_block = body[idx_cf:idx_sm].rstrip()
    source_block = body[idx_sm:idx_gw].rstrip()
    generated_block = body[idx_gw:].rstrip()
    return frontmatter_text, confirmed_block, source_block, generated_block


def compose_full_markdown(frontmatter: dict, confirmed_block: str, source_block: str, generated_block: str) -> str:
    return (
        render_frontmatter(frontmatter)
        + "\n\n"
        + confirmed_block.strip()
        + "\n\n"
        + source_block.strip()
        + "\n\n"
        + generated_block.strip()
        + "\n"
    )


def update_generated_wording_section(
    achievement: dict,
    *,
    language: str,
    model: str,
    output_types: list[str],
) -> tuple[str, dict]:
    outputs = generate_outputs_from_facts(achievement["confirmed_facts"], language)
    frontmatter_text, confirmed_block, source_block, _ = split_authoritative_sections(achievement["content"])
    frontmatter = parse_frontmatter(frontmatter_text)
    frontmatter["generated_language"] = language
    frontmatter["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    frontmatter["ai_model"] = model
    if "ai_provider" not in frontmatter:
        frontmatter["ai_provider"] = "local-template"
    generated_block = render_generated_section(
        achievement["generated_wording"],
        language,
        model,
        outputs,
        output_types,
    )
    new_content = compose_full_markdown(frontmatter, confirmed_block, source_block, generated_block)
    validate_authoritative_achievement(new_content)
    return new_content, outputs


def build_feedback(achievement: dict, language: str) -> dict:
    facts = achievement["confirmed_facts"]
    themes = extract_resume_themes(facts)
    missing = []
    if not has_explicit_metric(str(facts.get("outcome", ""))):
        missing.append("metric")
    if not str(facts.get("evidence", "")).strip():
        missing.append("evidence")
    return {
        "themes": themes,
        "missing": missing,
        "strongest_statement": strongest_statement(facts, language),
    }


def render_aggregate_output(
    *,
    achievements: list[dict],
    generated: list[dict],
    language: str,
    output_types: list[str],
) -> str:
    lines = [
        "# Aggregated Career Outputs",
        "",
        f"Language: {language}",
        f"Generated-At-UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Source Achievement IDs",
        "",
    ]
    for ach in achievements:
        lines.append(f"- {ach['id']}")
    lines.append("")
    labels = {
        "star": "STAR",
        "resume-bullet": "Resume Bullet",
        "performance-summary": "Performance Summary",
    }
    for idx, ach in enumerate(achievements):
        lines.append(f"## Achievement {ach['id']}")
        lines.append("")
        out = generated[idx]
        for output_type in output_types:
            lines.append(f"### {labels[output_type]}")
            lines.append("")
            lines.append(out[output_type])
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def resolve_vault_path(override_path: str | None) -> Path:
    if override_path:
        return ensure_existing_directory(override_path)
    config = load_config(config_file_path())
    return ensure_existing_directory(config["default_vault_path"])


def inbox_file_for_today(vault_path: Path) -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return vault_path / "Brag" / "Inbox" / f"{day}.md"


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp.flush()
        temp_name = tmp.name
    Path(temp_name).replace(path)


def append_inbox_entry(inbox_path: Path, entry: str) -> None:
    existing = ""
    if inbox_path.exists():
        existing = inbox_path.read_text(encoding="utf-8")
    joined = existing
    if joined and not joined.endswith("\n"):
        joined += "\n"
    if joined:
        joined += "\n"
    joined += entry
    write_text_atomic(inbox_path, joined)


def format_text_entry(text: str) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    return f"## Capture {ts}\n\n{text}\n"


def format_prompted_entry(args: argparse.Namespace) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    context = args.context or ""
    action = args.action or ""
    impact = args.impact or ""
    evidence = args.evidence or ""
    return (
        f"## Capture {ts}\n\n"
        f"- context: {context}\n"
        f"- action: {action}\n"
        f"- impact: {impact}\n"
        f"- evidence: {evidence}\n"
    )


def read_inbox_for_analysis(vault_path: Path | None, inbox_file_arg: str | None) -> tuple[Path, str]:
    if inbox_file_arg:
        inbox_file = Path(inbox_file_arg).expanduser().resolve()
    else:
        if not vault_path:
            raise ValueError("Vault path is required when --inbox-file is not provided.")
        inbox_file = inbox_file_for_today(vault_path)

    if not inbox_file.exists():
        raise ValueError(f"Inbox file does not exist: {inbox_file}")
    if not inbox_file.is_file():
        raise ValueError(f"Inbox path is not a file: {inbox_file}")

    return inbox_file, inbox_file.read_text(encoding="utf-8")


def estimate_bytes(content: str) -> int:
    return len(content.encode("utf-8"))


def request_openai_analysis(api_key: str, model: str, outbound_content: str) -> dict:
    prompt = (
        "Analyze the inbox content and return JSON only. "
        "Top-level keys: groups (array). "
        "Each group needs project_or_topic (string), items (array). "
        "Each item needs classification in [new_candidate, supporting_evidence, retained_raw_activity], "
        "value_assessment object with numeric fields impact, difficulty, leadership_ownership, "
        "evidence_strength, reusability, and reason (string)."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": outbound_content},
        ],
        "temperature": 0.1,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        OPENAI_API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urlerror.URLError as e:
        raise OSError("OpenAI request failed") from e

    parsed = json.loads(raw)
    try:
        model_content = parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError("OpenAI response format is invalid.") from e

    try:
        return json.loads(model_content)
    except json.JSONDecodeError as e:
        raise ValueError("OpenAI returned non-JSON analysis content.") from e


def request_openai_followup_suggestions(api_key: str, model: str, review_summary: str) -> dict:
    prompt = (
        "Suggest short inference hints for missing candidate details. Return JSON only with key "
        "suggestions as object; keys may include context, contribution, scope, constraints, outcome, evidence."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": review_summary},
        ],
        "temperature": 0.1,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        OPENAI_API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urlerror.URLError as e:
        raise OSError("OpenAI request failed") from e

    parsed = json.loads(raw)
    try:
        model_content = parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError("OpenAI response format is invalid.") from e
    try:
        obj = json.loads(model_content)
    except json.JSONDecodeError as e:
        raise ValueError("OpenAI returned non-JSON follow-up content.") from e
    if not isinstance(obj, dict):
        raise ValueError("Follow-up suggestions must be a JSON object.")
    suggestions = obj.get("suggestions", {})
    if suggestions is None:
        suggestions = {}
    if not isinstance(suggestions, dict):
        raise ValueError("Follow-up suggestions must be an object.")
    return {"suggestions": suggestions}


def validate_analysis_result(result: dict) -> None:
    if not isinstance(result, dict):
        raise ValueError("Analysis result must be a JSON object.")
    groups = result.get("groups")
    if not isinstance(groups, list):
        raise ValueError("Analysis result must include groups list.")

    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("Each group must be an object.")
        if not isinstance(group.get("project_or_topic"), str):
            raise ValueError("Each group needs project_or_topic string.")
        items = group.get("items")
        if not isinstance(items, list):
            raise ValueError("Each group needs items list.")

        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each item must be an object.")
            classification = item.get("classification")
            if classification not in CLASSIFICATION_VALUES:
                raise ValueError("Item classification is invalid.")
            reason = item.get("reason")
            if not isinstance(reason, str):
                raise ValueError("Item reason must be a string.")
            scores = item.get("value_assessment")
            if not isinstance(scores, dict):
                raise ValueError("Item value_assessment must be an object.")
            for key in ANALYSIS_REQUIRED_SCORES:
                value = scores.get(key)
                if not isinstance(value, (int, float)):
                    raise ValueError(f"value_assessment.{key} must be numeric.")


def build_cloud_payload_preview(label: str, content: str) -> str:
    outbound_size = estimate_bytes(content)
    return (
        f"{label}\n"
        "-----BEGIN OUTBOUND CONTENT-----\n"
        f"{content}\n"
        "-----END OUTBOUND CONTENT-----\n"
        f"Approx outbound size (bytes): {outbound_size}\n"
        "Warning: Review for confidential or sensitive data before sending.\n"
    )


def confirm_and_send_cloud_request(
    *,
    outbound_content: str,
    max_bytes: int,
    request_callable,
    model: str,
    label: str,
) -> dict | None:
    print(build_cloud_payload_preview(label, outbound_content), end="")
    size = estimate_bytes(outbound_content)
    if size > max_bytes:
        raise ValueError(f"Outbound content exceeds max bytes ({size} > {max_bytes}).")

    answer = input("Type YES to send this content to OpenAI: ").strip()
    if answer != "YES":
        print("Request cancelled. No request was sent.")
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing.")
    return request_callable(api_key=api_key, model=model, outbound_content=outbound_content)


def flatten_analysis_items(result: dict) -> list[dict]:
    items: list[dict] = []
    for group in result["groups"]:
        topic = group["project_or_topic"]
        for item in group["items"]:
            row = dict(item)
            row["project_or_topic"] = topic
            items.append(row)
    return items


def candidate_id_for(inbox_path: Path, candidate_index: int) -> str:
    return f"{inbox_path.resolve()}::{candidate_index}"


def status_from_answers(confirmed_answers: dict) -> str:
    if all((confirmed_answers.get(k) or "").strip() for k in READY_KEYS):
        return "ready-for-confirmation"
    return "needs-detail"


def cmd_init_vault(args: argparse.Namespace) -> int:
    vault_path = ensure_existing_directory(args.path)
    initialize_vault(vault_path)

    config = {
        "default_vault_path": str(vault_path),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_config_atomic(config_file_path(), config)

    print(f"Initialized vault: {vault_path}")
    print("Required directories are ready under Brag/.")
    return 0


def cmd_show_config(_: argparse.Namespace) -> int:
    config = load_config(config_file_path())
    print(json.dumps(config, ensure_ascii=True, indent=2))
    return 0


def cmd_capture_text(args: argparse.Namespace) -> int:
    vault_path = resolve_vault_path(args.vault)
    inbox_path = inbox_file_for_today(vault_path)
    entry = format_text_entry(args.text)
    append_inbox_entry(inbox_path, entry)
    print(f"Captured to: {inbox_path}")
    return 0


def cmd_capture_prompted(args: argparse.Namespace) -> int:
    vault_path = resolve_vault_path(args.vault)
    inbox_path = inbox_file_for_today(vault_path)
    entry = format_prompted_entry(args)
    append_inbox_entry(inbox_path, entry)
    print(f"Captured to: {inbox_path}")
    return 0


def cmd_analyze_inbox(args: argparse.Namespace) -> int:
    vault_path = None
    if not args.inbox_file:
        vault_path = resolve_vault_path(args.vault)
    inbox_path, outbound_content = read_inbox_for_analysis(vault_path, args.inbox_file)

    print(f"Analyzing inbox file: {inbox_path}")
    result = confirm_and_send_cloud_request(
        outbound_content=outbound_content,
        max_bytes=args.max_bytes,
        request_callable=request_openai_analysis,
        model=args.model,
        label="Outbound content preview (exact payload):",
    )
    if result is None:
        print("Analysis cancelled. No request was sent.")
        return 0
    validate_analysis_result(result)

    envelope = {
        "provider": "openai",
        "model": args.model,
        "analyzed_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis": result,
    }
    print(json.dumps(envelope, ensure_ascii=True, indent=2))
    return 0


def cmd_review_candidate(args: argparse.Namespace) -> int:
    vault_path = None
    if not args.inbox_file:
        vault_path = resolve_vault_path(args.vault)
    inbox_path, outbound_content = read_inbox_for_analysis(vault_path, args.inbox_file)

    analysis = confirm_and_send_cloud_request(
        outbound_content=outbound_content,
        max_bytes=args.max_bytes,
        request_callable=request_openai_analysis,
        model=args.model,
        label="Outbound content preview (exact payload):",
    )
    if analysis is None:
        print("Review cancelled. No analysis request was sent.")
        return 0
    validate_analysis_result(analysis)

    items = flatten_analysis_items(analysis)
    if not items:
        raise ValueError("No candidate items returned from analysis.")
    if args.candidate_index < 0 or args.candidate_index >= len(items):
        raise ValueError("candidate-index is out of range.")

    candidate = items[args.candidate_index]
    cid = candidate_id_for(inbox_path, args.candidate_index)
    state = load_review_state()
    candidate_state = state.setdefault("candidates", {}).get(
        cid,
        {
            "candidate_id": cid,
            "status": "needs-detail",
            "confirmed_answers": {},
            "pending_questions": FOLLOWUP_KEYS.copy(),
            "last_suggested_inferences": {},
            "project_or_topic": candidate.get("project_or_topic", ""),
        },
    )

    print(
        json.dumps(
            {
                "candidate_id": cid,
                "project_or_topic": candidate.get("project_or_topic"),
                "classification": candidate.get("classification"),
                "reason": candidate.get("reason"),
                "status": candidate_state.get("status", "needs-detail"),
            },
            ensure_ascii=True,
            indent=2,
        )
    )

    if args.mode == "quick":
        state["candidates"][cid] = candidate_state
        save_review_state(state)
        print("Quick review selected. Follow-up questions deferred.")
        return 0

    asked = 0
    pending = candidate_state.get("pending_questions", FOLLOWUP_KEYS.copy())
    confirmed_answers = candidate_state.get("confirmed_answers", {})
    deferred = False
    for key in list(pending):
        if asked >= args.max_followups:
            break
        prompt = f"Provide {key} (or type skip/defer): "
        answer = input(prompt).strip()
        asked += 1
        if answer.lower() == "skip":
            continue
        if answer.lower() == "defer":
            deferred = True
            break
        confirmed_answers[key] = answer
        pending.remove(key)

    candidate_state["confirmed_answers"] = confirmed_answers
    candidate_state["pending_questions"] = pending
    candidate_state["status"] = status_from_answers(confirmed_answers)

    if args.ask_ai_followup and pending:
        summary = json.dumps(
            {
                "candidate": {
                    "project_or_topic": candidate.get("project_or_topic"),
                    "classification": candidate.get("classification"),
                    "reason": candidate.get("reason"),
                },
                "confirmed_answers": confirmed_answers,
                "pending_questions": pending,
            },
            ensure_ascii=True,
        )
        followup = confirm_and_send_cloud_request(
            outbound_content=summary,
            max_bytes=args.max_bytes,
            request_callable=request_openai_followup_suggestions,
            model=args.model,
            label="Follow-up suggestion payload preview (exact payload):",
        )
        if followup is not None:
            candidate_state["last_suggested_inferences"] = followup.get("suggestions", {})

    state["candidates"][cid] = candidate_state
    save_review_state(state)

    print(
        json.dumps(
            {
                "candidate_id": cid,
                "asked_questions": asked,
                "deferred": deferred,
                "status": candidate_state["status"],
                "pending_questions": candidate_state["pending_questions"],
                "confirmed_answers": candidate_state["confirmed_answers"],
                "last_suggested_inferences": candidate_state.get("last_suggested_inferences", {}),
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


def cmd_confirm_candidate(args: argparse.Namespace) -> int:
    vault_path = resolve_vault_path(args.vault)
    state = load_review_state()
    candidate = find_candidate_state(state, args.candidate_id)
    if candidate.get("status") != "ready-for-confirmation":
        raise ValueError("Candidate must be ready-for-confirmation before confirmation.")

    print(json.dumps(candidate, ensure_ascii=False, indent=2))
    if not confirm_stage("Confirm grouping and project/topic."):
        print("Confirmation cancelled at grouping stage.")
        return 0

    if not confirm_stage("Confirm this candidate is worth retaining."):
        reason = input("Rejection reason: ").strip()
        if not reason:
            raise ValueError("A rejection reason is required.")
        rejection_id = uuid.uuid5(uuid.NAMESPACE_URL, candidate["candidate_id"])
        rejection_name = f"{safe_file_stem(candidate.get('project_or_topic', 'candidate'))}--{rejection_id}.md"
        rejection_path = vault_path / "Brag" / "Archive" / "Rejected" / rejection_name
        write_text_atomic(rejection_path, render_rejection_markdown(candidate, reason))
        candidate["status"] = "rejected"
        candidate["rejection_path"] = str(rejection_path)
        save_review_state(state)
        print(f"Rejected candidate recorded at: {rejection_path}")
        return 0

    answers = candidate.get("confirmed_answers", {})
    for key in READY_KEYS:
        print(f"{key}: {answers.get(key, '')}")
        if not confirm_stage(f"Confirm fact '{key}'."):
            print(f"Confirmation cancelled at fact stage: {key}.")
            return 0

    wording = args.wording or f"{answers.get('contribution', '')}; {answers.get('outcome', '')}"
    print(f"Generated wording: {wording}")
    if not confirm_stage("Confirm generated wording."):
        print("Confirmation cancelled at wording stage.")
        return 0

    achievement_id = validate_achievement_id(args.achievement_id or str(uuid.uuid4()))
    file_name = f"{safe_file_stem(candidate.get('project_or_topic', 'achievement'))}--{achievement_id}.md"
    achievement_path = vault_path / "Brag" / "Achievements" / file_name
    content = render_achievement_markdown(
        achievement_id=achievement_id,
        candidate=candidate,
        wording=wording,
        language=args.language,
        model=args.model,
    )
    validate_authoritative_achievement(content)
    if achievement_path.exists():
        validate_authoritative_achievement(achievement_path.read_text(encoding="utf-8"))
        raise ValueError(f"Achievement already exists and will not be overwritten: {achievement_path}")

    write_text_atomic(achievement_path, content)
    candidate["status"] = "confirmed"
    candidate["achievement_id"] = achievement_id
    candidate["achievement_path"] = str(achievement_path)
    save_review_state(state)
    print(f"Confirmed achievement created at: {achievement_path}")
    return 0


def cmd_attach_candidate(args: argparse.Namespace) -> int:
    vault_path = resolve_vault_path(args.vault)
    state = load_review_state()
    candidate = find_candidate_state(state, args.candidate_id)
    incoming_facts = candidate.get("confirmed_answers", {})
    if not isinstance(incoming_facts, dict):
        raise ValueError("Candidate confirmed answers are invalid.")

    achievements, warnings = scan_achievements(vault_path)
    for warning in warnings:
        print(warning)

    target = choose_target_achievement(achievements, candidate, args.achievement_id)
    action = args.action or input("Choose action (merge/separate/ignore): ").strip().lower()
    if action not in {"merge", "separate", "ignore"}:
        raise ValueError("Action must be one of: merge, separate, ignore.")

    if action == "ignore":
        candidate["status"] = "ignored"
        candidate["ignored_at_utc"] = datetime.now(timezone.utc).isoformat()
        save_review_state(state)
        print("Candidate ignored and preserved for traceability.")
        return 0

    if action == "separate":
        achievement_id = validate_achievement_id(args.new_achievement_id or str(uuid.uuid4()))
        wording = args.wording or default_wording_from_facts(incoming_facts)
        file_name = f"{safe_file_stem(candidate.get('project_or_topic', 'achievement'))}--{achievement_id}.md"
        achievement_path = vault_path / "Brag" / "Achievements" / file_name
        content = render_achievement_markdown(
            achievement_id=achievement_id,
            candidate=candidate,
            wording=wording,
            language=args.language,
            model=args.model,
        )
        validate_authoritative_achievement(content)
        if achievement_path.exists():
            validate_authoritative_achievement(achievement_path.read_text(encoding="utf-8"))
            raise ValueError(f"Achievement already exists and will not be overwritten: {achievement_path}")
        write_text_atomic(achievement_path, content)
        candidate["status"] = "confirmed"
        candidate["achievement_id"] = achievement_id
        candidate["achievement_path"] = str(achievement_path)
        save_review_state(state)
        print(f"Created separate achievement at: {achievement_path}")
        return 0

    if target is None:
        raise ValueError(
            "No target achievement selected. Provide --achievement-id for merge when auto-match is ambiguous."
        )

    print(f"Target achievement id: {target['id']}")
    print(f"Target path: {target['path']}")
    print(f"Existing source references: {json.dumps(target['source_references'], ensure_ascii=False)}")
    print(f"Incoming source: {candidate['candidate_id']}")

    existing_facts = dict(target["confirmed_facts"])
    facts_changed = False
    if not confirm_stage(f"Confirm merge into achievement '{target['id']}'."):
        print("Merge cancelled.")
        return 0

    for key in READY_KEYS:
        incoming = str(incoming_facts.get(key, "")).strip()
        existing = str(existing_facts.get(key, "")).strip()
        if not incoming or incoming == existing:
            continue
        print(f"Conflict on {key}:")
        print(f"- existing ({target['id']}): {existing}")
        print(f"- incoming ({candidate['candidate_id']}): {incoming}")
        if existing:
            if confirm_stage(f"Replace existing fact '{key}' with incoming value?"):
                existing_facts[key] = incoming
                facts_changed = True
        else:
            if confirm_stage(f"Adopt incoming fact '{key}' into empty field?"):
                existing_facts[key] = incoming
                facts_changed = True

    frontmatter = dict(target["frontmatter"])
    source_refs = list(target["source_references"])
    source_lines = list(target["source_lines"])
    incoming_source = candidate["candidate_id"]
    if incoming_source not in source_refs:
        if confirm_stage("Attach incoming source reference to the target achievement?"):
            source_refs.append(incoming_source)
    if incoming_source not in source_lines and incoming_source in source_refs:
        source_lines.append(incoming_source)

    confirmed_block = target["confirmed_block"]
    if facts_changed:
        confirmed_block = render_confirmed_facts_block(existing_facts)

    generated_wording = target["generated_wording"]
    if args.regenerate_generated:
        generated_wording = args.wording or default_wording_from_facts(existing_facts)
        frontmatter["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        frontmatter["generated_language"] = args.language
        frontmatter["ai_model"] = args.model

    frontmatter["source_references"] = source_refs
    content = compose_authoritative_markdown(
        frontmatter=frontmatter,
        confirmed_block=confirmed_block,
        source_lines=source_lines,
        generated_wording=generated_wording,
    )
    validate_authoritative_achievement(content)
    write_text_atomic(target["path"], content)

    candidate["status"] = "confirmed"
    candidate["attached_achievement_id"] = target["id"]
    candidate["achievement_path"] = str(target["path"])
    save_review_state(state)
    print(f"Merged candidate into achievement: {target['path']}")
    return 0


def cmd_generate_outputs(args: argparse.Namespace) -> int:
    vault_path = resolve_vault_path(args.vault)
    achievements, warnings = scan_achievements(vault_path)
    for warning in warnings:
        print(warning)

    ids = args.achievement_id
    if not ids:
        raise ValueError("At least one --achievement-id is required.")
    output_types = parse_output_types(args.output_types)

    selected: list[dict] = []
    for achievement_id in ids:
        key = validate_achievement_id(achievement_id)
        achievement = achievements.get(key)
        if achievement is None:
            raise ValueError(f"Achievement not found: {key}")
        state = str(achievement["frontmatter"].get("state", "")).strip().lower()
        if state != "confirmed":
            raise ValueError(f"Achievement is not confirmed: {key}")
        selected.append(achievement)

    generated_outputs: list[dict] = []
    for achievement in selected:
        feedback = build_feedback(achievement, args.language)
        print(
            json.dumps(
                {
                    "achievement_id": achievement["id"],
                    "resume_themes": feedback["themes"],
                    "missing_evidence": feedback["missing"],
                    "strongest_statement": feedback["strongest_statement"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        new_content, outputs = update_generated_wording_section(
            achievement,
            language=args.language,
            model=args.model,
            output_types=output_types,
        )
        write_text_atomic(achievement["path"], new_content)
        generated_outputs.append(outputs)
        print(f"Updated generated wording for: {achievement['path']}")

    if len(selected) > 1 or args.aggregate_name:
        aggregate_name = args.aggregate_name or f"aggregate-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        aggregate_path = vault_path / "Brag" / "Outputs" / f"{safe_file_stem(aggregate_name)}.md"
        aggregate_text = render_aggregate_output(
            achievements=selected,
            generated=generated_outputs,
            language=args.language,
            output_types=output_types,
        )
        write_text_atomic(aggregate_path, aggregate_text)
        print(f"Aggregate output created at: {aggregate_path}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brag-cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-vault", help="Initialize a vault for Brag documents")
    init_parser.add_argument("--path", required=True, help="Path to an existing vault directory")
    init_parser.set_defaults(handler=cmd_init_vault)

    show_parser = subparsers.add_parser("show-config", help="Show current local CLI configuration")
    show_parser.set_defaults(handler=cmd_show_config)

    capture_text_parser = subparsers.add_parser("capture-text", help="Capture free-form work notes")
    capture_text_parser.add_argument("--text", required=True, help="Text to capture as raw activity")
    capture_text_parser.add_argument("--vault", help="Optional vault path override for this command")
    capture_text_parser.set_defaults(handler=cmd_capture_text)

    capture_prompted_parser = subparsers.add_parser("capture-prompted", help="Capture prompted work notes")
    capture_prompted_parser.add_argument("--context", help="Optional context")
    capture_prompted_parser.add_argument("--action", help="Optional action")
    capture_prompted_parser.add_argument("--impact", help="Optional impact")
    capture_prompted_parser.add_argument("--evidence", help="Optional evidence")
    capture_prompted_parser.add_argument("--vault", help="Optional vault path override for this command")
    capture_prompted_parser.set_defaults(handler=cmd_capture_prompted)

    analyze_parser = subparsers.add_parser("analyze-inbox", help="Analyze inbox content safely")
    analyze_parser.add_argument("--vault", help="Optional vault path override")
    analyze_parser.add_argument("--inbox-file", help="Optional inbox file path to analyze")
    analyze_parser.add_argument("--max-bytes", type=int, default=12000, help="Max outbound bytes")
    analyze_parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model name")
    analyze_parser.set_defaults(handler=cmd_analyze_inbox)

    review_parser = subparsers.add_parser("review-candidate", help="Review one analyzed candidate")
    review_parser.add_argument("--vault", help="Optional vault path override")
    review_parser.add_argument("--inbox-file", help="Optional inbox file path to review")
    review_parser.add_argument("--candidate-index", type=int, default=0, help="Candidate index after flattening")
    review_parser.add_argument(
        "--mode",
        choices=["quick", "immediate"],
        default="quick",
        help="quick defers follow-up; immediate asks follow-up now",
    )
    review_parser.add_argument("--max-followups", type=int, default=3, help="Max follow-up questions per round")
    review_parser.add_argument("--max-bytes", type=int, default=12000, help="Max outbound bytes")
    review_parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model name")
    review_parser.add_argument(
        "--ask-ai-followup",
        action="store_true",
        help="Optionally ask AI for follow-up suggestions after manual answers",
    )
    review_parser.set_defaults(handler=cmd_review_candidate)

    confirm_parser = subparsers.add_parser(
        "confirm-candidate", help="Confirm or reject a reviewed candidate"
    )
    confirm_parser.add_argument("--candidate-id", required=True, help="Candidate ID from review state")
    confirm_parser.add_argument("--vault", help="Optional vault path override")
    confirm_parser.add_argument("--achievement-id", help="Optional immutable ID for deterministic retry")
    confirm_parser.add_argument("--wording", help="Generated wording proposed for confirmation")
    confirm_parser.add_argument(
        "--language", choices=["zh-TW", "en"], default="zh-TW", help="Generated wording language"
    )
    confirm_parser.add_argument("--model", default="gpt-4o-mini", help="Generation model metadata")
    confirm_parser.set_defaults(handler=cmd_confirm_candidate)

    attach_parser = subparsers.add_parser(
        "attach-candidate", help="Attach a reviewed candidate to an existing achievement"
    )
    attach_parser.add_argument("--candidate-id", required=True, help="Candidate ID from review state")
    attach_parser.add_argument("--vault", help="Optional vault path override")
    attach_parser.add_argument("--achievement-id", help="Target achievement immutable ID for merge")
    attach_parser.add_argument(
        "--action", choices=["merge", "separate", "ignore"], help="Attachment decision"
    )
    attach_parser.add_argument("--new-achievement-id", help="Immutable ID when action=separate")
    attach_parser.add_argument("--wording", help="Generated wording to store or regenerate")
    attach_parser.add_argument(
        "--language", choices=["zh-TW", "en"], default="zh-TW", help="Generated wording language"
    )
    attach_parser.add_argument("--model", default="gpt-4o-mini", help="Generation model metadata")
    attach_parser.add_argument(
        "--regenerate-generated",
        action="store_true",
        help="Regenerate only the generated wording section during merge",
    )
    attach_parser.set_defaults(handler=cmd_attach_candidate)

    generate_parser = subparsers.add_parser(
        "generate-outputs", help="Generate immediate feedback and career outputs"
    )
    generate_parser.add_argument(
        "--achievement-id",
        action="append",
        required=True,
        help="Confirmed achievement ID (repeatable)",
    )
    generate_parser.add_argument("--vault", help="Optional vault path override")
    generate_parser.add_argument(
        "--output-types",
        default="star,resume-bullet,performance-summary",
        help="Comma-separated output types",
    )
    generate_parser.add_argument("--aggregate-name", help="Optional aggregate output file name")
    generate_parser.add_argument(
        "--language", choices=["zh-TW", "en"], default="zh-TW", help="Output language"
    )
    generate_parser.add_argument("--model", default="local-template", help="Generation model metadata")
    generate_parser.set_defaults(handler=cmd_generate_outputs)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ValueError as e:
        print(f"Error: {e}")
        return 2
    except OSError as e:
        print(f"Error: filesystem operation failed: {e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())