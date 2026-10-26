"""Dependency-free metrics used in the Chapter 3 annotation study."""

from __future__ import annotations

from math import isnan
from typing import Iterable, Sequence


def _binary(values: Iterable[int], name: str) -> list[int]:
    result = list(values)
    if any(value not in (0, 1) for value in result):
        raise ValueError(f"{name} must contain only 0 and 1")
    return result


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return float("nan") if denominator == 0 else numerator / denominator


def classification_metrics(y_true: Iterable[int], y_pred: Iterable[int]) -> dict[str, float | int]:
    truth = _binary(y_true, "y_true")
    prediction = _binary(y_pred, "y_pred")
    if len(truth) != len(prediction):
        raise ValueError("y_true and y_pred must have the same length")
    if not truth:
        raise ValueError("At least one observation is required")

    tp = sum(actual == 1 and predicted == 1 for actual, predicted in zip(truth, prediction))
    tn = sum(actual == 0 and predicted == 0 for actual, predicted in zip(truth, prediction))
    fp = sum(actual == 0 and predicted == 1 for actual, predicted in zip(truth, prediction))
    fn = sum(actual == 1 and predicted == 0 for actual, predicted in zip(truth, prediction))
    n = len(truth)

    accuracy = (tp + tn) / n
    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    specificity = _safe_ratio(tn, tn + fp)
    f1 = (
        float("nan")
        if isnan(precision) or isnan(recall) or precision + recall == 0
        else 2 * precision * recall / (precision + recall)
    )

    observed_agreement = accuracy
    true_positive_share = (tp + fn) / n
    predicted_positive_share = (tp + fp) / n
    expected_agreement = (
        true_positive_share * predicted_positive_share
        + (1 - true_positive_share) * (1 - predicted_positive_share)
    )
    cohen_kappa = _safe_ratio(
        observed_agreement - expected_agreement,
        1 - expected_agreement,
    )

    return {
        "n": n,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy": accuracy,
        "human_positive_share": true_positive_share,
        "predicted_positive_share": predicted_positive_share,
        "false_positive_proportion": fp / n,
        "false_negative_proportion": fn / n,
        "false_positive_rate": _safe_ratio(fp, fp + tn),
        "false_negative_rate": _safe_ratio(fn, fn + tp),
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "cohen_kappa": cohen_kappa,
    }


def majority_vote(labels: Sequence[int], tie_policy: str = "error") -> int | None:
    values = _binary(labels, "labels")
    if not values:
        raise ValueError("At least one label is required")
    positives = sum(values)
    negatives = len(values) - positives
    if positives > negatives:
        return 1
    if negatives > positives:
        return 0
    if tie_policy == "zero":
        return 0
    if tie_policy == "one":
        return 1
    if tie_policy == "nan":
        return None
    if tie_policy == "error":
        raise ValueError("Majority vote is tied and no substantive tie rule was specified")
    raise ValueError(f"Unsupported tie policy: {tie_policy}")


def fleiss_kappa_binary(ratings: Sequence[Sequence[int]]) -> float:
    """Calculate Fleiss' kappa for a complete item by rater matrix."""

    matrix = [_binary(row, "ratings row") for row in ratings]
    if not matrix:
        raise ValueError("At least one item is required")
    n_raters = len(matrix[0])
    if n_raters < 2:
        raise ValueError("At least two raters or repeated calls are required")
    if any(len(row) != n_raters for row in matrix):
        raise ValueError("Every item must have the same number of ratings")

    item_agreements = []
    total_zero = 0
    total_one = 0
    for row in matrix:
        n_one = sum(row)
        n_zero = n_raters - n_one
        total_zero += n_zero
        total_one += n_one
        item_agreements.append(
            (n_zero * (n_zero - 1) + n_one * (n_one - 1))
            / (n_raters * (n_raters - 1))
        )

    observed = sum(item_agreements) / len(item_agreements)
    total_ratings = len(matrix) * n_raters
    p_zero = total_zero / total_ratings
    p_one = total_one / total_ratings
    expected = p_zero**2 + p_one**2
    if expected == 1:
        return 1.0 if observed == 1 else float("nan")
    return (observed - expected) / (1 - expected)
