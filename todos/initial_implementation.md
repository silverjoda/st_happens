# TODO - initial_implementation

- [x] Read `SPEC.md` and extract constraints relevant to initial implementation
- [x] Break requested work into concrete implementation tasks

## Completed milestones

- [x] M1 complete: ingestion pipeline + manual review flow implemented and validated
- [x] M2 complete: FastAPI voting session flow implemented and validated
- [x] M3 complete: ranking CLI + Bradley-Terry/Elo + normalization/persistence implemented and validated
- [x] Regression fixes complete: template rendering compatibility and detached-instance issues resolved

## Pending milestones

### M4 - AI voter integration

- [x] Create `src/ai_user/run.py` runner for description-only pair voting
- [x] Persist AI sessions and comparisons with `sessions.actor_type = ai`
- [x] Persist AI run configuration metadata (model, prompt style, temperature, seed)

### M5 - Comparative analysis reporting

- [x] Create `src/analysis/compare.py` with CLI args `--human-run` and `--ai-run`
- [x] Load ranking runs and join against approved cards + official scores
- [x] Compute required metrics: Spearman rank correlation, Kendall tau, and mean absolute difference (normalized 1-100)
- [x] Generate top-disagreement card list for official vs human and official vs AI
- [x] Write report artifacts to `outputs/` (machine-readable file + readable summary)
- [x] Add tests for metric computation and output artifact shape/path

## Final verification and smoke checks

- [x] Review implemented code paths against current SPEC acceptance criteria
- [x] Run `uv run pytest -q` and fix failures
- [ ] Run app smoke command: `uv run python -m src.app.main` (startup succeeds)
- [ ] Run ingest smoke command: `uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed` (run completes + report emitted)
- [ ] Run review smoke command: `uv run python -m src.ingest.review` (manual review loop starts)
- [ ] After M5 lands, run ranking/AI/analysis smoke commands end to end

## Next task queue (ordered, actionable)

- [x] Implement M4 runner scaffold in `src/ai_user/run.py` with CLI args (`--pairs`, `--model`, `--temperature`, optional `--seed`)
- [x] Add deterministic pair selection + vote loop for AI actor using description-only card data
- [x] Persist AI session/comparison rows and run metadata, then add focused tests for persistence and actor separation
- [x] Create `src/analysis/compare.py` CLI entrypoint and argument validation
- [x] Implement ranking/official data loading helpers and shared normalization alignment checks
- [x] Implement required metric calculations and disagreement extraction
- [x] Write outputs to `outputs/` and add/adjust tests in `tests/` for M5 coverage
- [x] Run `uv run pytest -q` and resolve any new failures

## Verification notes (latest run)

- `uv run pytest -q` -> 30 passed

## Immediate next task

- [x] Start M5 by implementing `src/analysis/compare.py` CLI scaffold plus metric computation helpers, then backfill tests
