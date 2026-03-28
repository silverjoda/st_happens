"""CLI and helpers for comparative ranking analysis (M5)."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from scipy.stats import kendalltau, spearmanr
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.common.db import create_schema, session_scope
from src.common.models import Card, RankingResult, RankingRun
from src.common.settings import PROJECT_ROOT, ensure_runtime_directories


@dataclass(slots=True)
class AlignedCardComparison:
    """Comparable scores for one card across official, human, and AI runs."""

    card_id: int
    description_text: str
    official_score: float
    official_rank_position: int
    human_score: float
    human_rank_position: int
    ai_score: float
    ai_rank_position: int


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare official, human, and AI ranking outputs and write M5 reports."
    )
    parser.add_argument("--human-run", required=True, type=int, help="Human ranking run ID.")
    parser.add_argument("--ai-run", required=True, type=int, help="AI ranking run ID.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs",
        help="Output directory for comparison artifacts (default: outputs/).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of disagreement cards to include per comparison.",
    )
    return parser


def _load_run(session: Session, *, run_id: int, expected_population: str) -> RankingRun:
    run = session.get(RankingRun, run_id)
    if run is None:
        raise ValueError(f"ranking_run_not_found:{run_id}")
    if run.population != expected_population:
        raise ValueError(
            f"ranking_run_population_mismatch:run_id={run_id}:expected={expected_population}:actual={run.population}"
        )
    return run


def _load_run_results(session: Session, *, run_id: int) -> list[RankingResult]:
    results = list(
        session.scalars(
            select(RankingResult)
            .where(RankingResult.ranking_run_id == run_id)
            .order_by(RankingResult.card_id.asc())
        ).all()
    )
    if not results:
        raise ValueError(f"ranking_run_without_results:{run_id}")
    return results


def _load_approved_cards(session: Session) -> list[Card]:
    cards = list(
        session.scalars(select(Card).where(Card.status == "approved").order_by(Card.id.asc())).all()
    )
    if not cards:
        raise ValueError("no_approved_cards")
    return cards


def _run_metadata_payload(run: RankingRun) -> dict[str, object]:
    parsed_config: object
    try:
        parsed_config = json.loads(run.config_json)
    except json.JSONDecodeError:
        parsed_config = run.config_json
    return {
        "id": run.id,
        "population": run.population,
        "algorithm": run.algorithm,
        "created_at": run.created_at.isoformat(),
        "config": parsed_config,
    }


def build_aligned_comparisons(
    session: Session,
    *,
    human_run_id: int,
    ai_run_id: int,
) -> tuple[list[AlignedCardComparison], dict[str, object], dict[str, object], dict[str, object]]:
    """Load and align official/human/ai scores on approved-card overlap."""
    human_run = _load_run(session, run_id=human_run_id, expected_population="human")
    ai_run = _load_run(session, run_id=ai_run_id, expected_population="ai")

    approved_cards = _load_approved_cards(session)
    approved_by_id = {card.id: card for card in approved_cards}
    approved_ids = set(approved_by_id)

    human_results = _load_run_results(session, run_id=human_run_id)
    ai_results = _load_run_results(session, run_id=ai_run_id)

    human_by_card = {result.card_id: result for result in human_results}
    ai_by_card = {result.card_id: result for result in ai_results}

    non_approved_in_human = set(human_by_card) - approved_ids
    non_approved_in_ai = set(ai_by_card) - approved_ids
    if non_approved_in_human or non_approved_in_ai:
        raise ValueError("ranking_results_include_non_approved_cards")

    missing_in_human = sorted(approved_ids - set(human_by_card))
    missing_in_ai = sorted(approved_ids - set(ai_by_card))

    overlap_ids = sorted(approved_ids & set(human_by_card) & set(ai_by_card))
    if not overlap_ids:
        raise ValueError("empty_aligned_overlap")

    official_ranked = sorted(
        approved_cards,
        key=lambda card: (
            -(card.official_score if card.official_score is not None else float("-inf")),
            card.id,
        ),
    )
    official_rank_by_id = {card.id: index for index, card in enumerate(official_ranked, start=1)}

    aligned: list[AlignedCardComparison] = []
    for card_id in overlap_ids:
        card = approved_by_id[card_id]
        if card.official_score is None:
            raise ValueError(f"approved_card_missing_official_score:{card_id}")
        human = human_by_card[card_id]
        ai = ai_by_card[card_id]
        aligned.append(
            AlignedCardComparison(
                card_id=card_id,
                description_text=card.description_text or "",
                official_score=card.official_score,
                official_rank_position=official_rank_by_id[card_id],
                human_score=human.normalized_score_1_100,
                human_rank_position=human.rank_position,
                ai_score=ai.normalized_score_1_100,
                ai_rank_position=ai.rank_position,
            )
        )

    warnings: list[str] = []
    if missing_in_human:
        warnings.append(f"missing_cards_in_human_run:{len(missing_in_human)}")
    if missing_in_ai:
        warnings.append(f"missing_cards_in_ai_run:{len(missing_in_ai)}")

    alignment = {
        "approved_card_count": len(approved_cards),
        "overlap_card_count": len(aligned),
        "missing_in_human": missing_in_human,
        "missing_in_ai": missing_in_ai,
        "warnings": warnings,
    }
    return aligned, alignment, _run_metadata_payload(human_run), _run_metadata_payload(ai_run)


def _safe_stat(value: float) -> float | None:
    if math.isnan(value) or math.isinf(value):
        return None
    return float(value)


def _correlation_pair(left: list[float], right: list[float]) -> tuple[float | None, float | None]:
    if len(left) < 2:
        return None, None
    spearman = spearmanr(left, right).statistic
    kendall = kendalltau(left, right).statistic
    return _safe_stat(float(spearman)), _safe_stat(float(kendall))


def compute_metrics(rows: list[AlignedCardComparison]) -> dict[str, object]:
    """Compute FR-7 metric outputs from aligned rows."""
    if not rows:
        raise ValueError("empty_metric_input")

    official = [row.official_score for row in rows]
    human = [row.human_score for row in rows]
    ai = [row.ai_score for row in rows]

    sp_off_h, kt_off_h = _correlation_pair(official, human)
    sp_off_ai, kt_off_ai = _correlation_pair(official, ai)
    sp_h_ai, kt_h_ai = _correlation_pair(human, ai)

    mad_off_h = sum(abs(left - right) for left, right in zip(official, human, strict=True)) / len(
        rows
    )
    mad_off_ai = sum(abs(left - right) for left, right in zip(official, ai, strict=True)) / len(
        rows
    )

    return {
        "spearman": {
            "official_vs_human": sp_off_h,
            "official_vs_ai": sp_off_ai,
            "human_vs_ai": sp_h_ai,
        },
        "kendall_tau": {
            "official_vs_human": kt_off_h,
            "official_vs_ai": kt_off_ai,
            "human_vs_ai": kt_h_ai,
        },
        "mean_absolute_difference": {
            "official_vs_human": mad_off_h,
            "official_vs_ai": mad_off_ai,
        },
    }


def _disagreement_payload(
    rows: list[AlignedCardComparison],
    *,
    against: str,
    top_n: int,
) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []

    for row in rows:
        if against == "human":
            compared_score = row.human_score
            compared_rank = row.human_rank_position
        elif against == "ai":
            compared_score = row.ai_score
            compared_rank = row.ai_rank_position
        else:
            raise ValueError("invalid_disagreement_target")

        score_delta = abs(row.official_score - compared_score)
        rank_delta = abs(row.official_rank_position - compared_rank)
        payload.append(
            {
                "card_id": row.card_id,
                "description_text": row.description_text,
                "official_score": row.official_score,
                "compared_score": compared_score,
                "absolute_score_delta": score_delta,
                "official_rank_position": row.official_rank_position,
                "compared_rank_position": compared_rank,
                "absolute_rank_delta": rank_delta,
            }
        )

    ordered = sorted(
        payload,
        key=lambda item: (
            -float(item["absolute_score_delta"]),
            -int(item["absolute_rank_delta"]),
            int(item["card_id"]),
        ),
    )
    return ordered[:top_n]


def extract_top_disagreements(
    rows: list[AlignedCardComparison],
    *,
    top_n: int,
) -> dict[str, list[dict[str, object]]]:
    """Return deterministic top-N disagreement cards for official-vs-human/ai."""
    if top_n < 1:
        raise ValueError("invalid_top_n")
    return {
        "official_vs_human": _disagreement_payload(rows, against="human", top_n=top_n),
        "official_vs_ai": _disagreement_payload(rows, against="ai", top_n=top_n),
    }


def _write_report_artifacts(
    *,
    output_dir: Path,
    human_run_id: int,
    ai_run_id: int,
    report: dict[str, object],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"comparison_h{human_run_id}_a{ai_run_id}"
    json_path = output_dir / f"{base_name}.json"
    md_path = output_dir / f"{base_name}.md"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    metrics = report["metrics"]
    disagreements = report["top_disagreements"]
    lines = [
        f"# Comparative Analysis (human_run={human_run_id}, ai_run={ai_run_id})",
        "",
        f"- Card overlap count: {report['card_count']}",
        "",
        "## Metrics",
        "",
        f"- Spearman (official vs human): {metrics['spearman']['official_vs_human']}",
        f"- Spearman (official vs ai): {metrics['spearman']['official_vs_ai']}",
        f"- Spearman (human vs ai): {metrics['spearman']['human_vs_ai']}",
        f"- Kendall tau (official vs human): {metrics['kendall_tau']['official_vs_human']}",
        f"- Kendall tau (official vs ai): {metrics['kendall_tau']['official_vs_ai']}",
        f"- Kendall tau (human vs ai): {metrics['kendall_tau']['human_vs_ai']}",
        (
            "- MAD normalized 1-100 (official vs human): "
            f"{metrics['mean_absolute_difference']['official_vs_human']}"
        ),
        (
            "- MAD normalized 1-100 (official vs ai): "
            f"{metrics['mean_absolute_difference']['official_vs_ai']}"
        ),
        "",
        "## Top disagreements (official vs human)",
    ]

    off_human = disagreements.get("official_vs_human", [])
    if off_human:
        for item in off_human:
            lines.append(
                "- card_id={card_id} delta={delta:.4f} official={official:.2f} compared={compared:.2f}".format(
                    card_id=item["card_id"],
                    delta=float(item["absolute_score_delta"]),
                    official=float(item["official_score"]),
                    compared=float(item["compared_score"]),
                )
            )
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Top disagreements (official vs ai)")
    off_ai = disagreements.get("official_vs_ai", [])
    if off_ai:
        for item in off_ai:
            lines.append(
                "- card_id={card_id} delta={delta:.4f} official={official:.2f} compared={compared:.2f}".format(
                    card_id=item["card_id"],
                    delta=float(item["absolute_score_delta"]),
                    official=float(item["official_score"]),
                    compared=float(item["compared_score"]),
                )
            )
    else:
        lines.append("- None")

    lines.append("")
    lines.append(f"- Generated at: {report['generated_at']}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return json_path, md_path


def run_comparison(
    *,
    human_run_id: int,
    ai_run_id: int,
    output_dir: Path,
    top_n: int,
) -> tuple[Path, Path]:
    """Run comparative analysis and emit report artifacts."""
    ensure_runtime_directories()
    create_schema()

    with session_scope() as session:
        rows, alignment, human_run_meta, ai_run_meta = build_aligned_comparisons(
            session,
            human_run_id=human_run_id,
            ai_run_id=ai_run_id,
        )

    metrics = compute_metrics(rows)
    disagreements = extract_top_disagreements(rows, top_n=top_n)

    report: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "human_run": human_run_meta,
        "ai_run": ai_run_meta,
        "card_count": len(rows),
        "alignment": alignment,
        "metrics": metrics,
        "top_disagreements": disagreements,
    }

    return _write_report_artifacts(
        output_dir=output_dir,
        human_run_id=human_run_id,
        ai_run_id=ai_run_id,
        report=report,
    )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        json_path, md_path = run_comparison(
            human_run_id=args.human_run,
            ai_run_id=args.ai_run,
            output_dir=args.output_dir,
            top_n=args.top_n,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"comparison_report_written json={json_path} markdown={md_path}")


if __name__ == "__main__":
    main()
