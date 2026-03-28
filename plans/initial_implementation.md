initial_implementation

# Implementation plan: next pending todo items (manual approvals -> ranking/AI/analysis smoke)

## Scope

This plan is tightly scoped to the first unchecked items in `todos/initial_implementation.md`:

1. Complete manual review approvals until the dataset is usable (target: at least 95% approved).
2. Confirm ranking and AI-voter preconditions from approved-card counts and pairability.
3. Run blocked smoke checks (ranking human/ai, AI voter, analysis compare) and capture evidence.
4. Update TODO checkboxes and verification notes with concrete command results and artifact paths.

Out of scope: new feature work, schema changes, refactors, ranking algorithm changes, and test-suite expansion.

## Spec and prompt alignment

- FR-1a and acceptance criteria require a real manual review/approval pass and approved-card gating.
- FR-5/FR-6/FR-7 require successful ranking, AI voting, and comparison report generation.
- Section 11 required command surface is exercised directly via `uv run ...` commands.
- Prompt asks for pragmatic first-iteration delivery: finish blocked operational steps with minimal churn.

## Detailed implementation plan

## 1) Finish manual review approvals (primary blocker)

### Goal
Move cards from `extracted` into final review states (`approved`, `needs_fix`, `rejected`) so downstream ranking is unblocked.

### Work items
1. Run `uv run python -m src.ingest.review` in an interactive shell.
2. Iterate through all extracted cards and apply status decisions:
   - approve cards with correct description/score,
   - edit/fix OCR fields when recoverable,
   - reject unusable extracts.
3. Keep scoring consistent with SPEC constraints (numeric score, 0.5-increment compatible where applicable).
4. Complete pass until extracted queue is exhausted or approval target is reached.

### Done when
- At least 95% of cards are `approved` (project acceptance target), or a clear blocker is documented.
- TODO item `Complete manual review approvals...` is checked or annotated with exact blocker evidence.

## 2) Validate preconditions for ranking and AI voter

### Goal
Confirm there are enough approved cards and pair combinations to support ranking and AI voting commands.

### Work items
1. Verify approved-card count from current DB state (using existing project tooling/queries).
2. Confirm pairability is sufficient for requested AI run volume (`--pairs 200`) or choose a lower safe pair count for smoke if needed.
3. Record quantitative precondition evidence in verification notes.

### Done when
- TODO item `Verify approved-card precondition for ranking...` is checked.
- Precondition numbers are written in `todos/initial_implementation.md` verification notes.

## 3) Run ranking smoke commands and capture run IDs

### Goal
Generate valid ranking runs for both populations to unblock analysis.

### Commands
- `uv run python -m src.ranking.run --population human --algorithm bradley_terry`
- `uv run python -m src.ranking.run --population ai --algorithm bradley_terry`

### Work items
1. Execute both commands after approvals/precondition checks pass.
2. Record produced run IDs and key command outcome lines.
3. Update TODO ranking items and add run IDs to verification notes for reuse by compare command.

### Done when
- Human and AI ranking smoke TODO items are checked.
- Both run IDs are available and documented.

## 4) Run AI voter smoke with concrete model config

### Goal
Create an AI session/comparison batch that satisfies FR-6 actor separation and provides fresh comparison data.

### Command
- `uv run python -m src.ai_user.run --pairs 200 --model heuristic_v1`

### Work items
1. Execute with `heuristic_v1` (or reduce pair count only if precondition check requires it).
2. Record session ID and summary stats emitted by the runner.
3. Confirm data persisted under `actor_type = ai` behavior path.

### Done when
- AI voter smoke TODO item is checked.
- Session/run metadata is captured in verification notes.

## 5) Run comparative analysis smoke and verify output artifacts

### Goal
Produce required comparison outputs once valid human/AI run IDs exist.

### Command
- `uv run python -m src.analysis.compare --human-run <human_id> --ai-run <ai_id>`

### Work items
1. Execute compare command using latest recorded run IDs.
2. Verify artifacts are emitted to `outputs/`.
3. Confirm report content includes required metrics and disagreement lists.

### Done when
- Analysis smoke TODO item and output-verification TODO item are checked.
- Output file paths are captured in verification notes.

## 6) Closeout in TODO tracker

### Goal
Keep `todos/initial_implementation.md` as accurate source of truth after each step.

### Work items
1. Immediately check each completed task item.
2. Leave failed items unchecked and add timestamped failure/blocker note with exact error token/message.
3. Update `## Immediate next tasks` to the first still-pending actionable item.

### Done when
- Remaining unchecked items (if any) represent true blockers only.
- Evidence trail is sufficient to reproduce outcomes.

## Execution order

1. Complete full manual review/approval pass.
2. Confirm approved-card and pairability preconditions.
3. Run human ranking smoke and record run ID.
4. Run AI ranking smoke and record run ID.
5. Run AI voter smoke and record session metadata.
6. Run analysis compare smoke with latest run IDs.
7. Update TODO checkboxes and verification notes.

Completion criteria:

- Manual-review and precondition items are complete with quantitative evidence.
- Ranking, AI voter, and analysis smoke commands complete with valid IDs/artifacts.
- `outputs/` contains comparison artifacts with required metrics/disagreement sections.
