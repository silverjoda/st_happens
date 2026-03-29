"""CLI runner for AI pairwise voting sessions."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI

from src.app.pairing import PairCard, select_next_pair
from src.app.session_results import (
    append_comparison,
    create_ai_session_result,
    ensure_results_directory,
    set_session_ended,
)
from src.common.db import create_schema, session_scope
from src.common.models import AIRunRecord, Comparison, SessionRecord
from src.common.settings import ensure_runtime_directories

DEFAULT_PROMPT_STYLE = "description_only_v1"
DEFAULT_SELECTION_STRATEGY = "warmup_random_seeded"
OPENAI_MAX_ATTEMPTS = 3
CHOICE_LEFT = "left"
CHOICE_RIGHT = "right"
_VALID_CHOICES = {CHOICE_LEFT, CHOICE_RIGHT}
_CHOICE_TOKEN_RE = re.compile(r"\b(left|right)\b", flags=re.IGNORECASE)

SYSTEM_PROMPT = (
    "You are roleplaying as a careful human evaluator in a pairwise ranking task. "
    "Given two incident descriptions, choose which one is WORSE overall. "
    "Assess total harm by weighing social, physical, and mental repercussions, "
    "including downstream effects on people, families, communities, and recovery. "
    "Respond with exactly one token: LEFT or RIGHT."
)
REASONING_SYSTEM_PROMPT = (
    "You are roleplaying as a human explaining a pairwise severity choice. "
    "Provide exactly one short sentence explaining why the chosen side is worse, "
    "referencing social, physical, or mental repercussions."
)


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


def _normalize_description(text: str | None) -> str:
    normalized = " ".join((text or "").split())
    return normalized or "(No description provided.)"


def _build_user_prompt(*, left_description: str, right_description: str, prompt_style: str) -> str:
    return (
        f"Prompt style: {prompt_style}\n"
        "Task: pick the worse situation overall.\n"
        "Return exactly one token: LEFT or RIGHT.\n\n"
        f"LEFT:\n{left_description}\n\n"
        f"RIGHT:\n{right_description}"
    )


def _build_reasoning_prompt(
    *,
    left_description: str,
    right_description: str,
    chosen_side: str,
) -> str:
    return (
        "Task: explain the selected worse situation in one short sentence.\n"
        f"Chosen side: {chosen_side.upper()}\n"
        "Keep it concise and human-sounding.\n\n"
        f"LEFT:\n{left_description}\n\n"
        f"RIGHT:\n{right_description}"
    )


def _parse_choice_token(raw_response: str | None) -> str:
    if not raw_response:
        raise ValueError("invalid_ai_choice")
    match = _CHOICE_TOKEN_RE.search(raw_response)
    if match is None:
        raise ValueError("invalid_ai_choice")
    parsed = match.group(1).lower()
    if parsed not in _VALID_CHOICES:
        raise ValueError("invalid_ai_choice")
    return parsed


def _normalize_reasoning_text(raw_reasoning: str | None) -> str:
    normalized = " ".join((raw_reasoning or "").split())
    if not normalized:
        raise ValueError("invalid_ai_reasoning")
    match = re.search(r"(.+?[.!?])(?:\s|$)", normalized)
    if match is not None:
        return match.group(1)
    return f"{normalized}."


def _fallback_severity_score(text: str) -> int:
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


def _fallback_choice_side(
    *,
    left_description: str,
    right_description: str,
    seed: int | None,
    presented_order: int,
) -> str:
    left_score = _fallback_severity_score(left_description)
    right_score = _fallback_severity_score(right_description)
    if left_score > right_score:
        return CHOICE_LEFT
    if right_score > left_score:
        return CHOICE_RIGHT

    tie_seed = (seed or 0) + (presented_order * 10_007)
    tie_rng = random.Random(tie_seed)
    return tie_rng.choice([CHOICE_LEFT, CHOICE_RIGHT])


def _pick_worse_side_with_openai(
    *,
    client: OpenAI,
    model: str,
    temperature: float,
    prompt_style: str,
    seed: int | None,
    presented_order: int,
    left_card: PairCard,
    right_card: PairCard,
) -> str:
    left_description = _normalize_description(left_card.description_text)
    right_description = _normalize_description(right_card.description_text)
    user_prompt = _build_user_prompt(
        left_description=left_description,
        right_description=right_description,
        prompt_style=prompt_style,
    )
    for _attempt in range(1, OPENAI_MAX_ATTEMPTS + 1):
        try:
            response = client.responses.create(
                model=model,
                temperature=temperature,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_prompt}],
                    },
                ],
            )
            return _parse_choice_token(response.output_text)
        except Exception:
            continue

    return _fallback_choice_side(
        left_description=left_description,
        right_description=right_description,
        seed=seed,
        presented_order=presented_order,
    )


def _fallback_reasoning(chosen_side: str) -> str:
    return (
        f"I chose {chosen_side.upper()} because it appears to cause greater overall social, "
        "physical, and mental harm."
    )


def _request_reasoning_with_openai(
    *,
    client: OpenAI,
    model: str,
    temperature: float,
    chosen_side: str,
    left_card: PairCard,
    right_card: PairCard,
) -> str:
    left_description = _normalize_description(left_card.description_text)
    right_description = _normalize_description(right_card.description_text)
    reasoning_prompt = _build_reasoning_prompt(
        left_description=left_description,
        right_description=right_description,
        chosen_side=chosen_side,
    )
    for _attempt in range(1, OPENAI_MAX_ATTEMPTS + 1):
        try:
            response = client.responses.create(
                model=model,
                temperature=temperature,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": REASONING_SYSTEM_PROMPT}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": reasoning_prompt}],
                    },
                ],
            )
            return _normalize_reasoning_text(response.output_text)
        except Exception:
            continue
    return _fallback_reasoning(chosen_side)


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
    ensure_results_directory()
    create_schema()

    normalized_model = model.strip()
    normalized_prompt_style = prompt_style.strip()
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("missing_openai_api_key")

    client = OpenAI(api_key=api_key)
    started_at = datetime.now(timezone.utc)
    file_session = create_ai_session_result(
        nickname=f"ai:{normalized_model}",
        pair_target_count=pairs,
    )

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
            "provider": "openai",
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
                    selection_seed_base=seed,
                )
            except ValueError as exc:
                stop_reason = str(exc)
                break

            chosen_side = _pick_worse_side_with_openai(
                client=client,
                model=normalized_model,
                temperature=temperature,
                prompt_style=normalized_prompt_style,
                seed=seed,
                presented_order=presented_order,
                left_card=pair.left_card,
                right_card=pair.right_card,
            )
            reasoning = _request_reasoning_with_openai(
                client=client,
                model=normalized_model,
                temperature=temperature,
                chosen_side=chosen_side,
                left_card=pair.left_card,
                right_card=pair.right_card,
            )
            chosen_card_id = pair.left_card.id if chosen_side == CHOICE_LEFT else pair.right_card.id
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
            append_comparison(
                file_session,
                left_card_id=pair.left_card.id,
                right_card_id=pair.right_card.id,
                left_card_description=pair.left_card.description_text,
                right_card_description=pair.right_card.description_text,
                chosen_card_id=chosen_card_id,
                presented_order=presented_order,
                response_ms=None,
                reasoning=reasoning,
            )
            comparisons_written += 1

        ended_at = datetime.now(timezone.utc)
        session_record.ended_at = ended_at.replace(tzinfo=None)
        metadata["ended_at"] = ended_at.isoformat()
        metadata["comparison_count"] = comparisons_written
        metadata["stopped_early_reason"] = stop_reason
        metadata["file_session_id"] = file_session.session_id
        run_record.config_json = json.dumps(metadata, sort_keys=True)
        set_session_ended(file_session)

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
