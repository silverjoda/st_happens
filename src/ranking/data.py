"""Data loading and validation helpers for ranking runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.common.models import Card, Comparison, SessionRecord

Population = Literal["human", "ai", "combined"]


@dataclass(slots=True)
class RankingEvent:
    """Single pairwise outcome event used by ranking algorithms."""

    comparison_id: int
    left_card_id: int
    right_card_id: int
    chosen_card_id: int
    created_at: datetime


@dataclass(slots=True)
class RankingInput:
    """Normalized in-memory ranking input shared by algorithms."""

    approved_card_ids: list[int]
    events: list[RankingEvent]


def load_approved_cards(session: Session) -> list[Card]:
    """Load approved cards eligible for ranking."""
    cards = list(
        session.scalars(select(Card).where(Card.status == "approved").order_by(Card.id)).all()
    )
    if not cards:
        raise ValueError("no_approved_cards")
    return cards


def load_comparisons_for_population(session: Session, population: Population) -> list[Comparison]:
    """Load comparisons filtered by actor population with deterministic ordering."""
    stmt = select(Comparison).join(SessionRecord, SessionRecord.id == Comparison.session_id)
    if population == "human":
        stmt = stmt.where(SessionRecord.actor_type == "human")
    elif population == "ai":
        stmt = stmt.where(SessionRecord.actor_type == "ai")
    elif population != "combined":
        raise ValueError("invalid_population")

    stmt = stmt.order_by(Comparison.created_at.asc(), Comparison.id.asc())
    return list(session.scalars(stmt).all())


def load_ranking_input(session: Session, population: Population) -> RankingInput:
    """Load and validate ranking input for one population."""
    approved_cards = load_approved_cards(session)
    approved_card_ids = [card.id for card in approved_cards]
    approved_set = set(approved_card_ids)

    comparisons = load_comparisons_for_population(session, population)

    events: list[RankingEvent] = []
    for comparison in comparisons:
        pair_ids = {comparison.left_card_id, comparison.right_card_id}
        if comparison.left_card_id not in approved_set:
            continue
        if comparison.right_card_id not in approved_set:
            continue
        if comparison.chosen_card_id not in pair_ids:
            continue
        if comparison.chosen_card_id not in approved_set:
            continue

        events.append(
            RankingEvent(
                comparison_id=comparison.id,
                left_card_id=comparison.left_card_id,
                right_card_id=comparison.right_card_id,
                chosen_card_id=comparison.chosen_card_id,
                created_at=comparison.created_at,
            )
        )

    if not events:
        raise ValueError("insufficient_comparisons")

    return RankingInput(approved_card_ids=approved_card_ids, events=events)
