"""Original/reduced correlation pair comparisons."""

from __future__ import annotations

from numbers import Real

import numpy as np

from app.core.network import _validated_matrix


def _undefined_mask(metrics: dict, name: str, size: int) -> np.ndarray:
    value = metrics.get(name, np.zeros((size, size), dtype=bool))
    mask = np.asarray(value)
    if size == 0 and mask.size == 0:
        return np.zeros((0, 0), dtype=bool)
    if mask.shape != (size, size) or mask.dtype != bool or not np.array_equal(mask, mask.T):
        raise ValueError("Undefined masks must be symmetric boolean matrices")
    return mask


def rank_correlation_pairs(metrics: dict) -> dict:
    """Rank unique pairs by |reduced - original|; input order breaks ties.

    Accepts the complete result of correlation_metrics for either supported
    method. Undefined pairs have null values and sort after measured changes.
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
    undefined_o = _undefined_mask(metrics, "undefined_original", len(columns))
    undefined_r = _undefined_mask(metrics, "undefined_reduced", len(columns))
    pairs = []
    for i, column in enumerate(columns):
        for j in range(i + 1, len(columns)):
            a, b = float(original[i, j]), float(reduced[i, j])
            missing_o, missing_r = bool(undefined_o[i, j]), bool(undefined_r[i, j])
            undefined = missing_o or missing_r
            difference = None if undefined else round(b - a, 8)
            pairs.append({
                "column_a": column, "column_b": columns[j],
                "original_r": None if missing_o else a, "reduced_r": None if missing_r else b,
                "original_undefined": missing_o, "reduced_undefined": missing_r,
                "undefined": undefined, "difference": difference,
                "abs_difference": None if undefined else abs(difference),
            })
    pairs.sort(key=lambda pair: (pair["undefined"], -(pair["abs_difference"] or 0)))
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
    counts = dict.fromkeys(["maintained", "lost", "new", "absent", "undefined"], 0)
    pairs = []
    statuses = {(True, True): "maintained", (True, False): "lost",
                (False, True): "new", (False, False): "absent"}
    for pair in ranked["pairs"]:
        a, b = pair["original_r"], pair["reduced_r"]
        original_present = None if a is None else abs(a) >= threshold
        reduced_present = None if b is None else abs(b) >= threshold
        status = "undefined" if pair["undefined"] else statuses[original_present, reduced_present]
        counts[status] += 1
        pairs.append({
            **pair, "status": status,
            "original_present": original_present, "reduced_present": reduced_present,
            "sign_changed": bool(original_present and reduced_present and a * b < 0),
        })
    return {"method": ranked["method"], "threshold": float(threshold),
            "pairs": pairs, "counts": counts}
