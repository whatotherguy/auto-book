"""Comprehensive evaluation metrics for calibration — editorial usefulness focused."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClassificationMetrics:
    """Precision/recall/F1 for a binary classification task."""
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) > 0 else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def false_positive_rate(self) -> float:
        return self.fp / (self.fp + self.tn) if (self.fp + self.tn) > 0 else 0.0

    @property
    def accuracy(self) -> float:
        total = self.tp + self.fp + self.fn + self.tn
        return (self.tp + self.tn) / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "fpr": round(self.false_positive_rate, 4),
            "accuracy": round(self.accuracy, 4),
        }


@dataclass
class RankingMetrics:
    """Metrics for alt-take ranking evaluation."""
    top1_correct: int = 0
    top1_total: int = 0
    kendall_tau_sum: float = 0.0
    kendall_tau_count: int = 0
    pairwise_correct: int = 0
    pairwise_total: int = 0

    @property
    def top1_accuracy(self) -> float:
        return self.top1_correct / self.top1_total if self.top1_total > 0 else 0.0

    @property
    def mean_kendall_tau(self) -> float:
        return self.kendall_tau_sum / self.kendall_tau_count if self.kendall_tau_count > 0 else 0.0

    @property
    def pairwise_accuracy(self) -> float:
        return self.pairwise_correct / self.pairwise_total if self.pairwise_total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "top1_accuracy": round(self.top1_accuracy, 4),
            "top1_correct": self.top1_correct,
            "top1_total": self.top1_total,
            "mean_kendall_tau": round(self.mean_kendall_tau, 4),
            "pairwise_accuracy": round(self.pairwise_accuracy, 4),
            "pairwise_correct": self.pairwise_correct,
            "pairwise_total": self.pairwise_total,
        }


@dataclass
class WorkloadMetrics:
    """Metrics measuring editorial workload burden."""
    total_segments: int = 0
    flagged_segments: int = 0
    total_duration_ms: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

    @property
    def flag_rate(self) -> float:
        """Fraction of segments requiring human review."""
        return self.flagged_segments / self.total_segments if self.total_segments > 0 else 0.0

    @property
    def flagged_per_hour(self) -> float:
        """Segments flagged per hour of audio."""
        hours = self.total_duration_ms / 3_600_000
        return self.flagged_segments / hours if hours > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_segments": self.total_segments,
            "flagged_segments": self.flagged_segments,
            "flag_rate": round(self.flag_rate, 4),
            "flagged_per_hour": round(self.flagged_per_hour, 1),
            "priority_distribution": {
                "critical": self.critical_count,
                "high": self.high_count,
                "medium": self.medium_count,
                "low": self.low_count,
            },
        }


@dataclass
class EvaluationResult:
    """Complete evaluation result for a single scoring configuration."""
    config_hash: str = ""
    mistake_metrics: ClassificationMetrics = field(default_factory=ClassificationMetrics)
    pickup_metrics: ClassificationMetrics = field(default_factory=ClassificationMetrics)
    review_metrics: ClassificationMetrics = field(default_factory=ClassificationMetrics)
    splice_metrics: ClassificationMetrics = field(default_factory=ClassificationMetrics)
    ranking_metrics: RankingMetrics = field(default_factory=RankingMetrics)
    workload_metrics: WorkloadMetrics = field(default_factory=WorkloadMetrics)
    priority_accuracy: float = 0.0
    action_accuracy: float = 0.0

    @property
    def combined_score(self) -> float:
        """Weighted combined score — single optimization target."""
        # Build dict without combined_score to avoid recursion
        d = {
            "mistake": self.mistake_metrics.to_dict(),
            "pickup": self.pickup_metrics.to_dict(),
            "ranking": self.ranking_metrics.to_dict(),
            "splice": self.splice_metrics.to_dict(),
            "workload": self.workload_metrics.to_dict(),
            "priority_accuracy": self.priority_accuracy,
            "action_accuracy": self.action_accuracy,
        }
        return compute_combined_score(d)

    def to_dict(self) -> dict[str, Any]:
        score = self.combined_score
        return {
            "config_hash": self.config_hash,
            "mistake": self.mistake_metrics.to_dict(),
            "pickup": self.pickup_metrics.to_dict(),
            "review": self.review_metrics.to_dict(),
            "splice": self.splice_metrics.to_dict(),
            "ranking": self.ranking_metrics.to_dict(),
            "workload": self.workload_metrics.to_dict(),
            "priority_accuracy": round(self.priority_accuracy, 4),
            "action_accuracy": round(self.action_accuracy, 4),
            "combined_score": round(score, 4),
        }


# ---------------------------------------------------------------------------
# Core evaluation functions
# ---------------------------------------------------------------------------

def evaluate_predictions(
    predictions: list[dict[str, Any]],
    ground_truths: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate prediction quality against labeled ground truth.

    Returns comprehensive metrics dict. Backward-compatible with existing callers
    while providing much richer data.
    """
    result = evaluate_full(predictions, ground_truths)
    flat = result.to_dict()

    # Backward compatibility: expose combined_f1, mistake_f1, pickup_f1
    flat["combined_f1"] = result.combined_score
    flat["mistake_f1"] = result.mistake_metrics.f1
    flat["pickup_f1"] = result.pickup_metrics.f1
    flat["mistake_tp"] = result.mistake_metrics.tp
    flat["mistake_fp"] = result.mistake_metrics.fp
    flat["mistake_fn"] = result.mistake_metrics.fn
    flat["pickup_tp"] = result.pickup_metrics.tp
    flat["pickup_fp"] = result.pickup_metrics.fp
    flat["pickup_fn"] = result.pickup_metrics.fn
    flat["total_segments"] = len(predictions)

    return flat


def evaluate_full(
    predictions: list[dict[str, Any]],
    ground_truths: list[dict[str, Any]],
) -> EvaluationResult:
    """Full evaluation producing structured EvaluationResult."""
    if not predictions or not ground_truths:
        # Return zeroed result that also computes to 0.0 combined
        r = EvaluationResult()
        r.workload_metrics.total_segments = 0
        return r

    result = EvaluationResult()

    # Mistake classification
    result.mistake_metrics = _binary_metrics(
        predictions, ground_truths, "is_mistake",
    )

    # Pickup classification
    result.pickup_metrics = _binary_metrics(
        predictions, ground_truths, "is_pickup",
    )

    # Review need classification
    result.review_metrics = _binary_metrics(
        predictions, ground_truths, "needs_review",
    )

    # Splice safety classification
    result.splice_metrics = _binary_metrics(
        predictions, ground_truths, "safe_to_auto_cut",
    )

    # Priority accuracy
    priority_correct = sum(
        1 for p, g in zip(predictions, ground_truths)
        if p.get("priority") == g.get("priority")
    )
    result.priority_accuracy = priority_correct / len(predictions) if predictions else 0.0

    # Action accuracy
    action_correct = sum(
        1 for p, g in zip(predictions, ground_truths)
        if p.get("action") == g.get("preferred_action", g.get("action"))
    )
    result.action_accuracy = action_correct / len(predictions) if predictions else 0.0

    # Workload metrics
    result.workload_metrics = _compute_workload(predictions, ground_truths)

    return result


def evaluate_ranking(
    predicted_rankings: list[list[str]],
    ground_truth_rankings: list[list[str]],
    predicted_top1: list[str],
    ground_truth_top1: list[str],
) -> RankingMetrics:
    """Evaluate alt-take ranking quality."""
    metrics = RankingMetrics()

    # Top-1 accuracy
    metrics.top1_total = len(predicted_top1)
    metrics.top1_correct = sum(
        1 for p, g in zip(predicted_top1, ground_truth_top1) if p == g
    )

    # Kendall tau + pairwise accuracy
    for pred_rank, gt_rank in zip(predicted_rankings, ground_truth_rankings):
        tau = _kendall_tau(pred_rank, gt_rank)
        if tau is not None:
            metrics.kendall_tau_sum += tau
            metrics.kendall_tau_count += 1

        pw_correct, pw_total = _pairwise_accuracy(pred_rank, gt_rank)
        metrics.pairwise_correct += pw_correct
        metrics.pairwise_total += pw_total

    return metrics


def compute_combined_score(
    metrics_dict: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> float:
    """Compute single combined optimization score from metrics.

    Default weighting prioritizes editorial usefulness:
    - Catching real mistakes is most important (high recall)
    - Low false positive rate keeps workload manageable
    - Ranking accuracy matters for alt-take workflows
    """
    w = weights or {
        "mistake_f1": 0.25,
        "pickup_f1": 0.20,
        "ranking_top1": 0.10,
        "splice_accuracy": 0.10,
        "workload_efficiency": 0.15,
        "priority_accuracy": 0.10,
        "action_accuracy": 0.10,
    }

    mistake = metrics_dict.get("mistake", {})
    pickup = metrics_dict.get("pickup", {})
    ranking = metrics_dict.get("ranking", {})
    splice = metrics_dict.get("splice", {})
    workload = metrics_dict.get("workload", {})

    # If no segments were evaluated, return 0
    total_segs = workload.get("total_segments", metrics_dict.get("total_segments", -1))
    if total_segs == 0:
        return 0.0

    components = {
        "mistake_f1": mistake.get("f1", 0.0),
        "pickup_f1": pickup.get("f1", 0.0),
        "ranking_top1": ranking.get("top1_accuracy", 0.0),
        "splice_accuracy": splice.get("accuracy", 0.0),
        "workload_efficiency": 1.0 - workload.get("flag_rate", 0.5),
        "priority_accuracy": metrics_dict.get("priority_accuracy", 0.0),
        "action_accuracy": metrics_dict.get("action_accuracy", 0.0),
    }

    score = sum(components.get(k, 0.0) * v for k, v in w.items())
    total_weight = sum(w.values())
    return score / total_weight if total_weight > 0 else 0.0


# ---------------------------------------------------------------------------
# Confusion matrix
# ---------------------------------------------------------------------------

def confusion_matrix(
    predictions: list[dict[str, Any]],
    ground_truths: list[dict[str, Any]],
    field_name: str,
) -> dict[str, int]:
    """Build confusion matrix for a boolean field."""
    m = _binary_metrics(predictions, ground_truths, field_name)
    return {"tp": m.tp, "fp": m.fp, "fn": m.fn, "tn": m.tn}


def multi_class_confusion(
    predictions: list[dict[str, Any]],
    ground_truths: list[dict[str, Any]],
    field_name: str,
    classes: list[str],
) -> dict[str, dict[str, int]]:
    """Build NxN confusion matrix for a multi-class field (e.g., priority)."""
    matrix: dict[str, dict[str, int]] = {c: {c2: 0 for c2 in classes} for c in classes}
    for p, g in zip(predictions, ground_truths):
        pred_val = p.get(field_name, "")
        true_val = g.get(field_name, "")
        if pred_val in matrix and true_val in matrix[pred_val]:
            matrix[true_val][pred_val] += 1
    return matrix


# ---------------------------------------------------------------------------
# Score distribution analysis
# ---------------------------------------------------------------------------

def score_distribution(
    results: list[dict[str, Any]],
    score_field: str,
    n_bins: int = 10,
) -> dict[str, Any]:
    """Compute histogram of score values for analysis."""
    values = [r.get(score_field, 0.0) for r in results if score_field in r]
    if not values:
        return {"bins": [], "counts": [], "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}

    min_val = min(values)
    max_val = max(values)
    bin_width = (max_val - min_val) / n_bins if max_val > min_val else 1.0

    bins = [min_val + i * bin_width for i in range(n_bins + 1)]
    counts = [0] * n_bins

    for v in values:
        idx = min(int((v - min_val) / bin_width), n_bins - 1) if bin_width > 0 else 0
        counts[idx] += 1

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)

    return {
        "bins": [round(b, 4) for b in bins],
        "counts": counts,
        "mean": round(mean, 4),
        "std": round(std, 4),
        "min": round(min_val, 4),
        "max": round(max_val, 4),
        "n": len(values),
    }


# ---------------------------------------------------------------------------
# ROC-like threshold sweep
# ---------------------------------------------------------------------------

def threshold_sweep(
    predictions: list[dict[str, Any]],
    ground_truths: list[dict[str, Any]],
    score_field: str,
    truth_field: str,
    thresholds: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Sweep thresholds to generate ROC-like precision/recall/FPR curve.

    Args:
        predictions: List of prediction dicts with continuous score values.
        ground_truths: List of ground truth dicts with boolean labels.
        score_field: Key in predictions for the continuous score (e.g., "mistake_score").
        truth_field: Key in ground_truths for the boolean label (e.g., "is_mistake").
        thresholds: List of threshold values to test. Defaults to 0.0-1.0 in 0.05 steps.

    Returns:
        List of {threshold, precision, recall, f1, fpr} dicts.
    """
    if thresholds is None:
        thresholds = [i * 0.05 for i in range(21)]

    curve = []
    for t in thresholds:
        cm = ClassificationMetrics()
        for p, g in zip(predictions, ground_truths):
            pred_positive = p.get(score_field, 0.0) > t
            actual_positive = g.get(truth_field, False)
            if pred_positive and actual_positive:
                cm.tp += 1
            elif pred_positive and not actual_positive:
                cm.fp += 1
            elif not pred_positive and actual_positive:
                cm.fn += 1
            else:
                cm.tn += 1

        curve.append({
            "threshold": round(t, 4),
            "precision": round(cm.precision, 4),
            "recall": round(cm.recall, 4),
            "f1": round(cm.f1, 4),
            "fpr": round(cm.false_positive_rate, 4),
        })

    return curve


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _binary_metrics(
    predictions: list[dict],
    ground_truths: list[dict],
    field: str,
) -> ClassificationMetrics:
    """Compute binary classification metrics for a field."""
    cm = ClassificationMetrics()
    for p, g in zip(predictions, ground_truths):
        pred = bool(p.get(field, False))
        actual = bool(g.get(field, False))
        if pred and actual:
            cm.tp += 1
        elif pred and not actual:
            cm.fp += 1
        elif not pred and actual:
            cm.fn += 1
        else:
            cm.tn += 1
    return cm


def _compute_workload(
    predictions: list[dict],
    ground_truths: list[dict],
) -> WorkloadMetrics:
    """Compute editorial workload metrics."""
    wm = WorkloadMetrics()
    wm.total_segments = len(predictions)

    for p in predictions:
        action = p.get("action", "no_action")
        priority = p.get("priority", "info")

        if action not in ("no_action", "safe_auto_cut"):
            wm.flagged_segments += 1

        if priority == "critical":
            wm.critical_count += 1
        elif priority == "high":
            wm.high_count += 1
        elif priority == "medium":
            wm.medium_count += 1
        elif priority == "low":
            wm.low_count += 1

    # Estimate duration from ground truth if available
    for g in ground_truths:
        wm.total_duration_ms += g.get("duration_ms", 3000)

    return wm


def _kendall_tau(ranking_a: list[str], ranking_b: list[str]) -> float | None:
    """Compute Kendall tau correlation between two rankings."""
    common = set(ranking_a) & set(ranking_b)
    if len(common) < 2:
        return None

    items = sorted(common)
    pos_a = {item: i for i, item in enumerate(ranking_a) if item in common}
    pos_b = {item: i for i, item in enumerate(ranking_b) if item in common}

    concordant = 0
    discordant = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a_diff = pos_a[items[i]] - pos_a[items[j]]
            b_diff = pos_b[items[i]] - pos_b[items[j]]
            if a_diff * b_diff > 0:
                concordant += 1
            elif a_diff * b_diff < 0:
                discordant += 1

    n_pairs = concordant + discordant
    if n_pairs == 0:
        return 0.0
    return (concordant - discordant) / n_pairs


def _pairwise_accuracy(pred_ranking: list[str], gt_ranking: list[str]) -> tuple[int, int]:
    """Compute pairwise ranking accuracy."""
    common = set(pred_ranking) & set(gt_ranking)
    if len(common) < 2:
        return 0, 0

    gt_pos = {item: i for i, item in enumerate(gt_ranking) if item in common}
    pred_pos = {item: i for i, item in enumerate(pred_ranking) if item in common}

    items = sorted(common)
    correct = 0
    total = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            gt_order = gt_pos[items[i]] < gt_pos[items[j]]
            pred_order = pred_pos[items[i]] < pred_pos[items[j]]
            if gt_order == pred_order:
                correct += 1
            total += 1

    return correct, total
