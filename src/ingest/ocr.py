"""OCR adapters for extraction pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from statistics import mean
from typing import Any

import cv2
import numpy as np
import pytesseract

from src.ingest.types import OCRField


class OCRAdapter(ABC):
    """Interface for OCR execution backends."""

    @abstractmethod
    def extract_text(self, image: np.ndarray) -> OCRField:
        """Extract text and confidence from an image."""


class TesseractOCR(OCRAdapter):
    """Default OCR adapter using pytesseract."""

    def extract_text(self, image: np.ndarray) -> OCRField:
        data: dict[str, list[Any]] = pytesseract.image_to_data(
            image,
            output_type=pytesseract.Output.DICT,
            config="--psm 6",
        )
        tokens: list[str] = []
        confidences: list[float] = []
        for text_value, confidence_value in zip(
            data.get("text", []), data.get("conf", []), strict=False
        ):
            if not text_value:
                continue
            cleaned = text_value.strip()
            if not cleaned:
                continue
            tokens.append(cleaned)
            try:
                confidence = float(confidence_value)
            except (TypeError, ValueError):
                continue
            if confidence >= 0:
                confidences.append(confidence)
        joined = " ".join(tokens).strip() or None
        aggregate_conf = mean(confidences) if confidences else None
        return OCRField(text=joined, confidence=aggregate_conf)


class EasyOCROCR(OCRAdapter):
    """Optional fallback OCR adapter using EasyOCR when installed."""

    def __init__(self) -> None:
        try:
            import easyocr  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("easyocr_not_installed") from exc
        self._reader = easyocr.Reader(["en"], gpu=False)

    def extract_text(self, image: np.ndarray) -> OCRField:
        if len(image.shape) == 2:
            image_for_ocr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            image_for_ocr = image
        results = self._reader.readtext(image_for_ocr, detail=1)
        if not results:
            return OCRField(text=None, confidence=None)
        texts: list[str] = []
        confidences: list[float] = []
        for _, text, confidence in results:
            if text and text.strip():
                texts.append(text.strip())
            try:
                confidences.append(float(confidence))
            except (TypeError, ValueError):
                continue
        return OCRField(
            text=" ".join(texts).strip() or None,
            confidence=mean(confidences) if confidences else None,
        )


class OCRWithFallback(OCRAdapter):
    """Wrapper using fallback adapter when primary yields no text."""

    def __init__(self, primary: OCRAdapter, fallback: OCRAdapter | None = None) -> None:
        self._primary = primary
        self._fallback = fallback

    def extract_text(self, image: np.ndarray) -> OCRField:
        primary_result = self._primary.extract_text(image)
        if primary_result.text:
            return primary_result
        if self._fallback is None:
            return primary_result
        fallback_result = self._fallback.extract_text(image)
        return fallback_result if fallback_result.text else primary_result
