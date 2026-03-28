initial_implementation

# Implementation plan: next pending todo items (M4 AI voter integration)

## Scope (tight to immediate unchecked items)

This plan covers the next pending items in `todos/initial_implementation.md`, limited to M4 and its immediate queue entries:

1. Create `src/ai_user/run.py` runner for description-only pair voting.
2. Persist AI sessions/comparisons with `sessions.actor_type = ai`.
3. Persist AI run configuration metadata (`model`, `prompt_style`, `temperature`, `seed`).
4. Add focused tests for persistence and actor separation.

Out of scope: M5 analysis CLI/reporting and post-M4 smoke-command checklist items.

## Spec + prompt alignment

- FR-6: AI voter runs as a separate actor, consumes description-only text, and writes results as AI sessions.
- FR-3 + NFR reproducibility: pair strategy and deterministic seed must be logged and replayable.
- FR-4 auditability: persisted records must tie AI-generated comparisons to run/session metadata.
- Section 11 command surface: support `uv run python -m src.ai_user.run --pairs <n> --model <model_name>`.
- Prompt guidance: first-iteration pragmatic implementation, minimal abstraction, maintainable structure.

## Detailed implementation plan

## 1) Define M4 runner contract and CLI surface

### Goal
Add a runnable AI-voter entrypoint with stable arguments and explicit defaults.

### Files in focus
- `src/ai_user/run.py` (new)
- `src/ai_user/__init__.py` (minimal export if needed)

### Work items
1. Implement `argparse` CLI with required `--pairs` and `--model`, plus `--temperature` (default `0.0`) and optional `--seed`.
2. Validate inputs (`pairs >= 1`, non-empty model string, non-negative temperature) and use stable `SystemExit` error messages for invalid input.
3. Bootstrap runtime with `ensure_runtime_directories()` and `create_schema()` to match existing CLI patterns.
4. Emit a concise completion line containing session/run identifiers for operator visibility.

### Definition of done
- `python -m src.ai_user.run --help` shows expected options.
- Runner exits cleanly with actionable error tokens/messages for bad args.

## 2) Build deterministic pair selection + AI vote loop

### Goal
Generate exactly `N` pairwise AI choices using approved cards and description-only prompts.

### Files in focus
- `src/ai_user/run.py`
- `src/app/pairing.py` (reuse existing deterministic pair logic, no behavior change)

### Work items
1. Start one `SessionRecord` with `actor_type="ai"`, `pair_target_count=<pairs>`, and deterministic nickname/tag for traceability.
2. For each `presented_order in 1..N`, call existing pair-selection logic (seeded by session/presented order) so constraints remain consistent:
   - approved cards only,
   - no self-pairs,
   - no immediate duplicate pair.
3. Construct description-only comparison prompt payload from `Card.description_text`; do not include image paths or official scores.
4. Implement a simple, deterministic AI decision adapter for v1 scaffold (placeholder heuristic or stubbed chooser) with clear seam for future model-provider integration.
5. Persist each vote as `Comparison(session_id, left_card_id, right_card_id, chosen_card_id, presented_order, response_ms=None)`.
6. Mark `ended_at` when loop completes or when early-stop conditions occur (e.g., not enough approved cards).

### Definition of done
- Exactly `N` comparisons are stored for a successful run.
- Stored votes reference only cards in each presented pair.
- Selection/vote flow is reproducible under fixed seed/session context.

## 3) Persist AI run configuration metadata for auditability

### Goal
Store AI-run config in durable DB metadata linked to generated votes.

### Files in focus
- `src/ai_user/run.py`
- `src/common/models.py` (only if schema extension is required)

### Work items
1. Persist run metadata as JSON containing at least: `model`, `prompt_style`, `temperature`, `seed`, `pair_count`, selection strategy identifier, and timestamps.
2. Prefer a minimal, non-breaking storage path first (e.g., existing `ranking_runs.config_json` with algorithm-style marker) if no dedicated AI-run table exists yet.
3. If schema change is required for clarity, add the smallest additive table/column and keep migration/bootstrap behavior compatible with `create_schema()`.
4. Include session linkage (`session_id`) in stored metadata so every AI run can be traced to its comparisons.

### Definition of done
- Queryable persisted metadata exists for each AI run and includes all required config fields.
- Metadata/session linkage is deterministic and stable across reruns.

## 4) Add focused M4 tests (persistence + actor separation)

### Goal
Prove M4 behavior without broad test churn.

### Files in focus
- `tests/test_ai_user_m4.py` (new)
- Existing test helpers/fixtures (reuse patterns from M2/M3 tests)

### Test cases
1. Runner creates one AI session with `actor_type="ai"`, correct target count, and `ended_at` set after completion.
2. Runner stores exactly `pairs` comparisons tied to that AI session.
3. All stored comparisons have valid chosen-card membership in `{left_card_id, right_card_id}`.
4. Persisted AI config metadata includes `model`, `prompt_style`, `temperature`, and `seed`.
5. Actor separation check: human-only ranking input excludes AI comparisons; AI-only ranking input excludes human comparisons (`load_comparisons_for_population`).

### Definition of done
- `uv run pytest tests/test_ai_user_m4.py -q` passes.
- Existing ranking tests still pass for population filtering behavior.

## 5) Verification and todo synchronization

### Commands
- `uv run pytest tests/test_ai_user_m4.py -q`
- `uv run pytest tests/test_ranking_m3.py -q`
- `uv run pytest -q`

### Completion criteria
- New M4 tests are green.
- Full suite remains green (or any unrelated failures are explicitly documented).
- Update `todos/initial_implementation.md` to mark completed M4 items and promote next M5 task.
