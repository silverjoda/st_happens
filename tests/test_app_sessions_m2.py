from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.app.main import app
from src.common.db import session_scope
from src.common.models import SessionRecord


def _db_url_for_tmp(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test_app_sessions.db'}"


def _count_sessions() -> int:
    with session_scope() as session:
        return session.scalar(select(func.count()).select_from(SessionRecord)) or 0


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
    assert response.headers["location"].endswith("/ready")
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
