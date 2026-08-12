## [0.2.0] - 2026-08-12

### Added
- Added Slice 2 capture commands: `capture-text` and `capture-prompted`.
- Added daily inbox capture writing under `Brag/Inbox/YYYY-MM-DD.md`.
- Added optional per-command vault override for capture commands.
- Added prompted capture support with optional partial answers.
- Added Slice 2 tests for capture behavior, append semantics, path reporting, offline/no-key operation, and write-failure safety.

### Changed
- Extended CLI workflow to resolve vault path from config or command override for capture operations.

## [0.1.0] - 2026-08-12

### Added
- Added a minimal Slice 1 Python CLI with `init-vault` and `show-config` commands.
- Added vault initialization that creates required `Brag/` directories idempotently.
- Added local operational config persistence using atomic writes.
- Added Slice 1 unit tests covering success, idempotency, invalid path handling, inaccessible path handling, and config output.
- Added initial project packaging metadata in `pyproject.toml`.