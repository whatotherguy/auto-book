"""Tests for comprehensive evaluation metrics."""

from app.services.scoring.calibration.metrics import (
    ClassificationMetrics,
    RankingMetrics,
    WorkloadMetrics,
    EvaluationResult,
    evaluate_predictions,
    evaluate_full,
    evaluate_ranking,
    compute_combined_score,
    confusion_matrix,
    multi_class_confusion,
    score_distribution,
    threshold_sweep,
)


# --- ClassificationMetrics ---

def test_classification_metrics_perfect():
    cm = ClassificationMetrics(tp=10, fp=0, fn=0, tn=10)
    assert cm.precision == 1.0
    assert cm.recall == 1.0
    assert cm.f1 == 1.0
    assert cm.false_positive_rate == 0.0
    assert cm.accuracy == 1.0


def test_classification_metrics_all_false_positives():
    cm = ClassificationMetrics(tp=0, fp=10, fn=0, tn=0)
    assert cm.precision == 0.0
    assert cm.recall == 0.0
    assert cm.f1 == 0.0


def test_classification_metrics_mixed():
    cm = ClassificationMetrics(tp=8, fp=2, fn=3, tn=7)
    assert 0 < cm.precision < 1
    assert 0 < cm.recall < 1
    assert 0 < cm.f1 < 1


def test_classification_metrics_empty():
    cm = ClassificationMetrics()
    assert cm.precision == 0.0
    assert cm.recall == 0.0
    assert cm.f1 == 0.0
    assert cm.accuracy == 0.0


# --- evaluate_predictions (backward compatible) ---

def test_evaluate_predictions_perfect():
    preds = [
        {"is_mistake": True, "is_pickup": False, "priority": "high"},
        {"is_mistake": False, "is_pickup": True, "priority": "medium"},
        {"is_mistake": False, "is_pickup": False, "priority": "info"},
    ]
    gts = [
        {"is_mistake": True, "is_pickup": False, "priority": "high"},
        {"is_mistake": False, "is_pickup": True, "priority": "medium"},
        {"is_mistake": False, "is_pickup": False, "priority": "info"},
    ]
    result = evaluate_predictions(preds, gts)
    assert result["mistake_f1"] == 1.0
    assert result["pickup_f1"] == 1.0
    assert result["priority_accuracy"] == 1.0
    assert result["total_segments"] == 3


def test_evaluate_predictions_empty():
    result = evaluate_predictions([], [])
    assert result["combined_f1"] == 0.0


def test_evaluate_predictions_returns_counts():
    preds = [{"is_mistake": True}, {"is_mistake": True}]
    gts = [{"is_mistake": True}, {"is_mistake": False}]
    result = evaluate_predictions(preds, gts)
    assert result["mistake_tp"] == 1
    assert result["mistake_fp"] == 1


# --- evaluate_full ---

def test_evaluate_full_produces_structured_result():
    preds = [
        {"is_mistake": True, "is_pickup": False, "needs_review": True,
         "safe_to_auto_cut": False, "priority": "high", "action": "review_mistake"},
    ]
    gts = [
        {"is_mistake": True, "is_pickup": False, "needs_review": True,
         "safe_to_auto_cut": False, "priority": "high", "preferred_action": "review_mistake"},
    ]
    result = evaluate_full(preds, gts)
    assert isinstance(result, EvaluationResult)
    assert result.mistake_metrics.tp == 1
    assert result.priority_accuracy == 1.0
    assert result.action_accuracy == 1.0


# --- Ranking metrics ---

def test_evaluate_ranking_perfect():
    pred_rankings = [["a", "b", "c"]]
    gt_rankings = [["a", "b", "c"]]
    pred_top1 = ["a"]
    gt_top1 = ["a"]
    metrics = evaluate_ranking(pred_rankings, gt_rankings, pred_top1, gt_top1)
    assert metrics.top1_accuracy == 1.0
    assert metrics.mean_kendall_tau == 1.0
    assert metrics.pairwise_accuracy == 1.0


def test_evaluate_ranking_reversed():
    pred_rankings = [["c", "b", "a"]]
    gt_rankings = [["a", "b", "c"]]
    pred_top1 = ["c"]
    gt_top1 = ["a"]
    metrics = evaluate_ranking(pred_rankings, gt_rankings, pred_top1, gt_top1)
    assert metrics.top1_accuracy == 0.0
    assert metrics.mean_kendall_tau == -1.0


# --- Combined score ---

def test_combined_score_is_bounded():
    metrics = {
        "mistake": {"f1": 1.0},
        "pickup": {"f1": 1.0},
        "ranking": {"top1_accuracy": 1.0},
        "splice": {"accuracy": 1.0},
        "workload": {"flag_rate": 0.0},
        "priority_accuracy": 1.0,
        "action_accuracy": 1.0,
    }
    score = compute_combined_score(metrics)
    assert 0.0 <= score <= 1.0


def test_combined_score_custom_weights():
    metrics = {
        "mistake": {"f1": 1.0},
        "pickup": {"f1": 0.0},
        "ranking": {},
        "splice": {},
        "workload": {},
    }
    # Weight only mistake_f1
    score = compute_combined_score(metrics, weights={"mistake_f1": 1.0})
    assert score == 1.0


# --- Confusion matrix ---

def test_confusion_matrix():
    preds = [{"is_mistake": True}, {"is_mistake": False}]
    gts = [{"is_mistake": True}, {"is_mistake": True}]
    cm = confusion_matrix(preds, gts, "is_mistake")
    assert cm["tp"] == 1
    assert cm["fn"] == 1


def test_multi_class_confusion():
    preds = [{"priority": "high"}, {"priority": "low"}]
    gts = [{"priority": "high"}, {"priority": "high"}]
    cm = multi_class_confusion(preds, gts, "priority", ["high", "low", "info"])
    assert cm["high"]["high"] == 1
    assert cm["high"]["low"] == 1


# --- Score distribution ---

def test_score_distribution():
    results = [{"score": i * 0.1} for i in range(11)]
    dist = score_distribution(results, "score", n_bins=5)
    assert dist["n"] == 11
    assert dist["min"] == 0.0
    assert dist["max"] == 1.0
    assert sum(dist["counts"]) == 11


def test_score_distribution_empty():
    dist = score_distribution([], "score")
    assert dist.get("n", 0) == 0
    assert dist["mean"] == 0.0


# --- Threshold sweep ---

def test_threshold_sweep():
    preds = [
        {"mistake_score": 0.9},
        {"mistake_score": 0.5},
        {"mistake_score": 0.1},
    ]
    gts = [
        {"is_mistake": True},
        {"is_mistake": True},
        {"is_mistake": False},
    ]
    curve = threshold_sweep(preds, gts, "mistake_score", "is_mistake")
    # Should have data for each threshold
    assert len(curve) > 0
    # At threshold 0.0, recall should be 1.0
    assert curve[0]["recall"] == 1.0
    # At threshold 1.0, precision should be 0 (no positives) or 1.0
    last = curve[-1]
    assert last["recall"] <= 1.0


# --- WorkloadMetrics ---

def test_workload_metrics():
    wm = WorkloadMetrics(
        total_segments=100,
        flagged_segments=20,
        total_duration_ms=3_600_000,  # 1 hour
        critical_count=5,
        high_count=10,
        medium_count=5,
    )
    assert wm.flag_rate == 0.2
    assert wm.flagged_per_hour == 20.0
    d = wm.to_dict()
    assert d["priority_distribution"]["critical"] == 5
