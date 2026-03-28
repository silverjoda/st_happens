initial_implementation

# Implementation plan: M1 next pending todo items

## Scope for this plan

This plan covers the next pending M1 tasks in order and keeps scope limited to ingestion foundation setup:

1. Create project package structure under `src/` with modules for ingest, app, ranking, ai_user, analysis.
2. Implement shared SQLite/SQLAlchemy setup and models (`cards`, `sessions`, `comparisons`, `ranking_runs`, `ranking_results`).
3. Implement ingestion CLI: `python -m src.ingest.run_extract --input ... --out ...`.
4. Add extraction pipeline skeleton (image loading, card region handling hooks, OCR calls, confidence capture).
5. Persist extraction outputs to DB and `data/processed/` artifacts.
6. Generate digitization report with success/failure counts, confidence summary, and missing 0.5 increments.

Out of scope for this pass: manual review UI/CLI flow, ranking execution, voting app, AI voter, comparative analytics.

## Guardrails from SPEC.md and prompt

- Use Python 3.11+, `uv`, and `pyproject.toml` workflows.
- Use FastAPI + SQLAlchemy + SQLite as approved defaults (even if FastAPI routes are not implemented yet).
- Design ingestion for noisy OCR and mandatory manual correction downstream.
- Keep implementation pragmatic and maintainable; avoid over-hardening and unnecessary abstractions.
- Persist enough metadata for auditability and reproducibility (timestamps, extraction confidence, run-level report artifacts).

## Implementation details

### 1) Package skeleton and shared conventions

### Deliverables
- `src/` package tree with `__init__.py` files for:
  - `src/ingest/`
  - `src/app/`
  - `src/ranking/`
  - `src/ai_user/`
  - `src/analysis/`
- Shared infra package for persistence/config (e.g., `src/common/` or `src/db/`) used by ingestion and future modules.
- Runtime data dirs created when needed: `data/processed/` and `outputs/`.

### Steps
1. Create minimal module layout with clear boundaries and no placeholder bloat.
2. Add a single source of truth for DB path/configuration (env override + sane local default).
3. Define a small utility layer for timestamps/session creation helpers reused by CLI scripts.

### Acceptance criteria
- Running Python module imports for all top-level packages works.
- Directory structure matches SPEC section 7 conventions.

### 2) SQLite + SQLAlchemy foundation and models

### Deliverables
- SQLAlchemy engine/session factory.
- Declarative models for:
  - `cards`
  - `sessions`
  - `comparisons`
  - `ranking_runs`
  - `ranking_results`
- Table creation entrypoint for local bootstrap.

### Steps
1. Implement `Base` + model classes with typed columns mapped directly to SPEC section 8.
2. Include key constraints and relationships needed for integrity:
   - FK links from comparisons and ranking results.
   - Non-null and enum-like text constraints for statuses/populations where practical in SQLite.
3. Add `created_at` / `updated_at` defaults and update behavior.
4. Add a bootstrap function invoked by ingestion CLI to ensure schema exists before writes.

### Acceptance criteria
- Fresh local run creates all required tables in SQLite.
- Basic insert/read cycle succeeds for a card and extraction metadata fields.

### 3) Ingestion CLI entrypoint

### Deliverables
- `src/ingest/run_extract.py` supporting:
  - `--input` (raw photos dir)
  - `--out` (processed artifacts dir)
  - optional `--limit` and `--seed` for deterministic development runs
- CLI execution via `python -m src.ingest.run_extract ...`.

### Steps
1. Parse args, validate paths, and create output directories.
2. Initialize DB/session and ingestion run context.
3. Enumerate image files deterministically (sorted order; optional seed only for sampling when limit is set).
4. Process each image through extraction skeleton and persist results.
5. Emit run report JSON/Markdown into `data/processed/`.

### Acceptance criteria
- CLI runs end-to-end over a small sample without crashing.
- Each processed image results in either a persisted card record or a tracked failure reason.

### 4) Extraction pipeline skeleton (not full OCR tuning)

### Deliverables
- Ingestion pipeline modules with clear seams:
  - image loader/preprocessor (OpenCV)
  - card-region hook (stubbed strategy with fallback to full image)
  - OCR adapter interface
  - Tesseract-first implementation with EasyOCR fallback hook
  - parser for description text and official score extraction
- Structured extraction result object with confidence fields.

### Steps
1. Implement image read/validation and basic preprocessing (grayscale/threshold hooks).
2. Add region extraction interface with default full-frame behavior; leave advanced alignment as follow-up.
3. Implement OCR adapter returning raw text + confidence (or `None` when unavailable).
4. Parse numeric score robustly (support integer/decimal, normalize to 0.5 grid check at reporting stage).
5. Return per-image result object with:
   - extracted description
   - extracted score
   - confidence metadata
   - failure reason if extraction incomplete

### Acceptance criteria
- Pipeline returns structured result for valid images even when OCR quality is poor.
- Failure cases are explicit and non-fatal to the full run.

### 5) Persistence + processed artifacts

### Deliverables
- DB writes for extracted cards with status default (e.g., `extracted`).
- Artifact files under `data/processed/`:
  - per-run extraction report
  - optional line-delimited raw extraction log for audit/debug

### Steps
1. Define transaction policy (commit per image or small batch; prefer per image for resilience in first iteration).
2. Persist `source_image_path`, extracted fields, confidence fields, and status.
3. Capture and persist failures in report output even when DB row is not created.
4. Write run metadata (start/end time, processed count, errors) for reproducibility.

### Acceptance criteria
- DB reflects extracted rows with required fields populated where available.
- `data/processed/` contains run artifact(s) with deterministic naming (timestamp/run-id).

### 6) Digitization report + missing increments check

### Deliverables
- Report generator producing:
  - total images processed
  - success/failure counts + categorized failure reasons
  - confidence summaries for description and score
  - list of records requiring manual review
  - missing expected score increments from `0.5` to `100.0`

### Steps
1. Aggregate extraction outputs from current run.
2. Compute confidence summaries (count/min/median/max for available confidence values).
3. Build expected increment set (`0.5, 1.0, ... 100.0`) and compare against extracted official scores.
4. Record missing increments and suspected extraction anomalies in report.
5. Save machine-readable (`.json`) and human-readable (`.md` or `.txt`) report forms.

### Acceptance criteria
- Report is generated for every run, including partial-failure runs.
- Missing increment detection is present and explicit.

## Execution order and checkpoints

1. Package skeleton + DB foundation.
2. Ingestion CLI wiring.
3. Extraction skeleton integration.
4. Persistence + report generation.
5. Smoke run on a small photo subset; verify DB rows and report contents.

Checkpoint outputs expected after this plan:
- Importable code layout under `src/`.
- SQLite DB with schema created and populated by ingestion runs.
- Repeatable extraction command producing DB data and digitization report artifacts.

## Risks and tight mitigations (within this scope)

- OCR confidence may be inconsistent across engines -> store nullable confidence fields and normalize later only for reporting.
- Card localization may be unreliable initially -> keep region hook pluggable, default to full-image OCR to avoid blocking.
- Score parsing noise -> strict numeric parser + failure classification + missing-increment report to force manual review visibility.

## Done definition for these next items

These todo items are complete when a developer can run:

`python -m src.ingest.run_extract --input data/raw_photos --out data/processed`

and obtain:
- populated `cards` rows with extraction metadata,
- a saved per-run digitization report including missing 0.5 increment analysis,
- clear failure accounting without aborting the full ingestion run.
