## [0.1.0] - 2026-08-12

### Added
- Added a minimal Slice 1 Python CLI with `init-vault` and `show-config` commands.
- Added vault initialization that creates required `Brag/` directories idempotently.
- Added local operational config persistence using atomic writes.
- Added Slice 1 unit tests covering success, idempotency, invalid path handling, inaccessible path handling, and config output.
- Added initial project packaging metadata in `pyproject.toml`.