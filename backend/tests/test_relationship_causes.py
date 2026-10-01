"""Relationship outcomes and evidence-backed cause rules."""

import copy
import json

import numpy as np
import pytest

from app.core.cluster_report import cluster_representation_report
from app.core.relationship_causes import explain_relationship_changes


def metrics(a, b, method="pearson"):
    return {"method": method, "columns": ["x", "y"],
            "matrix_original": [[1, a], [a, 1]], "matrix_reduced": [[1, b], [b, 1]]}


def report():
    return cluster_representation_report([0, 0, 0, 0, 0], [[0, 1], [2, 3]],
                                         np.array([False, False, False, False, True]))


def explain(a, b, **options):
    return explain_relationship_changes(metrics(a, b), report(), **options)["pairs"][0]


@pytest.mark.parametrize("a,b,outcome", [
    (.7, .7, "maintained"), (.7, .8, "strengthened"), (-.8, -.7, "weakened"),
    (.8, .2, "lost"), (.2, -.8, "new"), (.1, .2, "absent"),
])
def test_outcomes(a, b, outcome):
    assert explain(a, b)["result"] == outcome


def test_signed_reversal_is_not_attributed_to_dispersion():
    pair = explain(.7, -.8, dispersion_ratios={("x", "y"): 0.2})
    assert pair["sign_changed"] is True
    assert "cluster_representation" not in pair["causes"]


def test_boundary_rule_and_exact_band_and_tolerance():
    assert explain(.55, .45)["causes"] == ["threshold_boundary"]
    assert explain(-.49, -.51)["causes"] == ["threshold_boundary"]
    assert explain(.55, -.45)["causes"] == ["unresolved"]
    assert explain(.6, .61)["result"] == "maintained"
    assert explain(.6, .61)["causes"] == ["no_material_change"]
    assert explain(.9, .3)["causes"] == ["unresolved"]


def test_outlier_effect_requires_observed_movement_toward_reduced():
    pair = explain(.9, .5, after_exclusion=metrics(.55, .5))
    assert pair["causes"] == ["outlier_exclusion"]
    assert pair["evidence"][0]["after_exclusion_r"] == .55
    assert explain(.9, .5, after_exclusion=metrics(.95, .5))["causes"] == ["unresolved"]
    assert explain(.9, .5)["causes"] == ["unresolved"]


def test_representation_effect_requires_dispersion_evidence():
    pair = explain(.6, .8, dispersion_ratios={("y", "x"): .3})
    assert pair["causes"] == ["cluster_representation"]
    assert pair["evidence"][0]["kind"] == "inference"
    assert explain(.6, .8)["causes"] == ["unresolved"]
    assert explain(.6, .8, dispersion_ratios={("x", "y"): 1.2})["causes"] == ["unresolved"]


def test_multiple_candidates_preserve_inputs_and_json():
    source = metrics(.49, .52, "spearman")
    snapshot = copy.deepcopy(source)
    result = explain_relationship_changes(source, report(), after_exclusion=metrics(.51, .52,
                                         "spearman"), dispersion_ratios={("x", "y"): .2})
    assert result["pairs"][0]["causes"] == [
        "threshold_boundary", "outlier_exclusion", "cluster_representation"]
    assert result["causal_proof"] is False
    assert source == snapshot
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("options", [
    {"change_tolerance": True}, {"change_tolerance": np.nan}, {"boundary_band": -1},
    {"boundary_band": np.inf}, {"boundary_band": 10**100},
    {"after_exclusion": metrics(.5, .8, "spearman")},
    {"after_exclusion": metrics(.6, .9)},
    {"dispersion_ratios": {("x", "z"): .1}},
    {"dispersion_ratios": {("x", "y"): np.nan}},
    {"dispersion_ratios": {("x", "y"): 10**1000}},
    {"dispersion_ratios": {("x", "y"): .1, ("y", "x"): .2}},
    {"dispersion_ratios": {"xy": .1}},
])
def test_invalid_options_are_rejected(options):
    with pytest.raises(ValueError):
        explain(.5, .8, **options)


def test_invalid_cluster_counts_and_column_mismatch():
    broken = report()
    broken["original_count"] += 1
    with pytest.raises(ValueError):
        explain_relationship_changes(metrics(.5, .8), broken)
    clean = metrics(.6, .8)
    clean["columns"] = ["x", "z"]
    with pytest.raises(ValueError, match="columns"):
        explain(.5, .8, after_exclusion=clean)


def test_empty_results_and_absence_of_reduction_evidence():
    empty = {"method": "pearson", "columns": [], "matrix_original": [], "matrix_reduced": []}
    result = explain_relationship_changes(empty, cluster_representation_report([], []))
    assert result["pairs"] == []
    uncompressed = cluster_representation_report([0, 0], [[0], [1]])
    result = explain_relationship_changes(metrics(.6, .8), uncompressed,
                                          dispersion_ratios={("x", "y"): .2})
    assert result["pairs"][0]["causes"] == ["unresolved"]
    result = explain_relationship_changes(metrics(.9, .5), uncompressed,
                                          after_exclusion=metrics(.55, .5))
    assert result["pairs"][0]["causes"] == ["unresolved"]
