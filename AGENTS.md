# AGENTS.md

Operational guide for coding agents working in this repository.

## Scope

- Applies to the entire repo rooted at `st_happens/`.
- Stack is Python 3.11+, managed via `uv` and `pyproject.toml`.
- Current implementation is early-stage; prioritize pragmatic, incremental changes.

## Package management

- This project uses `uv` as the Python package/dependency and environment management tool.
- Use `uv sync` (or `uv sync --dev`) to install dependencies from `pyproject.toml`.
- Use `uv run ...` to execute project commands in the managed environment.

## Source of truth

- Product and technical requirements: `SPEC.md`.
- Dependency and tool config: `pyproject.toml`.
- Main code under `src/`.
- Tests under `tests/`.
- When the user provides a spec correction, addition, or amendment during work,
  record that change in `SPEC.md` as part of the task.

## Cursor and Copilot rules

- No `.cursorrules` file was found.
- No `.cursor/rules/` directory was found.
- No `.github/copilot-instructions.md` file was found.
- If any of these are added later, treat them as higher-priority local instructions.

## Environment setup commands

- Sync runtime + dev dependencies:
  - `uv sync --dev`
- If `--dev` is unsupported in your `uv` version, use:
  - `uv sync`

## Build commands

- Build package artifacts from `pyproject.toml`:
  - `uv build`
- Alternative build path (if needed):
  - `uv run python -m build`

## Lint and format commands

- Lint entire repo:
  - `uv run ruff check .`
- Auto-fix lint issues where safe:
  - `uv run ruff check . --fix`
- Format code:
  - `uv run ruff format .`

## Test commands

- Run all tests:
  - `uv run pytest`
- Run tests with concise output:
  - `uv run pytest -q`
- Run a single test file:
  - `uv run pytest tests/test_ingest_m1_validation.py`
- Run one test function (most important single-test pattern):
  - `uv run pytest tests/test_ingest_m1_validation.py::test_missing_increment_detection_behavior -q`
- Run tests matching an expression:
  - `uv run pytest -k session -q`
- Stop after first failure:
  - `uv run pytest -x`

## App and CLI commands

- Start FastAPI app:
  - `uv run python -m src.app.main`
- Run ingestion extraction:
  - `uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed`
- Run manual ingestion review:
  - `uv run python -m src.ingest.review`

## Working conventions

- Run commands from repo root.
- Prefer `uv run ...` for Python entrypoints and tooling.
- Use `pathlib.Path` for filesystem paths.
- Resolve relative paths against project root when needed.

## Python style baseline

- Target version: Python 3.11.
- Line length: 100 (configured in Ruff).
- Use `from __future__ import annotations` in modules (current convention).
- Add concise module docstrings at top of files.
- Keep functions focused and composable.

## Imports

- Group imports in this order:
  1) standard library
  2) third-party libraries
  3) local `src.*` imports
- Separate groups with one blank line.
- Prefer explicit imports over wildcard imports.

## Types and signatures

- Use type hints on all public function signatures.
- Use modern built-in generics (`list[str]`, `dict[str, object]`).
- Return explicit `None`-aware unions where applicable.
- Use dataclasses with `slots=True` for lightweight structured records.
- Keep internal helper return types explicit when non-trivial.

## Naming conventions

- Modules and functions: `snake_case`.
- Classes: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Private helpers: leading underscore (e.g., `_resolve_path`).
- Test functions: `test_<behavior>`.

## Error handling conventions

- Raise precise exceptions for invalid states.
- Use stable machine-readable error tokens for programmatic cases when useful
  (examples in code: `"no_approved_cards"`, `"card_not_found"`).
- For CLI fatal input issues, use `SystemExit` with a clear message.
- Handle optional dependency failures gracefully (e.g., OCR fallback adapter).
- Do not silently swallow exceptions unless there is a clear fallback path.

## Database and persistence patterns

- Use `session_scope()` for transactional DB work.
- Keep writes inside the context manager and rely on commit/rollback behavior.
- Call `session.flush()` when IDs are needed before commit.
- Keep model constraints aligned with `SPEC.md` requirements.

## FastAPI patterns

- Keep route handlers thin; extract validation/normalization into helpers.
- Return deterministic status codes (`303` redirects are used in session flow).
- Validate form input and re-render templates with explicit error messages.

## Testing patterns

- Use `pytest`.
- Use `tmp_path` for isolated filesystem/database cases.
- Use `monkeypatch` for env vars such as `SHIP_HAPPENS_DB_URL`.
- Keep tests deterministic and independent.
- Prefer behavior assertions over implementation-detail assertions.

## Data and outputs

- Runtime DB default is under `data/ship_happens.db` unless overridden by env.
- Processed ingestion artifacts go to `data/processed/`.
- Analysis/report outputs go to `outputs/`.
- Treat `outputs/ocr_test_claude_results.json` as a locked manual-correction baseline; its description and score fields are authoritative and must not be edited.
- Use UTF-8 when writing text/json artifacts.

## Change management for agents

- Make minimal, scoped edits tied to the requested task.
- Preserve existing conventions before introducing new abstractions.
- Update tests when behavior changes.
- Run lint and targeted tests before finalizing substantial changes.

## Quick pre-PR checklist

- `uv run ruff check .`
- `uv run ruff format .`
- `uv run pytest -q`
- If only one area changed, also run the most relevant single test directly.

## If unsure

- Default to `SPEC.md` for product behavior.
- Default to existing nearby code patterns for implementation style.
- Choose the simplest design that satisfies current milestone requirements.
