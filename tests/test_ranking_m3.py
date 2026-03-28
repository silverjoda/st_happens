from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.common.db import create_schema, session_scope
from src.common.models import Card, Comparison, RankingResult, RankingRun, SessionRecord
from src.ranking.data import load_comparisons_for_population, load_ranking_input
from src.ranking.run import run_ranking


def _db_url_for_tmp(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test_ranking_m3.db'}"


def _seed_cards() -> list[int]:
    with session_scope() as session:
        cards = [
            Card(
                source_image_path=f"/tmp/card-{idx}.jpg",
                description_text=f"Card {idx}",
                official_score=10.0 + idx,
                status="approved",
            )
            for idx in range(1, 4)
        ]
        session.add_all(cards)
        session.flush()
        return [card.id for card in cards]


def _seed_sessions() -> tuple[int, int]:
    with session_scope() as session:
        human = SessionRecord(actor_type="human", nickname="h", pair_target_count=10)
        ai = SessionRecord(actor_type="ai", nickname="a", pair_target_count=10)
        session.add_all([human, ai])
        session.flush()
        return human.id, ai.id


def _insert_comparison(
    *,
    session_id: int,
    left_card_id: int,
    right_card_id: int,
    chosen_card_id: int,
    presented_order: int,
    created_at: datetime,
) -> None:
    with session_scope() as session:
        session.add(
            Comparison(
                session_id=session_id,
                left_card_id=left_card_id,
                right_card_id=right_card_id,
                chosen_card_id=chosen_card_id,
                presented_order=presented_order,
                created_at=created_at,
            )
        )


def _ordered_results(run_id: int) -> list[RankingResult]:
    with session_scope() as session:
        return list(
            session.scalars(
                select(RankingResult)
                .where(RankingResult.ranking_run_id == run_id)
                .order_by(RankingResult.rank_position.asc())
            ).all()
        )


def _seed_synthetic_preferences() -> tuple[list[int], int, int]:
    card_ids = _seed_cards()
    human_session_id, ai_session_id = _seed_sessions()
    card_a, card_b, card_c = card_ids

    now = datetime(2025, 1, 1, 12, 0, 0)
    comparisons = [
        (human_session_id, card_a, card_b, card_b),
        (human_session_id, card_a, card_c, card_c),
        (human_session_id, card_b, card_c, card_c),
        (human_session_id, card_a, card_c, card_c),
        (human_session_id, card_a, card_b, card_b),
        (ai_session_id, card_a, card_b, card_b),
    ]
    for idx, (session_id, left, right, chosen) in enumerate(comparisons, start=1):
        _insert_comparison(
            session_id=session_id,
            left_card_id=left,
            right_card_id=right,
            chosen_card_id=chosen,
            presented_order=idx,
            created_at=now + timedelta(seconds=idx),
        )

    return card_ids, human_session_id, ai_session_id


def test_population_filtering_human_ai_combined(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    create_schema()
    _, _, _ = _seed_synthetic_preferences()

    with session_scope() as session:
        assert len(load_comparisons_for_population(session, "human")) == 5
        assert len(load_comparisons_for_population(session, "ai")) == 1
        assert len(load_comparisons_for_population(session, "combined")) == 6


def test_bradley_terry_synthetic_order_recovery(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    create_schema()
    card_ids, _, _ = _seed_synthetic_preferences()
    card_a, card_b, card_c = card_ids

    run_id = run_ranking(population="human", algorithm="bradley_terry", seed=7, k_factor=24.0)
    results = _ordered_results(run_id)
    ordered_card_ids = [result.card_id for result in results]

    assert ordered_card_ids == [card_c, card_b, card_a]
    assert len(results) == len(card_ids)
    assert all(1.0 <= result.normalized_score_1_100 <= 100.0 for result in results)

    with session_scope() as session:
        run = session.get(RankingRun, run_id)
        assert run is not None
        config = json.loads(run.config_json)
        assert config["algorithm"] == "bradley_terry"
        assert config["population"] == "human"
        assert config["seed"] == 7
        assert config["algorithm_config"]["seed"] == 7
        assert config["algorithm_config"]["converged"] is True


def test_elo_synthetic_order_recovery(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    create_schema()
    card_ids, _, _ = _seed_synthetic_preferences()
    card_a, card_b, card_c = card_ids

    run_id = run_ranking(population="human", algorithm="elo", seed=0, k_factor=32.0)
    results = _ordered_results(run_id)
    ordered_card_ids = [result.card_id for result in results]

    assert ordered_card_ids == [card_c, card_b, card_a]


def test_seed_stability_same_seed_same_scores(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    create_schema()
    _seed_synthetic_preferences()

    run1 = run_ranking(population="human", algorithm="bradley_terry", seed=42, k_factor=24.0)
    run2 = run_ranking(population="human", algorithm="bradley_terry", seed=42, k_factor=24.0)

    results1 = _ordered_results(run1)
    results2 = _ordered_results(run2)

    assert [row.card_id for row in results1] == [row.card_id for row in results2]
    for row1, row2 in zip(results1, results2, strict=True):
        assert row1.raw_score == pytest.approx(row2.raw_score)
        assert row1.normalized_score_1_100 == pytest.approx(row2.normalized_score_1_100)


def test_persistence_row_counts_and_normalization_bounds(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    create_schema()
    card_ids, _, _ = _seed_synthetic_preferences()

    run_id = run_ranking(population="human", algorithm="elo", seed=1, k_factor=24.0)

    with session_scope() as session:
        run_count = session.scalar(select(func.count()).select_from(RankingRun)) or 0
        result_count = session.scalar(select(func.count()).select_from(RankingResult)) or 0
        assert run_count == 1
        assert result_count == len(card_ids)

        run = session.get(RankingRun, run_id)
        assert run is not None
        config = json.loads(run.config_json)
        assert config["algorithm"] == "elo"
        assert config["population"] == "human"

        values = list(
            session.scalars(
                select(RankingResult.normalized_score_1_100).where(
                    RankingResult.ranking_run_id == run_id
                )
            ).all()
        )
        assert values
        assert all(1.0 <= value <= 100.0 for value in values)


def test_validation_tokens_for_invalid_states(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    create_schema()

    with session_scope() as session:
        with pytest.raises(ValueError, match="no_approved_cards"):
            load_ranking_input(session, "human")

    _seed_cards()
    _seed_sessions()
    with session_scope() as session:
        with pytest.raises(ValueError, match="insufficient_comparisons"):
            load_ranking_input(session, "human")
