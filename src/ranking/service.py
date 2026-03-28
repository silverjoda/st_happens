"""Ranking normalization and persistence services."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from src.common.models import RankingResult, RankingRun

Population = Literal["human", "ai", "combined"]
Algorithm = Literal["bradley_terry", "elo"]


@dataclass(slots=True)
class RankedScore:
    """Single card score with normalized value and rank."""

    card_id: int
    raw_score: float
    normalized_score_1_100: float
    rank_position: int


def normalize_scores(raw_scores: dict[int, float]) -> tuple[list[RankedScore], dict[str, object]]:
    """Normalize raw scores to [1, 100] and assign stable rank positions."""
    if not raw_scores:
        raise ValueError("no_scores_to_normalize")

    values = list(raw_scores.values())
    min_score = min(values)
    max_score = max(values)

    metadata: dict[str, object] = {
        "normalization": "min_max_1_100",
        "normalization_min": min_score,
        "normalization_max": max_score,
    }

    normalized_by_card: dict[int, float] = {}
    if max_score == min_score:
        fallback = 50.5
        for card_id in raw_scores:
            normalized_by_card[card_id] = fallback
        metadata["normalization_degenerate"] = True
        metadata["normalization_degenerate_value"] = fallback
    else:
        span = max_score - min_score
        for card_id, raw in raw_scores.items():
            normalized_by_card[card_id] = 1.0 + ((raw - min_score) / span) * 99.0
        metadata["normalization_degenerate"] = False

    ordered = sorted(
        raw_scores.items(),
        key=lambda item: (
            -normalized_by_card[item[0]],
            -item[1],
            item[0],
        ),
    )

    ranked_scores = [
        RankedScore(
            card_id=card_id,
            raw_score=raw,
            normalized_score_1_100=normalized_by_card[card_id],
            rank_position=index,
        )
        for index, (card_id, raw) in enumerate(ordered, start=1)
    ]
    return ranked_scores, metadata


def persist_ranking_run(
    session: Session,
    *,
    population: Population,
    algorithm: Algorithm,
    config: dict[str, object],
    ranked_scores: list[RankedScore],
) -> int:
    """Persist one ranking run and all per-card results."""
    run = RankingRun(
        population=population,
        algorithm=algorithm,
        config_json=json.dumps(config, sort_keys=True),
    )
    session.add(run)
    session.flush()

    for ranked in ranked_scores:
        session.add(
            RankingResult(
                ranking_run_id=run.id,
                card_id=ranked.card_id,
                raw_score=ranked.raw_score,
                normalized_score_1_100=ranked.normalized_score_1_100,
                rank_position=ranked.rank_position,
            )
        )

    session.flush()
    return run.id
