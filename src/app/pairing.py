"""Pair selection service for human voting sessions."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from src.common.settings import get_display_cards_dir

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


def _display_card_sort_key(path: Path) -> tuple[float, str]:
    stem = path.stem
    score_text = stem.removesuffix("_processed")
    try:
        numeric_score = float(score_text)
    except ValueError:
        return float("inf"), path.name
    return -numeric_score, path.name


def load_approved_cards(session: object | None = None) -> list[PairCard]:
    """Load cards eligible for human voting from display assets."""
    del session
    display_dir = get_display_cards_dir()
    cards: list[PairCard] = []
    for index, path in enumerate(
        sorted(display_dir.glob("*_processed.jpg"), key=_display_card_sort_key), start=1
    ):
        cards.append(PairCard(id=index, description_text=None, source_image_path=str(path)))

    if len(cards) < 2:
        raise ValueError("not_enough_approved_cards")
    return cards


def select_next_pair(
    session: object | None = None,
    *,
    session_id: int,
    presented_order: int,
    blocked_pair_key: str | None = None,
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
        left_card=card_lookup[chosen_left],
        right_card=card_lookup[chosen_right],
        mode=mode,
        seed=seed,
    )
