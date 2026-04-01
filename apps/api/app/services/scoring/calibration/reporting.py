"""Reporting and visualization: text-based reports, JSON export, ASCII charts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import ScoringConfig
from .metrics import (
    EvaluationResult,
    score_distribution,
    threshold_sweep,
    multi_class_confusion,
)
from .optimizer import OptimizationResult, ParetoPoint
from .simulation import SweepResult, SimulationResult


def generate_report(
    sweep: SweepResult,
    optimization: OptimizationResult | None = None,
    detailed: bool = True,
) -> str:
    """Generate a comprehensive text report of calibration results."""
    lines: list[str] = []
    _header(lines, "BLITZ CALIBRATION REPORT")

    # Summary
    _header(lines, "Summary", level=2)
    lines.append(f"Total configs evaluated: {sweep.total_configs}")
    lines.append(f"Elapsed: {sweep.total_elapsed_ms:.0f}ms ({sweep.total_elapsed_ms/1000:.1f}s)")
    lines.append(f"Strategy: {sweep.search_strategy}")
    if sweep.best_result:
        lines.append(f"Best combined score: {sweep.best_result.combined_score:.4f}")
        lines.append(f"Best config hash: {sweep.best_result.config.config_hash}")
    lines.append("")

    # Convergence
    if sweep.convergence_history:
        _header(lines, "Convergence", level=2)
        for iteration, score in sweep.convergence_history:
            bar = "█" * int(score * 40)
            lines.append(f"  iter {iteration:>5d}: {score:.4f} {bar}")
        lines.append("")

    # Top configurations
    if sweep.results:
        _header(lines, "Top 10 Configurations", level=2)
        top = sorted(sweep.results, key=lambda r: r.combined_score, reverse=True)[:10]
        lines.append(f"  {'Rank':>4s}  {'Score':>7s}  {'Mistake F1':>10s}  {'Pickup F1':>9s}  {'Pri Acc':>7s}  {'Hash':>12s}")
        lines.append("  " + "-" * 62)
        for i, r in enumerate(top, 1):
            m = r.metrics
            lines.append(
                f"  {i:>4d}  {r.combined_score:>7.4f}  "
                f"{m.get('mistake_f1', m.get('mistake', {}).get('f1', 0)):>10.4f}  "
                f"{m.get('pickup_f1', m.get('pickup', {}).get('f1', 0)):>9.4f}  "
                f"{m.get('priority_accuracy', 0):>7.4f}  "
                f"{r.config.config_hash:>12s}"
            )
        lines.append("")

    # Pareto frontier
    if optimization and optimization.pareto_frontier:
        _header(lines, "Pareto Frontier", level=2)
        lines.append(f"  Points on frontier: {len(optimization.pareto_frontier)}")
        for i, pp in enumerate(optimization.pareto_frontier[:10], 1):
            obj_str = "  ".join(f"{k}={v:.3f}" for k, v in pp.objectives.items())
            lines.append(f"  {i}. combined={pp.combined_score:.4f}  {obj_str}")
        lines.append("")

    # Best config details
    if detailed and sweep.best_result:
        _header(lines, "Best Configuration Details", level=2)
        best = sweep.best_result
        lines.append("  Mistake weights:")
        for k, v in sorted(best.config.mistake_weights.items(), key=lambda x: -abs(x[1])):
            lines.append(f"    {k:>25s}: {v:>7.4f}")
        lines.append("  Pickup weights:")
        for k, v in sorted(best.config.pickup_weights.items(), key=lambda x: -abs(x[1])):
            lines.append(f"    {k:>25s}: {v:>7.4f}")
        lines.append("  Performance weights:")
        for k, v in sorted(best.config.performance_weights.items(), key=lambda x: -abs(x[1])):
            lines.append(f"    {k:>25s}: {v:>7.4f}")
        lines.append("  Continuity weights:")
        for k, v in sorted(best.config.continuity_weights.items(), key=lambda x: -abs(x[1])):
            lines.append(f"    {k:>25s}: {v:>7.4f}")

        lines.append("\n  Recommendation thresholds:")
        rt = best.config.recommendation_thresholds
        lines.append(f"    mistake_trigger: {rt.mistake_trigger:.3f}")
        lines.append(f"    pickup_trigger: {rt.pickup_trigger:.3f}")
        lines.append(f"    splice_trigger: {rt.splice_trigger:.3f}")
        lines.append("")

    # Detailed metrics for best config
    if detailed and sweep.best_result:
        _header(lines, "Best Config Metrics", level=2)
        m = sweep.best_result.metrics
        lines.append(f"  Mistake: P={m.get('mistake', {}).get('precision', 0):.4f}  "
                     f"R={m.get('mistake', {}).get('recall', 0):.4f}  "
                     f"F1={m.get('mistake', {}).get('f1', m.get('mistake_f1', 0)):.4f}")
        lines.append(f"  Pickup:  P={m.get('pickup', {}).get('precision', 0):.4f}  "
                     f"R={m.get('pickup', {}).get('recall', 0):.4f}  "
                     f"F1={m.get('pickup', {}).get('f1', m.get('pickup_f1', 0)):.4f}")
        lines.append(f"  Priority accuracy: {m.get('priority_accuracy', 0):.4f}")
        lines.append(f"  Action accuracy:   {m.get('action_accuracy', 0):.4f}")
        wl = m.get("workload", {})
        lines.append(f"  Flag rate:         {wl.get('flag_rate', 0):.4f}")
        lines.append(f"  Flagged/hour:      {wl.get('flagged_per_hour', 0):.1f}")
        lines.append("")

    return "\n".join(lines)


def generate_confusion_matrix_report(
    predictions: list[dict[str, Any]],
    ground_truths: list[dict[str, Any]],
) -> str:
    """Generate confusion matrix report for mistake and pickup detection."""
    lines: list[str] = []

    for label, field_name in [("Mistake Detection", "is_mistake"), ("Pickup Detection", "is_pickup")]:
        _header(lines, label, level=2)

        tp = fp = fn = tn = 0
        for p, g in zip(predictions, ground_truths):
            pred = bool(p.get(field_name, False))
            actual = bool(g.get(field_name, False))
            if pred and actual: tp += 1
            elif pred and not actual: fp += 1
            elif not pred and actual: fn += 1
            else: tn += 1

        lines.append("                  Predicted")
        lines.append(f"              Positive  Negative")
        lines.append(f"  Actual +    {tp:>7d}   {fn:>7d}")
        lines.append(f"  Actual -    {fp:>7d}   {tn:>7d}")
        lines.append("")

    # Priority confusion matrix
    _header(lines, "Priority Classification", level=2)
    priorities = ["critical", "high", "medium", "low", "info"]
    cm = multi_class_confusion(predictions, ground_truths, "priority", priorities)

    header = "  " + " " * 10 + "".join(f"{p[:6]:>8s}" for p in priorities)
    lines.append("  Predicted →")
    lines.append(header)
    for true_p in priorities:
        row = f"  {true_p[:8]:>8s}  "
        row += "".join(f"{cm.get(true_p, {}).get(pred_p, 0):>8d}" for pred_p in priorities)
        lines.append(row)
    lines.append("")

    return "\n".join(lines)


def generate_threshold_sweep_report(
    predictions: list[dict[str, Any]],
    ground_truths: list[dict[str, Any]],
    score_field: str = "mistake_score",
    truth_field: str = "is_mistake",
) -> str:
    """Generate ROC-like threshold sweep report."""
    lines: list[str] = []
    _header(lines, f"Threshold Sweep: {score_field} → {truth_field}", level=2)

    curve = threshold_sweep(predictions, ground_truths, score_field, truth_field)

    lines.append(f"  {'Thresh':>7s}  {'Prec':>6s}  {'Recall':>6s}  {'F1':>6s}  {'FPR':>6s}  Chart")
    lines.append("  " + "-" * 55)
    for point in curve:
        f1_bar = "█" * int(point["f1"] * 20)
        lines.append(
            f"  {point['threshold']:>7.2f}  {point['precision']:>6.3f}  "
            f"{point['recall']:>6.3f}  {point['f1']:>6.3f}  "
            f"{point['fpr']:>6.3f}  {f1_bar}"
        )
    lines.append("")

    return "\n".join(lines)


def generate_ablation_report(ablation_results: list[dict[str, Any]]) -> str:
    """Generate ablation testing report."""
    lines: list[str] = []
    _header(lines, "Detector Ablation Analysis", level=2)

    lines.append(f"  {'Detector':>25s}  {'Base':>7s}  {'Ablated':>7s}  {'Delta':>7s}  {'Impact':>8s}")
    lines.append("  " + "-" * 62)

    for entry in ablation_results:
        delta_str = f"{entry['delta']:>+7.4f}"
        lines.append(
            f"  {entry['detector']:>25s}  {entry['base_score']:>7.4f}  "
            f"{entry['ablated_score']:>7.4f}  {delta_str}  {entry['impact']:>8s}"
        )
    lines.append("")

    return "\n".join(lines)


def export_results(
    sweep: SweepResult,
    optimization: OptimizationResult | None,
    output_dir: Path,
) -> dict[str, Path]:
    """Export full results to JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    # Best config
    if sweep.best_result:
        p = output_dir / "best_config.json"
        p.write_text(json.dumps(sweep.best_result.config.to_dict(), indent=2), encoding="utf-8")
        paths["best_config"] = p

    # Top 10 configs
    top10 = sorted(sweep.results, key=lambda r: r.combined_score, reverse=True)[:10]
    p = output_dir / "top_configs.json"
    p.write_text(json.dumps([
        {"rank": i + 1, "score": r.combined_score, "config": r.config.to_dict(), "metrics": r.metrics}
        for i, r in enumerate(top10)
    ], indent=2), encoding="utf-8")
    paths["top_configs"] = p

    # Convergence history
    p = output_dir / "convergence.json"
    p.write_text(json.dumps(sweep.convergence_history, indent=2), encoding="utf-8")
    paths["convergence"] = p

    # Pareto frontier
    if optimization and optimization.pareto_frontier:
        p = output_dir / "pareto_frontier.json"
        p.write_text(json.dumps([
            {"objectives": pp.objectives, "combined": pp.combined_score,
             "config_hash": pp.config.config_hash}
            for pp in optimization.pareto_frontier
        ], indent=2), encoding="utf-8")
        paths["pareto"] = p

    # Production-ready config
    if sweep.best_result:
        p = output_dir / "production_config.json"
        p.write_text(json.dumps(
            sweep.best_result.config.to_production_format(), indent=2
        ), encoding="utf-8")
        paths["production_config"] = p

    # Text report
    report = generate_report(sweep, optimization)
    p = output_dir / "report.txt"
    p.write_text(report, encoding="utf-8")
    paths["report"] = p

    return paths


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _header(lines: list[str], title: str, level: int = 1) -> None:
    """Add a section header."""
    if level == 1:
        lines.append("=" * 70)
        lines.append(f"  {title}")
        lines.append("=" * 70)
    else:
        lines.append(f"--- {title} ---")
    lines.append("")
