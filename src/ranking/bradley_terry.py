"""Bradley-Terry ranking fit for pairwise severity outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from random import Random

from src.ranking.data import RankingInput


@dataclass(slots=True)
class BradleyTerryResult:
    """Fitted Bradley-Terry card scores and metadata."""

    raw_scores: dict[int, float]
    metadata: dict[str, object]


def fit_bradley_terry(
    ranking_input: RankingInput,
    *,
    seed: int = 0,
    max_iterations: int = 500,
    tolerance: float = 1e-9,
) -> BradleyTerryResult:
    """Fit deterministic Bradley-Terry scores from pairwise worse-choice events."""
    card_ids = ranking_input.approved_card_ids
    if not card_ids:
        raise ValueError("no_approved_cards")
    if not ranking_input.events:
        raise ValueError("insufficient_comparisons")

    rng = Random(seed)
    index_by_card_id = {card_id: idx for idx, card_id in enumerate(card_ids)}
    card_count = len(card_ids)

    wins = [[0.0 for _ in range(card_count)] for _ in range(card_count)]
    total_wins = [0.0 for _ in range(card_count)]
    for event in ranking_input.events:
        if event.chosen_card_id == event.left_card_id:
            winner_id = event.left_card_id
            loser_id = event.right_card_id
        else:
            winner_id = event.chosen_card_id
            loser_id = event.left_card_id

        winner_idx = index_by_card_id[winner_id]
        loser_idx = index_by_card_id[loser_id]
        wins[winner_idx][loser_idx] += 1.0
        total_wins[winner_idx] += 1.0

    strengths = [1.0 + rng.random() * 1e-8 for _ in range(card_count)]
    converged = False
    iterations_used = 0

    for iteration in range(1, max_iterations + 1):
        updated = strengths.copy()
        max_delta = 0.0

        for i in range(card_count):
            numerator = total_wins[i]
            if numerator <= 0.0:
                updated[i] = strengths[i]
                continue

            denominator = 0.0
            for j in range(card_count):
                if i == j:
                    continue
                matches = wins[i][j] + wins[j][i]
                if matches <= 0.0:
                    continue
                denominator += matches / (strengths[i] + strengths[j])

            if denominator <= 0.0:
                updated[i] = strengths[i]
                continue

            updated[i] = numerator / denominator
            if updated[i] <= 0.0:
                updated[i] = 1e-12

            delta = abs(updated[i] - strengths[i])
            if delta > max_delta:
                max_delta = delta

        scale = sum(updated)
        if scale <= 0.0:
            raise ValueError("bradley_terry_convergence_failed")
        strengths = [value / scale for value in updated]

        iterations_used = iteration
        if max_delta < tolerance:
            converged = True
            break

    if not converged:
        raise ValueError("bradley_terry_convergence_failed")

    raw_scores = {
        card_id: strengths[index_by_card_id[card_id]] for card_id in ranking_input.approved_card_ids
    }
    vote_counts = {card_id: 0 for card_id in ranking_input.approved_card_ids}
    for event in ranking_input.events:
        vote_counts[event.left_card_id] += 1
        vote_counts[event.right_card_id] += 1

    metadata: dict[str, object] = {
        "seed": seed,
        "max_iterations": max_iterations,
        "tolerance": tolerance,
        "iterations": iterations_used,
        "converged": converged,
        "event_count": len(ranking_input.events),
        "uncertainty_proxy": {
            "type": "vote_count",
            "vote_count_by_card": vote_counts,
        },
    }
    return BradleyTerryResult(raw_scores=raw_scores, metadata=metadata)
