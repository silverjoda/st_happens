"""
Škála Posranosti – Card OCR Extractor
======================================
Extracts:
  - description  : Czech text at the top of the card (yellow text on black)
  - score        : numeric value from the yellow box at the bottom (e.g. 96.5)

Requirements:
    pip install opencv-python pillow pytesseract
    # also needs Tesseract + Czech language pack:
    # Ubuntu/Debian:  apt install tesseract-ocr tesseract-ocr-ces
    # macOS:          brew install tesseract && brew install tesseract-lang
"""

import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deskew(img: np.ndarray) -> np.ndarray:
    """
    Detect the card outline and rotate so it is axis-aligned.
    If no clear quadrilateral is found the image is returned unchanged.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    min_card_area = img.shape[0] * img.shape[1] * 0.20  # card ≥ 20 % of frame
    angle = 0.0

    for cnt in contours[:5]:
        if cv2.contourArea(cnt) < min_card_area:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) == 4:
            rect = cv2.minAreaRect(cnt)
            angle = rect[2]
            # minAreaRect returns angles in [-90, 0); normalise
            if angle < -45:
                angle += 90
            break

    if abs(angle) < 0.5:  # negligible tilt – skip warp
        return img

    (h, w) = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _extract_description(img_bgr: np.ndarray) -> str:
    """
    Isolate yellow text in the top ~42 % of the card and run Tesseract (Czech).
    """
    h, w = img_bgr.shape[:2]
    roi = img_bgr[0 : int(h * 0.42), 0:w]

    # Yellow mask in HSV
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.array([15, 80, 120]),  # lower yellow
        np.array([38, 255, 255]),
    )  # upper yellow

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # Upscale for Tesseract
    scale = 3
    h_m, w_m = mask.shape
    mask_big = cv2.resize(mask, (w_m * scale, h_m * scale), interpolation=cv2.INTER_LINEAR)
    _, mask_big = cv2.threshold(mask_big, 127, 255, cv2.THRESH_BINARY)

    text = pytesseract.image_to_string(Image.fromarray(mask_big), lang="ces", config="--psm 6")
    return text.strip()


def _find_yellow_box(roi: np.ndarray) -> np.ndarray | None:
    """
    Locate the yellow score box within a BGR ROI using connected components.
    Returns the cropped yellow box as a BGR array, or None if not found.

    The yellow box is identified as the largest connected region whose pixels
    satisfy:  Red high, Green high, Blue low  (robust across white-balance
    variation because it uses ratios rather than absolute thresholds).
    """
    h, w = roi.shape[:2]

    b = roi[:, :, 0].astype(float)
    g = roi[:, :, 1].astype(float)
    r = roi[:, :, 2].astype(float)

    # Yellow: R and G both high, B low, R clearly dominates B
    yellow_mask = ((r > 180) & (g > 150) & (b < 120) & (r > b * 2.0)).astype(np.uint8) * 255

    # Close small gaps so the box becomes one solid region
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 20))
    yellow_mask = cv2.morphologyEx(yellow_mask, cv2.MORPH_CLOSE, kernel)

    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(yellow_mask)
    if n_labels < 2:
        return None  # no yellow found at all

    # Pick the largest component (skip label 0 = background)
    areas = stats[1:, cv2.CC_STAT_AREA]
    best = int(np.argmax(areas)) + 1  # +1 because we skipped background

    x1 = stats[best, cv2.CC_STAT_LEFT]
    y1 = stats[best, cv2.CC_STAT_TOP]
    bw = stats[best, cv2.CC_STAT_WIDTH]
    bh = stats[best, cv2.CC_STAT_HEIGHT]

    # Sanity check: box should be reasonably wide and not tiny
    if bw < w * 0.25 or stats[best, cv2.CC_STAT_AREA] < 5000:
        return None

    return roi[y1 : y1 + bh, x1 : x1 + bw]


def _ocr_score_box(yellow_roi: np.ndarray) -> float | None:
    """
    Given a BGR crop of the yellow score box, OCR the number and return
    it as a float rounded to the nearest 0.5.
    """
    gray = cv2.cvtColor(yellow_roi, cv2.COLOR_BGR2GRAY)

    # Try Otsu threshold (adapts to actual brightness) then also a fixed threshold
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _, fixed = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)

    best_raw = ""
    for thresh in (otsu, fixed):
        scale = 4
        big = cv2.resize(
            thresh,
            (thresh.shape[1] * scale, thresh.shape[0] * scale),
            interpolation=cv2.INTER_LINEAR,
        )
        raw = pytesseract.image_to_string(
            Image.fromarray(big),
            lang="eng",
            config="--psm 7 -c tessedit_char_whitelist=0123456789,.",
        ).strip()
        # Pick whichever attempt returned more digit characters
        if len(re.sub(r"[^0-9]", "", raw)) > len(re.sub(r"[^0-9]", "", best_raw)):
            best_raw = raw

    normalised = re.sub(r"[^0-9.]", "", best_raw.replace(",", "."))
    if not normalised:
        return None
    try:
        value = float(normalised)
    except ValueError:
        return None

    return round(value * 2) / 2


def _extract_score(img_bgr: np.ndarray) -> float | None:
    """
    Find the yellow box in the bottom quarter of the card, read the number
    inside it (black digits on yellow background), and return it as a float
    rounded to the nearest 0.5.
    """
    h, w = img_bgr.shape[:2]
    roi = img_bgr[int(h * 0.70) : h, 0:w]

    yellow_roi = _find_yellow_box(roi)
    if yellow_roi is None or yellow_roi.size == 0:
        return None

    return _ocr_score_box(yellow_roi)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_card(image_path: str | Path) -> dict:
    """
    Parse a Škála Posranosti card photo.

    Returns a dict with keys:
        description  (str)         – Czech scenario text
        score        (float|None)  – numeric score, e.g. 96.5
        score_str    (str|None)    – score formatted Czech-style, e.g. "96,5"
        image_path   (str)         – resolved input path
    """
    path = str(image_path)
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"Cannot open image: {path}")

    img = _deskew(img)
    description = _extract_description(img)
    score = _extract_score(img)

    score_str = None
    if score is not None:
        # Use Czech comma notation; drop trailing ",0" for whole numbers
        if score == int(score):
            score_str = str(int(score))
        else:
            score_str = f"{score:.1f}".replace(".", ",")

    return {
        "image_path": path,
        "description": description,
        "score": score,
        "score_str": score_str,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if sys.argv[1:]:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        raw_photos_dir = Path(__file__).resolve().parents[1] / "data" / "raw_photos"
        image_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
        paths = sorted(
            p
            for p in raw_photos_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in image_suffixes
        )

        if not paths:
            raise SystemExit(f"No image files found under: {raw_photos_dir}")

    results: list[dict] = []
    for p in paths:
        result = extract_card(p)
        results.append(result)
        print("=" * 60)
        print(f"File   : {result['image_path']}")
        print(f"Score  : {result['score_str']}  ({result['score']})")
        print(f"Desc   :\n{result['description']}")

    output_path = Path(__file__).resolve().parents[1] / "outputs" / "ocr_test_claude_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print("=" * 60)
    print(f"Saved {len(results)} card results to: {output_path}")
