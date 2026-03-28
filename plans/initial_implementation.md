initial_implementation

# Implementation plan: next pending todo items (M2/M3 stabilization)

## Scope (tight to immediate unchecked items)

This plan covers only the next pending items listed in `todos/initial_implementation.md` under "Current actionable next tasks (ordered)" and matching unchecked M2/M3 stabilization tasks:

1. M2: fix FastAPI/Jinja template rendering compatibility regression.
2. M2: eliminate detached-instance usage in pair-selection/session routes.
3. M2: get `tests/test_app_sessions_m2.py` fully green.
4. M3: fix Bradley-Terry convergence and deterministic behavior on synthetic fixture.
5. M3: ensure ranking result access paths are detached-safe in tests/runtime flow.
6. M3: get `tests/test_ranking_m3.py` fully green.
7. Run full `uv run pytest -q` to confirm no cross-area regressions.

Out of scope: M4 AI voter, M5 analysis reporting, and non-blocking smoke commands.

## Spec + prompt alignment

- FR-2 + App validation requirements: session start, pair presentation, vote persistence, and completion behavior must work reliably through route-level tests.
- FR-5 + Section 12 + Ranking validation requirements: Bradley-Terry must fit pairwise worse-choice events, normalize outputs to `[1, 100]`, and be reproducible with seed support.
- NFR reproducibility/transparency: keep strategy/seed and ranking diagnostics persisted for auditability.
- Prompt guidance: first-iteration pragmatism; minimal targeted fixes instead of broader refactors.

## Detailed implementation plan

## 1) M2 regression triage and compatibility fixes

### Goal
Resolve current M2 failures without changing product behavior or route contracts.

### Files in focus
- `src/app/main.py`
- `src/app/pairing.py`
- `tests/test_app_sessions_m2.py`

### Work items
1. Reproduce failing M2 tests (`uv run pytest tests/test_app_sessions_m2.py -q`) and group failures into two buckets already identified in todos: `TemplateResponse` TypeError and detached-instance access.
2. Standardize template rendering calls in `src/app/main.py` to the Starlette/Jinja API shape expected by the pinned dependency version (consistent argument ordering and context object shape across all routes/helpers).
3. Keep response semantics unchanged: status codes, redirects, and template names remain stable so existing tests stay valid.
4. Add/adjust only minimal assertions in M2 tests if required for dependency-version-compatible behavior (avoid rewriting test intent).

### Definition of done for this step
- No `TemplateResponse` cache-key/unhashable-dict errors in M2 test run.

## 2) M2 detached-instance safety in pair flow

### Goal
Ensure route handlers do not rely on ORM attributes after their session context is closed.

### Files in focus
- `src/app/pairing.py`
- `src/app/main.py`

### Work items
1. Audit return types from pair-selection helpers to identify ORM instances crossing session boundaries.
2. Convert pair payloads to detached-safe structures before leaving DB scope (e.g., primitive IDs/fields or lightweight dataclass snapshots).
3. Update consuming route code to use detached-safe payloads while keeping rendered data unchanged (description/image references only, no official score exposure).
4. Preserve pair constraints from FR-2 and existing tests: no self-pairs, no immediate duplicate pair keys, approved cards only.

### Definition of done for this step
- No `DetachedInstanceError` in pair-selection tests or route execution paths.

## 3) M2 verification loop

### Commands
- `uv run pytest tests/test_app_sessions_m2.py -q`

### Exit criteria
- All tests in `tests/test_app_sessions_m2.py` pass.
- Session lifecycle behavior remains compliant (create -> pair -> vote -> complete).

## 4) M3 Bradley-Terry convergence + reproducibility fixes

### Goal
Make Bradley-Terry pass synthetic-order and same-seed stability tests while preserving existing data-loading/persistence design.

### Files in focus
- `src/ranking/bradley_terry.py`
- `src/ranking/service.py`
- `src/ranking/run.py`
- `tests/test_ranking_m3.py`

### Work items
1. Reproduce M3 failures (`uv run pytest tests/test_ranking_m3.py -q`) and confirm current failure mode (`bradley_terry_convergence_failed` and/or order mismatch).
2. Correct outcome-matrix/event interpretation logic so each comparison consistently models "chosen card is worse" across left/right orientation.
3. Improve numerical stability/convergence behavior for sparse small synthetic sets (bounded initialization, safe updates, deterministic scaling/normalization each iteration).
4. Keep deterministic same-seed behavior explicit and persisted in `config_json` metadata (`seed`, convergence status, iterations, tolerance/max-iterations).
5. Preserve existing invalid-state tokens (`no_approved_cards`, `insufficient_comparisons`, convergence token) and only change them if tests/spec require.

### Definition of done for this step
- Bradley-Terry synthetic fixture recovers expected order and reports `converged = true` in run metadata.
- Same-seed repeated runs produce stable ordering and numerically equivalent scores (within test tolerance).

## 5) M3 detached-safe access and persistence sanity

### Goal
Ensure ranking outputs are accessed in a session-safe way and persisted exactly once per run/card universe.

### Files in focus
- `src/ranking/service.py`
- `tests/test_ranking_m3.py`

### Work items
1. Review any helper that returns ORM rows outside active session contexts; switch to detached-safe data where needed.
2. Confirm persisted row counts and bounds remain correct for both algorithms:
   - one `ranking_runs` row per invocation,
   - one `ranking_results` row per approved card,
   - normalized score range `[1.0, 100.0]`.
3. Keep tie/order determinism consistent across repeated runs on fixed input.

### Definition of done for this step
- No detached-instance failures in ranking tests.
- Persistence/count/bound assertions continue passing.

## 6) Final verification and checklist updates

### Commands
- `uv run pytest tests/test_ranking_m3.py -q`
- `uv run pytest -q`

### Completion criteria
- M2 and M3 targeted suites are green.
- Full test suite is green, or any remaining failure is outside this slice and documented with explicit follow-up todo.
- Update `todos/initial_implementation.md` statuses for completed M2/M3 stabilization items immediately after verification.
