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

- [ ] Create `src/analysis/compare.py` CLI for ranking comparisons
- [ ] Compute/report Spearman, Kendall tau, and mean absolute difference on normalized scores
- [ ] Output top disagreement cards and write report artifacts to `outputs/`

## Final verification and smoke checks

- [x] Review implemented code paths against current SPEC acceptance criteria
- [x] Run `uv run pytest -q` and fix failures
- [ ] Run app smoke command: `uv run python -m src.app.main`
- [ ] Run ingest smoke command: `uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed`
- [ ] Run review smoke command: `uv run python -m src.ingest.review`
- [ ] After M4/M5 land, run ranking/AI/analysis smoke commands end to end

## Next task queue (ordered, actionable)

- [x] Implement M4 runner scaffold in `src/ai_user/run.py` with CLI args (`--pairs`, `--model`, `--temperature`, optional `--seed`)
- [x] Add deterministic pair selection + vote loop for AI actor using description-only card data
- [x] Persist AI session/comparison rows and run metadata, then add focused tests for persistence and actor separation
- [ ] Implement `src/analysis/compare.py` to load official/human/AI rankings and compute required metrics
- [ ] Emit analysis outputs (table + disagreement list artifact) to `outputs/` and add tests for metric/report shape

## Verification notes (latest run)

- `uv run pytest -q` -> 24 passed
