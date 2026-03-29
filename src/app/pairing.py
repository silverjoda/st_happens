"""Pair selection service for human voting sessions."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from src.common.settings import PROJECT_ROOT, get_display_cards_dir

WARMUP_PAIR_COUNT = 20
OCR_RESULTS_PATH = PROJECT_ROOT / "outputs" / "ocr_test_claude_results.json"


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


def _parse_score_prefix(path: Path) -> float | None:
    stem = path.stem
    score_text = stem.removesuffix("_processed")
    try:
        return float(score_text)
    except ValueError:
        return None


def _load_description_by_score() -> dict[float, str]:
    if not OCR_RESULTS_PATH.exists():
        return {}

    payload = json.loads(OCR_RESULTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return {}

    descriptions: dict[float, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        raw_score = item.get("score")
        raw_description = item.get("description")
        if raw_score is None:
            continue
        try:
            score = round(float(raw_score) * 2.0) / 2.0
        except (TypeError, ValueError):
            continue
        if raw_description is None:
            continue
        description = str(raw_description)
        descriptions[score] = description
    return descriptions


def load_approved_cards(session: object | None = None) -> list[PairCard]:
    """Load cards eligible for voting from display assets + OCR artifact descriptions."""
    del session

    display_dir = get_display_cards_dir()
    description_by_score = _load_description_by_score()
    cards: list[PairCard] = []
    for index, path in enumerate(
        sorted(display_dir.glob("*_processed.jpg"), key=_display_card_sort_key), start=1
    ):
        score = _parse_score_prefix(path)
        description_text = None
        if score is not None:
            description_text = description_by_score.get(score)
        cards.append(
            PairCard(
                id=index,
                description_text=description_text,
                source_image_path=str(path),
            )
        )

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
    excluded_pair_keys: set[str] | None = None,
    session_pair_history: list[tuple[int, int]] | None = None,
) -> PairSelection:
    """Select next card pair with warm-up random strategy and repeat guards."""
    del session_id
    cards = load_approved_cards(session)
    card_ids = [card.id for card in cards]
    card_lookup = {card.id: card for card in cards}

    if presented_order <= WARMUP_PAIR_COUNT:
        mode = "warmup_random"
    else:
        mode = "warmup_random"
    if selection_seed_base is None:
        seed = random.SystemRandom().randrange(1, 2**63)
        rng = random.Random(seed + presented_order)
    else:
        seed = selection_seed_base
        rng = random.Random(seed + presented_order)

    blocked_keys = set(excluded_pair_keys or set())
    if blocked_pair_key is not None:
        blocked_keys.add(blocked_pair_key)

    history = session_pair_history or []
    total_counts: dict[int, int] = {card_id: 0 for card_id in card_ids}
    left_counts: dict[int, int] = {card_id: 0 for card_id in card_ids}
    right_counts: dict[int, int] = {card_id: 0 for card_id in card_ids}
    for left_id, right_id in history:
        if left_id in total_counts:
            total_counts[left_id] += 1
            left_counts[left_id] += 1
        if right_id in total_counts:
            total_counts[right_id] += 1
            right_counts[right_id] += 1

    available_pairs: list[tuple[int, int, str]] = []
    for first_id, second_id in combinations(card_ids, 2):
        pair_key = canonical_pair_key(first_id, second_id)
        if pair_key in blocked_keys:
            continue
        available_pairs.append((first_id, second_id, pair_key))

    if not available_pairs:
        raise ValueError("pair_selection_exhausted")

    ranked_pairs: list[tuple[tuple[int, int], tuple[int, int, str]]] = []
    for first_id, second_id, pair_key in available_pairs:
        load_score = max(total_counts[first_id] + 1, total_counts[second_id] + 1)
        sum_score = total_counts[first_id] + total_counts[second_id]
        ranked_pairs.append(((load_score, sum_score), (first_id, second_id, pair_key)))

    best_score = min(score for score, _ in ranked_pairs)
    best_pairs = [pair for score, pair in ranked_pairs if score == best_score]
    first_id, second_id, _ = rng.choice(best_pairs)

    left_first_imbalance = abs((left_counts[first_id] + 1) - right_counts[first_id]) + abs(
        left_counts[second_id] - (right_counts[second_id] + 1)
    )
    left_second_imbalance = abs((left_counts[second_id] + 1) - right_counts[second_id]) + abs(
        left_counts[first_id] - (right_counts[first_id] + 1)
    )

    if left_first_imbalance < left_second_imbalance:
        chosen_left, chosen_right = first_id, second_id
    elif left_second_imbalance < left_first_imbalance:
        chosen_left, chosen_right = second_id, first_id
    else:
        if rng.random() < 0.5:
            chosen_left, chosen_right = first_id, second_id
        else:
            chosen_left, chosen_right = second_id, first_id

    return PairSelection(
        left_card=card_lookup[chosen_left],
        right_card=card_lookup[chosen_right],
        mode=mode,
        seed=seed,
    )
