"""Card selection helpers for downstream ranking inputs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.common.models import Card


def get_approved_cards(session: Session) -> list[Card]:
    """Return cards eligible for ranking; only approved rows are included."""
    cards = list(
        session.scalars(select(Card).where(Card.status == "approved").order_by(Card.id)).all()
    )
    if not cards:
        raise ValueError("no_approved_cards")
    return cards
