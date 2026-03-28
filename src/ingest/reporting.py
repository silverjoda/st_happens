"""Run-level digitization reporting for ingestion."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from src.ingest.types import ExtractionResult


def _confidence_summary(values: list[float | None]) -> dict[str, float | int | None]:
    present = [value for value in values if value is not None]
    if not present:
        return {"count": 0, "min": None, "median": None, "max": None}
    return {
        "count": len(present),
        "min": min(present),
        "median": median(present),
        "max": max(present),
    }


def _expected_score_increments() -> set[float]:
    return {value / 2 for value in range(1, 201)}


def _normalized_half_step(score: float) -> float:
    return round(score * 2) / 2


def find_missing_score_increments(scores: set[float]) -> list[float]:
    """Return sorted expected 0.5 increments absent from observed scores."""
    return sorted(_expected_score_increments() - scores)


def build_run_report(
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    input_dir: str,
    output_dir: str,
    results: list[ExtractionResult],
) -> dict[str, object]:
    """Build a JSON-serializable report payload for the extraction run."""
    failure_counter = Counter(result.failure_reason for result in results if result.failure_reason)
    successes = [result for result in results if result.failure_reason is None]
    manual_review_candidates = [
        result.source_image_path for result in results if result.failure_reason is not None
    ]
    desc_conf_summary = _confidence_summary([result.ocr_confidence_desc for result in results])
    score_conf_summary = _confidence_summary([result.ocr_confidence_score for result in results])

    observed_scores = {
        _normalized_half_step(result.official_score)
        for result in successes
        if result.official_score is not None
    }
    missing_increments = find_missing_score_increments(observed_scores)

    report: dict[str, object] = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "input_dir": input_dir,
        "output_dir": output_dir,
        "total_images_processed": len(results),
        "success_count": len(successes),
        "failure_count": len(results) - len(successes),
        "failure_reasons": dict(failure_counter),
        "confidence_summary": {
            "description": desc_conf_summary,
            "score": score_conf_summary,
        },
        "manual_review_required": manual_review_candidates,
        "missing_score_increments": missing_increments,
        "suspected_extraction_anomalies": ["Missing expected score increments detected."]
        if missing_increments
        else [],
        "records": [asdict(result) for result in results],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return report


def write_run_report(output_dir: Path, run_id: str, report: dict[str, object]) -> tuple[Path, Path]:
    """Write JSON and markdown reports and return both paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"ingestion_report_{run_id}.json"
    md_path = output_dir / f"ingestion_report_{run_id}.md"
    log_path = output_dir / f"ingestion_log_{run_id}.jsonl"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        f"# Digitization Report ({run_id})",
        "",
        f"- Total images processed: {report['total_images_processed']}",
        f"- Success count: {report['success_count']}",
        f"- Failure count: {report['failure_count']}",
        "",
        "## Failure reasons",
    ]
    failure_reasons = report.get("failure_reasons", {})
    if isinstance(failure_reasons, dict) and failure_reasons:
        for reason, count in failure_reasons.items():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Confidence summary",
            f"- Description: {report['confidence_summary']['description']}",
            f"- Score: {report['confidence_summary']['score']}",
            "",
            "## Missing 0.5 increments",
        ]
    )

    missing_increments = report.get("missing_score_increments", [])
    if isinstance(missing_increments, list) and missing_increments:
        lines.append("- " + ", ".join(str(value) for value in missing_increments))
    else:
        lines.append("- None")

    lines.extend(["", "## Manual review required", ""])
    review_list = report.get("manual_review_required", [])
    if isinstance(review_list, list) and review_list:
        lines.extend(f"- {item}" for item in review_list)
    else:
        lines.append("- None")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with log_path.open("w", encoding="utf-8") as handle:
        for record in report.get("records", []):
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    return json_path, md_path
