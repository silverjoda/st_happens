initial_implementation

# Implementation plan: next pending todo items (M5 comparative analysis)

## Scope (tight to immediate pending work)

This plan targets the next unchecked items in `todos/initial_implementation.md`, centered on M5 only:

1. Create `src/analysis/compare.py` CLI with `--human-run` and `--ai-run` validation.
2. Load ranking runs and align them to approved cards + official scores.
3. Compute required metrics (Spearman, Kendall tau, MAD on normalized 1-100).
4. Generate top-disagreement lists for official vs human and official vs AI.
5. Write machine-readable and readable report artifacts to `outputs/`.
6. Add focused tests for metric correctness and output artifact shape/path.

Out of scope for this pass: app/ingest smoke commands and broad non-M5 refactors.

## Spec + prompt alignment

- FR-7 requires official vs human vs AI comparison outputs with Spearman, Kendall tau, MAD, and disagreement cards.
- FR-5/Section 12 require normalized 1-100 comparisons; preserve precision and avoid accidental re-scaling mismatches.
- FR-4/NFR transparency require run-linked, reproducible artifacts with explicit metadata.
- Section 11 command surface requires `uv run python -m src.analysis.compare --human-run <id> --ai-run <id>`.
- Prompt guidance favors pragmatic, maintainable first-iteration design: minimal moving parts, clear helpers, deterministic outputs.

## Detailed implementation plan

## 1) Scaffold compare CLI and input validation

### Goal
Add a reliable analysis entrypoint that fails fast on invalid run references or population mismatches.

### Files in focus
- `src/analysis/compare.py` (new)
- `src/analysis/__init__.py` (only if export wiring is needed)

### Work items
1. Implement `argparse` with required `--human-run` and `--ai-run` integer arguments.
2. Add optional output controls only if already consistent with repository patterns (e.g., output dir defaulting to `outputs/`).
3. Validate run existence from `ranking_runs` and assert population compatibility (`human` for `--human-run`, `ai` for `--ai-run`).
4. Surface clear `SystemExit` messages for bad IDs, wrong populations, or missing ranking results.
5. Reuse existing runtime bootstrap utilities (`ensure_runtime_directories()`, schema init) rather than introducing new startup pathways.

### Definition of done
- `uv run python -m src.analysis.compare --help` exposes expected CLI surface.
- Invalid run inputs fail with deterministic, actionable messages.

## 2) Implement data-loading and alignment helpers

### Goal
Build one canonical in-memory comparison table keyed by card, containing official, human, and AI normalized values.

### Files in focus
- `src/analysis/compare.py`
- Existing DB models/helpers under `src/common/` (reuse only)

### Work items
1. Load approved cards (`cards.status = approved`) with `official_score` and `description_text`.
2. Load ranking results for the selected human and AI run IDs.
3. Join by `card_id` and enforce intersection semantics so each compared card has all required values.
4. Add explicit alignment checks and warnings/errors for:
   - cards missing in either ranking run,
   - non-approved cards leaking into ranking outputs,
   - empty overlap set.
5. Normalize representation in a typed internal structure (dataclass/dict rows) to keep metric and report generation simple.

### Definition of done
- A single aligned dataset is produced deterministically from the two run IDs.
- Fail-fast behavior is in place for unusable or inconsistent input data.

## 3) Implement required metrics and disagreement extraction

### Goal
Compute all FR-7 metrics from aligned data with predictable formulas and edge-case handling.

### Files in focus
- `src/analysis/compare.py`
- `pyproject.toml` (only if a missing statistical dependency must be added)

### Work items
1. Compute Spearman rank correlation for:
   - official vs human,
   - official vs AI,
   - human vs AI (supporting metric, useful for interpretation).
2. Compute Kendall tau for the same pairs.
3. Compute mean absolute difference on normalized 1-100 scores for official vs human and official vs AI.
4. Extract top disagreement cards by absolute score delta (and optionally rank delta as tie-breaker), separately for official-human and official-AI.
5. Handle small-sample/tie edge cases gracefully (return `None` or `nan` with explicit serialization policy).

### Definition of done
- Metric outputs match expected values on deterministic test fixtures.
- Disagreement lists are stable in ordering under ties.

## 4) Generate report artifacts under outputs/

### Goal
Emit one machine-readable artifact plus one readable summary, both traceable to the selected run IDs.

### Files in focus
- `src/analysis/compare.py`
- `outputs/` (runtime artifacts)

### Work items
1. Write JSON artifact containing:
   - run metadata (`human_run_id`, `ai_run_id`, timestamps),
   - card count used,
   - metric values,
   - top-disagreement card payloads.
2. Write a companion readable text/markdown summary with the same headline metrics and top disagreements.
3. Use deterministic filenames including run IDs (example: `comparison_h{human}_a{ai}.json` and `.md`).
4. Ensure directories exist and paths are printed to stdout for operator visibility.

### Definition of done
- Two artifacts are produced in `outputs/` for each successful run.
- Artifacts are easy to diff and replay across reruns.

## 5) Add focused tests for M5 behavior

### Goal
Cover core correctness and output contract without broad suite churn.

### Files in focus
- `tests/test_analysis_compare_m5.py` (new)
- Existing fixtures/helpers reused from current test suite

### Test cases
1. CLI rejects nonexistent run IDs and population mismatches.
2. Alignment helper excludes non-approved/missing cards and errors on empty overlap.
3. Metric helper returns expected Spearman/Kendall/MAD values on a known synthetic dataset.
4. Disagreement extraction returns deterministic top-N ordering.
5. Successful CLI execution writes both JSON and readable summary files to expected `outputs/` paths and includes required keys/fields.

### Definition of done
- `uv run pytest tests/test_analysis_compare_m5.py -q` passes.
- `uv run pytest -q` remains green after M5 changes.

## 6) Execution order and completion checklist

1. Implement CLI scaffold + validation.
2. Implement aligned data loading helpers.
3. Implement metrics + disagreement helpers.
4. Implement artifact writers.
5. Add M5 tests and fix any regressions.
6. Run full test suite and update `todos/initial_implementation.md` to mark completed M5 items.

Completion criteria for this plan:

- All unchecked M5 implementation items in `todos/initial_implementation.md` are done.
- Tests covering M5 pass locally.
- Project is ready for final smoke checks listed in todo file.
