"""Persistence helpers for ingestion outputs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from src.common.models import Card
from src.ingest.types import ExtractionResult


def persist_card_extraction(session: Session, result: ExtractionResult) -> Card:
    """Persist a single extraction result into the cards table."""
    card = Card(
        source_image_path=result.source_image_path,
        description_text=result.description_text,
        official_score=result.official_score,
        ocr_confidence_desc=result.ocr_confidence_desc,
        ocr_confidence_score=result.ocr_confidence_score,
        status=result.status,
    )
    session.add(card)
    session.flush()
    return card


def fetch_review_queue(
    session: Session,
    *,
    status: str = "extracted",
    limit: int | None = None,
) -> list[int]:
    """Return candidate card IDs for review in deterministic order."""
    description_missing = or_(
        Card.description_text.is_(None), func.trim(Card.description_text) == ""
    )
    score_missing = Card.official_score.is_(None)
    salvage_priority = case(
        (
            or_(
                and_(description_missing, Card.official_score.is_not(None)),
                and_(~description_missing, score_missing),
            ),
            0,
        ),
        (and_(description_missing, score_missing), 2),
        else_=1,
    )
    stmt = (
        select(Card.id)
        .where(Card.status == status)
        .order_by(salvage_priority.asc(), Card.created_at.asc(), Card.id.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).all())


def get_card_by_id(session: Session, card_id: int) -> Card | None:
    """Load a single card row by primary key."""
    return session.get(Card, card_id)


def save_review_edits(
    session: Session,
    *,
    card_id: int,
    expected_updated_at: datetime,
    description_text: str | None,
    official_score: float | None,
    status: str | None,
) -> Card:
    """Persist review edits if the row has not changed concurrently."""
    card = session.get(Card, card_id)
    if card is None:
        raise ValueError("card_not_found")
    if card.updated_at != expected_updated_at:
        raise RuntimeError("card_changed_since_load")

    card.description_text = description_text
    card.official_score = official_score
    if status is not None:
        card.status = status
    session.flush()
    return card
