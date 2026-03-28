"""CLI runner for ranking computation and persistence."""

from __future__ import annotations

import argparse

from src.common.db import create_schema, session_scope
from src.ranking.bradley_terry import fit_bradley_terry
from src.ranking.data import Population, load_ranking_input
from src.ranking.elo import fit_elo
from src.ranking.service import normalize_scores, persist_ranking_run

Algorithm = str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute and persist card severity rankings.")
    parser.add_argument(
        "--population",
        required=True,
        choices=["human", "ai", "combined"],
        help="Actor population to include in the ranking run.",
    )
    parser.add_argument(
        "--algorithm",
        required=True,
        choices=["bradley_terry", "elo"],
        help="Ranking algorithm to execute.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Deterministic seed used by algorithms that require initialization.",
    )
    parser.add_argument(
        "--k-factor",
        type=float,
        default=24.0,
        help="Elo K factor (only used when --algorithm elo).",
    )
    return parser


def _run_algorithm(
    *,
    algorithm: Algorithm,
    ranking_input,
    seed: int,
    k_factor: float,
) -> tuple[dict[int, float], dict[str, object]]:
    if algorithm == "bradley_terry":
        result = fit_bradley_terry(ranking_input, seed=seed)
        return result.raw_scores, result.metadata
    if algorithm == "elo":
        result = fit_elo(ranking_input, k_factor=k_factor)
        return result.raw_scores, result.metadata
    raise SystemExit("invalid_algorithm")


def run_ranking(
    *,
    population: Population,
    algorithm: Algorithm,
    seed: int,
    k_factor: float,
) -> int:
    """Run one ranking computation and persist outputs."""
    create_schema()
    with session_scope() as session:
        ranking_input = load_ranking_input(session, population)
        raw_scores, algorithm_metadata = _run_algorithm(
            algorithm=algorithm,
            ranking_input=ranking_input,
            seed=seed,
            k_factor=k_factor,
        )
        ranked_scores, normalization_metadata = normalize_scores(raw_scores)

        config: dict[str, object] = {
            "seed": seed,
            "population": population,
            "algorithm": algorithm,
            "approved_card_count": len(ranking_input.approved_card_ids),
            "comparison_event_count": len(ranking_input.events),
            "algorithm_config": algorithm_metadata,
            "normalization": normalization_metadata,
        }
        if algorithm == "elo":
            config["k_factor"] = k_factor

        return persist_ranking_run(
            session,
            population=population,
            algorithm=algorithm,
            config=config,
            ranked_scores=ranked_scores,
        )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        run_id = run_ranking(
            population=args.population,
            algorithm=args.algorithm,
            seed=args.seed,
            k_factor=args.k_factor,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(
        f"ranking_run_saved run_id={run_id} population={args.population} algorithm={args.algorithm}"
    )


if __name__ == "__main__":
    main()
