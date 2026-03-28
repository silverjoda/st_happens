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
- [ ] Implement manual review CLI/UI flow: iterate card-by-card, edit fields, set status (`approved|needs_fix|rejected`)
- [ ] Enforce ranking eligibility to approved cards only

## M1 validation

- [ ] Add automated test that validates full official score increment coverage from 0.5 to 100.0
- [ ] Add ingestion-focused tests (basic extraction result persistence, report generation shape)

## Next milestones (after M1)

- [ ] M2: Build FastAPI human voting flow (session start, configurable pair count, pair display, vote capture)
- [ ] M2: Implement pair generation constraints (no self-pairs, no immediate duplicate repeats, seed logging)
- [ ] M3: Implement ranking runner with Bradley-Terry primary and Elo baseline + normalization to [1, 100]
- [ ] M4: Implement AI voter runner storing `actor_type=ai` sessions and comparisons
- [ ] M5: Implement comparative analysis report (Spearman, Kendall tau, MAD, top disagreements)

## Final checks

- [ ] Review changes and run tests
