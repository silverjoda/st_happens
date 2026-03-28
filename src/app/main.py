"""FastAPI app entrypoint for the human session flow."""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from src.common.db import create_schema, session_scope
from src.common.models import SessionRecord
from src.common.settings import ensure_runtime_directories

DEFAULT_PAIR_TARGET = 20
MIN_PAIR_TARGET = 1
MAX_PAIR_TARGET = 500

_template_dir = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_template_dir))

app = FastAPI(title="Ship Happens", version="0.1.0")


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

    return RedirectResponse(url=f"/sessions/{session_id}/ready", status_code=303)


@app.get("/sessions/{session_id}/ready")
async def session_ready(request: Request, session_id: int):
    return templates.TemplateResponse(
        "session_ready.html",
        {
            "request": request,
            "session_id": session_id,
        },
    )


if __name__ == "__main__":
    uvicorn.run("src.app.main:app", host="127.0.0.1", port=8000, reload=False)
