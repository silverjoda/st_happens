initial_implementation

# Implementation plan: next pending M2 voting-flow items

## Scope (next pending todo items only)

This plan covers the next unchecked items in `todos/initial_implementation.md` under **M2 - Voting flow completion**:

1. Add pair selection service module with approved-card loading, warm-up random sampling, and reproducibility logging.
2. Enforce pair constraints (no self-pairs, no immediate duplicate repeats).
3. Add GET route to render the current pair (description + image only, no official score).
4. Add POST vote route persisting `comparisons` fields (`left_card_id`, `right_card_id`, `chosen_card_id`, `presented_order`, `response_ms`).
5. Implement session progression and completion (`ended_at`, stop at `pair_target_count`).
6. Add completion page/template and redirect after final vote.
7. Add/extend tests for pair constraints, vote persistence, and completion behavior.

Out of scope for this slice: ranking (M3), AI voter (M4), analysis (M5), and broad UI polish unrelated to pair-voting flow.

## Alignment with SPEC and prompt

- FR-2: session-based pairwise voting, configurable count, record each choice, hide official ranking in voting UI.
- FR-3: warm-up random sampling and deterministic behavior via logged seed/strategy.
- FR-4: durable persistence and auditability for sessions/comparisons.
- Prompt constraint: pragmatic first implementation, maintainable structure, avoid overengineering.

## Implementation plan

## 1) Pairing service module (`src/app/pairing.py`)

### Deliverables
- A focused service that returns the next valid pair for a session.
- Strategy metadata (`mode`, `seed`) captured in a reproducible way.

### Tasks
1. Create a `PairSelector` (or equivalent pure functions) that takes session ID, DB session, and RNG seed.
2. Query only cards eligible for voting (`status = approved`) and fail with a clear app error if fewer than 2 cards exist.
3. Implement warm-up mode as random sampling from approved cards for early orders.
4. Seed RNG deterministically (session-derived seed or persisted seed) and keep seed stable across requests.
5. Return a pair payload with card IDs and display fields needed by templates (description text and image path only).

### Notes
- Keep the interface narrow so adaptive/uncertainty mode can be added later without route rewrites.
- Persist strategy/seed using existing metadata surface if available; otherwise add minimal session-linked metadata storage in app scope.

## 2) Pair constraints and validation rules

### Deliverables
- Guards for no self-pairs and no immediate duplicate pair repeats.

### Tasks
1. Add canonical pair-key normalization (`min_id:max_id`) to compare pairs independent of left/right order.
2. Ensure candidate generation always uses distinct card IDs.
3. Read last presented pair for the session from `comparisons` and exclude that pair-key for the next selection.
4. Add retry loop with bounded attempts; if exhausted, return a deterministic fallback or a clear completion/blocked state.

## 3) Voting routes in `src/app/main.py`

### GET route: present current pair
1. Add route like `GET /sessions/{session_id}/pair`.
2. Validate session exists, `actor_type = human`, and not already completed.
3. Compute `presented_order = current_comparison_count + 1`.
4. If target already reached, redirect to completion route.
5. Render pair template showing only description and image (no `official_score`).

### POST route: submit vote
1. Add route like `POST /sessions/{session_id}/vote`.
2. Validate posted `chosen_card_id` belongs to current left/right card IDs.
3. Parse `response_ms` as nullable int (allow empty/missing).
4. Insert `comparisons` row with required fields and computed `presented_order`.
5. Commit and redirect to next pair or completion depending on count.

## 4) Session progression and completion

### Deliverables
- Reliable stop condition at `pair_target_count` with `sessions.ended_at` persisted.

### Tasks
1. After each vote, count comparisons for session and compare to `pair_target_count`.
2. On reaching target, set `ended_at` once and redirect to completion page.
3. Prevent additional vote writes for ended sessions (idempotent guard).
4. Ensure completion route is accessible for completed sessions and safe for refresh.

## 5) Templates for pair and completion

### Deliverables
- `pair.html` and `complete.html` integrated with existing base layout.

### Tasks
1. `pair.html`: render left/right cards with description + image and submit controls for selected card.
2. Include hidden values required for safe vote validation (`left_card_id`, `right_card_id`, `presented_order` if used).
3. Add optional client-side response-time capture (hidden `response_ms`) with server-side nullable fallback.
4. `complete.html`: show session completion state and compact summary (session ID, total votes recorded).

## 6) Tests (route + pairing behavior)

### Deliverables
- Deterministic tests covering all new M2 behavior in this slice.

### Test cases
1. Pair selection uses only approved cards.
2. Pair selection never returns identical card IDs.
3. Consecutive selections avoid immediate duplicate pair-key.
4. GET pair route redirects to completion when target met.
5. POST vote persists required comparison fields correctly.
6. Invalid chosen card submission is rejected and does not write a comparison.
7. Session sets `ended_at` exactly when final vote is recorded.

### Test data strategy
- Use `tmp_path` DB fixtures and small card sets (2-5 cards) for deterministic edge coverage.
- Seed RNG explicitly in tests to avoid flaky pair expectations.

## Execution order

1. Build `src/app/pairing.py` and unit-test core pair constraints first.
2. Add pair/completion templates and GET pair route.
3. Implement POST vote write path with validation.
4. Add session completion updates (`ended_at`) and redirects.
5. Finish route-level tests and run targeted then full app tests.

## Verification commands

- `uv run pytest tests -k "pair or session or vote" -q`
- `uv run pytest -q`
- `uv run python -m src.app.main`

## Done definition for this slice

This slice is done when a human session can repeatedly receive valid approved-card pairs, submit votes that persist complete comparison records, and automatically reach a completion page at `pair_target_count` with `sessions.ended_at` set; tests validate pair constraints, vote persistence, and completion behavior.
