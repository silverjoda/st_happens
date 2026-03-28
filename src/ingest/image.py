"""Image loading and preprocessing helpers."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def load_image(image_path: Path) -> np.ndarray:
    """Load an image from disk and raise on failure."""
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError("unable_to_load_image")
    return image


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """Apply a lightweight preprocessing pass for OCR."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    processed = cv2.GaussianBlur(gray, (3, 3), 0)
    return processed
