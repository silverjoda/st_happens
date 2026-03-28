from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from src.app.main import app
from src.app.pairing import canonical_pair_key, load_approved_cards, select_next_pair
from src.app.session_results import load_session_result
from src.common.db import create_schema, session_scope
from src.common.models import Card
from src.common.settings import display_card_path_for_score, display_card_path_for_source


def _db_url_for_tmp(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test_app_sessions.db'}"


def _results_dir_for_tmp(tmp_path: Path) -> str:
    return str(tmp_path / "session_results")


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
            card.id
            for card in session.query(Card)
            .filter(Card.status == "approved")
            .order_by(Card.id)
            .all()
        ]

    return inserted_ids


def _extract_hidden_value(html: str, field_name: str) -> int:
    pattern = rf'name="{field_name}" value="(\d+)"'
    match = re.search(pattern, html)
    assert match is not None
    return int(match.group(1))


def test_session_start_route_renders_form(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))

    with TestClient(app) as client:
        response = client.get("/sessions/start")

    assert response.status_code == 200
    assert 'name="nickname"' in response.text
    assert 'name="pair_target_count"' in response.text
    assert 'value="20"' in response.text


def test_create_session_valid_post_persists_human_session_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))

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
    assert response.headers["location"] == "/sessions/1/pair"

    saved = load_session_result(1)
    assert saved is not None
    assert saved.actor_type == "human"
    assert saved.nickname == "Alice"
    assert saved.pair_target_count == 25
    assert saved.ended_at is None
    assert saved.comparisons == []


def test_create_session_invalid_pair_target_shows_error_no_file(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))

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
    assert load_session_result(1) is None


def test_nickname_empty_persists_null(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))

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
    saved = load_session_result(1)
    assert saved is not None
    assert saved.nickname is None


def test_pair_selection_uses_only_approved_cards(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))

    _insert_cards(tmp_path, approved_count=3, extracted_count=2)

    with session_scope() as session:
        approved = load_approved_cards(session)
        assert len(approved) == 3
        assert all(card.status == "approved" for card in approved)


def test_card_image_prefers_preprocessed_display_asset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))
    monkeypatch.setattr("src.common.settings.PROJECT_ROOT", tmp_path)

    source_path = tmp_path / "raw-card.jpg"
    source_path.write_bytes(b"raw")
    display_path = display_card_path_for_score(10.0)
    display_path.parent.mkdir(parents=True, exist_ok=True)
    display_path.write_bytes(b"processed")

    create_schema()
    with session_scope() as session:
        card = Card(
            source_image_path=str(source_path),
            description_text="Card",
            official_score=10.0,
            status="approved",
        )
        session.add(card)
        session.flush()
        card_id = card.id

    with TestClient(app) as client:
        response = client.get(f"/cards/{card_id}/image")

    assert response.status_code == 200
    assert response.content == b"processed"


def test_card_image_serves_display_asset_even_if_raw_source_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))
    monkeypatch.setattr("src.common.settings.PROJECT_ROOT", tmp_path)

    source_path = tmp_path / "missing-raw-card.jpg"
    display_path = display_card_path_for_score(44.5)
    display_path.parent.mkdir(parents=True, exist_ok=True)
    display_path.write_bytes(b"processed-only")

    create_schema()
    with session_scope() as session:
        card = Card(
            source_image_path=str(source_path),
            description_text="Card",
            official_score=44.5,
            status="approved",
        )
        session.add(card)
        session.flush()
        card_id = card.id

    with TestClient(app) as client:
        response = client.get(f"/cards/{card_id}/image")

    assert response.status_code == 200
    assert response.content == b"processed-only"


def test_card_image_prefers_score_prefixed_display_asset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))
    monkeypatch.setattr("src.common.settings.PROJECT_ROOT", tmp_path)

    source_path = tmp_path / "20230909_120741.jpg"
    source_path.write_bytes(b"raw")

    score_display_path = display_card_path_for_score(333.0)
    score_display_path.parent.mkdir(parents=True, exist_ok=True)
    score_display_path.write_bytes(b"score-prefixed")

    create_schema()
    with session_scope() as session:
        card = Card(
            source_image_path=str(source_path),
            description_text="Card",
            official_score=333.0,
            status="approved",
        )
        session.add(card)
        session.flush()
        card_id = card.id

    with TestClient(app) as client:
        response = client.get(f"/cards/{card_id}/image")

    assert response.status_code == 200
    assert response.content == b"score-prefixed"


def test_card_image_requires_official_score(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))
    monkeypatch.setattr("src.common.settings.PROJECT_ROOT", tmp_path)

    source_path = tmp_path / "raw-card.jpg"
    source_path.write_bytes(b"raw")

    create_schema()
    with session_scope() as session:
        card = Card(
            source_image_path=str(source_path),
            description_text="Card",
            official_score=None,
            status="approved",
        )
        session.add(card)
        session.flush()
        card_id = card.id

    with TestClient(app) as client:
        response = client.get(f"/cards/{card_id}/image")

    assert response.status_code == 404


def test_card_image_never_falls_back_to_raw_source(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))
    monkeypatch.setattr("src.common.settings.PROJECT_ROOT", tmp_path)

    source_path = tmp_path / "raw-card.jpg"
    source_path.write_bytes(b"raw")

    create_schema()
    with session_scope() as session:
        card = Card(
            source_image_path=str(source_path),
            description_text="Card",
            official_score=88.0,
            status="approved",
        )
        session.add(card)
        session.flush()
        card_id = card.id

    with TestClient(app) as client:
        response_missing = client.get(f"/cards/{card_id}/image")

    assert response_missing.status_code == 404

    source_based_display_path = display_card_path_for_source(source_path)
    source_based_display_path.parent.mkdir(parents=True, exist_ok=True)
    source_based_display_path.write_bytes(b"processed")

    with TestClient(app) as client:
        response = client.get(f"/cards/{card_id}/image")

    assert response.status_code == 200
    assert response.content == b"processed"


def test_pair_selection_never_self_pairs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))

    _insert_cards(tmp_path, approved_count=3)

    with session_scope() as session:
        selected = select_next_pair(session, session_id=11, presented_order=1)

    assert selected.left_card.id != selected.right_card.id


def test_pair_selection_avoids_immediate_duplicate_pair_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))

    card_ids = _insert_cards(tmp_path, approved_count=4)
    with session_scope() as session:
        previous = select_next_pair(session, session_id=1, presented_order=1)
        previous_key = canonical_pair_key(previous.left_card.id, previous.right_card.id)
        current = select_next_pair(
            session,
            session_id=1,
            presented_order=2,
            blocked_pair_key=previous_key,
        )

    current_key = canonical_pair_key(current.left_card.id, current.right_card.id)
    assert previous_key != current_key
    assert {current.left_card.id, current.right_card.id}.issubset(set(card_ids))


def test_get_pair_redirects_to_complete_when_target_met(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))

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
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))

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

    saved = load_session_result(session_id)
    assert saved is not None
    assert len(saved.comparisons) == 1
    comparison = saved.comparisons[0]
    assert comparison.left_card_id == left_card_id
    assert comparison.right_card_id == right_card_id
    assert comparison.chosen_card_id == right_card_id
    assert comparison.presented_order == 1
    assert comparison.response_ms == 321


def test_invalid_chosen_card_rejected_without_write(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))

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

    saved = load_session_result(session_id)
    assert saved is not None
    assert saved.comparisons == []


def test_session_sets_ended_at_on_final_vote(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_DB_URL", _db_url_for_tmp(tmp_path))
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))

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

    saved = load_session_result(session_id)
    assert saved is not None
    assert saved.ended_at is not None
