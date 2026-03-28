# Ship Happens - Product and Technical Specification

## 1) Purpose and Context

This project digitizes a physical "Ship Happens" card deck and builds a data-driven system to compare three severity rankings for the same situations:

1. Card author ranking (from the printed cards)
2. Human preference-derived ranking (from pairwise user choices)
3. AI preference-derived ranking (from pairwise AI choices)

The core question is: how closely do human and AI rankings align with the official deck ranking, and where do they differ?

## 2) Goals

- Digitize card data from raw photos into structured records (situation text + official score).
- Provide a UI where a user can complete a configurable number of pairwise comparisons per session.
- Persist all session and comparison data for reproducible analysis.
- Infer card ranking from pairwise preferences using principled ranking algorithms.
- Run a separate AI voter flow over card pairs and store its votes as a distinct actor population.
- Produce analysis artifacts comparing official vs human vs AI rankings.

## 3) Non-Goals (Initial Version)

- Multiplayer real-time synchronization.
- User authentication beyond anonymous or nickname-based sessions.
- Production cloud deployment and multi-tenant scaling.
- Perfect OCR without human correction.

## 4) Assumptions and Constraints

- Source data is in `data/raw_photos/` as smartphone photos.
- Card count is roughly ~200 cards (exact count discovered during ingestion).
- Official card scores are numeric and expected on a 1-100 style scale; 0.5 increments are possible and should be supported.
- OCR from photos will be noisy; manual correction pass is mandatory in workflow design.
- First implementation should prioritize local reproducibility and low operational complexity.

## 5) Technology Choices (Approved Defaults)

- Language: Python 3.11+
- Python/package management: `uv` + `pyproject.toml`
- API/UI backend: FastAPI with server-rendered templates
- Persistence: SQLite via SQLAlchemy
- Image processing: OpenCV
- OCR: Tesseract first, EasyOCR fallback if needed
- Ranking algorithms:
  - Primary: Bradley-Terry (pairwise preference native)
  - Baseline/secondary: Elo-style updates
- Analysis: Python scripts/notebooks with plots and ranking quality metrics

Rationale:
- This stack minimizes setup complexity while remaining robust and extensible.
- SQLite is sufficient for expected local volume and supports transparent auditing.
- `uv` keeps environment/dependency workflows fast and reproducible for local development.

## 6) High-Level System Architecture

1. Ingestion pipeline
   - Reads raw card photos
   - Detects/aligned card region
   - Extracts text fields (situation + official score)
   - Stores extracted results and confidence metadata
   - Supports manual review/edit and approval

2. Comparison session app
   - Starts session (anonymous or nickname)
   - Presents N card pairs sequentially (N configurable in UI)
   - Captures left/right choice and latency metadata
   - Persists each choice as one preference event

3. Ranking engine
   - Trains ranking model from accumulated preferences
   - Produces latent severities then normalizes to 1-100
   - Exports ranking table and run metadata

4. AI voter
   - Consumes card pairs as text descriptions
   - Chooses worse card for each pair
   - Saves votes with `actor_type = ai`

5. Analysis/reporting
   - Compares author, human, and AI rankings
   - Computes correlations and distance/error metrics
   - Outputs tables and plots to `outputs/`

## 7) Repository and Directory Conventions

### Existing and required runtime directories

- `prompts/ralph/` (required by `ralph_loop.sh` for prompt files)
- `todos/` (runtime todo tracking)
- `plans/` (runtime planning output)

### Project directories for implementation

- `pyproject.toml` - canonical project metadata and dependency specification
- `src/ingest/` - card detection, alignment, OCR, extraction logic
- `src/app/` - FastAPI app, routes, templates, session flow
- `src/ranking/` - Bradley-Terry and Elo ranking logic
- `src/analysis/` - comparison metrics and reports
- `src/ai_user/` - AI voter adapters and runners
- `data/processed/` - cleaned/extracted card dataset and review files
- `outputs/` - ranking outputs, charts, and analysis artifacts

## 8) Data Model (SQLite)

### cards
- `id` (PK)
- `source_image_path` (text)
- `description_text` (text)
- `official_score` (real)
- `ocr_confidence_desc` (real, nullable)
- `ocr_confidence_score` (real, nullable)
- `status` (enum/text: `extracted|reviewed|approved`)
- `created_at`, `updated_at`

### sessions
- `id` (PK)
- `actor_type` (enum/text: `human|ai`)
- `nickname` (text, nullable)
- `pair_target_count` (int)
- `started_at`, `ended_at`

### comparisons
- `id` (PK)
- `session_id` (FK -> sessions)
- `left_card_id` (FK -> cards)
- `right_card_id` (FK -> cards)
- `chosen_card_id` (FK -> cards)
- `presented_order` (int)
- `response_ms` (int, nullable)
- `created_at`

### ranking_runs
- `id` (PK)
- `population` (enum/text: `human|ai|combined`)
- `algorithm` (text: `bradley_terry|elo`)
- `config_json` (text/json)
- `created_at`

### ranking_results
- `id` (PK)
- `ranking_run_id` (FK -> ranking_runs)
- `card_id` (FK -> cards)
- `raw_score` (real)
- `normalized_score_1_100` (real)
- `rank_position` (int)

## 9) Functional Requirements

### FR-1: Card ingestion and digitization
- System scans all images in `data/raw_photos/`.
- For each image, system attempts card localization/alignment and text extraction.
- System extracts:
  - situation description (top region)
  - official numeric score (bottom region)
- System persists extraction result with confidence metadata.
- System provides manual review workflow to correct OCR output before approval.
- System generates a full digitization report per extraction run, including:
  - total images processed, success/failure counts, and failure reasons
  - extraction confidence summaries for description and score fields
  - list of cards requiring manual review
  - score-distribution sanity checks, including missing expected score increments

### FR-1a: Manual result review workflow
- Reviewer can iterate through extracted cards one by one with image preview and extracted fields.
- Reviewer can edit extracted description and official score before approval.
- Reviewer can mark extraction status as `approved`, `needs_fix`, or `rejected`.
- Only `approved` cards are eligible for ranking runs.

### FR-2: Human session flow
- User can start a new session as anonymous or with nickname.
- User can choose session pair count (default configurable; example 20).
- System presents one pair at a time and records choice.
- For each card in the pair, UI shows description + card image but does not show official author ranking.
- System prevents self-pairing and duplicate immediate repeats within a session.
- Session ends when target pair count is reached or user exits.

### FR-3: Pair generation strategy
- Warm-up: random sampling for initial comparisons.
- Main mode: uncertainty/adaptive sampling to maximize ranking information gain.
- Strategy and seed are logged for reproducibility.

### FR-4: Persistent storage and auditability
- All card records, sessions, comparisons, and ranking runs are stored persistently.
- Data must survive app restarts.
- All derived rankings can be tied back to source comparisons and algorithm configs.

### FR-5: Ranking computation
- Provide script/command to compute rankings from stored comparisons.
- Primary algorithm: Bradley-Terry.
- Baseline algorithm: Elo.
- Output normalized severity score in [1, 100] with optional 0.5 rounding for display.

### FR-6: AI voter as separate actor
- Provide runner to execute pairwise choices by an LLM/agent from descriptions only.
- AI input excludes card image and excludes official author ranking.
- AI results are stored as distinct sessions with `actor_type = ai`.
- AI run config (model, prompt style, temperature, etc.) is persisted with run metadata.

### FR-7: Comparative analysis outputs
- Generate comparison report between:
  - official author ranking
  - human-derived ranking
  - AI-derived ranking
- Include at least:
  - Spearman rank correlation
  - Kendall tau
  - Mean absolute difference on normalized 1-100 scores
  - Top disagreement cards list

## 10) Non-Functional Requirements

- Reproducibility: deterministic mode via random seed support for pair generation and ranking runs.
- Transparency: store configs and metadata for each run.
- Maintainability: modular package layout with clear boundaries.
- Local-first operation: full system runs locally without cloud dependencies.
- Performance target (initial): responsive UI for pair voting and ranking recomputation within practical local times on ~200 cards.
- Environment consistency: all dependencies and project metadata are managed via `pyproject.toml`, installed/synced with `uv`.

## 11) API and Script Surface (Initial)

Expected commands/scripts (exact filenames may evolve, behavior is required):

- Environment and dependency management
  - `uv sync`
  - `uv run <command>` for all project scripts

- Ingestion
  - `uv run python -m src.ingest.run_extract --input data/raw_photos --out data/processed`
  - `uv run python -m src.ingest.review` (manual correction/approval flow)

- App
  - `uv run python -m src.app.main` (start FastAPI server)

- Ranking
  - `uv run python -m src.ranking.run --population human --algorithm bradley_terry`
  - `uv run python -m src.ranking.run --population ai --algorithm bradley_terry`

- AI voter
  - `uv run python -m src.ai_user.run --pairs 200 --model <model_name>`

- Analysis
  - `uv run python -m src.analysis.compare --human-run <id> --ai-run <id>`

## 12) Ranking and Normalization Details

- Fit model on pairwise outcomes where selected card is interpreted as "worse".
- Convert model latent score to normalized [1, 100] scale:
  - min-max normalization within run,
  - optional display rounding to nearest 0.5,
  - preserve unrounded value in DB for analysis precision.
- Support confidence intervals or uncertainty proxy where possible.

## 13) Quality Assurance and Validation

### Ingestion validation
- Sample-based spot checks after extraction.
- Require manual approval status for inclusion in ranking runs.
- Add automated test that verifies the extracted official-score set contains every 0.5 increment from 0.5 to 100.0.
- If any increment in `0.5, 1.0, 1.5, ..., 100.0` is missing, ingestion run is flagged as invalid pending review.
- Digitization report must explicitly list missing increments and suspected extraction errors.

### App validation
- Unit tests for pair generation constraints.
- Route-level tests for session creation and vote submission.

### Ranking validation
- Synthetic preference tests to confirm algorithm recovers known ordering.
- Stability checks across random seeds and subsets.

### End-to-end acceptance criteria
- At least 95% of cards approved in dataset.
- Human and AI sessions can be recorded and replayed from DB.
- Ranking script outputs normalized scores for all approved cards.
- Comparison report generated successfully with required metrics.
- Digitization report is generated and saved for each extraction run.
- Manual review interface allows stepping through extracted cards with image + extracted fields and editing/approval actions.
- Validation test for full 0.5 increment coverage from 0.5 to 100 passes, or blocks dataset approval with explicit missing-value report.

## 14) Milestone Plan

### M1 - Data ingestion foundation
- Build extraction pipeline and persisted card dataset.
- Implement manual review/correction pass.

### M2 - Voting application
- Build session UI and persistence for pairwise comparisons.
- Add configurable pair count and metadata capture.

### M3 - Ranking engine
- Implement Bradley-Terry + Elo baseline and normalized outputs.

### M4 - AI voter integration
- Implement AI runner and store AI-generated comparisons.

### M5 - Comparative analysis
- Produce final comparison metrics, reports, and disagreement views.

## 15) Risks and Mitigations

- OCR noise risk -> mitigation: manual review gate and confidence-based triage.
- Preference sparsity risk -> mitigation: adaptive pair sampling and minimum vote thresholds.
- User bias/sample bias risk -> mitigation: track per-session metadata and report uncertainty.
- Model sensitivity risk -> mitigation: compare Bradley-Terry against Elo baseline.

## 16) Open Questions (Tracked)

- Exact card count and whether all cards are represented in photos.
- Whether to enforce strict content filtering for potentially explicit card text in UI.
- AI model/provider selection for stable, cost-aware runs.

These remain configurable decisions and do not block initial implementation.

## 17) Definition of Done (Project-Level)

Project is considered complete for v1 when:

- Card deck is digitized and approved in persistent storage.
- Human pairwise UI is usable and configurable.
- AI voter can run independently and store comparable results.
- Human and AI rankings are computed on the same normalized scale.
- Official vs human vs AI comparison report is generated and interpretable.
