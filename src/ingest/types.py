"""Data structures used by ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OCRField:
    text: str | None
    confidence: float | None


@dataclass(slots=True)
class ExtractionResult:
    source_image_path: str
    description_text: str | None
    official_score: float | None
    ocr_confidence_desc: float | None
    ocr_confidence_score: float | None
    status: str
    failure_reason: str | None
    display_image_path: str | None = None


@dataclass(slots=True)
class RunCounts:
    total_images: int
    success_count: int
    failure_count: int
