"""FastAPI app entrypoint for the human session flow."""

from __future__ import annotations

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from src.app.pairing import PairSelection, load_approved_cards, select_next_pair
from src.app.session_results import (
    all_used_human_pair_keys,
    SessionResult,
    append_comparison,
    comparison_count,
    create_human_session_result,
    ensure_results_directory,
    get_pair_by_order,
    last_pair_key,
    load_session_result,
    pending_pair_for_order,
    set_pending_pair,
    set_session_ended,
)
from src.common.settings import ensure_runtime_directories

DEFAULT_PAIR_TARGET = 20
MIN_PAIR_TARGET = 1
MAX_PAIR_TARGET = 500
SESSION_START_PATH = "/sessions/start"

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
    notice: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "session_start.html",
        {
            "nickname": nickname,
            "pair_target_count": pair_target_count,
            "error": error,
            "notice": notice,
        },
    )


def _start_notice_message(notice_code: str | None) -> str | None:
    messages = {
        "pair_selection_exhausted": "All available unique pairs have been used. Add more cards or reset pair history to continue.",
        "not_enough_approved_cards": "Need at least two approved cards before starting a session.",
    }
    if notice_code is None:
        return None
    return messages.get(notice_code)


def _get_human_session_or_404(session_id: int) -> SessionResult:
    record = load_session_result(session_id)
    if record is None or record.actor_type != "human":
        raise HTTPException(status_code=404, detail="session_not_found")
    return record


def _comparison_count(session_id: int) -> int:
    record = _get_human_session_or_404(session_id)
    return comparison_count(record)


def _set_session_ended(session_id: int) -> None:
    record = _get_human_session_or_404(session_id)
    set_session_ended(record)


def _current_pair_for_session(
    session_id: int,
    *,
    selection_seed_base: int | None = None,
) -> tuple[SessionResult, PairSelection, int]:
    session_record = _get_human_session_or_404(session_id)
    if session_record.ended_at is not None:
        raise HTTPException(status_code=409, detail="session_already_completed")

    presented_order = _comparison_count(session_id) + 1
    if presented_order > session_record.pair_target_count:
        _set_session_ended(session_id)
        raise HTTPException(status_code=409, detail="session_already_completed")

    pending_pair = pending_pair_for_order(session_record, presented_order)
    if pending_pair is not None:
        left_card_id, right_card_id, pair_seed = pending_pair
        cards = load_approved_cards()
        card_lookup = {card.id: card for card in cards}
        left_card = card_lookup.get(left_card_id)
        right_card = card_lookup.get(right_card_id)
        if left_card is not None and right_card is not None:
            return (
                session_record,
                PairSelection(
                    left_card=left_card,
                    right_card=right_card,
                    mode="warmup_random",
                    seed=pair_seed,
                ),
                presented_order,
            )

    excluded_pair_keys = all_used_human_pair_keys()
    try:
        pair = select_next_pair(
            session_id=session_id,
            presented_order=presented_order,
            blocked_pair_key=last_pair_key(session_record),
            selection_seed_base=selection_seed_base,
            excluded_pair_keys=excluded_pair_keys,
            session_pair_history=[
                (row.left_card_id, row.right_card_id) for row in session_record.comparisons
            ],
        )
    except ValueError as exc:
        if str(exc) in {"not_enough_approved_cards", "pair_selection_exhausted"}:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise

    set_pending_pair(
        session_record,
        left_card_id=pair.left_card.id,
        right_card_id=pair.right_card.id,
        presented_order=presented_order,
        seed=pair.seed,
    )

    logger.info(
        "pair_selected session_id=%s presented_order=%s mode=%s seed=%s",
        session_id,
        presented_order,
        pair.mode,
        pair.seed,
    )
    return session_record, pair, presented_order


def _load_pair_by_order(session_id: int, presented_order: int) -> tuple[int, int] | None:
    record = _get_human_session_or_404(session_id)
    return get_pair_by_order(record, presented_order)


@app.on_event("startup")
def on_startup() -> None:
    ensure_runtime_directories()
    ensure_results_directory()


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url=SESSION_START_PATH, status_code=303)


@app.get("/sessions/start")
async def session_start(request: Request):
    notice_code = request.query_params.get("notice")
    return _render_session_start(request, notice=_start_notice_message(notice_code))


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

    session_record = create_human_session_result(
        nickname=_normalize_nickname(raw_nickname),
        pair_target_count=pair_target_count,
    )
    session_id = session_record.session_id

    return RedirectResponse(url=f"/sessions/{session_id}/pair", status_code=303)


@app.get("/sessions/{session_id}/ready")
async def session_ready(request: Request, session_id: int):
    return templates.TemplateResponse(
        request,
        "session_ready.html",
        {
            "session_id": session_id,
        },
    )


@app.get("/cards/{card_id}/image")
async def card_image(card_id: int):
    cards = load_approved_cards()
    card = next((entry for entry in cards if entry.id == card_id), None)
    if card is None:
        raise HTTPException(status_code=404, detail="card_not_found")

    return FileResponse(path=card.source_image_path)


@app.get("/sessions/{session_id}/pair")
async def session_pair(request: Request, session_id: int):
    session_record = _get_human_session_or_404(session_id)
    if session_record.ended_at is not None:
        return RedirectResponse(url=SESSION_START_PATH, status_code=303)

    current_count = _comparison_count(session_id)
    if current_count >= session_record.pair_target_count:
        _set_session_ended(session_id)
        return RedirectResponse(url=SESSION_START_PATH, status_code=303)

    try:
        _, pair, presented_order = _current_pair_for_session(session_id)
    except HTTPException as exc:
        if exc.status_code == 400 and str(exc.detail) in {
            "pair_selection_exhausted",
            "not_enough_approved_cards",
        }:
            return RedirectResponse(
                url=f"{SESSION_START_PATH}?notice={exc.detail}",
                status_code=303,
            )
        raise
    return templates.TemplateResponse(
        request,
        "pair.html",
        {
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
        return RedirectResponse(url=SESSION_START_PATH, status_code=303)

    current_count = _comparison_count(session_id)
    if current_count >= session_record.pair_target_count:
        _set_session_ended(session_id)
        return RedirectResponse(url=SESSION_START_PATH, status_code=303)

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
    pair_seed = _parse_required_positive_int(form.get("pair_seed"), field_name="pair_seed")
    response_ms = _parse_response_ms(form.get("response_ms"))

    if posted_order > session_record.pair_target_count:
        raise HTTPException(status_code=400, detail="stale_or_invalid_pair")

    expected = _load_pair_by_order(session_id, posted_order)
    if expected is None:
        pending_pair = pending_pair_for_order(session_record, posted_order)
        if pending_pair is None:
            raise HTTPException(status_code=400, detail="stale_or_invalid_pair")
        pending_left_card_id, pending_right_card_id, pending_seed = pending_pair
        if pair_seed != pending_seed:
            raise HTTPException(status_code=400, detail="stale_or_invalid_pair")
        presented_order = posted_order
        expected_pair_set = {pending_left_card_id, pending_right_card_id}
    else:
        presented_order = posted_order
        expected_pair_set = {expected[0], expected[1]}

    posted_pair_set = {left_card_id, right_card_id}
    if posted_order != presented_order or posted_pair_set != expected_pair_set:
        raise HTTPException(status_code=400, detail="stale_or_invalid_pair")

    if chosen_card_id not in posted_pair_set:
        raise HTTPException(status_code=400, detail="chosen_card_not_in_pair")

    session_record = _get_human_session_or_404(session_id)
    cards = load_approved_cards()
    card_lookup = {card.id: card for card in cards}
    left_description = (
        card_lookup.get(left_card_id).description_text if left_card_id in card_lookup else None
    )
    right_description = (
        card_lookup.get(right_card_id).description_text if right_card_id in card_lookup else None
    )
    try:
        append_comparison(
            session_record,
            left_card_id=left_card_id,
            right_card_id=right_card_id,
            left_card_description=left_description,
            right_card_description=right_description,
            chosen_card_id=chosen_card_id,
            presented_order=presented_order,
            response_ms=response_ms,
        )
    except ValueError as exc:
        if str(exc) == "duplicate_presented_order":
            raise HTTPException(status_code=400, detail="stale_or_invalid_pair") from exc
        raise

    new_count = current_count + 1
    if new_count >= session_record.pair_target_count:
        _set_session_ended(session_id)
        return RedirectResponse(url=SESSION_START_PATH, status_code=303)

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
    return RedirectResponse(url=SESSION_START_PATH, status_code=303)


if __name__ == "__main__":
    uvicorn.run("src.app.main:app", host="127.0.0.1", port=8000, reload=False)
