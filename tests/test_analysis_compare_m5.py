from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.analysis.compare import (
    AlignedCardComparison,
    build_aligned_comparisons,
    compute_metrics,
    extract_top_disagreements,
    main,
    run_comparison,
)
from src.common.db import create_schema, session_scope
from src.common.models import Card, RankingResult, RankingRun


def _db_url_for_tmp(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test_analysis_m5.db'}"


def _seed_cards_for_analysis() -> list[int]:
    with session_scope() as session:
        cards = [
            Card(
                source_image_path=f"/tmp/analysis-card-{idx}.jpg",
                description_text=f"Scenario {idx}",
                official_score=float(idx * 10),
                status="approved",
            )
            for idx in range(1, 4)
        ]
        session.add_all(cards)
        session.flush()
        return [card.id for card in cards]


def _seed_ranking_run(*, population: str, algorithm: str = "bradley_terry") -> int:
    with session_scope() as session:
        run = RankingRun(population=population, algorithm=algorithm, config_json=json.dumps({}))
        session.add(run)
        session.flush()
        return run.id


def _seed_ranking_results(
    *,
    run_id: int,
    rows: list[tuple[int, float, float, int]],
) -> None:
    with session_scope() as session:
        for card_id, raw_score, normalized_score, rank in rows:
            session.add(
                RankingResult(
                    ranking_run_id=run_id,
                    card_id=card_id,
                    raw_score=raw_score,
                    normalized_score_1_100=normalized_score,
                    rank_position=rank,
                )
            )


def test_cli_rejects_nonexistent_runs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    create_schema()

    monkeypatch.setattr(
        sys,
        "argv",
        ["compare", "--human-run", "99", "--ai-run", "100", "--output-dir", str(tmp_path)],
    )

    with pytest.raises(SystemExit, match=r"ranking_run_not_found:99"):
        main()


def test_cli_rejects_population_mismatch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    create_schema()
    human_run = _seed_ranking_run(population="human")
    another_human_run = _seed_ranking_run(population="human")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compare",
            "--human-run",
            str(human_run),
            "--ai-run",
            str(another_human_run),
            "--output-dir",
            str(tmp_path),
        ],
    )

    with pytest.raises(SystemExit, match=r"ranking_run_population_mismatch"):
        main()


def test_alignment_handles_missing_cards_and_errors_on_empty_overlap(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    create_schema()
    card_ids = _seed_cards_for_analysis()
    card_a, card_b, card_c = card_ids

    human_run = _seed_ranking_run(population="human")
    ai_run = _seed_ranking_run(population="ai")
    _seed_ranking_results(
        run_id=human_run,
        rows=[
            (card_a, 1.0, 10.0, 3),
            (card_b, 2.0, 20.0, 2),
        ],
    )
    _seed_ranking_results(
        run_id=ai_run,
        rows=[
            (card_b, 2.0, 21.0, 2),
            (card_c, 3.0, 31.0, 1),
        ],
    )

    with session_scope() as session:
        rows, alignment, _, _ = build_aligned_comparisons(
            session, human_run_id=human_run, ai_run_id=ai_run
        )

    assert [row.card_id for row in rows] == [card_b]
    assert alignment["missing_in_human"] == [card_c]
    assert alignment["missing_in_ai"] == [card_a]

    empty_human = _seed_ranking_run(population="human")
    empty_ai = _seed_ranking_run(population="ai")
    _seed_ranking_results(run_id=empty_human, rows=[(card_a, 1.0, 11.0, 3)])
    _seed_ranking_results(run_id=empty_ai, rows=[(card_c, 3.0, 33.0, 1)])

    with session_scope() as session:
        with pytest.raises(ValueError, match=r"empty_aligned_overlap"):
            build_aligned_comparisons(session, human_run_id=empty_human, ai_run_id=empty_ai)


def test_metric_helper_expected_values_on_known_fixture() -> None:
    rows = [
        AlignedCardComparison(
            card_id=1,
            description_text="a",
            official_score=1.0,
            official_rank_position=3,
            human_score=1.0,
            human_rank_position=3,
            ai_score=3.0,
            ai_rank_position=1,
        ),
        AlignedCardComparison(
            card_id=2,
            description_text="b",
            official_score=2.0,
            official_rank_position=2,
            human_score=2.0,
            human_rank_position=2,
            ai_score=2.0,
            ai_rank_position=2,
        ),
        AlignedCardComparison(
            card_id=3,
            description_text="c",
            official_score=3.0,
            official_rank_position=1,
            human_score=3.0,
            human_rank_position=1,
            ai_score=1.0,
            ai_rank_position=3,
        ),
    ]

    metrics = compute_metrics(rows)

    assert metrics["spearman"]["official_vs_human"] == pytest.approx(1.0)
    assert metrics["spearman"]["official_vs_ai"] == pytest.approx(-1.0)
    assert metrics["kendall_tau"]["official_vs_human"] == pytest.approx(1.0)
    assert metrics["kendall_tau"]["official_vs_ai"] == pytest.approx(-1.0)
    assert metrics["mean_absolute_difference"]["official_vs_human"] == pytest.approx(0.0)
    assert metrics["mean_absolute_difference"]["official_vs_ai"] == pytest.approx(4.0 / 3.0)


def test_disagreement_extraction_is_deterministic_under_ties() -> None:
    rows = [
        AlignedCardComparison(
            card_id=1,
            description_text="card-1",
            official_score=30.0,
            official_rank_position=1,
            human_score=20.0,
            human_rank_position=2,
            ai_score=29.0,
            ai_rank_position=1,
        ),
        AlignedCardComparison(
            card_id=2,
            description_text="card-2",
            official_score=40.0,
            official_rank_position=1,
            human_score=30.0,
            human_rank_position=4,
            ai_score=38.0,
            ai_rank_position=2,
        ),
        AlignedCardComparison(
            card_id=3,
            description_text="card-3",
            official_score=25.0,
            official_rank_position=3,
            human_score=20.0,
            human_rank_position=3,
            ai_score=27.0,
            ai_rank_position=2,
        ),
    ]

    disagreements = extract_top_disagreements(rows, top_n=3)
    ordered = [item["card_id"] for item in disagreements["official_vs_human"]]
    assert ordered == [2, 1, 3]


def test_run_comparison_writes_json_and_markdown_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    create_schema()
    card_ids = _seed_cards_for_analysis()

    human_run = _seed_ranking_run(population="human")
    ai_run = _seed_ranking_run(population="ai")
    _seed_ranking_results(
        run_id=human_run,
        rows=[
            (card_ids[0], 0.1, 20.0, 3),
            (card_ids[1], 0.2, 50.0, 2),
            (card_ids[2], 0.3, 80.0, 1),
        ],
    )
    _seed_ranking_results(
        run_id=ai_run,
        rows=[
            (card_ids[0], 0.4, 30.0, 3),
            (card_ids[1], 0.5, 55.0, 2),
            (card_ids[2], 0.6, 70.0, 1),
        ],
    )

    output_dir = tmp_path / "outputs"
    json_path, md_path = run_comparison(
        human_run_id=human_run,
        ai_run_id=ai_run,
        output_dir=output_dir,
        top_n=5,
    )

    assert json_path == output_dir / f"comparison_h{human_run}_a{ai_run}.json"
    assert md_path == output_dir / f"comparison_h{human_run}_a{ai_run}.md"
    assert json_path.exists()
    assert md_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["human_run"]["id"] == human_run
    assert payload["ai_run"]["id"] == ai_run
    assert payload["card_count"] == 3
    assert "spearman" in payload["metrics"]
    assert "kendall_tau" in payload["metrics"]
    assert "mean_absolute_difference" in payload["metrics"]
    assert "official_vs_human" in payload["top_disagreements"]
    assert "official_vs_ai" in payload["top_disagreements"]
