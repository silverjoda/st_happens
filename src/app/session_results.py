"""File-backed storage for human session voting results."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.common.settings import PROJECT_ROOT


@dataclass(slots=True)
class SessionComparison:
    left_card_id: int
    right_card_id: int
    left_card_description: str | None
    right_card_description: str | None
    chosen_card_id: int
    presented_order: int
    response_ms: int | None
    reasoning: str | None
    created_at: str


@dataclass(slots=True)
class SessionResult:
    session_id: int
    actor_type: str
    nickname: str | None
    pair_target_count: int
    started_at: str
    ended_at: str | None
    comparisons: list[SessionComparison]
    pending_pair: SessionPendingPair | None


@dataclass(slots=True)
class SessionPendingPair:
    left_card_id: int
    right_card_id: int
    presented_order: int
    seed: int
    created_at: str


_SESSION_FILENAME_RE = re.compile(r"^session_(\d+)\.json$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _results_dir() -> Path:
    configured = os.getenv("SHIP_HAPPENS_RESULTS_DIR")
    if configured:
        return Path(configured)
    return PROJECT_ROOT / "outputs" / "session_results"


def ensure_results_directory() -> Path:
    target = _results_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target


def _session_path(session_id: int) -> Path:
    return ensure_results_directory() / f"session_{session_id}.json"


def _next_session_id() -> int:
    current_max = 0
    for path in ensure_results_directory().glob("session_*.json"):
        match = _SESSION_FILENAME_RE.match(path.name)
        if match is None:
            continue
        current_max = max(current_max, int(match.group(1)))
    return current_max + 1


def _from_dict(payload: dict[str, object]) -> SessionResult:
    raw_comparisons = payload.get("comparisons", [])
    comparisons: list[SessionComparison] = []
    if isinstance(raw_comparisons, list):
        for row in raw_comparisons:
            if not isinstance(row, dict):
                continue
            comparisons.append(
                SessionComparison(
                    left_card_id=int(row["left_card_id"]),
                    right_card_id=int(row["right_card_id"]),
                    left_card_description=(
                        str(row["left_card_description"])
                        if row.get("left_card_description") is not None
                        else None
                    ),
                    right_card_description=(
                        str(row["right_card_description"])
                        if row.get("right_card_description") is not None
                        else None
                    ),
                    chosen_card_id=int(row["chosen_card_id"]),
                    presented_order=int(row["presented_order"]),
                    response_ms=(
                        int(row["response_ms"]) if row.get("response_ms") is not None else None
                    ),
                    reasoning=(str(row["reasoning"]) if row.get("reasoning") is not None else None),
                    created_at=str(row["created_at"]),
                )
            )

    pending_payload = payload.get("pending_pair")
    pending_pair: SessionPendingPair | None = None
    if isinstance(pending_payload, dict):
        seed_value = pending_payload.get("seed")
        if seed_value is not None:
            pending_pair = SessionPendingPair(
                left_card_id=int(pending_payload["left_card_id"]),
                right_card_id=int(pending_payload["right_card_id"]),
                presented_order=int(pending_payload["presented_order"]),
                seed=int(seed_value),
                created_at=str(pending_payload["created_at"]),
            )

    return SessionResult(
        session_id=int(payload["session_id"]),
        actor_type=str(payload["actor_type"]),
        nickname=(str(payload["nickname"]) if payload.get("nickname") is not None else None),
        pair_target_count=int(payload["pair_target_count"]),
        started_at=str(payload["started_at"]),
        ended_at=(str(payload["ended_at"]) if payload.get("ended_at") is not None else None),
        comparisons=comparisons,
        pending_pair=pending_pair,
    )


def save_session_result(result: SessionResult) -> None:
    path = _session_path(result.session_id)
    path.write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_session_result(session_id: int) -> SessionResult | None:
    path = _session_path(session_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return _from_dict(payload)


def create_human_session_result(nickname: str | None, pair_target_count: int) -> SessionResult:
    return _create_session_result(
        actor_type="human",
        nickname=nickname,
        pair_target_count=pair_target_count,
    )


def create_ai_session_result(nickname: str | None, pair_target_count: int) -> SessionResult:
    return _create_session_result(
        actor_type="ai",
        nickname=nickname,
        pair_target_count=pair_target_count,
    )


def _create_session_result(
    *,
    actor_type: str,
    nickname: str | None,
    pair_target_count: int,
) -> SessionResult:
    result = SessionResult(
        session_id=_next_session_id(),
        actor_type=actor_type,
        nickname=nickname,
        pair_target_count=pair_target_count,
        started_at=_utc_now_iso(),
        ended_at=None,
        comparisons=[],
        pending_pair=None,
    )
    save_session_result(result)
    return result


def comparison_count(result: SessionResult) -> int:
    return len(result.comparisons)


def set_session_ended(result: SessionResult) -> SessionResult:
    if result.ended_at is None:
        result.ended_at = _utc_now_iso()
        save_session_result(result)
    return result


def get_pair_by_order(result: SessionResult, presented_order: int) -> tuple[int, int] | None:
    for row in result.comparisons:
        if row.presented_order == presented_order:
            return row.left_card_id, row.right_card_id
    return None


def last_pair_key(result: SessionResult) -> str | None:
    if not result.comparisons:
        return None
    last = max(result.comparisons, key=lambda row: row.presented_order)
    low, high = sorted((last.left_card_id, last.right_card_id))
    return f"{low}:{high}"


def append_comparison(
    result: SessionResult,
    *,
    left_card_id: int,
    right_card_id: int,
    left_card_description: str | None = None,
    right_card_description: str | None = None,
    chosen_card_id: int,
    presented_order: int,
    response_ms: int | None,
    reasoning: str | None = None,
) -> SessionResult:
    for row in result.comparisons:
        if row.presented_order == presented_order:
            raise ValueError("duplicate_presented_order")

    result.comparisons.append(
        SessionComparison(
            left_card_id=left_card_id,
            right_card_id=right_card_id,
            left_card_description=left_card_description,
            right_card_description=right_card_description,
            chosen_card_id=chosen_card_id,
            presented_order=presented_order,
            response_ms=response_ms,
            reasoning=reasoning,
            created_at=_utc_now_iso(),
        )
    )
    result.pending_pair = None
    save_session_result(result)
    return result


def set_pending_pair(
    result: SessionResult,
    *,
    left_card_id: int,
    right_card_id: int,
    presented_order: int,
    seed: int,
) -> SessionResult:
    result.pending_pair = SessionPendingPair(
        left_card_id=left_card_id,
        right_card_id=right_card_id,
        presented_order=presented_order,
        seed=seed,
        created_at=_utc_now_iso(),
    )
    save_session_result(result)
    return result


def pending_pair_for_order(
    result: SessionResult, presented_order: int
) -> tuple[int, int, int] | None:
    pending = result.pending_pair
    if pending is None or pending.presented_order != presented_order:
        return None
    return pending.left_card_id, pending.right_card_id, pending.seed


def all_used_human_pair_keys() -> set[str]:
    used: set[str] = set()
    for path in ensure_results_directory().glob("session_*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        if payload.get("actor_type") != "human":
            continue
        session = _from_dict(payload)
        for row in session.comparisons:
            low, high = sorted((row.left_card_id, row.right_card_id))
            used.add(f"{low}:{high}")
        if session.pending_pair is not None:
            low, high = sorted(
                (session.pending_pair.left_card_id, session.pending_pair.right_card_id)
            )
            used.add(f"{low}:{high}")
    return used
