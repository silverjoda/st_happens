"""Card region extraction hooks."""

from __future__ import annotations

import cv2
import numpy as np


def _order_quad_points(points: np.ndarray) -> np.ndarray:
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).reshape(-1)
    top_left = points[np.argmin(sums)]
    top_right = points[np.argmin(diffs)]
    bottom_right = points[np.argmax(sums)]
    bottom_left = points[np.argmax(diffs)]
    return np.array([top_left, top_right, bottom_right, bottom_left], dtype=np.float32)


def _warp_card_from_contour(image: np.ndarray, contour: np.ndarray) -> np.ndarray:
    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)
    source = _order_quad_points(box.astype(np.float32))

    top_left, top_right, bottom_right, bottom_left = source
    width = int(
        max(
            np.linalg.norm(bottom_right - bottom_left),
            np.linalg.norm(top_right - top_left),
        )
    )
    height = int(
        max(
            np.linalg.norm(top_right - bottom_right),
            np.linalg.norm(top_left - bottom_left),
        )
    )
    if width < 50 or height < 50:
        return image

    destination = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    perspective = cv2.getPerspectiveTransform(source, destination)
    warped = cv2.warpPerspective(image, perspective, (width, height))
    if warped.shape[0] < warped.shape[1]:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
    return warped


def extract_card_region(image: np.ndarray) -> np.ndarray:
    """Detect dark card on light background and align it to vertical orientation."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    otsu_threshold, dark_mask = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    adaptive_mask = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        35,
        5,
    )
    dark_mask = cv2.bitwise_or(dark_mask, adaptive_mask)

    if otsu_threshold > 185:
        _, fallback_mask = cv2.threshold(blurred, 195, 255, cv2.THRESH_BINARY_INV)
        dark_mask = cv2.bitwise_or(dark_mask, fallback_mask)

    dark_mask = cv2.morphologyEx(
        dark_mask,
        cv2.MORPH_CLOSE,
        np.ones((9, 9), dtype=np.uint8),
        iterations=2,
    )
    dark_mask = cv2.morphologyEx(
        dark_mask,
        cv2.MORPH_OPEN,
        np.ones((5, 5), dtype=np.uint8),
        iterations=1,
    )

    contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image

    contour = max(contours, key=cv2.contourArea)
    image_area = float(image.shape[0] * image.shape[1])
    if cv2.contourArea(contour) < image_area * 0.12:
        return image

    return _warp_card_from_contour(image, contour)


def split_description_and_score_regions(card_region: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split aligned card into top description and center-bottom score regions."""
    height, width = card_region.shape[:2]

    desc_y1 = max(0, int(height * 0.08))
    desc_y2 = min(height, int(height * 0.62))
    desc_x1 = max(0, int(width * 0.08))
    desc_x2 = min(width, int(width * 0.92))

    score_y1 = max(0, int(height * 0.68))
    score_y2 = min(height, int(height * 0.96))
    score_x1 = max(0, int(width * 0.20))
    score_x2 = min(width, int(width * 0.80))

    if desc_y2 <= desc_y1:
        desc_y1, desc_y2 = 0, max(1, int(height * 0.62))
    if desc_x2 <= desc_x1:
        desc_x1, desc_x2 = 0, width
    if score_y2 <= score_y1:
        score_y1, score_y2 = int(height * 0.68), height
    if score_x2 <= score_x1:
        score_x1, score_x2 = 0, width

    description = card_region[desc_y1:desc_y2, desc_x1:desc_x2]
    score = card_region[score_y1:score_y2, score_x1:score_x2]
    return description, score
