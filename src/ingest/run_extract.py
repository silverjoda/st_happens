"""CLI entrypoint for ingestion extraction runs."""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timezone
from pathlib import Path

from src.common.db import create_schema, session_scope
from src.common.settings import PROJECT_ROOT, ensure_runtime_directories
from src.ingest.ocr import EasyOCROCR, OCRWithFallback, TesseractOCR
from src.ingest.pipeline import extract_from_image
from src.ingest.reporting import build_run_report, write_run_report
from src.ingest.storage import persist_card_extraction
from src.ingest.types import ExtractionResult


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract card data from raw photos")
    parser.add_argument("--input", required=True, help="Input directory containing raw card photos")
    parser.add_argument("--out", required=True, help="Output directory for processed artifacts")
    parser.add_argument("--limit", type=int, default=None, help="Optional max images to process")
    parser.add_argument(
        "--seed", type=int, default=None, help="Optional random seed used with --limit"
    )
    return parser.parse_args()


def _resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _list_input_images(input_dir: Path, limit: int | None, seed: int | None) -> list[Path]:
    images = [
        path
        for path in sorted(input_dir.iterdir())
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    ]
    if limit is None:
        return images
    if limit < 0:
        raise ValueError("limit_must_be_non_negative")
    if limit >= len(images):
        return images
    if seed is None:
        return images[:limit]
    rng = random.Random(seed)
    sampled = rng.sample(images, limit)
    sampled.sort()
    return sampled


def _build_ocr_adapter() -> OCRWithFallback:
    primary = TesseractOCR()
    try:
        fallback = EasyOCROCR()
    except RuntimeError:
        fallback = None
    return OCRWithFallback(primary=primary, fallback=fallback)


def main() -> None:
    args = parse_args()
    input_dir = _resolve_path(args.input)
    output_dir = _resolve_path(args.out)

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    ensure_runtime_directories()
    output_dir.mkdir(parents=True, exist_ok=True)
    create_schema()

    images = _list_input_images(input_dir=input_dir, limit=args.limit, seed=args.seed)
    run_started = datetime.now(timezone.utc)
    run_id = run_started.strftime("%Y%m%dT%H%M%SZ")
    ocr = _build_ocr_adapter()

    results: list[ExtractionResult] = []
    for image_path in images:
        result = extract_from_image(image_path=image_path, ocr=ocr)
        results.append(result)
        with session_scope() as session:
            persist_card_extraction(session, result)

    run_finished = datetime.now(timezone.utc)
    report = build_run_report(
        run_id=run_id,
        started_at=run_started,
        finished_at=run_finished,
        input_dir=str(input_dir),
        output_dir=str(output_dir),
        results=results,
    )
    json_path, md_path = write_run_report(output_dir=output_dir, run_id=run_id, report=report)

    print(f"Processed images: {report['total_images_processed']}")
    print(f"Successes: {report['success_count']}")
    print(f"Failures: {report['failure_count']}")
    print(f"Report JSON: {json_path}")
    print(f"Report Markdown: {md_path}")


if __name__ == "__main__":
    main()
