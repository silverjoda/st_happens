"""FastAPI app entrypoint for the human session flow."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from src.app.pairing import PairSelection, select_next_pair
from src.common.db import create_schema, session_scope
from src.common.models import Card, Comparison, SessionRecord
from src.common.settings import ensure_runtime_directories

DEFAULT_PAIR_TARGET = 20
MIN_PAIR_TARGET = 1
MAX_PAIR_TARGET = 500

_template_dir = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_template_dir))

app = FastAPI(title="Ship Happens", version="0.1.0")
logger = logging.getLogger(__name__)


def _normalize_nickname(value: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def _parse_pair_target_count(value: str) -> tuple[int | None, str | None]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, "Pair target count must be a whole number."

    if parsed < MIN_PAIR_TARGET or parsed > MAX_PAIR_TARGET:
        return (
            None,
            f"Pair target count must be between {MIN_PAIR_TARGET} and {MAX_PAIR_TARGET}.",
        )

    return parsed, None


def _render_session_start(
    request: Request,
    *,
    nickname: str = "",
    pair_target_count: str = str(DEFAULT_PAIR_TARGET),
    error: str | None = None,
):
    return templates.TemplateResponse(
        "session_start.html",
        {
            "request": request,
            "nickname": nickname,
            "pair_target_count": pair_target_count,
            "error": error,
        },
    )


def _get_human_session_or_404(session_id: int) -> SessionRecord:
    with session_scope() as session:
        record = session.get(SessionRecord, session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        if record.actor_type != "human":
            raise HTTPException(status_code=404, detail="session_not_found")
        session.expunge(record)
        return record


def _comparison_count(session_id: int) -> int:
    with session_scope() as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(Comparison)
                .where(Comparison.session_id == session_id)
            )
            or 0
        )


def _set_session_ended(session_id: int) -> None:
    with session_scope() as session:
        record = session.get(SessionRecord, session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        if record.ended_at is None:
            record.ended_at = datetime.utcnow()


def _current_pair_for_session(session_id: int) -> tuple[SessionRecord, PairSelection, int]:
    session_record = _get_human_session_or_404(session_id)
    if session_record.ended_at is not None:
        raise HTTPException(status_code=409, detail="session_already_completed")

    presented_order = _comparison_count(session_id) + 1
    if presented_order > session_record.pair_target_count:
        _set_session_ended(session_id)
        raise HTTPException(status_code=409, detail="session_already_completed")

    with session_scope() as session:
        try:
            pair = select_next_pair(session, session_id=session_id, presented_order=presented_order)
        except ValueError as exc:
            if str(exc) in {"not_enough_approved_cards", "pair_selection_exhausted"}:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            raise

    logger.info(
        "pair_selected session_id=%s presented_order=%s mode=%s seed=%s",
        session_id,
        presented_order,
        pair.mode,
        pair.seed,
    )
    return session_record, pair, presented_order


def _load_pair_by_order(session_id: int, presented_order: int) -> tuple[int, int] | None:
    with session_scope() as session:
        row = session.scalar(
            select(Comparison)
            .where(Comparison.session_id == session_id)
            .where(Comparison.presented_order == presented_order)
            .limit(1)
        )
        if row is None:
            return None
        return row.left_card_id, row.right_card_id


@app.on_event("startup")
def on_startup() -> None:
    ensure_runtime_directories()
    create_schema()


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/sessions/start", status_code=303)


@app.get("/sessions/start")
async def session_start(request: Request):
    return _render_session_start(request)


@app.post("/sessions")
async def create_session(request: Request):
    form = await request.form()

    raw_nickname = str(form.get("nickname", ""))
    raw_pair_target_count = str(form.get("pair_target_count", ""))

    pair_target_count, error = _parse_pair_target_count(raw_pair_target_count)
    if error is not None:
        return _render_session_start(
            request,
            nickname=raw_nickname,
            pair_target_count=raw_pair_target_count,
            error=error,
        )

    with session_scope() as session:
        session_record = SessionRecord(
            actor_type="human",
            nickname=_normalize_nickname(raw_nickname),
            pair_target_count=pair_target_count,
        )
        session.add(session_record)
        session.flush()
        session_id = session_record.id

    return RedirectResponse(url=f"/sessions/{session_id}/pair", status_code=303)


@app.get("/sessions/{session_id}/ready")
async def session_ready(request: Request, session_id: int):
    return templates.TemplateResponse(
        "session_ready.html",
        {
            "request": request,
            "session_id": session_id,
        },
    )


@app.get("/cards/{card_id}/image")
async def card_image(card_id: int):
    with session_scope() as session:
        card = session.get(Card, card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="card_not_found")
        image_path = Path(card.source_image_path)

    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="card_image_not_found")

    return FileResponse(path=image_path)


@app.get("/sessions/{session_id}/pair")
async def session_pair(request: Request, session_id: int):
    session_record = _get_human_session_or_404(session_id)
    if session_record.ended_at is not None:
        return RedirectResponse(url=f"/sessions/{session_id}/complete", status_code=303)

    current_count = _comparison_count(session_id)
    if current_count >= session_record.pair_target_count:
        _set_session_ended(session_id)
        return RedirectResponse(url=f"/sessions/{session_id}/complete", status_code=303)

    _, pair, presented_order = _current_pair_for_session(session_id)
    return templates.TemplateResponse(
        "pair.html",
        {
            "request": request,
            "session_id": session_id,
            "presented_order": presented_order,
            "left_card": pair.left_card,
            "right_card": pair.right_card,
            "pair_mode": pair.mode,
            "pair_seed": pair.seed,
            "total_pairs": session_record.pair_target_count,
            "current_count": current_count,
        },
    )


def _parse_response_ms(raw_value: str | None) -> int | None:
    if raw_value is None:
        return None

    normalized = raw_value.strip()
    if not normalized:
        return None

    try:
        parsed = int(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_response_ms") from exc

    if parsed < 0:
        raise HTTPException(status_code=400, detail="invalid_response_ms")

    return parsed


def _parse_required_positive_int(raw_value: str | None, *, field_name: str) -> int:
    if raw_value is None:
        raise HTTPException(status_code=400, detail=f"invalid_{field_name}")

    normalized = raw_value.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=f"invalid_{field_name}")

    try:
        parsed = int(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_{field_name}") from exc

    if parsed <= 0:
        raise HTTPException(status_code=400, detail=f"invalid_{field_name}")

    return parsed


@app.post("/sessions/{session_id}/vote")
async def session_vote(request: Request, session_id: int):
    session_record = _get_human_session_or_404(session_id)
    if session_record.ended_at is not None:
        return RedirectResponse(url=f"/sessions/{session_id}/complete", status_code=303)

    current_count = _comparison_count(session_id)
    if current_count >= session_record.pair_target_count:
        _set_session_ended(session_id)
        return RedirectResponse(url=f"/sessions/{session_id}/complete", status_code=303)

    form = await request.form()
    left_card_id = _parse_required_positive_int(form.get("left_card_id"), field_name="left_card_id")
    right_card_id = _parse_required_positive_int(
        form.get("right_card_id"), field_name="right_card_id"
    )
    chosen_card_id = _parse_required_positive_int(
        form.get("chosen_card_id"), field_name="chosen_card_id"
    )
    posted_order = _parse_required_positive_int(
        form.get("presented_order"), field_name="presented_order"
    )
    response_ms = _parse_response_ms(form.get("response_ms"))

    if posted_order > session_record.pair_target_count:
        raise HTTPException(status_code=400, detail="stale_or_invalid_pair")

    expected = _load_pair_by_order(session_id, posted_order)
    if expected is None:
        _, expected_pair, presented_order = _current_pair_for_session(session_id)
        expected_pair_set = {expected_pair.left_card.id, expected_pair.right_card.id}
    else:
        presented_order = posted_order
        expected_pair_set = {expected[0], expected[1]}

    posted_pair_set = {left_card_id, right_card_id}
    if posted_order != presented_order or posted_pair_set != expected_pair_set:
        raise HTTPException(status_code=400, detail="stale_or_invalid_pair")

    if chosen_card_id not in posted_pair_set:
        raise HTTPException(status_code=400, detail="chosen_card_not_in_pair")

    with session_scope() as session:
        comparison = Comparison(
            session_id=session_id,
            left_card_id=left_card_id,
            right_card_id=right_card_id,
            chosen_card_id=chosen_card_id,
            presented_order=presented_order,
            response_ms=response_ms,
        )
        session.add(comparison)

    new_count = current_count + 1
    if new_count >= session_record.pair_target_count:
        _set_session_ended(session_id)
        return RedirectResponse(url=f"/sessions/{session_id}/complete", status_code=303)

    return RedirectResponse(url=f"/sessions/{session_id}/pair", status_code=303)


@app.get("/sessions/{session_id}/complete")
async def session_complete(request: Request, session_id: int):
    session_record = _get_human_session_or_404(session_id)
    vote_count = _comparison_count(session_id)

    if session_record.ended_at is None and vote_count >= session_record.pair_target_count:
        _set_session_ended(session_id)
        session_record = _get_human_session_or_404(session_id)

    if session_record.ended_at is None:
        return RedirectResponse(url=f"/sessions/{session_id}/pair", status_code=303)

    return templates.TemplateResponse(
        "complete.html",
        {
            "request": request,
            "session_id": session_id,
            "vote_count": vote_count,
            "pair_target_count": session_record.pair_target_count,
        },
    )


if __name__ == "__main__":
    uvicorn.run("src.app.main:app", host="127.0.0.1", port=8000, reload=False)
