"""Report conservation, allocation provenance, and clustering integration."""

import json

import numpy as np
import pytest

from app.core.cluster_report import cluster_representation_report
from app.core.clustering import cluster_reduce
from app.core.sampling import random_sample


def test_counts_ratios_status_and_outliers():
    report = cluster_representation_report(
        [0, 0, 0, 1, 1, 2, 3], [[0, 1], [2], [3]],
        np.array([False, False, False, False, True, False, True]), {0: 2})
    rows = report["clusters"]
    assert sum(r["original_count"] for r in rows) == 7
    assert sum(r["representative_count"] for r in rows) == 3
    assert sum(r["excluded_count"] for r in rows) == 2
    assert sum(r["original_ratio"] for r in rows) == pytest.approx(1)
    assert sum(r["representative_ratio"] for r in rows) == pytest.approx(1)
    assert [r["status"] for r in rows] == ["최소 보장", "반영", "미반영", "미반영"]
    assert rows[3]["reason"] == "이상치 제외로 남은 행 없음"
    json.dumps(report, allow_nan=False)


def test_minimum_target_must_actually_be_met():
    row = cluster_representation_report([9, 9], [[0, 1]], minimum_targets={9: 2})["clusters"][0]
    assert row["status"] == "반영" and row["reason"] == "최소 보장 목표 미달"


def test_empty_and_unrepresented_clusters():
    assert cluster_representation_report([], [])["clusters"] == []
    rows = cluster_representation_report([1, 3], [])["clusters"]
    assert all(r["representative_ratio"] == 0 and r["status"] == "미반영" for r in rows)


@pytest.mark.parametrize("members", [[[0, 0]], [[0], [0]], [[-1]], [[3]], [[]],
                                     [[0, 2]], [[0.5]], [[True]]])
def test_invalid_membership_is_rejected(members):
    with pytest.raises(ValueError):
        cluster_representation_report([0, 0, 1], members)


def test_excluded_members_and_invalid_labels_masks_targets():
    with pytest.raises(ValueError):
        cluster_representation_report([0], [[0]], np.array([True]))
    for labels, mask, targets in [([0.1], None, None), ([[0]], None, None),
                                 ([0], [0], None), ([0], [False, False], None),
                                 ([0], None, {1: 1}), ([0], None, {0: 0})]:
        with pytest.raises(ValueError):
            cluster_representation_report(labels, [], mask, targets)


@pytest.mark.parametrize("virtual", [False, True])
@pytest.mark.parametrize("drop_outliers", [False, True])
def test_actual_and_virtual_reports_conserve_observed_counts(virtual, drop_outliers):
    rng = np.random.default_rng(10)
    x = np.vstack([rng.normal(size=(180, 2)), [[60, 60]]])
    reduction = cluster_reduce(x, 20, seed=2, virtual=virtual,
                               min_per_cluster=8, drop_outliers=drop_outliers)
    report = reduction.cluster_report
    assert report["original_count"] == len(x)
    assert report["representative_count"] == reduction.size
    assert report["excluded_count"] == reduction.excluded
    assert sum(r["original_count"] for r in report["clusters"]) == len(x)
    assert sum(r["covered_count"] for r in report["clusters"]) == reduction.weights.sum()
    assert sum(r["representative_count"] for r in report["clusters"]) == reduction.size
    json.dumps(report, allow_nan=False)


def test_noncluster_reductions_remain_compatible():
    assert random_sample(10, 2).cluster_report is None
