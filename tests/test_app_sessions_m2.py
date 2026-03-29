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

    assert response.status_code == 404


def test_card_image_prefers_score_asset_over_source_fallback(monkeypatch, tmp_path: Path) -> None:
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

    source_based_display_path = display_card_path_for_source(source_path)
    source_based_display_path.parent.mkdir(parents=True, exist_ok=True)
    source_based_display_path.write_bytes(b"source-based")

    score_based_display_path = display_card_path_for_score(88.0)
    score_based_display_path.parent.mkdir(parents=True, exist_ok=True)
    score_based_display_path.write_bytes(b"score-based")

    with TestClient(app) as client:
        response = client.get(f"/cards/{card_id}/image")

    assert response.status_code == 200
    assert response.content == b"score-based"


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


def test_pair_selection_uses_fresh_random_seed_per_selection(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("src.common.settings.PROJECT_ROOT", tmp_path)

    display_dir = tmp_path / "data" / "processed" / "display_cards"
    display_dir.mkdir(parents=True, exist_ok=True)
    for score_prefix in ("100", "99.5", "99"):
        (display_dir / f"{score_prefix}_processed.jpg").write_bytes(b"fake")

    queued_seeds = [111, 222]

    class _FakeSystemRandom:
        def randrange(self, start: int, stop: int) -> int:
            assert start == 1
            assert stop == 2**63
            return queued_seeds.pop(0)

    monkeypatch.setattr("src.app.pairing.random.SystemRandom", _FakeSystemRandom)

    first = select_next_pair(session_id=1, presented_order=1)
    blocked = canonical_pair_key(first.left_card.id, first.right_card.id)
    second = select_next_pair(session_id=1, presented_order=2, blocked_pair_key=blocked)

    assert first.seed == 111
    assert second.seed == 222


def test_pair_selection_balances_card_exposure_within_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("src.common.settings.PROJECT_ROOT", tmp_path)

    display_dir = tmp_path / "data" / "processed" / "display_cards"
    display_dir.mkdir(parents=True, exist_ok=True)
    for score_prefix in ("100", "99.5", "99", "98.5", "98", "97.5"):
        (display_dir / f"{score_prefix}_processed.jpg").write_bytes(b"fake")

    used_pair_keys: set[str] = set()
    history: list[tuple[int, int]] = []
    last_key: str | None = None

    for presented_order in range(1, 11):
        selected = select_next_pair(
            session_id=1,
            presented_order=presented_order,
            blocked_pair_key=last_key,
            selection_seed_base=9001,
            excluded_pair_keys=used_pair_keys,
            session_pair_history=history,
        )
        key = canonical_pair_key(selected.left_card.id, selected.right_card.id)
        used_pair_keys.add(key)
        history.append((selected.left_card.id, selected.right_card.id))
        last_key = key

    total_counts: dict[int, int] = {}
    left_counts: dict[int, int] = {}
    right_counts: dict[int, int] = {}
    for left_id, right_id in history:
        total_counts[left_id] = total_counts.get(left_id, 0) + 1
        total_counts[right_id] = total_counts.get(right_id, 0) + 1
        left_counts[left_id] = left_counts.get(left_id, 0) + 1
        right_counts[right_id] = right_counts.get(right_id, 0) + 1

    assert len(used_pair_keys) == len(history)
    assert max(total_counts.values()) <= 4
    for card_id, left_count in left_counts.items():
        right_count = right_counts.get(card_id, 0)
        assert abs(left_count - right_count) <= 2


def test_second_session_gets_unused_pair(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))
    monkeypatch.setattr("src.common.settings.PROJECT_ROOT", tmp_path)

    display_dir = tmp_path / "data" / "processed" / "display_cards"
    display_dir.mkdir(parents=True, exist_ok=True)
    for score_prefix in ("100", "99.5", "99"):
        (display_dir / f"{score_prefix}_processed.jpg").write_bytes(b"fake")

    with TestClient(app) as client:
        first_create = client.post(
            "/sessions",
            data={"nickname": "", "pair_target_count": "1"},
            follow_redirects=False,
        )
        first_session_id = int(first_create.headers["location"].split("/")[2])
        first_pair_page = client.get(f"/sessions/{first_session_id}/pair")
        first_left = _extract_hidden_value(first_pair_page.text, "left_card_id")
        first_right = _extract_hidden_value(first_pair_page.text, "right_card_id")
        first_order = _extract_hidden_value(first_pair_page.text, "presented_order")
        first_seed = _extract_hidden_value(first_pair_page.text, "pair_seed")
        first_pair_key = canonical_pair_key(first_left, first_right)

        first_vote = client.post(
            f"/sessions/{first_session_id}/vote",
            data={
                "left_card_id": str(first_left),
                "right_card_id": str(first_right),
                "chosen_card_id": str(first_left),
                "presented_order": str(first_order),
                "pair_seed": str(first_seed),
            },
            follow_redirects=False,
        )
        assert first_vote.status_code == 303

        second_create = client.post(
            "/sessions",
            data={"nickname": "", "pair_target_count": "1"},
            follow_redirects=False,
        )
        second_session_id = int(second_create.headers["location"].split("/")[2])
        second_pair_page = client.get(f"/sessions/{second_session_id}/pair")
        second_left = _extract_hidden_value(second_pair_page.text, "left_card_id")
        second_right = _extract_hidden_value(second_pair_page.text, "right_card_id")
        second_pair_key = canonical_pair_key(second_left, second_right)

    assert first_pair_key != second_pair_key


def test_pair_route_redirects_to_start_notice_when_pair_space_exhausted(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SHIP_HAPPENS_RESULTS_DIR", _results_dir_for_tmp(tmp_path))
    monkeypatch.setattr("src.common.settings.PROJECT_ROOT", tmp_path)

    display_dir = tmp_path / "data" / "processed" / "display_cards"
    display_dir.mkdir(parents=True, exist_ok=True)
    for score_prefix in ("100", "99.5"):
        (display_dir / f"{score_prefix}_processed.jpg").write_bytes(b"fake")

    with TestClient(app) as client:
        first_create = client.post(
            "/sessions",
            data={"nickname": "", "pair_target_count": "1"},
            follow_redirects=False,
        )
        first_session_id = int(first_create.headers["location"].split("/")[2])
        first_pair_page = client.get(f"/sessions/{first_session_id}/pair")
        first_left = _extract_hidden_value(first_pair_page.text, "left_card_id")
        first_right = _extract_hidden_value(first_pair_page.text, "right_card_id")
        first_order = _extract_hidden_value(first_pair_page.text, "presented_order")
        first_seed = _extract_hidden_value(first_pair_page.text, "pair_seed")
        first_vote = client.post(
            f"/sessions/{first_session_id}/vote",
            data={
                "left_card_id": str(first_left),
                "right_card_id": str(first_right),
                "chosen_card_id": str(first_left),
                "presented_order": str(first_order),
                "pair_seed": str(first_seed),
            },
            follow_redirects=False,
        )
        assert first_vote.status_code == 303

        second_create = client.post(
            "/sessions",
            data={"nickname": "", "pair_target_count": "1"},
            follow_redirects=False,
        )
        second_session_id = int(second_create.headers["location"].split("/")[2])

        exhausted = client.get(f"/sessions/{second_session_id}/pair", follow_redirects=False)
        assert exhausted.status_code == 303
        assert exhausted.headers["location"] == "/sessions/start?notice=pair_selection_exhausted"

        start_page = client.get(exhausted.headers["location"])

    assert "All available unique pairs have been used." in start_page.text


def test_get_pair_redirects_to_start_when_target_met(monkeypatch, tmp_path: Path) -> None:
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
        pair_seed = _extract_hidden_value(first_pair.text, "pair_seed")

        vote = client.post(
            f"/sessions/{session_id}/vote",
            data={
                "left_card_id": str(left_card_id),
                "right_card_id": str(right_card_id),
                "chosen_card_id": str(left_card_id),
                "presented_order": str(presented_order),
                "pair_seed": str(pair_seed),
            },
            follow_redirects=False,
        )
        assert vote.status_code == 303
        assert vote.headers["location"] == "/sessions/start"

        complete_page = client.get(f"/sessions/{session_id}/complete", follow_redirects=False)
        after_complete = client.get(f"/sessions/{session_id}/pair", follow_redirects=False)

    assert complete_page.status_code == 303
    assert complete_page.headers["location"] == "/sessions/start"
    assert after_complete.status_code == 303
    assert after_complete.headers["location"] == "/sessions/start"


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
        pair_seed = _extract_hidden_value(pair_page.text, "pair_seed")

        response = client.post(
            f"/sessions/{session_id}/vote",
            data={
                "left_card_id": str(left_card_id),
                "right_card_id": str(right_card_id),
                "chosen_card_id": str(right_card_id),
                "presented_order": str(presented_order),
                "pair_seed": str(pair_seed),
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
        pair_seed = _extract_hidden_value(pair_page.text, "pair_seed")

        response = client.post(
            f"/sessions/{session_id}/vote",
            data={
                "left_card_id": str(left_card_id),
                "right_card_id": str(right_card_id),
                "chosen_card_id": str(outside_card_id),
                "presented_order": str(presented_order),
                "pair_seed": str(pair_seed),
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
        pair_seed = _extract_hidden_value(pair_page.text, "pair_seed")

        response = client.post(
            f"/sessions/{session_id}/vote",
            data={
                "left_card_id": str(left_card_id),
                "right_card_id": str(right_card_id),
                "chosen_card_id": str(left_card_id),
                "presented_order": str(presented_order),
                "pair_seed": str(pair_seed),
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/sessions/start"

    saved = load_session_result(session_id)
    assert saved is not None
    assert saved.ended_at is not None
