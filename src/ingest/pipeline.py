"""End-to-end extraction pipeline for one image."""

from __future__ import annotations

from pathlib import Path

from src.ingest.image import load_image, preprocess_image, preprocess_score_recovery
from src.ingest.ocr import OCRAdapter
from src.ingest.parser import clean_description, parse_official_score
from src.ingest.regions import extract_card_region, split_description_and_score_regions
from src.ingest.types import ExtractionResult


def extract_from_image(image_path: Path, ocr: OCRAdapter) -> ExtractionResult:
    """Extract card description and score from a single image path."""
    try:
        image = load_image(image_path)
    except ValueError as exc:
        return ExtractionResult(
            source_image_path=str(image_path),
            description_text=None,
            official_score=None,
            ocr_confidence_desc=None,
            ocr_confidence_score=None,
            status="extracted",
            failure_reason=str(exc),
        )

    card = extract_card_region(image)
    description_region, score_region = split_description_and_score_regions(card)
    desc_processed = preprocess_image(description_region)
    score_processed = preprocess_image(score_region)

    desc_ocr = ocr.extract_text(desc_processed)
    score_ocr = ocr.extract_text(score_processed)

    description_text = clean_description(desc_ocr.text)
    official_score = parse_official_score(score_ocr.text)
    if official_score is None:
        score_recovery_processed = preprocess_score_recovery(score_region)
        recovery_ocr = ocr.extract_text(score_recovery_processed)
        recovered_score = parse_official_score(recovery_ocr.text)
        if recovered_score is not None:
            official_score = recovered_score
            score_ocr = recovery_ocr

    failure_reason = None
    if not description_text and official_score is None:
        failure_reason = "missing_description_and_score"
    elif not description_text:
        failure_reason = "missing_description"
    elif official_score is None:
        failure_reason = "missing_score"

    return ExtractionResult(
        source_image_path=str(image_path),
        description_text=description_text,
        official_score=official_score,
        ocr_confidence_desc=desc_ocr.confidence,
        ocr_confidence_score=score_ocr.confidence,
        status="extracted",
        failure_reason=failure_reason,
    )
