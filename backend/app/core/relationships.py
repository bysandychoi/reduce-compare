"""Original/reduced correlation pair comparisons."""

from __future__ import annotations

from numbers import Real

import numpy as np

from app.core.network import _validated_matrix


def rank_correlation_pairs(metrics: dict) -> dict:
    """Rank unique pairs by |reduced - original|; input order breaks ties.

    Accepts the complete result of correlation_metrics for either supported
    method. Undefined correlations already map to zero in that upstream result.
    """
    if not isinstance(metrics, dict) or metrics.get("method") not in ("pearson", "spearman"):
        raise ValueError("Metrics must specify pearson or spearman")
    if not isinstance(metrics.get("columns"), list):
        raise ValueError("Metrics must include a column list")
    columns = metrics["columns"]
    original = _validated_matrix(columns, metrics.get("matrix_original"))
    reduced = _validated_matrix(columns, metrics.get("matrix_reduced"))
    if not np.isfinite(original).all() or not np.isfinite(reduced).all():
        raise ValueError("Metrics matrices must contain finite correlations")
    pairs = []
    for i, column in enumerate(columns):
        for j in range(i + 1, len(columns)):
            a, b = float(original[i, j]), float(reduced[i, j])
            difference = round(b - a, 8)
            pairs.append({
                "column_a": column, "column_b": columns[j],
                "original_r": a, "reduced_r": b,
                "difference": difference, "abs_difference": abs(difference),
            })
    pairs.sort(key=lambda pair: pair["abs_difference"], reverse=True)
    return {"method": metrics["method"], "pairs": pairs}


def classify_relationships(metrics: dict, threshold: float = 0.5) -> dict:
    """Classify pair topology by inclusive absolute correlation thresholds.

    A maintained pair may reverse sign; that fact is returned separately from
    topology. Results describe observed relationships, not causes of changes.
    """
    if (isinstance(threshold, bool) or not isinstance(threshold, Real)
            or not 0 <= threshold <= 1 or not np.isfinite(threshold)):
        raise ValueError("Threshold must be a finite number within [0, 1]")
    ranked = rank_correlation_pairs(metrics)
    counts = dict.fromkeys(["maintained", "lost", "new", "absent"], 0)
    pairs = []
    statuses = {(True, True): "maintained", (True, False): "lost",
                (False, True): "new", (False, False): "absent"}
    for pair in ranked["pairs"]:
        a, b = pair["original_r"], pair["reduced_r"]
        original_present, reduced_present = abs(a) >= threshold, abs(b) >= threshold
        status = statuses[original_present, reduced_present]
        counts[status] += 1
        pairs.append({
            **pair, "status": status,
            "original_present": original_present, "reduced_present": reduced_present,
            "sign_changed": bool(original_present and reduced_present and a * b < 0),
        })
    return {"method": ranked["method"], "threshold": float(threshold),
            "pairs": pairs, "counts": counts}
