from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.app.main import app
from src.app.pairing import canonical_pair_key, load_approved_cards, select_next_pair
from src.common.db import create_schema, session_scope
from src.common.models import Card, Comparison, SessionRecord


def _db_url_for_tmp(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test_app_sessions.db'}"


def _count_sessions() -> int:
    with session_scope() as session:
        return session.scalar(select(func.count()).select_from(SessionRecord)) or 0


def _write_fake_image(tmp_path: Path, name: str) -> str:
    image_path = tmp_path / name
    image_path.write_bytes(b"fake")
    return str(image_path)


def _insert_cards(
    tmp_path: Path,
    *,
    approved_count: int,
    extracted_count: int = 0,
) -> list[int]:
    create_schema()
    inserted_ids: list[int] = []
    with session_scope() as session:
        for idx in range(approved_count):
            card = Card(
                source_image_path=_write_fake_image(tmp_path, f"approved-{idx}.jpg"),
                description_text=f"Approved {idx}",
                official_score=10.0 + idx,
                status="approved",
            )
            session.add(card)

        for idx in range(extracted_count):
            card = Card(
                source_image_path=_write_fake_image(tmp_path, f"extracted-{idx}.jpg"),
                description_text=f"Extracted {idx}",
                official_score=50.0 + idx,
                status="extracted",
            )
            session.add(card)

        session.flush()
        inserted_ids = [
            card_id
            for card_id in session.scalars(
                select(Card.id).where(Card.status == "approved").order_by(Card.id)
            )
        ]

    return inserted_ids


def _extract_hidden_value(html: str, field_name: str) -> int:
    pattern = rf'name="{field_name}" value="(\d+)"'
    match = re.search(pattern, html)
    assert match is not None
    return int(match.group(1))


def test_session_start_route_renders_form(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))

    with TestClient(app) as client:
        response = client.get("/sessions/start")

    assert response.status_code == 200
    assert 'name="nickname"' in response.text
    assert 'name="pair_target_count"' in response.text
    assert 'value="20"' in response.text


def test_create_session_valid_post_persists_human_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            data={
                "nickname": "  Alice  ",
                "pair_target_count": "25",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/sessions/")
    assert response.headers["location"].endswith("/pair")
    assert _count_sessions() == 1

    with session_scope() as session:
        saved = session.scalar(select(SessionRecord))
        assert saved is not None
        assert saved.actor_type == "human"
        assert saved.nickname == "Alice"
        assert saved.pair_target_count == 25


def test_create_session_invalid_pair_target_shows_error_no_insert(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            data={
                "nickname": "Bob",
                "pair_target_count": "-1",
            },
            follow_redirects=False,
        )

    assert response.status_code == 200
    assert "Pair target count must be between 1 and 500." in response.text
    assert _count_sessions() == 0


def test_nickname_empty_persists_null(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            data={
                "nickname": "   ",
                "pair_target_count": "10",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303

    with session_scope() as session:
        saved = session.scalar(select(SessionRecord))
        assert saved is not None
        assert saved.nickname is None


def test_pair_selection_uses_only_approved_cards(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))

    _insert_cards(tmp_path, approved_count=3, extracted_count=2)

    with session_scope() as session:
        approved = load_approved_cards(session)
        assert len(approved) == 3
        assert all(card.status == "approved" for card in approved)


def test_pair_selection_never_self_pairs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))

    _insert_cards(tmp_path, approved_count=3)

    with session_scope() as session:
        selected = select_next_pair(session, session_id=11, presented_order=1)

    assert selected.left_card.id != selected.right_card.id


def test_pair_selection_avoids_immediate_duplicate_pair_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))

    card_ids = _insert_cards(tmp_path, approved_count=4)
    with session_scope() as session:
        session.add(
            SessionRecord(
                actor_type="human",
                nickname="alice",
                pair_target_count=10,
            )
        )
        session.flush()
        session_id = session.scalar(select(SessionRecord.id).limit(1))
        assert session_id is not None

        previous = select_next_pair(session, session_id=session_id, presented_order=1)
        session.add(
            Comparison(
                session_id=session_id,
                left_card_id=previous.left_card.id,
                right_card_id=previous.right_card.id,
                chosen_card_id=previous.left_card.id,
                presented_order=1,
                response_ms=10,
            )
        )
        session.flush()

        current = select_next_pair(session, session_id=session_id, presented_order=2)

    previous_key = canonical_pair_key(previous.left_card.id, previous.right_card.id)
    current_key = canonical_pair_key(current.left_card.id, current.right_card.id)
    assert previous_key != current_key
    assert {current.left_card.id, current.right_card.id}.issubset(set(card_ids))


def test_get_pair_redirects_to_complete_when_target_met(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))

    _insert_cards(tmp_path, approved_count=2)

    with TestClient(app) as client:
        create = client.post(
            "/sessions",
            data={"nickname": "", "pair_target_count": "1"},
            follow_redirects=False,
        )
        session_id = int(create.headers["location"].split("/")[2])

        first_pair = client.get(f"/sessions/{session_id}/pair")
        left_card_id = _extract_hidden_value(first_pair.text, "left_card_id")
        right_card_id = _extract_hidden_value(first_pair.text, "right_card_id")
        presented_order = _extract_hidden_value(first_pair.text, "presented_order")

        vote = client.post(
            f"/sessions/{session_id}/vote",
            data={
                "left_card_id": str(left_card_id),
                "right_card_id": str(right_card_id),
                "chosen_card_id": str(left_card_id),
                "presented_order": str(presented_order),
            },
            follow_redirects=False,
        )
        assert vote.status_code == 303
        assert vote.headers["location"] == f"/sessions/{session_id}/complete"

        after_complete = client.get(f"/sessions/{session_id}/pair", follow_redirects=False)

    assert after_complete.status_code == 303
    assert after_complete.headers["location"] == f"/sessions/{session_id}/complete"


def test_post_vote_persists_required_fields(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))

    _insert_cards(tmp_path, approved_count=3)

    with TestClient(app) as client:
        create = client.post(
            "/sessions",
            data={"nickname": "", "pair_target_count": "2"},
            follow_redirects=False,
        )
        session_id = int(create.headers["location"].split("/")[2])

        pair_page = client.get(f"/sessions/{session_id}/pair")
        left_card_id = _extract_hidden_value(pair_page.text, "left_card_id")
        right_card_id = _extract_hidden_value(pair_page.text, "right_card_id")
        presented_order = _extract_hidden_value(pair_page.text, "presented_order")

        response = client.post(
            f"/sessions/{session_id}/vote",
            data={
                "left_card_id": str(left_card_id),
                "right_card_id": str(right_card_id),
                "chosen_card_id": str(right_card_id),
                "presented_order": str(presented_order),
                "response_ms": "321",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/sessions/{session_id}/pair"

    with session_scope() as session:
        comparison = session.scalar(select(Comparison).where(Comparison.session_id == session_id))
        assert comparison is not None
        assert comparison.left_card_id == left_card_id
        assert comparison.right_card_id == right_card_id
        assert comparison.chosen_card_id == right_card_id
        assert comparison.presented_order == 1
        assert comparison.response_ms == 321


def test_invalid_chosen_card_rejected_without_write(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))

    card_ids = _insert_cards(tmp_path, approved_count=3)
    outside_card_id = max(card_ids) + 999

    with TestClient(app) as client:
        create = client.post(
            "/sessions",
            data={"nickname": "", "pair_target_count": "2"},
            follow_redirects=False,
        )
        session_id = int(create.headers["location"].split("/")[2])

        pair_page = client.get(f"/sessions/{session_id}/pair")
        left_card_id = _extract_hidden_value(pair_page.text, "left_card_id")
        right_card_id = _extract_hidden_value(pair_page.text, "right_card_id")
        presented_order = _extract_hidden_value(pair_page.text, "presented_order")

        response = client.post(
            f"/sessions/{session_id}/vote",
            data={
                "left_card_id": str(left_card_id),
                "right_card_id": str(right_card_id),
                "chosen_card_id": str(outside_card_id),
                "presented_order": str(presented_order),
            },
            follow_redirects=False,
        )

    assert response.status_code == 400

    with session_scope() as session:
        count = (
            session.scalar(
                select(func.count())
                .select_from(Comparison)
                .where(Comparison.session_id == session_id)
            )
            or 0
        )
        assert count == 0


def test_session_sets_ended_at_on_final_vote(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))

    _insert_cards(tmp_path, approved_count=2)

    with TestClient(app) as client:
        create = client.post(
            "/sessions",
            data={"nickname": "", "pair_target_count": "1"},
            follow_redirects=False,
        )
        session_id = int(create.headers["location"].split("/")[2])

        pair_page = client.get(f"/sessions/{session_id}/pair")
        left_card_id = _extract_hidden_value(pair_page.text, "left_card_id")
        right_card_id = _extract_hidden_value(pair_page.text, "right_card_id")
        presented_order = _extract_hidden_value(pair_page.text, "presented_order")

        response = client.post(
            f"/sessions/{session_id}/vote",
            data={
                "left_card_id": str(left_card_id),
                "right_card_id": str(right_card_id),
                "chosen_card_id": str(left_card_id),
                "presented_order": str(presented_order),
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/sessions/{session_id}/complete"

    with session_scope() as session:
        record = session.get(SessionRecord, session_id)
        assert record is not None
        assert record.ended_at is not None
