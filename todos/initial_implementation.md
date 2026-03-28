# TODO - initial_implementation

- [x] Read SPEC.md and extract constraints relevant to initial_implementation
- [x] Break the requested work into concrete implementation tasks

## Status snapshot (from this checklist)

- Completed milestone scope: M1 implemented and verified (`tests/test_ingest_m1_validation.py` passes)
- M2/M3 implementation exists but validation is currently failing and needs regression fixes before marking stable
- Remaining milestone work after stabilization: M4 AI voter, then M5 analysis reporting
- Immediate priority: fix M2/M3 failing tests, then proceed to M4/M5

## M1 - Data ingestion foundation (highest priority)

- [x] Create project package structure under `src/` with modules for ingest, app, ranking, ai_user, analysis
- [x] Implement shared SQLite/SQLAlchemy setup and models (`cards`, `sessions`, `comparisons`, `ranking_runs`, `ranking_results`)
- [x] Implement ingestion CLI: `python -m src.ingest.run_extract --input ... --out ...`
- [x] Add extraction pipeline skeleton (image loading, card region handling hooks, OCR calls, confidence capture)
- [x] Persist extraction outputs to DB and `data/processed/` artifacts
- [x] Generate digitization report with success/failure counts, confidence summary, and missing 0.5 increments
- [x] Implement manual review workflow entrypoint (`python -m src.ingest.review`)
- [x] Add card-by-card review navigation with image preview + extracted fields
- [x] Support editing description and official score before save
- [x] Support review actions/statuses: `approved`, `needs_fix`, `rejected`
- [x] Persist reviewer edits and statuses back to SQLite
- [x] Ensure only `approved` cards are eligible for downstream ranking selection

## M1 validation

- [x] Add automated test for full official score increment coverage from 0.5 to 100.0
- [x] Add ingestion test for extraction persistence into `cards`
- [x] Add ingestion test for report payload shape and required fields
- [x] Add ingestion test for missing increment detection behavior

## Next milestones (after M1)

- [x] M2: Create `src/app/main.py` FastAPI entrypoint and app factory
- [x] M2: Add template set for session flow (`start`, `pair`, `complete`) and shared layout
- [x] M2: Implement session start route (anonymous/nickname + pair target input)
- [x] M2: Implement pair generator with deterministic seed logging and warm-up random sampling
- [x] M2: Enforce pair constraints (no self-pairs, no immediate duplicate repeats)
- [x] M2: Implement vote submission route and persist `comparisons` (order + latency)
- [x] M2: Stabilize route-level tests for session creation and vote submission
- [x] M3: Create `src/ranking/run.py` CLI runner with args for `population` and `algorithm`
- [x] M3: Implement Bradley-Terry ranking module from stored comparisons
- [x] M3: Implement Elo baseline ranking from stored comparisons
- [x] M3: Normalize scores to [1, 100] and persist `ranking_runs` + `ranking_results`
- [x] M3: Stabilize Bradley-Terry synthetic-order and seed-stability tests
- [ ] M4: Create `src/ai_user/run.py` runner for description-only pair voting
- [ ] M4: Persist AI sessions/comparisons with `sessions.actor_type = ai`
- [ ] M4: Persist AI run config metadata (model, prompt style, temperature, seed)
- [ ] M5: Create `src/analysis/compare.py` CLI for ranking comparisons
- [ ] M5: Compute/report Spearman, Kendall tau, and mean absolute difference
- [ ] M5: Output top disagreement cards and write report artifacts to `outputs/`

## Immediate next task slice (M2 - completed)

- [x] Create `src/app/main.py` with FastAPI app initialization and local run entrypoint
- [x] Add template wiring and base page layout for the voting flow
- [x] Add `session_start` page route + form (nickname optional, pair count input)
- [x] Add POST handler to create `sessions` rows for human actor_type
- [x] Add route tests for session start/create basics

## Immediate next task slice (M3)

- [x] Create ranking CLI command entrypoint: `uv run python -m src.ranking.run --population <human|ai|combined> --algorithm <bradley_terry|elo>`
- [x] Add ranking data loader utilities:
  - [x] load approved cards for ranking universe
  - [x] load comparisons filtered by population (`human`, `ai`, `combined`)
  - [x] validate minimum data and emit stable error tokens for invalid states
- [x] Implement Bradley-Terry ranking core:
  - [x] convert comparisons into win/loss signals where chosen card is treated as worse
- [x] make latent severity fitting converge on synthetic fixture and remain deterministic across same-seed runs
  - [x] expose uncertainty proxy placeholder in run metadata if full CI not yet implemented
- [x] Implement Elo baseline ranking core:
  - [x] deterministic pass over comparisons
  - [x] configurable K-factor in `config_json`
- [x] Implement normalization + persistence:
  - [x] min-max normalize raw scores to `[1, 100]`
  - [x] persist `ranking_runs` row with algorithm/config metadata
  - [x] persist one `ranking_results` row per approved card with raw + normalized scores + rank position
- [x] Add M3 tests:
- [x] synthetic-order recovery for Bradley-Terry
  - [x] synthetic-order recovery for Elo
- [x] seed stability sanity check (same seed -> same ordering on fixed input)
  - [x] DB persistence checks for `ranking_runs` and `ranking_results`

## Current actionable next tasks (ordered)

- [x] M2: Fix FastAPI template rendering calls to pass request/context in a way compatible with current Starlette/Jinja behavior
- [x] M2: Return detached-safe pair payloads from selection flow (or avoid using ORM instances outside session) to eliminate `DetachedInstanceError`
- [x] M2: Re-run `uv run pytest tests/test_app_sessions_m2.py -q` until green
- [x] M3: Fix Bradley-Terry fitting convergence on the synthetic ranking fixture while preserving deterministic seed behavior
- [x] M3: Re-run `uv run pytest tests/test_ranking_m3.py -q` until green
- [x] M3: Confirm ranking result access is detached-safe in tests/app code paths
- [x] Run full `uv run pytest -q` after M2/M3 fixes

## Refined actionable checklist (current focus)

### M2 - Voting flow completion

- [x] Add pair selection service module (for example `src/app/pairing.py`) that:
  - [x] loads only `approved` cards
  - [x] performs warm-up random sampling
  - [x] logs strategy mode and seed for reproducibility
- [x] Implement immediate-repeat and self-pair guards in pair generation
- [x] Add GET route to render current pair for a session (description + image only; no official score)
- [x] Add POST route to record vote into `comparisons` with:
  - [x] `left_card_id`, `right_card_id`, `chosen_card_id`
  - [x] `presented_order`
  - [x] `response_ms` (nullable when not provided)
- [x] Implement session progression logic:
  - [x] increment presented order each vote
  - [x] stop at `pair_target_count`
  - [x] set `sessions.ended_at` on completion
- [x] Add completion page route/template and redirect flow after final vote
- [x] Add/extend app tests for:
  - [x] pair generation constraints
  - [x] vote submission persistence
  - [x] session completion behavior
- [x] Fix regressions revealed by current app test run:
  - [x] resolve Jinja `TemplateResponse` cache key `TypeError` (`unhashable type: 'dict'`)
  - [x] resolve SQLAlchemy detached-instance access in pair-selection tests and downstream handlers

### M3 - Ranking engine skeleton

- [x] Create `src/ranking/run.py` CLI with args for `population` and `algorithm`
- [x] Implement Bradley-Terry fit from stored comparisons
- [x] Implement Elo baseline from stored comparisons
- [x] Normalize to [1, 100] and persist `ranking_runs` + `ranking_results`
- [x] Fix Bradley-Terry convergence failures and make ranking tests fully green
- [x] Resolve detached-instance result access pattern in ranking test helper(s)

### M4 - AI voter skeleton

- [ ] Create `src/ai_user/run.py` runner for description-only pair voting
- [ ] Persist AI sessions/comparisons with `sessions.actor_type = ai`
- [ ] Persist AI run configuration metadata (model, prompt style, temperature, seed)

### M5 - Analysis reporting skeleton

- [ ] Create `src/analysis/compare.py` CLI for ranking comparisons
- [ ] Compute/report Spearman, Kendall tau, and mean absolute difference
- [ ] Output top disagreement cards and write report artifacts to `outputs/`

## Final checks

- [x] Review code paths against SPEC acceptance criteria
- [x] Run `uv run pytest -q` and fix failures
- [ ] Run smoke command for implemented app flow: `uv run python -m src.app.main`
- [ ] Run smoke command for implemented ingest flow: `uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed`
- [ ] Run smoke command for implemented review flow: `uv run python -m src.ingest.review`
- [ ] After M3-M5 land, run smoke commands for ranking/ai/analysis CLIs

## Verification notes (latest run)

- `uv run pytest tests/test_ingest_m1_validation.py -q` -> 5 passed
- `uv run pytest tests/test_app_sessions_m2.py -q` -> 11 passed
- `uv run pytest tests/test_ranking_m3.py -q` -> 6 passed
- `uv run pytest -q` -> 22 passed
