# TODO - initial_implementation

- [x] Read SPEC.md and extract constraints relevant to initial_implementation
- [x] Break the requested work into concrete implementation tasks

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

- [ ] M2: Create `src/app/main.py` FastAPI entrypoint and app factory
- [ ] M2: Add template set for session flow (`start`, `pair`, `complete`) and shared layout
- [x] M2: Implement session start route (anonymous/nickname + pair target input)
- [ ] M2: Implement pair generator with deterministic seed logging and warm-up random sampling
- [ ] M2: Enforce pair constraints (no self-pairs, no immediate duplicate repeats)
- [ ] M2: Implement vote submission route and persist `comparisons` (order + latency)
- [ ] M2: Add route-level tests for session creation and vote submission
- [ ] M3: Create `src/ranking/run.py` CLI runner with args for `population` and `algorithm`
- [ ] M3: Implement Bradley-Terry ranking from stored comparisons
- [ ] M3: Implement Elo baseline ranking from stored comparisons
- [ ] M3: Normalize scores to [1, 100] and persist `ranking_runs` + `ranking_results`
- [ ] M3: Add synthetic-order ranking tests and basic seed stability checks
- [ ] M4: Create `src/ai_user/run.py` runner for description-only pair voting
- [ ] M4: Persist AI sessions/comparisons with `sessions.actor_type = ai`
- [ ] M4: Persist AI run config metadata (model, prompt style, temperature, seed)
- [ ] M5: Create `src/analysis/compare.py` CLI for ranking comparisons
- [ ] M5: Compute/report Spearman, Kendall tau, and mean absolute difference
- [ ] M5: Output top disagreement cards and write report artifacts to `outputs/`

## Immediate next task slice (M2)

- [x] Create `src/app/main.py` with FastAPI app initialization and local run entrypoint
- [x] Add template wiring and base page layout for the voting flow
- [x] Add session start page route + form (nickname optional, pair count input)
- [x] Add POST handler to create `sessions` rows for human actor_type
- [x] Add route tests for session start/create basics

## Final checks

- [x] Review code paths against SPEC acceptance criteria
- [ ] Run test suite and fix failures
- [ ] Run smoke commands for ingest/app/ranking/ai/analysis CLIs
