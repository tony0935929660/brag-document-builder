from __future__ import annotations

import argparse
import json
import os
import tempfile
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