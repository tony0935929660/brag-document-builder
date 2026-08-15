# Brag Document Builder

Local-first CLI for turning raw work notes into confirmed achievements and career-ready outputs.

## Highlights

- Markdown-authoritative workflow: confirmed facts and generated wording are stored separately.
- Safety-first AI analysis: payload preview, warning, explicit YES, and max-bytes checks.
- End-to-end delivery completed through Slice 10.
- Built-in MVP evaluation command with deterministic fixtures and threshold reporting.

## Current release

- Latest tag: v0.10.0
- Python: 3.12+

## Quick Start

Create and activate a virtual environment.

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

Run the core flow.

```bash
python -m src.brag_cli init-vault --path /path/to/vault
python -m src.brag_cli capture-text --text "Reduced p95 latency by 28% in checkout flow"
python -m src.brag_cli analyze-inbox --model gpt-4o-mini
python -m src.brag_cli review-candidate --mode immediate
python -m src.brag_cli confirm-candidate --candidate-id <candidate-id>
python -m src.brag_cli generate-outputs --achievement-id <achievement-id> --output-types star,resume-bullet,performance-summary --language en
```

## MVP Evaluation

Deterministic end-to-end check:

```bash
python -m src.brag_cli mvp-eval --fixtures-file tests/fixtures/mvp_eval_cases.json --deterministic
```

Optional simulated OpenAI failure mode:

```bash
python -m src.brag_cli mvp-eval --fixtures-file tests/fixtures/mvp_eval_cases.json --deterministic --simulate-openai-failure
```

The report covers grouping acceptance, missed worthwhile rate, minor-edit rate, average processing time, and per-case traceability.

## Command Groups

- Vault and config: init-vault, show-config
- Capture and analysis: capture-text, capture-prompted, analyze-inbox, review-candidate
- Decision flow: confirm-candidate, attach-candidate
- Output generation: generate-outputs
- Repo import: repo-register, repo-list, repo-remove, changelog-import, import-ledger-rebuild
- Evaluation: mvp-eval

## Test

```bash
python -m unittest discover -s tests
```

## Docs

- [docs/SPEC.md](docs/SPEC.md)
- [docs/PLAN.md](docs/PLAN.md)
- [CHANGELOG.md](CHANGELOG.md)
