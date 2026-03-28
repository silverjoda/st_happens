initial_implementation

# Implementation plan: pending dataset quality and acceptance gating work

## Scope

This plan is tightly scoped to the current unchecked items in `todos/initial_implementation.md`:

1. Improve ingestion/review quality to reach the acceptance target (`>=95%` approved cards).
2. Resolve card-table inflation/duplicate rows and choose a clean dataset strategy.
3. Re-run extraction + review on the clean baseline, then re-validate downstream smoke commands.
4. Update TODO evidence with concrete counts, run IDs, and artifact paths.

Out of scope: new product features, ranking algorithm changes, UI redesign, and broad refactors.

## Spec and prompt alignment

- FR-1/FR-1a require extraction plus manual correction/approval before cards are used downstream.
- Acceptance criteria require at least 95% of cards approved and successful end-to-end reporting.
- M1 quality gate is currently the blocker; this plan focuses on clearing that gate with minimal churn.
- Prompt direction (first iteration, pragmatic) is respected by preferring operational cleanup over new architecture.

## Detailed plan for next pending items

## 1) Audit row inflation and duplicate causes

### Goal
Explain why `cards` rows exceed source-photo count and document the exact failure mode before cleanup.

### Work items
1. Capture baseline counts from DB and filesystem:
   - total rows in `cards`,
   - distinct `source_image_path` count,
   - status breakdown (`approved`, `rejected`, `extracted`, `reviewed`),
   - raw photo file count in `data/raw_photos/`.
2. Identify duplicate patterns by grouping on `source_image_path` and noting repeated extraction timestamps/status mixes.
3. Record root-cause statement in TODO notes (for example: repeated extraction appends without dedupe/upsert).

### Done when
- TODO item `Audit card-table row inflation and duplicates...` is checked.
- Evidence includes numeric counts and a one-line root-cause conclusion.

## 2) Choose and commit dataset strategy (A vs B)

### Goal
Select one reproducible cleanup path for acceptance validation.

### Decision criteria
- **Data integrity:** one canonical card row per source card for review/ranking eligibility.
- **Reproducibility:** can be rerun via explicit command sequence.
- **Low risk:** minimal manual SQL surgery and minimal chance of hidden stale data.

### Recommended default
Choose **B: reset/rebuild from clean extraction pass** unless strong evidence shows safe deterministic dedupe in place already. This is the safer first-iteration path given current inflation.

### Work items
1. Document chosen path in TODO with rationale.
2. If choosing A, define exact deterministic dedupe rule and backup steps before mutation.
3. If choosing B, define reset boundary (DB and/or processed artifacts) and exact rebuild commands.

### Done when
- TODO item `Choose dataset strategy for acceptance gating...` is checked.
- Decision and rationale are written in verification notes.

## 3) Execute cleanup path with command-level reproducibility

### Goal
Apply the chosen strategy and produce a clean working dataset.

### Work items (path B default)
1. Snapshot current DB/report artifacts for traceability.
2. Reset to clean ingestion baseline (fresh DB state and clean `data/processed/` artifacts as defined by chosen boundary).
3. Run extraction once:
   - `uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed`
4. Verify post-extraction invariants:
   - card-row count matches expected one-pass behavior,
   - extraction report files exist,
   - failure reasons/missing increments are captured.

### Done when
- TODO item `Implement the chosen dataset cleanup path...` is checked.
- Notes include command outputs and emitted report paths.

## 4) Re-run manual review to completion on clean set

### Goal
Produce final review statuses and maximize approved-card ratio against acceptance target.

### Work items
1. Run review loop:
   - `uv run python -m src.ingest.review`
2. For each extracted card:
   - correct recoverable OCR description/score,
   - approve valid cards,
   - reject only unrecoverable entries.
3. Keep score edits aligned with SPEC constraints (numeric score, 0.5 increment support).
4. Finish queue and compute final approval ratio.

### Done when
- TODO item `Re-run extraction and complete manual review on the clean card set` is checked.
- TODO item `Recompute approval ratio...` is checked with explicit ratio math.

## 5) If below 95%, tighten OCR/review loop and iterate once

### Goal
Reach acceptance quality threshold or document a concrete blocker with evidence.

### Work items
1. Analyze low-yield causes from report + rejected-card sample.
2. Apply narrow improvements only (for example: confidence triage order, score parsing guardrails, targeted correction heuristics).
3. Re-run extract + review loop and recompute ratio.

### Done when
- Either approval ratio reaches `>=95%`, or remaining gap is documented with quantified blocker details.
- TODO item `If approval ratio is still below target...` is checked or annotated with blocker evidence.

## 6) Re-validate downstream smoke flow on accepted dataset

### Goal
Confirm M4/M5 flow still works after dataset cleanup and that outputs are fresh.

### Commands
- `uv run python -m src.ranking.run --population human --algorithm bradley_terry`
- `uv run python -m src.ai_user.run --pairs 200 --model heuristic_v1`
- `uv run python -m src.ranking.run --population ai --algorithm bradley_terry`
- `uv run python -m src.analysis.compare --human-run <id> --ai-run <id>`

### Work items
1. Run commands in dependency order and capture IDs.
2. Confirm `outputs/` contains fresh comparison artifacts.
3. Verify report includes required metrics/disagreement sections.

### Done when
- TODO item `Re-run ranking + AI voter + compare smoke commands...` is checked.
- Verification notes include run IDs and artifact paths.

## 7) Final TODO and evidence closeout

### Goal
Leave `todos/initial_implementation.md` as the canonical, auditable status record.

### Work items
1. Check completed items immediately after each step.
2. For any blocked item, add timestamp + exact error token/message.
3. Add final acceptance statement with:
   - approved ratio,
   - run IDs,
   - output file locations.

### Done when
- TODO item `Update this TODO with command evidence...` is checked.
- Only true blockers remain unchecked.

## Execution order

1. Audit inflation/duplicates.
2. Choose strategy (prefer reset/rebuild).
3. Execute cleanup/rebuild.
4. Complete manual review and recompute approval ratio.
5. Iterate quality loop if still below 95%.
6. Re-run ranking/AI/analysis smoke flow.
7. Close TODO with evidence.

Completion criteria:

- Dataset quality gate meets acceptance target (`>=95% approved`) or has explicit quantified blocker.
- End-to-end smoke flow succeeds on the cleaned dataset with fresh run IDs/artifacts.
- `todos/initial_implementation.md` contains complete reproducible evidence trail.
