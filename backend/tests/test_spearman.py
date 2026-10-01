"""Spearman rank behavior and the shared Pearson result schema."""

import json

import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

from app.core.metrics import correlation_metrics
from app.core.schema import classify_column


def compare(frame, reduced=None, method="spearman"):
    columns = [classify_column(frame[name], name) for name in frame.columns]
    return correlation_metrics(frame, frame if reduced is None else reduced,
                               columns, list(frame.columns), method)


def test_monotone_nonlinear_correlation_differs_from_pearson():
    frame = pd.DataFrame({"x": np.arange(1, 10), "y": np.arange(1, 10)**3})
    rank, linear = compare(frame), compare(frame, method="pearson")
    assert rank["matrix_original"][0][1] == 1
    assert linear["matrix_original"][0][1] < 0.95
    assert rank.keys() == linear.keys()


def test_tied_ranks_and_negative_correlations_match_scipy():
    frame = pd.DataFrame({"x": [1, 1, 2, 3, 4], "y": [5, 4, 4, 2, 1],
                          "z": [2, 1, 2, 4, 3]})
    result = compare(frame)
    expected = spearmanr(frame.to_numpy(), axis=0).statistic
    np.testing.assert_allclose(result["matrix_original"], expected, atol=5e-5)
    assert result["matrix_original"][0][1] < 0
    assert result["score"] == 100


def test_reduced_ranks_are_computed_independently():
    frame = pd.DataFrame({"x": [1, 2, 3, 4], "y": [2, 4, 6, 8]})
    reduced = frame.copy()
    reduced["y"] = [8, 6, 4, 2]
    result = compare(frame, reduced)
    assert result["matrix_original"][0][1] == 1
    assert result["matrix_reduced"][0][1] == -1
    assert result["max_gap"] == 2
    assert result["score"] == 0


@pytest.mark.parametrize("method", ["pearson", "spearman"])
@pytest.mark.parametrize("frame", [
    pd.DataFrame(), pd.DataFrame({"x": [1, 2]}),
    pd.DataFrame({"x": [1, 1], "y": [np.nan, np.nan], "z": [2, 2]}),
    pd.DataFrame({"x": [1, 2, np.nan, 4], "y": [4, np.nan, 2, 1]}),
    pd.DataFrame({"x": pd.Series(dtype=float), "y": pd.Series(dtype=float)}),
])
def test_edge_cases_share_complete_finite_schema(frame, method):
    result = compare(frame, method=method)
    assert {"score", "columns", "method", "frobenius", "mean_gap", "max_gap",
            "corr_of_corr", "matrix_original", "matrix_reduced"} <= result.keys()
    assert result["method"] == method
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("method", ["kendall", "invalid", None])
def test_unsupported_methods_fail(method):
    with pytest.raises(ValueError, match="method"):
        compare(pd.DataFrame({"x": [1, 2]}), method=method)
