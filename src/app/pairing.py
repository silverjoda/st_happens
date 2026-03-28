"""Pair selection service for human voting sessions."""

from __future__ import annotations

import random
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.common.models import Card, Comparison

WARMUP_PAIR_COUNT = 20


@dataclass(slots=True)
class PairSelection:
    """Selected card pair plus reproducibility metadata."""

    left_card: PairCard
    right_card: PairCard
    mode: str
    seed: int


@dataclass(slots=True)
class PairCard:
    """Detached-safe card payload for template rendering."""

    id: int
    description_text: str | None
    source_image_path: str


def canonical_pair_key(left_card_id: int, right_card_id: int) -> str:
    """Build pair key independent of left/right order."""
    low, high = sorted((left_card_id, right_card_id))
    return f"{low}:{high}"


def load_approved_cards(session: Session) -> list[Card]:
    """Load cards eligible for human voting."""
    cards = list(
        session.scalars(select(Card).where(Card.status == "approved").order_by(Card.id)).all()
    )
    if len(cards) < 2:
        raise ValueError("not_enough_approved_cards")
    return cards


def _to_pair_card(card: Card) -> PairCard:
    return PairCard(
        id=card.id,
        description_text=card.description_text,
        source_image_path=card.source_image_path,
    )


def _last_pair_key(session: Session, session_id: int) -> str | None:
    last = session.scalar(
        select(Comparison)
        .where(Comparison.session_id == session_id)
        .order_by(Comparison.presented_order.desc())
        .limit(1)
    )
    if last is None:
        return None
    return canonical_pair_key(last.left_card_id, last.right_card_id)


def select_next_pair(
    session: Session,
    *,
    session_id: int,
    presented_order: int,
    selection_seed_base: int | None = None,
) -> PairSelection:
    """Select next card pair with warm-up random strategy and repeat guards."""
    cards = load_approved_cards(session)
    card_ids = [card.id for card in cards]
    card_lookup = {card.id: card for card in cards}

    if presented_order <= WARMUP_PAIR_COUNT:
        mode = "warmup_random"
    else:
        mode = "warmup_random"
    seed = session_id if selection_seed_base is None else selection_seed_base
    rng = random.Random(seed + presented_order)
    blocked_pair_key = _last_pair_key(session, session_id)

    max_attempts = max(8, len(card_ids) * 2)
    chosen_pair_key: str | None = None
    chosen_left: int | None = None
    chosen_right: int | None = None

    for _ in range(max_attempts):
        left_id, right_id = rng.sample(card_ids, 2)
        pair_key = canonical_pair_key(left_id, right_id)
        if pair_key == blocked_pair_key:
            continue

        chosen_left = left_id
        chosen_right = right_id
        chosen_pair_key = pair_key
        break

    if chosen_pair_key is None:
        for left_id in card_ids:
            for right_id in card_ids:
                if left_id == right_id:
                    continue
                pair_key = canonical_pair_key(left_id, right_id)
                if pair_key == blocked_pair_key:
                    continue
                chosen_left = left_id
                chosen_right = right_id
                chosen_pair_key = pair_key
                break
            if chosen_pair_key is not None:
                break

    if chosen_pair_key is None or chosen_left is None or chosen_right is None:
        raise ValueError("pair_selection_exhausted")

    return PairSelection(
        left_card=_to_pair_card(card_lookup[chosen_left]),
        right_card=_to_pair_card(card_lookup[chosen_right]),
        mode=mode,
        seed=seed,
    )
