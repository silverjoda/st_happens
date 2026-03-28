initial_implementation

# Implementation plan: next pending todo items (OCR yield and acceptance gate)

## Scope and alignment

This plan is tightly scoped to the currently unchecked next-queue items in `todos/initial_implementation.md`:

1. Audit latest ingestion artifacts to quantify dominant OCR failure modes.
2. Implement one focused deterministic OCR-yield improvement pass with targeted tests.
3. Improve review workflow to prioritize salvage via edit-and-approve.
4. Re-run clean baseline (reset -> extract -> review) and recompute approval ratio.
5. If still below target, run one additional tighten-and-retry cycle with delta reporting.
6. After acceptance is met, rerun ranking/AI/analysis smoke chain and update TODO evidence.

Spec alignment:
- FR-1 / FR-1a: extraction plus manual correction and approval workflow.
- QA and acceptance criteria: explicit validation/reporting and `>=95%` approved cards target.
- Milestone intent: pragmatic first-iteration reliability improvements over broad redesign.

Out of scope:
- New product features beyond ingestion/review quality and acceptance-gate completion.
- Ranking algorithm redesign, app UX redesign, or non-essential refactors.

## Detailed execution plan

## 1) Failure-mode audit from latest extraction artifacts

### Objective
Produce a quantified baseline of why cards are failing approval so fixes target the largest failure bucket first.

### Inputs
- Latest `data/processed/ingestion_report_*.json`
- Latest `data/processed/ingestion_log_*.jsonl`
- Current `cards` status counts from DB snapshot

### Work steps
1. Parse the most recent ingestion report and log files.
2. Bucket failures by stage/type (for example: region detect, description OCR missing/noisy, score OCR parse failure, increment-normalization failure).
3. Compute percentages per bucket and identify top 1-2 dominant failure classes.
4. Add a concise audit note to TODO verification notes with counts and percentages.

### Deliverable
- One short failure-distribution summary that clearly identifies the primary improvement target.

### Exit criteria
- TODO item `Audit data/processed/ingestion_report_*.json + latest ingestion_log_*.jsonl...` checked with numeric evidence.

## 2) Implement one focused OCR-yield improvement pass

### Objective
Increase recoverable extraction yield in the highest-impact failure class while keeping behavior deterministic and minimal.

### Strategy constraints
- Prefer a single high-leverage pass (not multiple speculative rewrites).
- Keep changes local to `src/ingest/`.
- Preserve existing interfaces/CLI behavior.

### Candidate implementation targets (pick based on Step 1 evidence)
- If score parsing dominates: strengthen OCR normalization/parsing recovery (character substitution, decimal reconstruction, strict range + 0.5-step validation).
- If description extraction dominates: improve ROI preprocessing (contrast/threshold/denoise) before OCR while preserving deterministic transforms.
- If mixed failures dominate: prioritize score reliability first (faster acceptance impact), then apply one minimal description preprocess tweak.

### Work steps
1. Implement exactly one focused logic update in ingestion/parser path.
2. Add/extend targeted unit tests for the new behavior (success and guardrail/failure cases).
3. Run focused test file(s), then `uv run pytest -q`.
4. Record changed behavior and test evidence in TODO notes.

### Deliverable
- Minimal code + test patch that improves extraction salvage probability for dominant failures.

### Exit criteria
- TODO item `Implement one focused OCR-yield improvement pass...` checked.
- Tests pass and verify deterministic behavior.

## 3) Adjust manual-review flow for salvage-first editing

### Objective
Convert recoverable rejected/extracted cards into approved cards through explicit edit-and-approve workflow without losing auditability.

### Work steps
1. Review current `src.ingest.review` interaction path for approve/reject/edit friction.
2. Ensure reviewer can edit description and score quickly before status action.
3. Add lightweight prioritization guidance/order for salvage candidates (for example: process cards with partial OCR fields before fully empty failures).
4. Preserve audit trail semantics (status transitions and explicit reviewer action path).
5. Add/adjust tests for review-flow behavior if logic changes.

### Deliverable
- Review loop behavior that practically favors correction + approval over direct rejection when salvageable.

### Exit criteria
- TODO item `Add/adjust manual-review flow to prioritize salvage...` checked with evidence.

## 4) Rebuild clean baseline and measure approval ratio

### Objective
Measure real impact after improvements using a clean reproducible dataset cycle.

### Command sequence
1. `uv run python -m src.ingest.reset_dataset`
2. `uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed`
3. `uv run python -m src.ingest.review` (complete full queue)

### Measurement steps
1. Capture final status counts (`approved`, `rejected`, `extracted/reviewed`).
2. Compute approval ratio against `200` source photos and target `>=95%`.
3. Record report artifact paths and timestamped metrics in TODO.

### Deliverable
- Clean-cycle evidence with updated approval ratio and artifact references.

### Exit criteria
- TODO item `Re-run clean baseline...` checked with explicit ratio math.

## 5) Single additional tighten-and-retry cycle if needed

### Trigger
Run only if Step 4 ratio is still `<95%`.

### Objective
Perform one more narrow improvement cycle and quantify exact delta from prior run.

### Work steps
1. Re-audit post-Step-4 failures and select one additional focused adjustment.
2. Repeat clean cycle: reset -> extract -> full review.
3. Report before/after deltas:
   - approval ratio delta,
   - top failure bucket delta,
   - any unchanged blocker categories.

### Deliverable
- Documented second-pass outcome with precise delta and blocker clarity.

### Exit criteria
- TODO item `If still below target, run one additional tighten-and-retry cycle...` checked.

## 6) Downstream smoke chain after acceptance target is met

### Objective
Confirm M4/M5 paths still pass on the accepted dataset and produce fresh artifacts.

### Command sequence
1. `uv run python -m src.ranking.run --population human --algorithm bradley_terry`
2. `uv run python -m src.ai_user.run --pairs 200 --model heuristic_v1`
3. `uv run python -m src.ranking.run --population ai --algorithm bradley_terry`
4. `uv run python -m src.analysis.compare --human-run <id> --ai-run <id>`

### Verification
- Capture run/session IDs.
- Confirm fresh files in `outputs/`.
- Verify required metrics/disagreement sections exist.

### Exit criteria
- TODO item `After acceptance target is met, rerun smoke chain...` checked with IDs and output paths.

## Order of execution

1. Artifact audit and failure quantification.
2. One focused ingestion improvement + tests.
3. Salvage-first review workflow adjustment.
4. Clean rebuild cycle and ratio recomputation.
5. Optional one additional tighten-and-retry cycle.
6. Downstream smoke chain and TODO evidence closeout.

## Definition of done for this plan

- Acceptance gate reached (`>=95%` approved cards) with reproducible command evidence.
- If not reached after allowed retry cycle, quantified blocker report clearly identifies why.
- TODO file updated with timestamps, ratios, run IDs, and artifact paths as canonical audit trail.
