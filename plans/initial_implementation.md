initial_implementation

# Implementation plan: next pending M2 app foundation tasks

## Scope (tight to next unchecked todo slice)

This plan targets the immediate pending items in `todos/initial_implementation.md` under **Immediate next task slice (M2)**:

1. Create `src/app/main.py` with FastAPI app initialization and local run entrypoint.
2. Add template wiring and base page layout for the voting flow.
3. Add session start page route + form (nickname optional, pair count input).
4. Add POST handler to create `sessions` rows for `actor_type = human`.
5. Add route tests for session start/create basics.

Out of scope for this slice: pair generation logic, voting route, comparison persistence, ranking, AI voter, and analysis.

## Alignment constraints from SPEC + prompt

- Follow approved stack: Python 3.11+, FastAPI templates, SQLite via SQLAlchemy, `uv run` commands.
- Keep first iteration pragmatic: clean structure, minimal complexity, no unnecessary hardening.
- Match FR-2 session behavior now (anonymous or nickname, configurable pair count, persistent session records).
- Preserve auditability (persist `pair_target_count`, timestamps, and actor type consistently).
- Keep architecture modular so M2 pair flow can plug in without rework.

## Work plan

## 1) FastAPI app entrypoint (`src/app/main.py`)

### Deliverables
- App factory or module-level `FastAPI` instance.
- Local run entrypoint compatible with `uv run python -m src.app.main`.
- Basic router registration for start/create session endpoints.

### Steps
1. Create `src/app/main.py` with `FastAPI(...)` app metadata (`title`, version placeholder).
2. Wire Jinja2 template directory (`src/app/templates` or existing project convention).
3. Add root route redirect to session start route (or render start directly).
4. Add `if __name__ == "__main__"` block using `uvicorn.run("src.app.main:app", ...)` for local development.

### Acceptance checks
- `uv run python -m src.app.main` starts server without import/runtime errors.
- `GET /` reaches session start UX path.

## 2) Template wiring and base voting layout

### Deliverables
- Shared base template (minimal but reusable for upcoming pair UI).
- Session start template extending base.

### Steps
1. Add `base.html` with app title, content block, and area for validation/error messages.
2. Add `session_start.html` with:
   - optional `nickname` field,
   - `pair_target_count` numeric input,
   - submit action to session creation endpoint.
3. Keep layout intentionally simple and maintainable; avoid speculative components not needed by current todo items.

### Acceptance checks
- Template renders without missing-block or path errors.
- Form fields map exactly to backend handler payload keys.

## 3) Session start GET route + form behavior

### Deliverables
- Route that displays start form with sensible default pair count.

### Steps
1. Add `GET /sessions/start` (or equivalent) returning template response.
2. Provide default value from config constant (e.g., `DEFAULT_PAIR_TARGET = 20`, aligned with SPEC example).
3. Add simple server-side rendering for field-level errors when submission is invalid.

### Acceptance checks
- Route returns `200` and includes required fields.
- Default pair count is visible on first load.

## 4) Session creation POST route (human actor)

### Deliverables
- Route to insert `sessions` row with `actor_type = human`, optional nickname, selected pair target.
- Redirect after create (to next step placeholder route or confirmation page).

### Steps
1. Add POST endpoint (e.g., `POST /sessions`).
2. Parse/validate input:
   - nickname: optional, trim whitespace, store `NULL` when empty,
   - pair target: integer, positive, bounded by practical max (small guardrail for local UX).
3. Persist session with required fields from data model: `actor_type`, `nickname`, `pair_target_count`, `started_at`.
4. Commit transaction and return redirect response.
5. On validation failure, re-render start form with error message and previous values.

### Acceptance checks
- Valid POST creates one `sessions` record with expected values.
- Invalid POST does not create a row and returns form with clear error.

## 5) Route tests for session start/create

### Deliverables
- Test module covering happy path and basic validation.

### Steps
1. Add tests using FastAPI `TestClient` and test database/session fixture.
2. Test `GET` start route returns `200` and contains form controls.
3. Test valid `POST`:
   - returns redirect status,
   - persists session row,
   - stores `actor_type = human` and expected `pair_target_count`.
4. Test invalid `POST` (non-integer/negative/out-of-range count) returns `200` form with error and no DB insert.
5. Test empty nickname persists as `NULL` and non-empty nickname is trimmed.

### Acceptance checks
- `uv run pytest` passes new route tests.
- Tests are deterministic and independent of existing local DB state.

## Execution order

1. Build `src/app/main.py` and template environment wiring.
2. Create base + session start templates.
3. Implement `GET` session start route.
4. Implement `POST` session creation + validation + redirect.
5. Add route tests and run targeted pytest.

## Verification commands

- `uv run python -m src.app.main`
- `uv run pytest -k "session and app"` (or the specific new test module path)

## Done definition for this planning slice

This slice is complete when a user can open the FastAPI app, start a human session via form submission, and have the session stored in SQLite with validated `pair_target_count`; route tests confirm GET/POST behavior and basic input handling.
