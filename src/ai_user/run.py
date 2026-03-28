"""CLI runner for AI pairwise voting sessions."""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone

from src.app.pairing import PairCard, select_next_pair
from src.common.db import create_schema, session_scope
from src.common.models import AIRunRecord, Comparison, SessionRecord
from src.common.settings import ensure_runtime_directories

DEFAULT_PROMPT_STYLE = "description_only_v1"
DEFAULT_SELECTION_STRATEGY = "warmup_random_seeded"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AI pairwise voting over approved cards.")
    parser.add_argument("--pairs", required=True, type=int, help="Number of card pairs to vote on.")
    parser.add_argument("--model", required=True, help="Model identifier used for this run.")
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature metadata for provider integration.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional deterministic seed used for pair sampling and tie-breaks.",
    )
    parser.add_argument(
        "--prompt-style",
        default=DEFAULT_PROMPT_STYLE,
        help="Prompt style metadata label for traceability.",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if args.pairs < 1:
        raise SystemExit("invalid_pairs")
    if not str(args.model).strip():
        raise SystemExit("invalid_model")
    if args.temperature < 0:
        raise SystemExit("invalid_temperature")
    if not str(args.prompt_style).strip():
        raise SystemExit("invalid_prompt_style")


def _severity_heuristic_score(text: str) -> int:
    normalized = " ".join(text.lower().split())
    tokens = normalized.split()
    keyword_bonus = (
        5 * normalized.count("die")
        + 4 * normalized.count("death")
        + 4 * normalized.count("injury")
        + 3 * normalized.count("fire")
        + 3 * normalized.count("hospital")
        + 2 * normalized.count("crash")
    )
    punctuation_bonus = normalized.count("!")
    return len(tokens) + keyword_bonus + punctuation_bonus


def _choose_worse_card_id(
    *,
    left_card: PairCard,
    right_card: PairCard,
    seed: int,
    presented_order: int,
) -> int:
    left_text = left_card.description_text or ""
    right_text = right_card.description_text or ""
    left_score = _severity_heuristic_score(left_text)
    right_score = _severity_heuristic_score(right_text)

    if left_score > right_score:
        return left_card.id
    if right_score > left_score:
        return right_card.id

    tie_rng = random.Random(seed + (presented_order * 10_007))
    return tie_rng.choice([left_card.id, right_card.id])


def run_ai_votes(
    *,
    pairs: int,
    model: str,
    temperature: float,
    seed: int | None,
    prompt_style: str,
) -> tuple[int, int]:
    """Run one AI voting session and persist comparisons + metadata."""
    ensure_runtime_directories()
    create_schema()

    normalized_model = model.strip()
    normalized_prompt_style = prompt_style.strip()
    deterministic_seed = seed if seed is not None else 0
    started_at = datetime.now(timezone.utc)

    with session_scope() as session:
        session_record = SessionRecord(
            actor_type="ai",
            nickname=f"ai:{normalized_model}",
            pair_target_count=pairs,
        )
        session.add(session_record)
        session.flush()

        metadata: dict[str, object] = {
            "model": normalized_model,
            "prompt_style": normalized_prompt_style,
            "temperature": temperature,
            "seed": seed,
            "pair_count": pairs,
            "selection_strategy": DEFAULT_SELECTION_STRATEGY,
            "session_id": session_record.id,
            "started_at": started_at.isoformat(),
        }

        run_record = AIRunRecord(
            session_id=session_record.id,
            model=normalized_model,
            prompt_style=normalized_prompt_style,
            temperature=temperature,
            seed=seed,
            pair_count=pairs,
            selection_strategy=DEFAULT_SELECTION_STRATEGY,
            config_json=json.dumps(metadata, sort_keys=True),
        )
        session.add(run_record)
        session.flush()

        comparisons_written = 0
        stop_reason: str | None = None
        for presented_order in range(1, pairs + 1):
            try:
                pair = select_next_pair(
                    session,
                    session_id=session_record.id,
                    presented_order=presented_order,
                    selection_seed_base=deterministic_seed,
                )
            except ValueError as exc:
                stop_reason = str(exc)
                break

            chosen_card_id = _choose_worse_card_id(
                left_card=pair.left_card,
                right_card=pair.right_card,
                seed=deterministic_seed,
                presented_order=presented_order,
            )
            session.add(
                Comparison(
                    session_id=session_record.id,
                    left_card_id=pair.left_card.id,
                    right_card_id=pair.right_card.id,
                    chosen_card_id=chosen_card_id,
                    presented_order=presented_order,
                    response_ms=None,
                )
            )
            comparisons_written += 1

        ended_at = datetime.now(timezone.utc)
        session_record.ended_at = ended_at.replace(tzinfo=None)
        metadata["ended_at"] = ended_at.isoformat()
        metadata["comparison_count"] = comparisons_written
        metadata["stopped_early_reason"] = stop_reason
        run_record.config_json = json.dumps(metadata, sort_keys=True)

        if comparisons_written != pairs:
            raise ValueError("insufficient_pairs_available")

        return session_record.id, run_record.id


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _validate_args(args)

    try:
        session_id, run_id = run_ai_votes(
            pairs=args.pairs,
            model=args.model,
            temperature=args.temperature,
            seed=args.seed,
            prompt_style=args.prompt_style,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"ai_run_saved session_id={session_id} run_id={run_id} pairs={args.pairs}")


if __name__ == "__main__":
    main()
