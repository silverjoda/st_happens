initial_implementation

# Implementation plan: next pending todo items (M3 only)

## Scope (tight, next unchecked items only)

This plan covers only the next pending tasks in `todos/initial_implementation.md`:

1. M3: Implement Bradley-Terry fitting in ranking core with deterministic seed behavior.
2. M3: Wire Bradley-Terry outputs into existing normalization + persistence path.
3. M3: Add synthetic known-order test for Bradley-Terry recovery.
4. M3: Add seed stability test (same seed and input -> same ordering).
5. M3: Run targeted ranking tests, then full `uv run pytest -q`.

Out of scope: M4 AI voter, M5 analysis reporting, and remaining smoke checks unrelated to these M3 items.

## Spec + prompt alignment

- FR-5 and Section 12: Bradley-Terry must consume pairwise choices where selected card is treated as worse, then normalize to `[1, 100]`.
- NFR reproducibility/transparency: deterministic seed handling and metadata persisted in `ranking_runs.config_json`.
- Initial prompt constraints: pragmatic first pass, maintainable structure, no extra abstractions beyond current ranking flow.

## Detailed implementation plan

## 1) Bradley-Terry fitting with deterministic seed behavior

### Goal
Implement a production-usable Bradley-Terry fit path that is deterministic for fixed input and seed.

### Work items
1. Reuse current approved-card universe + filtered comparison loader as ranking input; avoid duplicate data-loading paths.
2. Construct the pairwise outcome matrix/signals so `chosen_card_id` is interpreted as the "worse" winner.
3. Ensure every approved card receives a latent score, including cards with sparse comparisons.
4. Add deterministic initialization controlled by seed (for any stochastic step); if solver is inherently deterministic, still record effective seed in metadata for auditability.
5. Return fit diagnostics needed for traceability (e.g., iterations, convergence flag, or fallback token) to include in `config_json`.

### Edge handling
- If comparisons are insufficient/degenerate, raise existing stable error tokens instead of silently degrading.
- Keep behavior consistent with Elo path for invalid-input handling semantics.

## 2) Integrate Bradley-Terry output into persistence path

### Goal
Use the existing normalization and DB-write pipeline so Bradley-Terry behaves like Elo operationally.

### Work items
1. Plug Bradley-Terry raw score map into current normalization utility (no algorithm-specific normalization fork).
2. Persist one `ranking_runs` row with:
   - `population = human|ai|combined`
   - `algorithm = bradley_terry`
   - `config_json` including seed + fit diagnostics.
3. Persist one `ranking_results` row per approved card with raw and unrounded normalized score.
4. Keep rank ordering stable with deterministic tie-break rules already used in ranking persistence.
5. Confirm CLI output/reporting mirrors existing Elo run summary format for consistency.

## 3) Bradley-Terry synthetic-order recovery test

### Goal
Prove Bradley-Terry recovers a known ordering on controlled synthetic data.

### Work items
1. Add a compact fixture (3-6 cards) with explicit comparison outcomes encoding a strict severity order.
2. Run ranking via the real ranking entrypoint or service used by CLI (avoid testing private internals only).
3. Assert recovered ordering matches expected ranking direction for all cards.
4. Assert normalized scores are within `[1, 100]` and ranking rows count equals approved-card count.

## 4) Seed stability sanity test

### Goal
Verify reproducibility: same input + same seed gives same result.

### Work items
1. Execute Bradley-Terry twice on identical fixture data with same seed.
2. Assert identical ordering and stable score output (exact match or tight tolerance if float solver noise exists).
3. Optionally verify different seed behavior only if implementation is seed-sensitive; otherwise assert seed is ignored deterministically and documented.

## 5) Verification and completion pass

### Commands
- `uv run pytest tests -k ranking -q`
- `uv run pytest -q`

### Completion criteria for this plan
- Bradley-Terry path is implemented and wired through the existing ranking persistence workflow.
- New Bradley-Terry synthetic-order + seed-stability tests pass.
- Full test suite passes, or failures are isolated and documented with clear follow-up actions.
