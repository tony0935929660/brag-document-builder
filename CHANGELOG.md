## [0.8.0] - 2026-08-15

### Added
- Added repository registration commands (`repo-register`, `repo-list`, `repo-remove`) for explicit local repo/changelog management.
- Added `changelog-import` with heading-range selection and explicit IMPORT confirmation before inbox write.
- Added changelog source preservation in inbox entries with repo path, changelog path, and selected range metadata.
- Added optional post-import analysis path that reuses existing cloud safety gates (preview, warning, confirmation, and size limits).
- Added Slice 8 tests for registration lifecycle, invalid registration rollback, heading-range import behavior, offline import, and analysis gating.

### Changed
- Updated initial config structure to include an empty `repositories` collection and aligned Slice 1 config assertions.

## [0.7.0] - 2026-08-15

### Added
- Added a `generate-outputs` command to create STAR stories, resume bullets, and performance summaries from confirmed achievements.
- Added immediate feedback output with resume themes, missing evidence/metric indicators, and strongest supported statement.
- Added aggregate output generation in `Brag/Outputs/` for multiple confirmed achievements with source achievement IDs.
- Added strict confirmed-only generation checks and placeholder handling (`[X%]`) for missing metrics.
- Added Slice 7 tests for multilingual generation, aggregate output creation, unconfirmed rejection, metric placeholders, and regeneration boundaries.

## [0.6.0] - 2026-08-15

### Added
- Added an `attach-candidate` command with explicit `merge`, `separate`, and `ignore` decisions for reviewed candidates.
- Added authoritative achievement scanning and parsing directly from Markdown files using immutable achievement IDs.
- Added conflict presentation for incoming versus existing facts and sources, with explicit confirmation before any replacement.
- Added malformed achievement-file reporting and skip behavior to prevent unsafe modifications.
- Added Slice 6 tests covering rename/move identity lookup, merge/separate/ignore behavior, conflict confirmation, authority precedence, and generated-section-only regeneration.

## [0.5.0] - 2026-08-15

### Added
- Added a new `confirm-candidate` command with staged confirmation for grouping, retention, facts, and generated wording.
- Added authoritative achievement Markdown generation with immutable ID, required source references, and generation metadata.
- Added rejection record creation with source reference and explicit rejection reason.
- Added Slice 5 tests covering staged cancellation, rejection flow, malformed-target protection, retry safety after write failures, and achievement-id validation.

## [0.4.0] - 2026-08-12

### Added
- Added a new review-candidate command with quick and immediate review modes for candidate triage.
- Added persistent review state tracking for candidate status, pending questions, confirmed answers, and suggested inferences.
- Added Slice 4 test coverage for follow-up limits, defer behavior, readiness transition, and inference-confirmation separation.

### Changed
- Unified outbound cloud safety gate logic for preview, size checks, and explicit YES confirmation across analysis and follow-up requests.

## [0.3.0] - 2026-08-12

### Added
- Added Slice 3 `analyze-inbox` command with optional inbox-file, vault override, model, and max-bytes options.
- Added explicit outbound preview showing exact transmitted content and byte-size estimate before cloud analysis.
- Added mandatory user confirmation gate before sending inbox content to OpenAI.
- Added analysis result validation for required grouping, classification, scoring dimensions, and reason fields.
- Added Slice 3 tests for preview behavior, confirmation rejection, size-limit blocking, missing key handling, API failure safety, malformed response handling, and secret non-leakage.

### Changed
- Extended CLI workflow to support safe inbox analysis without persisting prompt/response payloads to Markdown.

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