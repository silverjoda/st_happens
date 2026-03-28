initial_implementation

# Implementation plan: next pending todo items (Tesseract unblock + dependent smoke checks)

## Scope

This plan is intentionally tight to the next unchecked work in `todos/initial_implementation.md`, starting with the immediate blocker:

1. Install/configure Tesseract and verify `tesseract --version`.
2. Rerun ingestion extraction and confirm `data/processed/` artifacts (including digitization report).
3. Rerun the currently blocked downstream smoke checks that depend on approved cards/ranking outputs.
4. Update TODO checkboxes and verification notes with concrete command evidence.

Out of scope: feature development, algorithm changes, schema changes, refactors, and test rewrites.

## Spec and prompt alignment

- FR-1 requires successful extraction from `data/raw_photos/` and digitization report output.
- FR-1a requires review flow to start and operate on extracted cards.
- FR-5/FR-6/FR-7 smoke checks are currently blocked by missing ingestion output and must be rerun after unblock.
- Section 11 command surface is validated using the existing `uv run ...` entrypoints.
- Prompt constraint (first iteration): pragmatic unblock and verification, minimal code churn.

## Detailed implementation plan

## 1) Environment unblock: Tesseract availability

### Goal
Satisfy the host dependency precondition that previously caused `TesseractNotFoundError`.

### Work items
1. Confirm package manager path for host OS (macOS expected; Homebrew default).
2. Install Tesseract if missing (or repair PATH if already installed but unresolved).
3. Run `tesseract --version` from repo root shell and record output headline.
4. Capture timestamped pass/fail note in `todos/initial_implementation.md` verification notes.

### Done when
- The command `tesseract --version` succeeds without PATH errors.
- TODO item "Install/configure Tesseract and verify availability" can be checked.

## 2) Ingestion smoke rerun and artifact verification

### Goal
Produce extracted card outputs needed for all remaining smoke checks.

### Command
`uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed`

### Work items
1. Execute extraction and capture summary counts (processed/succeeded/failed).
2. Verify `data/processed/` contains fresh artifacts for the run.
3. Identify and record the digitization report path explicitly.
4. If failures remain, record precise failure reason(s) and stop downstream checks that require approved cards.

### Done when
- Extraction command completes successfully (or has explicitly documented blocker).
- TODO items for ingestion smoke and processed/report verification are updated accurately.

## 3) Manual review CLI smoke rerun

### Goal
Confirm review loop now starts against extracted cards (not empty-state blocked).

### Command
`uv run python -m src.ingest.review`

### Work items
1. Start review command after extraction run.
2. Verify entry into interactive review flow (prompt/menu/card loop).
3. Exit cleanly after startup verification; record observed behavior.

### Done when
- Manual review smoke TODO item is checked or annotated with a concrete new blocker.

## 4) Ranking smoke rerun (human + AI)

### Goal
Generate ranking runs now that approved-card precondition is expected to be met.

### Commands
- `uv run python -m src.ranking.run --population human --algorithm bradley_terry`
- `uv run python -m src.ranking.run --population ai --algorithm bradley_terry`

### Work items
1. Run both commands sequentially and capture emitted run IDs.
2. Record key output context (card count and completion status).
3. Add run IDs to verification notes for direct use in compare command.

### Done when
- Ranking smoke TODO item is checked with concrete run IDs recorded.

## 5) AI voter + analysis smoke rerun

### Goal
Complete remaining end-to-end smoke checks after ingestion/ranking unblock.

### Commands
- `uv run python -m src.ai_user.run --pairs 200 --model heuristic_v1`
- `uv run python -m src.analysis.compare --human-run <human_id> --ai-run <ai_id>`

### Work items
1. Run AI voter command and capture session/result metadata (or explicit environment blocker).
2. Run compare command with latest valid run IDs.
3. Verify expected files are written to `outputs/` and include required metrics/disagreement content.

### Done when
- AI voter and analysis smoke TODO items are checked, or blockers are documented with exact error tokens.

## 6) Todo and evidence closeout

### Goal
Leave `todos/initial_implementation.md` as the single accurate status log.

### Work items
1. Check completed items immediately after each successful command.
2. For failures, leave unchecked and add one-line remediation note in verification notes.
3. Update `## Immediate next task` to the first remaining unchecked actionable item.

### Done when
- TODO state and verification notes are consistent, current, and auditable.

## Execution order (strict)

1. Tesseract install/PATH verification.
2. Ingestion extraction rerun + processed/report verification.
3. Manual review rerun.
4. Human and AI ranking reruns (collect run IDs).
5. AI voter rerun.
6. Analysis compare rerun.
7. TODO/verification-note closeout.

Completion criteria:

- The Tesseract dependency blocker is resolved or explicitly documented as external.
- All currently pending smoke-check TODOs have a fresh pass/fail/blocked status.
- Required artifact evidence is recorded for `data/processed/` and `outputs/`.
