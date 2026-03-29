"""CLI entrypoint for ingestion extraction runs."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.common.settings import PROJECT_ROOT, ensure_runtime_directories, get_display_cards_dir
from src.ingest.ocr import EasyOCROCR, OCRWithFallback, TesseractOCR
from src.ingest.pipeline import extract_from_image
from src.ingest.reporting import build_run_report, write_run_report
from src.ingest.types import ExtractionResult


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
MAX_SCORE_PREFIXED_IMAGES = 200
DEFAULT_WORKERS = 1
_WORKER_OCR: OCRWithFallback | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract card data from raw photos")
    parser.add_argument("--input", required=True, help="Input directory containing raw card photos")
    parser.add_argument("--out", required=True, help="Output directory for processed artifacts")
    parser.add_argument("--limit", type=int, default=None, help="Optional max images to process")
    parser.add_argument(
        "--seed", type=int, default=None, help="Optional random seed used with --limit"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Number of worker processes for extraction (default: 1, use 0 for CPU count)",
    )
    parser.add_argument(
        "--rename-score-prefixes",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Rename raw images to score-prefixed filenames before extraction "
            "(use --no-rename-score-prefixes to keep existing filenames)"
        ),
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


def _select_images(images: list[Path], limit: int | None, seed: int | None) -> list[Path]:
    if limit is None:
        return images
    if limit < 0:
        raise ValueError("limit_must_be_non_negative")
    if limit >= len(images):
        return images
    if seed is None:
        return images[:limit]
    rng = random.Random(seed)
    selected_indexes = sorted(rng.sample(range(len(images)), limit))
    return [images[index] for index in selected_indexes]


def _score_for_index(index: int) -> float:
    score = 100.0 - (index * 0.5)
    if score < 0.5:
        raise ValueError("too_many_images_for_score_prefixes")
    return score


def _format_score_prefix(score: float) -> str:
    if score.is_integer():
        return str(int(score))
    return f"{score:.1f}"


def _rename_images_with_score_prefixes(images: list[Path]) -> list[Path]:
    if len(images) > MAX_SCORE_PREFIXED_IMAGES:
        raise SystemExit(
            "Input directory has more than 200 images; score-based 100..0.5 prefixes require <= 200 images."
        )

    planned_paths: list[Path] = []
    staged_paths: list[tuple[Path, Path, Path]] = []

    for index, path in enumerate(images):
        score = _score_for_index(index)
        prefix = _format_score_prefix(score)
        target_name = f"{prefix}_raw{path.suffix.lower()}"
        target_path = path.with_name(target_name)
        planned_paths.append(target_path)
        if path == target_path:
            continue
        temp_name = f".{path.stem}.tmp-{uuid4().hex}{path.suffix.lower()}"
        temp_path = path.with_name(temp_name)
        staged_paths.append((path, temp_path, target_path))

    for source_path, temp_path, _ in staged_paths:
        source_path.rename(temp_path)
    for _, temp_path, target_path in staged_paths:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.rename(target_path)

    return planned_paths


def _prepare_images_for_extraction(images: list[Path], rename_score_prefixes: bool) -> list[Path]:
    if not rename_score_prefixes:
        return images
    return _rename_images_with_score_prefixes(images)


def _build_ocr_adapter() -> OCRWithFallback:
    primary = TesseractOCR()
    try:
        fallback = EasyOCROCR()
    except RuntimeError:
        fallback = None
    return OCRWithFallback(primary=primary, fallback=fallback)


def _resolve_worker_count(raw_workers: int) -> int:
    if raw_workers < 0:
        raise SystemExit("--workers must be >= 0")
    if raw_workers == 0:
        return max(1, os.cpu_count() or 1)
    return raw_workers


def _extract_single_for_worker(image_path: str) -> ExtractionResult:
    global _WORKER_OCR
    if _WORKER_OCR is None:
        _WORKER_OCR = _build_ocr_adapter()
    return extract_from_image(image_path=Path(image_path), ocr=_WORKER_OCR)


def _run_extraction(images: list[Path], worker_count: int) -> list[ExtractionResult]:
    if worker_count <= 1:
        ocr = _build_ocr_adapter()
        return [extract_from_image(image_path=image_path, ocr=ocr) for image_path in images]

    image_paths = [str(path) for path in images]
    with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
        return list(executor.map(_extract_single_for_worker, image_paths))


def _write_extraction_records(
    output_dir: Path, run_id: str, results: list[ExtractionResult]
) -> tuple[Path, Path]:
    records = [asdict(result) for result in results]
    json_path = output_dir / f"cards_{run_id}.json"
    jsonl_path = output_dir / f"cards_{run_id}.jsonl"

    json_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    return json_path, jsonl_path


def main() -> None:
    args = parse_args()
    input_dir = _resolve_path(args.input)
    output_dir = _resolve_path(args.out)

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    ensure_runtime_directories()
    output_dir.mkdir(parents=True, exist_ok=True)
    display_dir = get_display_cards_dir()
    display_dir.mkdir(parents=True, exist_ok=True)

    all_images = _list_input_images(input_dir=input_dir, limit=None, seed=None)
    prepared_images = _prepare_images_for_extraction(
        all_images,
        rename_score_prefixes=args.rename_score_prefixes,
    )
    images = _select_images(prepared_images, limit=args.limit, seed=args.seed)
    worker_count = _resolve_worker_count(args.workers)
    run_started = datetime.now(timezone.utc)
    run_id = run_started.strftime("%Y%m%dT%H%M%SZ")
    results = _run_extraction(images=images, worker_count=worker_count)

    run_finished = datetime.now(timezone.utc)
    report = build_run_report(
        run_id=run_id,
        started_at=run_started,
        finished_at=run_finished,
        input_dir=str(input_dir),
        output_dir=str(output_dir),
        results=results,
    )
    records_json_path, records_jsonl_path = _write_extraction_records(
        output_dir=output_dir,
        run_id=run_id,
        results=results,
    )
    json_path, md_path = write_run_report(output_dir=output_dir, run_id=run_id, report=report)

    print(f"Processed images: {report['total_images_processed']}")
    print(f"Successes: {report['success_count']}")
    print(f"Failures: {report['failure_count']}")
    print(f"Cards JSON: {records_json_path}")
    print(f"Cards JSONL: {records_jsonl_path}")
    print(f"Report JSON: {json_path}")
    print(f"Report Markdown: {md_path}")
    print(f"Display images: {display_dir}")
    print(f"Workers: {worker_count}")


if __name__ == "__main__":
    main()
