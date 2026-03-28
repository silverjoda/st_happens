"""Overwrite OCR scores in the Claude OCR results JSON.

The expected score sequence is index-based:
100, 99.5, 99.0, ..., 0.5
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _format_score_cz(score: float) -> str:
    if score == int(score):
        return str(int(score))
    return f"{score:.1f}".replace(".", ",")


def _expected_score(index: int) -> float:
    return 100.0 - (index * 0.5)


def overwrite_scores(input_path: Path, output_path: Path) -> tuple[int, int]:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("Expected top-level JSON array of card results.")

    updated_count = 0
    for i, card in enumerate(data):
        if not isinstance(card, dict):
            raise SystemExit(f"Entry at index {i} is not a JSON object.")

        expected = _expected_score(i)
        if expected < 0.5:
            raise SystemExit(f"Index {i} exceeds supported sequence range (100 to 0.5 by 0.5).")

        if card.get("score") != expected or card.get("score_str") != _format_score_cz(expected):
            updated_count += 1

        card["score"] = expected
        card["score_str"] = _format_score_cz(expected)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return updated_count, len(data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Overwrite score values in OCR card results using fixed 100..0.5 order."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("outputs/ocr_test_claude_results.json"),
        help="Input JSON file (default: outputs/ocr_test_claude_results.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON file (default: overwrite input)",
    )

    args = parser.parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve() if args.output else input_path

    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    updated_count, total = overwrite_scores(input_path, output_path)
    print(f"Updated scores for {updated_count} out of {total} entries.")
    print(f"Wrote updated results to: {output_path}")


if __name__ == "__main__":
    main()
