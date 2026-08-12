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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brag-cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-vault", help="Initialize a vault for Brag documents")
    init_parser.add_argument("--path", required=True, help="Path to an existing vault directory")
    init_parser.set_defaults(handler=cmd_init_vault)

    show_parser = subparsers.add_parser("show-config", help="Show current local CLI configuration")
    show_parser.set_defaults(handler=cmd_show_config)

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