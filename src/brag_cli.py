from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_VAULT_DIRS = [
    Path("Brag/Inbox"),
    Path("Brag/Achievements"),
    Path("Brag/Archive/Rejected"),
    Path("Brag/Outputs"),
]


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