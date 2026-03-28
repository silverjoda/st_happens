"""Card region extraction hooks."""

from __future__ import annotations

import numpy as np


def extract_card_region(image: np.ndarray) -> np.ndarray:
    """Return the detected card region; defaults to full frame."""
    return image


def split_description_and_score_regions(card_region: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split card into description and score regions."""
    height = card_region.shape[0]
    split_index = int(height * 0.8)
    split_index = min(max(split_index, 1), height - 1)
    description = card_region[:split_index, :]
    score = card_region[split_index:, :]
    return description, score
