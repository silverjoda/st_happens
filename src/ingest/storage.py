"""Persistence helpers for ingestion outputs."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.common.models import Card
from src.ingest.types import ExtractionResult


def persist_card_extraction(session: Session, result: ExtractionResult) -> Card:
    """Persist a single extraction result into the cards table."""
    card = Card(
        source_image_path=result.source_image_path,
        description_text=result.description_text,
        official_score=result.official_score,
        ocr_confidence_desc=result.ocr_confidence_desc,
        ocr_confidence_score=result.ocr_confidence_score,
        status=result.status,
    )
    session.add(card)
    session.flush()
    return card
