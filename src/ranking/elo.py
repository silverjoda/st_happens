"""Elo baseline ranking for pairwise severity outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from src.ranking.data import RankingInput

DEFAULT_INITIAL_RATING = 1500.0


@dataclass(slots=True)
class EloResult:
    """Final Elo scores and metadata."""

    raw_scores: dict[int, float]
    metadata: dict[str, object]


def fit_elo(
    ranking_input: RankingInput,
    *,
    k_factor: float = 24.0,
    initial_rating: float = DEFAULT_INITIAL_RATING,
) -> EloResult:
    """Run deterministic Elo updates in comparison created-order."""
    if not ranking_input.approved_card_ids:
        raise ValueError("no_approved_cards")
    if not ranking_input.events:
        raise ValueError("insufficient_comparisons")
    if k_factor <= 0:
        raise ValueError("invalid_k_factor")

    ratings = {card_id: float(initial_rating) for card_id in ranking_input.approved_card_ids}

    for event in ranking_input.events:
        left = event.left_card_id
        right = event.right_card_id

        if event.chosen_card_id == left:
            winner = left
            loser = right
        else:
            winner = right
            loser = left

        winner_rating = ratings[winner]
        loser_rating = ratings[loser]

        expected_winner = 1.0 / (1.0 + 10.0 ** ((loser_rating - winner_rating) / 400.0))
        delta = k_factor * (1.0 - expected_winner)

        ratings[winner] = winner_rating + delta
        ratings[loser] = loser_rating - delta

    metadata: dict[str, object] = {
        "k_factor": k_factor,
        "initial_rating": initial_rating,
        "ordering_rule": "comparisons.created_at_asc_then_id_asc",
        "event_count": len(ranking_input.events),
    }
    return EloResult(raw_scores=ratings, metadata=metadata)
