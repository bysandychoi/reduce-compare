"""Pair rank ordering, numerical validation, and upstream integration."""

import copy
import json

import numpy as np
import pandas as pd
import pytest

from app.core.metrics import correlation_metrics
from app.core.network import correlation_network
from app.core.relationships import classify_relationships, rank_correlation_pairs
from app.core.schema import classify_column


def metrics(method="pearson"):
    return {"method": method, "columns": ["a", "b", "c"],
            "matrix_original": [[1, 0.8, -0.7], [0.8, 1, 0.2], [-0.7, 0.2, 1]],
            "matrix_reduced": [[1, -0.8, -0.4], [-0.8, 1, 0.5], [-0.4, 0.5, 1]]}


@pytest.mark.parametrize("method", ["pearson", "spearman"])
def test_ranks_all_unique_pairs_and_signed_differences(method):
    source = metrics(method)
    snapshot = copy.deepcopy(source)
    result = rank_correlation_pairs(source)
    assert result["method"] == method
    assert [(p["column_a"], p["column_b"]) for p in result["pairs"]] == [
        ("a", "b"), ("a", "c"), ("b", "c")]
    assert [p["abs_difference"] for p in result["pairs"]] == [1.6, 0.3, 0.3]
    assert result["pairs"][0]["difference"] == -1.6
    assert result["pairs"][0]["original_r"] == 0.8
    assert source == snapshot
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("columns,matrix", [([], []), (["a"], [[1]])])
def test_no_pairs_with_fewer_than_two_columns(columns, matrix):
    result = rank_correlation_pairs({"method": "spearman", "columns": columns,
                                    "matrix_original": matrix, "matrix_reduced": matrix})
    assert result == {"method": "spearman", "pairs": []}


@pytest.mark.parametrize("change", [
    {"method": "kendall"}, {"columns": None}, {"columns": ["a", "a", "c"]},
    {"matrix_original": None}, {"matrix_reduced": [[1]]},
    {"matrix_original": [[1, np.nan, 0], [np.nan, 1, 0], [0, 0, 1]]},
    {"matrix_reduced": [[1, 0.8, 0], [0.6, 1, 0], [0, 0, 1]]},
])
def test_invalid_metric_result_fails(change):
    source = metrics()
    source.update(change)
    with pytest.raises(ValueError):
        rank_correlation_pairs(source)


@pytest.mark.parametrize("method", ["pearson", "spearman"])
def test_actual_metric_results(method):
    original = pd.DataFrame({"a": [1, 2, 3, 4], "b": [1, 4, 9, 16], "c": [4, 3, 2, 1]})
    reduced = original.copy()
    reduced["b"] = [16, 9, 4, 1]
    columns = [classify_column(original[c], c) for c in original.columns]
    result = correlation_metrics(original, reduced, columns, list(original.columns), method)
    ranked = rank_correlation_pairs(result)
    assert len(ranked["pairs"]) == 3
    assert ranked["pairs"][0]["abs_difference"] > 1.9
    assert ranked["pairs"][-1]["abs_difference"] == 0


def relationship_metrics():
    return {"method": "spearman", "columns": ["a", "b", "c", "d"],
            "matrix_original": [[1, 0.8, -0.7, 0.2], [0.8, 1, 0.1, 0],
                                [-0.7, 0.1, 1, 0.6], [0.2, 0, 0.6, 1]],
            "matrix_reduced": [[1, -0.8, -0.4, 0.5], [-0.8, 1, 0.2, 0],
                               [-0.4, 0.2, 1, 0.6], [0.5, 0, 0.6, 1]]}


def test_all_relationship_classes_and_sign_reversal():
    source = relationship_metrics()
    snapshot = copy.deepcopy(source)
    result = classify_relationships(source, 0.5)
    pairs = {(p["column_a"], p["column_b"]): p for p in result["pairs"]}
    assert result["counts"] == {"maintained": 2, "lost": 1, "new": 1, "absent": 2}
    assert pairs["a", "b"]["status"] == "maintained"
    assert pairs["a", "b"]["sign_changed"] is True
    assert pairs["a", "c"]["status"] == "lost"
    assert pairs["a", "d"]["status"] == "new"
    assert pairs["b", "c"]["status"] == "absent"
    assert pairs["c", "d"]["sign_changed"] is False
    assert source == snapshot
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("threshold", [0, 0.2, 0.5, 0.6, 0.8, 1])
def test_classification_matches_network_edges_and_keeps_rank_order(threshold):
    source = relationship_metrics()
    result = classify_relationships(source, threshold)
    for matrix, flag in [("matrix_original", "original_present"),
                         ("matrix_reduced", "reduced_present")]:
        graph = correlation_network(source["columns"], source[matrix], threshold)
        edges = {(e["source"], e["target"]) for e in graph["edges"]}
        assert edges == {(p["column_a"], p["column_b"]) for p in result["pairs"] if p[flag]}
    gaps = [p["abs_difference"] for p in result["pairs"]]
    assert gaps == sorted(gaps, reverse=True)
    assert sum(result["counts"].values()) == 6


@pytest.mark.parametrize("threshold", [True, None, "0.5", np.nan, np.inf, -0.1, 1.1, 10**100])
def test_classification_rejects_invalid_threshold(threshold):
    with pytest.raises(ValueError, match="Threshold"):
        classify_relationships(relationship_metrics(), threshold)


def test_empty_classification_and_boundary_one():
    empty = {"method": "pearson", "columns": [],
             "matrix_original": [], "matrix_reduced": []}
    result = classify_relationships(empty)
    assert result["pairs"] == []
    assert all(count == 0 for count in result["counts"].values())
    source = {"method": "pearson", "columns": ["a", "b"],
              "matrix_original": [[1, -1], [-1, 1]], "matrix_reduced": [[1, 1], [1, 1]]}
    pair = classify_relationships(source, 1)["pairs"][0]
    assert pair["status"] == "maintained" and pair["sign_changed"] is True
