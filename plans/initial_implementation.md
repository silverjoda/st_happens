initial_implementation

# Implementation plan: next pending todo items (final smoke checks)

## Scope (tight to immediate pending work)

This plan targets only the next unchecked items in `todos/initial_implementation.md`:

1. App startup smoke check.
2. Ingestion extraction smoke check and report verification.
3. Manual review CLI smoke check.
4. Human and AI ranking smoke checks with run-id capture.
5. AI voter smoke check.
6. Analysis compare smoke check and output verification.
7. Verification-note and todo updates.

Out of scope: new feature development, refactors, and broad test rewrites.

## Spec + prompt alignment

- Section 11 requires each CLI/app command to run from repo root using `uv run ...`.
- FR-1/FR-1a require extraction artifacts and manual review loop to be operational.
- FR-5 requires ranking CLI execution for both populations.
- FR-6 requires AI voter execution as `actor_type = ai`.
- FR-7 requires compare report generation with required metrics/disagreement outputs in `outputs/`.
- Prompt requires pragmatic first-iteration validation: verify critical paths end-to-end without adding unnecessary complexity.

## Detailed implementation plan

## 1) Preflight and logging setup

### Goal
Establish a repeatable smoke-check workflow and capture results in one place.

### Files in focus
- `todos/initial_implementation.md`

### Work items
1. Confirm dependencies are synced (`uv sync --dev` if needed).
2. Use a single execution order that mirrors runtime dependencies: app -> ingest -> review -> ranking -> AI voter -> analysis.
3. For each command, capture: timestamp, command, pass/fail, and key outputs (artifact paths or run IDs).
4. Append concise findings to `## Verification notes (latest run)` after each command.

### Definition of done
- Verification-note format is consistent and ready for final summary.

## 2) App startup smoke check

### Goal
Verify FastAPI entrypoint imports and boots without immediate runtime errors.

### Command
`uv run python -m src.app.main`

### Work items
1. Run command from repo root.
2. Confirm startup log appears and process reaches serving state.
3. Treat immediate import/config exceptions as failure; record traceback headline.
4. Stop process cleanly after successful startup confirmation.

### Definition of done
- Todo item "Execute app startup smoke check and capture pass/fail result" is checkable.

## 3) Ingestion extraction smoke check + artifact verification

### Goal
Verify extraction command executes and emits processed artifacts including digitization report.

### Command
`uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed`

### Work items
1. Run extraction command and capture high-level processing summary.
2. Verify output files exist under `data/processed/`.
3. Explicitly locate the digitization report artifact and record its path.
4. If extraction fails due to data/environment preconditions, record exact blocker and continue remaining non-blocked checks where possible.

### Definition of done
- Todo items for extraction smoke check and report-path confirmation are checkable.

## 4) Manual review CLI smoke check

### Goal
Confirm review flow starts and reaches interactive card-review entrypoint.

### Command
`uv run python -m src.ingest.review`

### Work items
1. Run command and verify interactive loop/menu initializes.
2. Confirm no immediate crash on startup or first prompt render.
3. Exit gracefully after startup verification; record whether at least one review prompt rendered.

### Definition of done
- Todo item for manual-review CLI interactive entry is checkable.

## 5) Ranking smoke checks (human + AI)

### Goal
Verify ranking CLIs run for both populations and produce run IDs for downstream compare.

### Commands
- `uv run python -m src.ranking.run --population human --algorithm bradley_terry`
- `uv run python -m src.ranking.run --population ai --algorithm bradley_terry`

### Work items
1. Run human ranking command and capture resulting `ranking_run.id` (or equivalent emitted identifier).
2. Run AI ranking command and capture resulting run ID.
3. Record normalization/output summary if printed (card count, score range, artifact hints).
4. Add both IDs to verification notes for direct reuse in compare step.

### Definition of done
- Todo item for human+AI ranking execution and run-id recording is checkable.

## 6) AI voter smoke check

### Goal
Verify AI pairwise voting runner executes its main loop with description-only inputs.

### Command
`uv run python -m src.ai_user.run --pairs 200 --model <model_name>`

### Work items
1. Choose a locally configured model value consistent with current project setup.
2. Run command and verify session creation plus at least initial voting progression.
3. Capture resulting AI session/run metadata identifiers if emitted.
4. If external model credentials are missing, record blocker explicitly and mark as environment-blocked (not code-failed).

### Definition of done
- Todo item for AI voter smoke execution is checkable (pass or clearly blocked with reason).

## 7) Analysis compare smoke check + output verification

### Goal
Run final comparison and verify required output artifacts are produced under `outputs/`.

### Command
`uv run python -m src.analysis.compare --human-run <id> --ai-run <id>`

### Work items
1. Run command using latest valid human/AI run IDs from step 5.
2. Confirm command completes and emits output file paths.
3. Verify `outputs/` contains machine-readable and readable summary artifacts.
4. Confirm artifacts include required metrics and disagreement lists (FR-7 contract-level check).

### Definition of done
- Todo items for analysis smoke execution and output verification are checkable.

## 8) Closeout updates

### Goal
Synchronize todo state and leave an auditable record of what passed/failed.

### Files in focus
- `todos/initial_implementation.md`

### Work items
1. Mark each completed smoke-check todo as checked.
2. For any failures, keep todo unchecked and add one-line remediation note in verification notes.
3. Ensure `## Immediate next task` reflects the first remaining unchecked item (or mark complete if none remain).

### Definition of done
- Todo file accurately reflects current state, with no ambiguity on remaining blockers.

## Execution order (strict)

1. Preflight logging setup.
2. App startup smoke check.
3. Ingestion extraction + artifact verification.
4. Manual review smoke check.
5. Human and AI ranking smoke checks.
6. AI voter smoke check.
7. Analysis compare smoke check.
8. Todo and verification-note closeout.

Completion criteria for this plan:

- Every currently pending smoke-check todo has a recorded result (pass/fail/blocked).
- Required report/artifact paths are documented for `data/processed/` and `outputs/`.
- Latest run IDs needed for comparison are captured in `todos/initial_implementation.md` verification notes.
