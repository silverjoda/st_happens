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


def preprocess_score_recovery(image: np.ndarray) -> np.ndarray:
    """Apply deterministic score-focused preprocessing for OCR retry."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    equalized = cv2.equalizeHist(gray)
    thresholded = cv2.adaptiveThreshold(
        equalized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        4,
    )
    denoised = cv2.medianBlur(thresholded, 3)
    return cv2.resize(denoised, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
