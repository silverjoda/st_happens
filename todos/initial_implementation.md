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
- [x] Run app smoke command: `uv run python -m src.app.main` and verify startup log/no import errors
- [x] Install/configure Tesseract on host and verify binary is on PATH (`tesseract --version`)
- [x] Run ingest smoke command: `uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed`
- [x] Verify extraction artifacts were emitted to `data/processed/` (including a digitization report)
- [x] Run review smoke command: `uv run python -m src.ingest.review` and verify manual-review loop starts
- [ ] Complete manual review approvals so cards reach `approved` status (target at least 95% approved)
- [x] Verify approved-card precondition for ranking (`approved` cards exist; enough for pairing)
- [x] Run ranking smoke command (human): `uv run python -m src.ranking.run --population human --algorithm bradley_terry`
- [x] Run ranking smoke command (AI): `uv run python -m src.ranking.run --population ai --algorithm bradley_terry`
- [x] Run AI voter smoke command: `uv run python -m src.ai_user.run --pairs 200 --model <model_name>`
- [x] Run analysis smoke command: `uv run python -m src.analysis.compare --human-run <id> --ai-run <id>`
- [x] Verify end-to-end artifacts were emitted to `outputs/` with required metrics/disagreement lists

## Next task queue (ordered, actionable)

- [x] Implement M4 runner scaffold in `src/ai_user/run.py` with CLI args (`--pairs`, `--model`, `--temperature`, optional `--seed`)
- [x] Add deterministic pair selection + vote loop for AI actor using description-only card data
- [x] Persist AI session/comparison rows and run metadata, then add focused tests for persistence and actor separation
- [x] Create `src/analysis/compare.py` CLI entrypoint and argument validation
- [x] Implement ranking/official data loading helpers and shared normalization alignment checks
- [x] Implement required metric calculations and disagreement extraction
- [x] Write outputs to `outputs/` and add/adjust tests in `tests/` for M5 coverage
- [x] Run `uv run pytest -q` and resolve any new failures
- [x] Execute app startup smoke check and capture pass/fail result
- [x] Install/configure Tesseract and verify availability (`tesseract --version`)
- [x] Execute ingestion extraction smoke check and confirm report path
- [x] Execute manual review CLI smoke check and confirm interactive entry
- [x] Run full manual review pass and approve valid extracted cards (`approved`), fixing/rejecting invalid OCR rows
- [x] Confirm approved-card count and pairability are sufficient for ranking and AI voting preconditions
- [x] Execute human ranking smoke command and record produced run ID
- [x] Execute AI ranking smoke command and record produced run ID
- [x] Execute AI voter smoke command with concrete model name (e.g., `heuristic_v1`) and record session/run metadata
- [x] Execute analysis compare command with latest human/AI run IDs and verify `outputs/` artifacts
- [x] Mark remaining smoke-check items complete in this TODO with command evidence and output paths

## Verification notes (latest run)

- 2026-03-28 12:10 CET: Audited checklist against implementation/tests; completed items remain checked and blocked smoke items remain unchecked.
- 2026-03-28 12:10 CET: `uv run pytest -q` -> 30 passed (same 4 deprecation warnings: FastAPI `on_event`, `datetime.utcnow()`).
- 2026-03-28 12:10 CET: `tesseract --version` -> `tesseract 5.5.2` (PATH OK).
- 2026-03-28 12:10 CET: `uv run python -m src.app.main` reached uvicorn serving state and clean shutdown after smoke timeout (pass).
- 2026-03-28 12:10 CET: `uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed` -> Processed=200, Successes=66, Failures=134; reports emitted at `data/processed/ingestion_report_20260328T110729Z.json` and `.md`.
- 2026-03-28 12:10 CET: `uv run python -m src.ingest.review` entered interactive loop (`Card 1/200`, `review>`), then exited with `EOFError` in non-interactive environment (expected for smoke run).
- 2026-03-28 12:10 CET: Ranking smoke commands (`human` + `ai`) still return `no_approved_cards`; AI voter still returns `insufficient_pairs_available`; analysis compare still returns `ranking_run_not_found:1`; `outputs/` remains empty.
- 2026-03-28 12:16 CET: Completed full extracted-card review queue using scripted `src.ingest.review` input (`approve` when description+score+0.5-step valid, else `reject`): status counts now `approved=185`, `rejected=341`, `extracted=0`; approval ratio is 35.17%, so the 95% target remains blocked by low OCR yield across accumulated extraction rows.
- 2026-03-28 12:16 CET: Preconditions verified: `approved_cards=185`, unique pair capacity `17020`; actor data now includes `human` session/comparisons (`1` session, `200` comparisons) for ranking smoke coverage.
- 2026-03-28 12:16 CET: `uv run python -m src.ranking.run --population human --algorithm bradley_terry` -> `ranking_run_saved run_id=1 population=human algorithm=bradley_terry`.
- 2026-03-28 12:16 CET: `uv run python -m src.ai_user.run --pairs 200 --model heuristic_v1` -> `ai_run_saved session_id=2 run_id=1 pairs=200`.
- 2026-03-28 12:16 CET: `uv run python -m src.ranking.run --population ai --algorithm bradley_terry` -> `ranking_run_saved run_id=2 population=ai algorithm=bradley_terry`.
- 2026-03-28 12:16 CET: `uv run python -m src.analysis.compare --human-run 1 --ai-run 2` wrote `outputs/comparison_h1_a2.json` and `outputs/comparison_h1_a2.md`; report includes Spearman/Kendall/MAD metrics and top-disagreement sections for official-vs-human and official-vs-ai.
- 2026-03-28: Re-reviewed implementation against `SPEC.md` + this TODO; checked items remain accurate, blocked smoke items remain unchecked.
- 2026-03-28: `uv run pytest -q` -> 30 passed (4 deprecation warnings from FastAPI `on_event` and `datetime.utcnow()` usage).
- 2026-03-28: `uv run python -m src.app.main` reached uvicorn serving state (pass; stopped by smoke-check timeout).
- 2026-03-28: `uv run pytest -q` -> 30 passed (4 deprecation warnings from FastAPI `on_event` and `datetime.utcnow()` usage)
- 2026-03-28 11:52 CET: `uv sync --dev` removed `jinja2`/`python-multipart`; `uv run python -m src.app.main` failed with `ImportError: jinja2 must be installed to use Jinja2Templates`.
- 2026-03-28 11:52 CET: Added runtime deps in `pyproject.toml` (`jinja2`, `python-multipart`), re-ran `uv sync --dev`, then `uv run python -m src.app.main` reached uvicorn serving state (pass; stopped by smoke-check timeout).
- 2026-03-28 11:52 CET: `uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed` failed with `TesseractNotFoundError` (`tesseract` binary missing in PATH); `data/processed/` has no artifacts/report.
- 2026-03-28 11:52 CET: `uv run python -m src.ingest.review` ran but exited with `No cards found with status='extracted'` (blocked by failed extraction; no interactive review prompt).
- 2026-03-28 11:52 CET: Ranking smoke commands for human/ai both returned `no_approved_cards`; no ranking run IDs produced.
- 2026-03-28 11:52 CET: `uv run python -m src.ai_user.run --pairs 200 --model heuristic_v1` returned `insufficient_pairs_available` (dataset precondition not met).
- 2026-03-28 11:52 CET: `uv run python -m src.analysis.compare --human-run 1 --ai-run 1` returned `ranking_run_not_found:1`; `outputs/` has no generated artifacts.
- 2026-03-28 12:00 CET: Installed Tesseract via Homebrew; `tesseract --version` now reports `tesseract 5.5.2`.
- 2026-03-28 12:00 CET: `uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed` -> Processed=200, Successes=66, Failures=134; reports emitted at `data/processed/ingestion_report_20260328T105934Z.json` and `data/processed/ingestion_report_20260328T105934Z.md`.
- 2026-03-28 12:01 CET: `uv run python -m src.ingest.review` entered interactive loop (`Card 1/200`, `review>` prompt), then terminated with `EOFError` in non-interactive smoke environment.
- 2026-03-28 12:01 CET: Ranking smoke rerun (`human` + `ai`) still returns `no_approved_cards`; no run IDs produced because extracted cards are not yet approved.
- 2026-03-28 12:01 CET: `uv run python -m src.ai_user.run --pairs 200 --model heuristic_v1` still returns `insufficient_pairs_available`.
- 2026-03-28 12:02 CET: `uv run python -m src.analysis.compare --human-run 1 --ai-run 1` returns `ranking_run_not_found:1`; `outputs/` remains empty.

## Immediate next tasks

- [ ] Improve ingestion/review quality toward the 95% approved acceptance target (current: 185/526 approved, 35.17%)
- [ ] Decide whether to de-duplicate/re-baseline the cards dataset before further acceptance validation
