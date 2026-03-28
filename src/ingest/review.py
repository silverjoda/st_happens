"""Interactive manual review workflow for extracted cards."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.common.db import create_schema, session_scope
from src.common.settings import PROJECT_ROOT
from src.ingest.storage import fetch_review_queue, get_card_by_id, save_review_edits


VALID_STATUSES = {"extracted", "reviewed", "approved", "needs_fix", "rejected"}
STATUS_ACTIONS = {
    "approve": "approved",
    "needs_fix": "needs_fix",
    "reject": "rejected",
}


@dataclass(slots=True)
class DraftState:
    description_text: str | None
    official_score: float | None
    dirty: bool = False


@dataclass(slots=True)
class CardSnapshot:
    id: int
    source_image_path: str
    description_text: str | None
    official_score: float | None
    ocr_confidence_desc: float | None
    ocr_confidence_score: float | None
    status: str
    updated_at: datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review extracted cards and persist edits/status")
    parser.add_argument(
        "--status",
        default="extracted",
        choices=sorted(VALID_STATUSES),
        help="Queue filter for cards with this status",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional max cards in queue")
    parser.add_argument(
        "--interactive",
        action="store_true",
        default=True,
        help="Run interactive terminal review loop (default)",
    )
    return parser.parse_args()


def _resolve_image_path(image_path: str) -> Path:
    path = Path(image_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _format_score(score: float | None) -> str:
    if score is None:
        return "None"
    if score.is_integer():
        return str(int(score))
    return str(score)


def _print_card_panel(
    card_id: int,
    index: int,
    total: int,
    run_action_counts: dict[str, int],
    source_image_path: str,
    description_text: str | None,
    official_score: float | None,
    ocr_confidence_desc: float | None,
    ocr_confidence_score: float | None,
    status: str,
    draft: DraftState,
) -> None:
    image_path = _resolve_image_path(source_image_path)
    print("\n" + "=" * 72)
    print(f"Card {index + 1}/{total} | id={card_id}")
    print(
        "Run actions: "
        f"approved={run_action_counts['approved']} "
        f"needs_fix={run_action_counts['needs_fix']} "
        f"rejected={run_action_counts['rejected']}"
    )
    print("-" * 72)
    print(f"Image: {image_path}")
    if not image_path.exists():
        print("WARNING: source image file is missing on disk")
    print(f"Status: {status}")
    print(f"Description (db): {description_text!r}")
    print(f"Score (db): {_format_score(official_score)}")
    print(f"OCR confidence description: {ocr_confidence_desc}")
    print(f"OCR confidence score: {ocr_confidence_score}")
    print("-" * 72)
    print(f"Draft description: {draft.description_text!r}")
    print(f"Draft score: {_format_score(draft.official_score)}")
    print(f"Draft dirty: {draft.dirty}")
    print("Queue order: salvage-first (partial OCR rows before fully empty rows)")
    print(
        "Commands: next prev jump <id> edit desc edit score save discard approve needs_fix reject open quit"
    )


def _open_image(image_path: Path) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(image_path)], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(image_path)], check=False)
        elif sys.platform.startswith("win"):
            subprocess.run(["cmd", "/c", "start", str(image_path)], check=False)
    except Exception as exc:
        print(f"Could not open image: {exc}")


def _parse_score_input(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("Score must be a number") from exc

    if value < 0.5 or value > 100.0:
        raise ValueError("Score must be between 0.5 and 100.0")

    doubled = value * 2
    if abs(doubled - round(doubled)) > 1e-9:
        raise ValueError("Score must use 0.5 increments")

    return round(doubled) / 2


def _load_card_snapshot(card_id: int) -> tuple[CardSnapshot, DraftState]:
    with session_scope() as session:
        card = get_card_by_id(session, card_id)
        if card is None:
            raise RuntimeError(f"Card not found: {card_id}")
        snapshot = CardSnapshot(
            id=card.id,
            source_image_path=card.source_image_path,
            description_text=card.description_text,
            official_score=card.official_score,
            ocr_confidence_desc=card.ocr_confidence_desc,
            ocr_confidence_score=card.ocr_confidence_score,
            status=card.status,
            updated_at=card.updated_at,
        )
        draft = DraftState(
            description_text=card.description_text, official_score=card.official_score
        )
        return snapshot, draft


def _persist_with_optional_status(
    card: CardSnapshot, draft: DraftState, status: str | None
) -> bool:
    with session_scope() as session:
        try:
            save_review_edits(
                session,
                card_id=card.id,
                expected_updated_at=card.updated_at,
                description_text=draft.description_text,
                official_score=draft.official_score,
                status=status,
            )
        except (RuntimeError, ValueError):
            print("Card changed since it was loaded. Please reload and retry.")
            return False
    draft.dirty = False
    return True


def _interactive_review(status: str, limit: int | None) -> None:
    with session_scope() as session:
        queue_ids = fetch_review_queue(session, status=status, limit=limit)

    if not queue_ids:
        print(f"No cards found with status='{status}'.")
        return

    idx = 0
    run_action_counts = {"approved": 0, "needs_fix": 0, "rejected": 0}

    while 0 <= idx < len(queue_ids):
        card_id = queue_ids[idx]
        card, draft = _load_card_snapshot(card_id)
        while True:
            _print_card_panel(
                card_id=card.id,
                index=idx,
                total=len(queue_ids),
                run_action_counts=run_action_counts,
                source_image_path=card.source_image_path,
                description_text=card.description_text,
                official_score=card.official_score,
                ocr_confidence_desc=card.ocr_confidence_desc,
                ocr_confidence_score=card.ocr_confidence_score,
                status=card.status,
                draft=draft,
            )

            raw = input("review> ").strip()
            if not raw:
                continue
            parts = shlex.split(raw)
            command = parts[0]

            if command == "quit":
                return
            if command == "next":
                if draft.dirty:
                    print("Unsaved draft changes. Run save/discard before moving.")
                    continue
                idx = min(idx + 1, len(queue_ids) - 1)
                break
            if command == "prev":
                if draft.dirty:
                    print("Unsaved draft changes. Run save/discard before moving.")
                    continue
                idx = max(idx - 1, 0)
                break
            if command == "jump":
                if len(parts) != 2:
                    print("Usage: jump <id>")
                    continue
                if draft.dirty:
                    print("Unsaved draft changes. Run save/discard before moving.")
                    continue
                try:
                    target_id = int(parts[1])
                except ValueError:
                    print("jump expects integer card id")
                    continue
                if target_id not in queue_ids:
                    print("Card id is not in current queue")
                    continue
                idx = queue_ids.index(target_id)
                break
            if command == "open":
                image_path = _resolve_image_path(card.source_image_path)
                _open_image(image_path)
                continue
            if command == "edit":
                if len(parts) != 2:
                    print("Usage: edit desc|score")
                    continue
                field = parts[1]
                if field == "desc":
                    new_desc = input("New description: ")
                    if not new_desc.strip():
                        confirm = input(
                            "Description is empty. Type YES to confirm blank value: "
                        ).strip()
                        if confirm != "YES":
                            print("Description edit cancelled.")
                            continue
                        draft.description_text = None
                    else:
                        draft.description_text = " ".join(new_desc.split())
                    draft.dirty = True
                    continue
                if field == "score":
                    raw_score = input("New score (0.5-100.0, step 0.5): ").strip()
                    try:
                        draft.official_score = _parse_score_input(raw_score)
                    except ValueError as exc:
                        print(str(exc))
                        continue
                    draft.dirty = True
                    continue
                print("Usage: edit desc|score")
                continue
            if command == "discard":
                draft.description_text = card.description_text
                draft.official_score = card.official_score
                draft.dirty = False
                continue
            if command == "save":
                if not draft.dirty:
                    print("No draft changes to save.")
                    continue
                if _persist_with_optional_status(card, draft, status=None):
                    card, draft = _load_card_snapshot(card.id)
                    print("Draft saved.")
                continue
            if command in STATUS_ACTIONS:
                status_value = STATUS_ACTIONS[command]
                if _persist_with_optional_status(card, draft, status=status_value):
                    run_action_counts[status_value] += 1
                    if idx < len(queue_ids) - 1:
                        idx += 1
                    break
                continue

            print("Unknown command.")


def main() -> None:
    args = parse_args()
    create_schema()
    _interactive_review(status=args.status, limit=args.limit)


if __name__ == "__main__":
    main()
