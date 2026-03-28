"""Parsing helpers for OCR output."""

from __future__ import annotations

import re


_SCORE_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def clean_description(text: str | None) -> str | None:
    """Normalize extracted description text."""
    if text is None:
        return None
    cleaned = " ".join(text.split()).strip()
    return cleaned or None


def parse_official_score(text: str | None) -> float | None:
    """Extract numeric score candidate from OCR text."""
    if text is None:
        return None
    matches = _SCORE_PATTERN.findall(text)
    if not matches:
        return None
    try:
        score = float(matches[-1])
    except ValueError:
        return None
    if score <= 0 or score > 100:
        return None
    return score
