from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.common.db import create_schema, session_scope
from src.common.models import Card
from src.ingest.reporting import build_run_report, find_missing_score_increments
from src.ingest.storage import persist_card_extraction
from src.ingest.types import ExtractionResult
from src.ranking.selection import get_approved_cards


def _db_url_for_tmp(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test_ship_happens.db'}"


def _make_result(path: str, score: float | None = 1.0) -> ExtractionResult:
    return ExtractionResult(
        source_image_path=path,
        description_text="Sample description",
        official_score=score,
        ocr_confidence_desc=0.9,
        ocr_confidence_score=0.8,
        status="extracted",
        failure_reason=None,
    )


def test_full_official_score_increment_coverage() -> None:
    observed = {value / 2 for value in range(1, 201)}
    assert find_missing_score_increments(observed) == []


def test_extraction_persistence_into_cards(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))

    create_schema()
    result = _make_result("/tmp/card-1.jpg", score=12.5)

    with session_scope() as session:
        persisted = persist_card_extraction(session, result)
        persisted_id = persisted.id

    with session_scope() as session:
        card = session.get(Card, persisted_id)
        assert card is not None
        assert card.source_image_path == "/tmp/card-1.jpg"
        assert card.description_text == "Sample description"
        assert card.official_score == 12.5
        assert card.status == "extracted"


def test_report_payload_shape_required_fields() -> None:
    now = datetime.now(timezone.utc)
    results = [
        _make_result("/tmp/card-a.jpg", score=1.0),
        _make_result("/tmp/card-b.jpg", score=1.5),
    ]

    report = build_run_report(
        run_id="run-1",
        started_at=now,
        finished_at=now,
        input_dir="data/raw_photos",
        output_dir="data/processed",
        results=results,
    )

    required_keys = {
        "run_id",
        "started_at",
        "finished_at",
        "duration_seconds",
        "input_dir",
        "output_dir",
        "total_images_processed",
        "success_count",
        "failure_count",
        "failure_reasons",
        "confidence_summary",
        "manual_review_required",
        "missing_score_increments",
        "suspected_extraction_anomalies",
        "records",
        "generated_at",
    }
    assert required_keys.issubset(report.keys())
    assert isinstance(report["confidence_summary"], dict)
    assert isinstance(report["missing_score_increments"], list)
    assert isinstance(report["records"], list)


def test_missing_increment_detection_behavior() -> None:
    observed = {0.5, 1.0, 2.0, 2.5}
    missing = find_missing_score_increments(observed)
    assert 1.5 in missing
    assert 3.0 in missing


def test_downstream_selection_approved_only(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    create_schema()

    with session_scope() as session:
        session.add_all(
            [
                Card(
                    source_image_path="/tmp/approved.jpg",
                    description_text="Approved",
                    official_score=10.0,
                    status="approved",
                ),
                Card(
                    source_image_path="/tmp/extracted.jpg",
                    description_text="Extracted",
                    official_score=11.0,
                    status="extracted",
                ),
            ]
        )

    with session_scope() as session:
        approved = get_approved_cards(session)
        assert len(approved) == 1
        assert approved[0].status == "approved"
        assert approved[0].source_image_path == "/tmp/approved.jpg"
