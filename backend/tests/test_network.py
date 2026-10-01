"""Correlation network thresholds, stable nodes, and invalid inputs (T097)."""

import json

import numpy as np
import pandas as pd
import pytest

from app.core.metrics import correlation_metrics
from app.core.network import correlation_network
from app.core.schema import classify_column

COLUMNS = ["a", "b", "c", "isolated"]
MATRIX = [
    [1, 0.8, -0.5, 0],
    [0.8, 1, 0.2, 0],
    [-0.5, 0.2, 1, 0],
    [0, 0, 0, 1],
]


def test_threshold_is_inclusive_and_preserves_signed_edges():
    graph = correlation_network(COLUMNS, MATRIX, 0.5)
    assert graph["edges"] == [
        {"source": "a", "target": "b", "correlation": 0.8,
         "weight": 0.8, "sign": "positive"},
        {"source": "a", "target": "c", "correlation": -0.5,
         "weight": 0.5, "sign": "negative"},
    ]
    assert graph["nodes"] == [{"id": name, "label": name} for name in COLUMNS]
    assert json.loads(json.dumps(graph, allow_nan=False)) == graph


def test_threshold_controls_edge_count_without_changing_nodes():
    graphs = [correlation_network(COLUMNS, MATRIX, t) for t in [0, 0.2, 0.5, 0.8, 1]]
    assert [len(graph["edges"]) for graph in graphs] == [6, 3, 2, 1, 0]
    assert all(graph["nodes"] == graphs[0]["nodes"] for graph in graphs)
    pairs = [(edge["source"], edge["target"]) for edge in graphs[0]["edges"]]
    assert len(set(pairs)) == 6
    assert all(source != target for source, target in pairs)
    assert graphs[0]["edges"][-1]["sign"] == "zero"


@pytest.mark.parametrize("coefficient", [1, -1])
def test_perfect_correlations_at_threshold_one(coefficient):
    graph = correlation_network(["x", "y"], [[1, coefficient], [coefficient, 1]], 1)
    assert graph["edges"][0]["weight"] == 1


@pytest.mark.parametrize("columns,matrix", [([], []), (["only"], [[1]])])
def test_empty_and_single_column_graphs(columns, matrix):
    graph = correlation_network(columns, matrix)
    assert len(graph["nodes"]) == len(columns)
    assert graph["edges"] == []


def test_undefined_correlations_are_skipped_even_at_zero_threshold():
    matrix = [[1, np.nan, -0.7], [np.nan, np.nan, np.nan], [-0.7, np.nan, 1]]
    graph = correlation_network(["a", "constant", "b"], matrix, 0)
    assert len(graph["nodes"]) == 3
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["target"] == "b"
    json.dumps(graph, allow_nan=False)


@pytest.mark.parametrize("threshold", [
    -0.1, 1.1, np.nan, np.inf, -np.inf, "0.5", None, True, 10**100, -(10**100),
])
def test_invalid_threshold_is_rejected(threshold):
    with pytest.raises(ValueError, match="Threshold"):
        correlation_network(COLUMNS, MATRIX, threshold)


@pytest.mark.parametrize("columns,matrix", [
    (["a", "a"], [[1, 0], [0, 1]]),
    (["a", 1], [[1, 0], [0, 1]]),
    (["a", "b"], [[1, 0]]),
    (["a", "b"], [[1], [0, 1]]),
    (["a", "b"], [[1, "bad"], ["bad", 1]]),
    (["a", "b"], [[1, 0.5], [0.6, 1]]),
    (["a", "b"], [[1, np.nan], [0, 1]]),
    (["a", "b"], [[1, np.inf], [np.inf, 1]]),
    (["a", "b"], [[1, 1.01], [1.01, 1]]),
    (["a", "b"], [[1, -1.01], [-1.01, 1]]),
    (["a", "b"], np.array([[1, 0.7 + 0.4j], [0.7 + 0.4j, 1]])),
    ([], [[]]),
])
def test_invalid_matrix_or_names_are_rejected(columns, matrix):
    with pytest.raises(ValueError):
        correlation_network(columns, matrix)


def test_original_and_reduced_metric_outputs_share_node_ids():
    original = pd.DataFrame({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8], "c": [8, 6, 4, 2]})
    reduced = original.copy()
    reduced["c"] = [4, 8, 2, 6]
    columns = [classify_column(original[name], name) for name in original.columns]
    metrics = correlation_metrics(original, reduced, columns, list(original.columns))
    graphs = [correlation_network(metrics["columns"], metrics[key], 0.5)
              for key in ["matrix_original", "matrix_reduced"]]
    assert graphs[0]["nodes"] == graphs[1]["nodes"]
    assert len(graphs[0]["edges"]) == 3
    assert len(graphs[1]["edges"]) == 1
