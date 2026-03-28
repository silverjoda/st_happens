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
    """Preprocess description text (yellow on dark) with contrast normalization."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    equalized = cv2.equalizeHist(gray)
    blurred = cv2.GaussianBlur(equalized, (3, 3), 0)
    thresholded = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        7,
    )
    return cv2.resize(thresholded, None, fx=1.8, fy=1.8, interpolation=cv2.INTER_CUBIC)


def preprocess_score_image(image: np.ndarray) -> np.ndarray:
    """Preprocess score area with yellow-box aware thresholding."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    yellow_mask = cv2.inRange(hsv, (12, 50, 60), (45, 255, 255))
    yellow_mask = cv2.morphologyEx(
        yellow_mask,
        cv2.MORPH_CLOSE,
        np.ones((5, 5), dtype=np.uint8),
        iterations=2,
    )

    crop = image
    contours, _ = cv2.findContours(yellow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(contour)
        if w * h > image.shape[0] * image.shape[1] * 0.02:
            pad = 8
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(image.shape[1], x + w + pad)
            y2 = min(image.shape[0], y + h + pad)
            crop = image[y1:y2, x1:x2]

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    thresholded = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    cleaned = cv2.morphologyEx(
        thresholded,
        cv2.MORPH_OPEN,
        np.ones((3, 3), dtype=np.uint8),
        iterations=1,
    )
    normalized = cv2.bitwise_not(cleaned)
    return cv2.resize(normalized, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)


def preprocess_score_recovery(image: np.ndarray) -> np.ndarray:
    """Apply deterministic score-focused preprocessing for OCR retry."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    equalized = cv2.equalizeHist(gray)
    thresholded = cv2.adaptiveThreshold(
        equalized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        4,
    )
    denoised = cv2.medianBlur(thresholded, 3)
    normalized = cv2.bitwise_not(denoised)
    return cv2.resize(normalized, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)


def _detect_score_box_rect(card_image: np.ndarray) -> tuple[int, int, int, int] | None:
    """Locate likely yellow score-box rectangle on aligned card image."""
    height, width = card_image.shape[:2]
    if height == 0 or width == 0:
        return None

    search_y1 = max(0, int(height * 0.55))
    search_y2 = min(height, int(height * 0.98))
    search_x1 = max(0, int(width * 0.08))
    search_x2 = min(width, int(width * 0.92))
    roi = card_image[search_y1:search_y2, search_x1:search_x2]
    if roi.size == 0:
        return None

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    yellow_mask = cv2.inRange(hsv, (10, 45, 70), (50, 255, 255))
    yellow_mask = cv2.morphologyEx(
        yellow_mask,
        cv2.MORPH_CLOSE,
        np.ones((5, 5), dtype=np.uint8),
        iterations=2,
    )
    yellow_mask = cv2.morphologyEx(
        yellow_mask,
        cv2.MORPH_OPEN,
        np.ones((3, 3), dtype=np.uint8),
        iterations=1,
    )

    contours, _ = cv2.findContours(yellow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    min_area = float(roi.shape[0] * roi.shape[1]) * 0.01
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < min_area:
        return None

    x, y, w, h = cv2.boundingRect(contour)
    if w < 20 or h < 10:
        return None

    return (search_x1 + x, search_y1 + y, w, h)


def mask_score_box(card_image: np.ndarray) -> np.ndarray:
    """Mask the yellow score box so score is hidden in UI-facing card image."""
    masked = card_image.copy()
    rect = _detect_score_box_rect(masked)

    if rect is None:
        height, width = masked.shape[:2]
        rect = (
            int(width * 0.18),
            int(height * 0.72),
            int(width * 0.64),
            int(height * 0.18),
        )

    x, y, w, h = rect
    pad_x = max(4, int(w * 0.06))
    pad_y = max(4, int(h * 0.18))

    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(masked.shape[1], x + w + pad_x)
    y2 = min(masked.shape[0], y + h + pad_y)

    cv2.rectangle(masked, (x1, y1), (x2, y2), (0, 0, 0), thickness=-1)
    return masked


def resize_card_image(
    card_image: np.ndarray, *, width: int = 720, height: int = 1080
) -> np.ndarray:
    """Resize card to fixed dimensions with letterboxing for consistent display size."""
    source_h, source_w = card_image.shape[:2]
    if source_h == 0 or source_w == 0:
        return np.zeros((height, width, 3), dtype=np.uint8)

    scale = min(width / float(source_w), height / float(source_h))
    target_w = max(1, int(round(source_w * scale)))
    target_h = max(1, int(round(source_h * scale)))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    resized = cv2.resize(card_image, (target_w, target_h), interpolation=interpolation)

    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    x_offset = (width - target_w) // 2
    y_offset = (height - target_h) // 2
    canvas[y_offset : y_offset + target_h, x_offset : x_offset + target_w] = resized
    return canvas


def build_ui_card_image(card_image: np.ndarray) -> np.ndarray:
    """Prepare aligned card image for UI display (masked score + normalized size)."""
    masked = mask_score_box(card_image)
    return resize_card_image(masked)
