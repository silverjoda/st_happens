from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from src.ai_user.run import run_ai_votes
from src.app.session_results import load_session_result
from src.common.db import create_schema, session_scope
from src.common.models import AIRunRecord, Card, Comparison, SessionRecord
from src.ranking.data import load_comparisons_for_population


def _db_url_for_tmp(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test_ai_user_m4.db'}"


def _results_dir_for_tmp(tmp_path: Path) -> str:
    return str(tmp_path / "session_results")


def _seed_approved_cards(count: int) -> list[int]:
    with session_scope() as session:
        cards = [
            Card(
                source_image_path=f"/tmp/ai-card-{idx}.jpg",
                description_text=f"Scenario {idx} with potential crash",
                official_score=10.0 + idx,
                status="approved",
            )
            for idx in range(1, count + 1)
        ]
        session.add_all(cards)
        session.flush()
        return [card.id for card in cards]


def test_run_ai_votes_persists_session_comparisons_and_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("src.ai_user.run._pick_worse_side_with_openai", lambda **_: "left")
    monkeypatch.setattr(
        "src.ai_user.run._request_reasoning_with_openai",
        lambda **_: "I chose LEFT because it creates broader long-term harm.",
    )
    create_schema()
    _seed_approved_cards(5)

    session_id, run_id = run_ai_votes(
        pairs=4,
        model="stub-model-v1",
        temperature=0.0,
        seed=13,
        prompt_style="description_only_v1",
    )

    with session_scope() as session:
        record = session.get(SessionRecord, session_id)
        assert record is not None
        assert record.actor_type == "ai"
        assert record.pair_target_count == 4
        assert record.ended_at is not None

        comparisons = list(
            session.scalars(
                select(Comparison)
                .where(Comparison.session_id == session_id)
                .order_by(Comparison.presented_order.asc())
            ).all()
        )
        assert len(comparisons) == 4
        assert all(
            comparison.chosen_card_id in {comparison.left_card_id, comparison.right_card_id}
            for comparison in comparisons
        )

        run = session.get(AIRunRecord, run_id)
        assert run is not None
        assert run.session_id == session_id
        metadata = json.loads(run.config_json)
        assert metadata["model"] == "stub-model-v1"
        assert metadata["prompt_style"] == "description_only_v1"
        assert metadata["temperature"] == 0.0
        assert metadata["seed"] == 13
        assert metadata["session_id"] == session_id
        assert metadata["provider"] == "openai"
        assert isinstance(metadata["file_session_id"], int)

    file_record = load_session_result(1)
    assert file_record is not None
    assert file_record.actor_type == "ai"
    assert file_record.pair_target_count == 4
    assert file_record.ended_at is not None
    assert len(file_record.comparisons) == 4
    assert all(
        row.reasoning == "I chose LEFT because it creates broader long-term harm."
        for row in file_record.comparisons
    )


def test_actor_population_filtering_separates_human_and_ai(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("src.ai_user.run._pick_worse_side_with_openai", lambda **_: "left")
    monkeypatch.setattr(
        "src.ai_user.run._request_reasoning_with_openai",
        lambda **_: "I chose LEFT because it creates broader long-term harm.",
    )
    create_schema()
    card_ids = _seed_approved_cards(3)

    with session_scope() as session:
        human = SessionRecord(actor_type="human", nickname="person", pair_target_count=1)
        session.add(human)
        session.flush()
        session.add(
            Comparison(
                session_id=human.id,
                left_card_id=card_ids[0],
                right_card_id=card_ids[1],
                chosen_card_id=card_ids[1],
                presented_order=1,
                response_ms=200,
            )
        )

    run_ai_votes(
        pairs=2,
        model="stub-model-v1",
        temperature=0.0,
        seed=7,
        prompt_style="description_only_v1",
    )

    with session_scope() as session:
        human_events = load_comparisons_for_population(session, "human")
        ai_events = load_comparisons_for_population(session, "ai")
        combined = load_comparisons_for_population(session, "combined")

    assert len(human_events) == 1
    assert len(ai_events) == 2
    assert len(combined) == 3
