"""Convert correlation matrices into stable, undirected network data (T097)."""

from __future__ import annotations

from numbers import Real

import numpy as np


def _validated_matrix(columns: list[str], matrix: object) -> np.ndarray:
    if any(not isinstance(column, str) for column in columns):
        raise ValueError("Column names must be strings")
    if len(set(columns)) != len(columns):
        raise ValueError("Column names must be unique")
    try:
        if np.iscomplexobj(matrix):
            raise ValueError("Correlation matrix must contain real values")
        values = np.asarray(matrix, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("Correlation matrix must contain numeric values") from error
    if not columns and values.shape == (0,):
        values = values.reshape(0, 0)
    if values.shape != (len(columns), len(columns)):
        raise ValueError("Correlation matrix shape must match the column count")
    if np.isinf(values).any() or (np.abs(values[np.isfinite(values)]) > 1).any():
        raise ValueError("Correlations must be within [-1, 1] or NaN")
    if not np.allclose(values, values.T, rtol=0, atol=1e-8, equal_nan=True):
        raise ValueError("Correlation matrix must be symmetric")
    return values


def correlation_network(columns: list[str], matrix: object, threshold: float = 0.5) -> dict:
    """Return all column nodes and unique pairs with finite |r| >= threshold.

    Accepts either matrix_original or matrix_reduced from correlation_metrics.
    Column names serve as stable node IDs; layout belongs to the renderer.
    Undefined pairs are omitted rather than represented as zero correlation.
    """
    if (isinstance(threshold, bool) or not isinstance(threshold, Real)
            or not 0 <= threshold <= 1 or not np.isfinite(threshold)):
        raise ValueError("Threshold must be a finite number within [0, 1]")
    values = _validated_matrix(columns, matrix)
    edges = []
    for i, source in enumerate(columns):
        for j in range(i + 1, len(columns)):
            correlation = float(values[i, j])
            if not np.isfinite(correlation) or abs(correlation) < threshold:
                continue
            sign = "positive" if correlation > 0 else "negative" if correlation < 0 else "zero"
            edges.append({
                "source": source, "target": columns[j], "correlation": correlation,
                "weight": abs(correlation), "sign": sign,
            })
    return {
        "nodes": [{"id": column, "label": column} for column in columns],
        "edges": edges,
        "threshold": float(threshold),
    }
