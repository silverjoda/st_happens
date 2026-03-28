"""Parsing helpers for OCR output."""

from __future__ import annotations

import re


_SCORE_PATTERN = re.compile(r"\d+(?:\.\d+)?")
_STATIC_LABEL_PATTERN = re.compile(r"\bSKALA\s+POSRANOSTI\b", re.IGNORECASE)
_OCR_SCORE_TRANSLATION = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "Q": "0",
        "D": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "S": "5",
        "s": "5",
        "B": "8",
        "Z": "2",
    }
)


def clean_description(text: str | None) -> str | None:
    """Normalize extracted description text."""
    if text is None:
        return None
    without_static_label = _STATIC_LABEL_PATTERN.sub(" ", text)
    cleaned = " ".join(without_static_label.split()).strip(" -_:")
    return cleaned or None


def parse_official_score(text: str | None) -> float | None:
    """Extract numeric score candidate from OCR text."""
    if text is None:
        return None

    normalized = text.translate(_OCR_SCORE_TRANSLATION).replace(",", ".")
    matches = _SCORE_PATTERN.findall(normalized)
    if not matches:
        return None

    for raw_value in reversed(matches):
        try:
            candidate = float(raw_value)
        except ValueError:
            continue

        if 0.5 <= candidate <= 100.0:
            return round(candidate * 2) / 2

        if candidate > 100.0:
            scaled = candidate / 10
            if 0.5 <= scaled <= 100.0:
                return round(scaled * 2) / 2

    return None
