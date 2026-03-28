"""Application settings and path helpers."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCORE_RAW_RE = re.compile(r"^(\d{1,3}(?:\.5)?)_raw$")


def get_storage_url() -> str:
    """Return the configured local storage URL."""
    configured = os.getenv("SHIP_HAPPENS_DB_URL")
    if configured:
        return configured
    default_db_path = PROJECT_ROOT / "data" / "ship_happens.db"
    return f"sqlite:///{default_db_path}"


def get_display_cards_dir() -> Path:
    """Return canonical directory for UI-safe preprocessed card images."""
    return PROJECT_ROOT / "data" / "processed" / "display_cards"


def display_card_path_for_score(score: float) -> Path:
    """Build display-card path for a card score prefix."""
    rounded = round(score * 2.0) / 2.0
    if float(rounded).is_integer():
        score_prefix = str(int(rounded))
    else:
        score_prefix = f"{rounded:.1f}".rstrip("0").rstrip(".")
    return get_display_cards_dir() / f"{score_prefix}_processed.jpg"


def display_card_path_for_source(source_image_path: str | Path) -> Path:
    """Build deterministic display-card path for a source image path."""
    source = Path(source_image_path).expanduser().resolve(strict=False)
    stem_match = SCORE_RAW_RE.match(source.stem)
    if stem_match:
        score_prefix = stem_match.group(1)
        return get_display_cards_dir() / f"{score_prefix}_processed.jpg"

    digest = hashlib.sha1(str(source).encode("utf-8")).hexdigest()
    return get_display_cards_dir() / f"{digest}.jpg"


def ensure_runtime_directories() -> None:
    """Create runtime directories required by the project."""
    (PROJECT_ROOT / "data" / "processed").mkdir(parents=True, exist_ok=True)
    get_display_cards_dir().mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "outputs").mkdir(parents=True, exist_ok=True)
