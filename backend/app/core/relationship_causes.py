"""Evidence-backed relationship-change candidates, not causal proofs (T141)."""

from __future__ import annotations

from numbers import Integral, Real

import numpy as np

from app.core.relationships import classify_relationships, rank_correlation_pairs


def _number(value: object, name: str, upper: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite nonnegative number")
    try:
        value = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a finite nonnegative number") from error
    if (value < 0
            or (upper is not None and value > upper) or not np.isfinite(value)):
        raise ValueError(f"{name} must be a finite nonnegative number")
    return float(value)


def _cluster_reduction(report: dict) -> bool:
    if not isinstance(report, dict) or not isinstance(report.get("clusters"), list):
        raise ValueError("A cluster representation report is required")
    keys = ["original_count", "representative_count", "excluded_count"]
    rows = report["clusters"]
    for record in [report, *rows]:
        for key in keys + ([] if record is report else ["covered_count"]):
            value = record.get(key) if isinstance(record, dict) else None
            if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
                raise ValueError("Cluster report counts must be nonnegative integers")
        if record["excluded_count"] > record["original_count"]:
            raise ValueError("Excluded counts exceed original counts")
    if any(sum(row[key] for row in rows) != report[key] for key in keys):
        raise ValueError("Cluster report totals do not match cluster rows")
    if any(not row["representative_count"] <= row["covered_count"]
           <= row["original_count"] - row["excluded_count"] for row in rows):
        raise ValueError("Cluster coverage counts are inconsistent")
    return sum(row["covered_count"] for row in rows) > report["representative_count"]


def _evidence_inputs(metrics: dict, after_exclusion: dict | None,
                     dispersion_ratios: dict | None) -> tuple[dict, dict]:
    known = {tuple(sorted((p["column_a"], p["column_b"])))
             for p in rank_correlation_pairs(metrics)["pairs"]}
    clean = {}
    if after_exclusion is not None:
        ranks = rank_correlation_pairs(after_exclusion)
        if (ranks["method"] != metrics["method"]
                or set(after_exclusion["columns"]) != set(metrics["columns"])):
            raise ValueError("Post-exclusion method and columns must match")
        clean = {tuple(sorted((p["column_a"], p["column_b"]))): p["original_r"]
                 for p in ranks["pairs"]}
        expected = {tuple(sorted((p["column_a"], p["column_b"]))): p["reduced_r"]
                    for p in rank_correlation_pairs(metrics)["pairs"]}
        if any(p["reduced_r"] != expected[tuple(sorted((p["column_a"], p["column_b"])))]
               for p in ranks["pairs"]):
            raise ValueError("Post-exclusion comparison must use the same reduced matrix")
    dispersion = {}
    if dispersion_ratios is not None:
        if not isinstance(dispersion_ratios, dict):
            raise ValueError("Dispersion ratios must be a pair-keyed dictionary")
        for key, value in dispersion_ratios.items():
            if not isinstance(key, tuple) or len(key) != 2 or any(
                    not isinstance(name, str) for name in key):
                raise ValueError("Dispersion keys must be column-name pairs")
            pair = tuple(sorted(key))
            if pair not in known or pair in dispersion:
                raise ValueError("Unknown or duplicate dispersion pair")
            dispersion[pair] = _number(value, "Dispersion ratio")
    return clean, dispersion


def _explain_pair(pair: dict, threshold: float, tolerance: float, band: float,
                  clean: dict, dispersion: dict, clustered: bool) -> dict:
    a, b = pair["original_r"], pair["reduced_r"]
    key = tuple(sorted((pair["column_a"], pair["column_b"])))
    sources = [name for name in ("original", "reduced") if pair[f"{name}_undefined"]]
    if key in clean and clean[key] is None:
        sources.append("after_exclusion")
    if pair["undefined"]:
        return {**pair, "status": "undefined", "result": "undefined", "undefined": True,
                "undefined_sources": sources,
                "after_exclusion_undefined": "after_exclusion" in sources,
                "causes": [], "evidence": []}
    gap = abs(b) - abs(a)
    result = pair["status"]
    if result == "maintained" and abs(gap) > tolerance + 1e-12:
        result = "strengthened" if gap > 0 else "weakened"
    evidence = []
    if (pair["status"] in ("lost", "new") and abs(b - a) <= 2 * band + 1e-12
            and max(abs(abs(a) - threshold), abs(abs(b) - threshold)) <= band + 1e-12):
        evidence.append({"cause": "threshold_boundary", "kind": "rule",
                         "original_distance": abs(abs(a) - threshold),
                         "reduced_distance": abs(abs(b) - threshold)})
    if (key in clean and clean[key] is not None and abs(clean[key] - a) > tolerance + 1e-12
            and abs(b - clean[key]) + 1e-12 < abs(b - a)):
        evidence.append({"cause": "outlier_exclusion", "kind": "measured_comparison",
                         "after_exclusion_r": clean[key],
                         "exclusion_difference": round(clean[key] - a, 8),
                         "remaining_difference": round(b - clean[key], 8)})
    if (clustered and gap > tolerance + 1e-12 and not pair["sign_changed"]
            and key in dispersion and dispersion[key] < 1):
        evidence.append({"cause": "cluster_representation", "kind": "inference",
                         "within_cluster_dispersion_ratio": dispersion[key]})
    causes = [item["cause"] for item in evidence]
    if not causes:
        causes = ["no_material_change" if abs(b - a) <= tolerance + 1e-12 else "unresolved"]
    return {**pair, "result": result, "causes": causes, "evidence": evidence,
            "undefined_sources": sources,
            "after_exclusion_undefined": "after_exclusion" in sources}


def explain_relationship_changes(metrics: dict, cluster_report: dict, threshold: float = 0.5,
                                 after_exclusion: dict | None = None,
                                 dispersion_ratios: dict | None = None,
                                 change_tolerance: float = 0.01,
                                 boundary_band: float = 0.05) -> dict:
    """Explain T132 results with configurable heuristics and supplied evidence.

    after_exclusion is a same-method correlation_metrics result whose original
    matrix describes the retained data. Dispersion ratios are reduced/original
    within-cluster dispersion for each column pair, supplied by the caller.
    Missing evidence yields unresolved, never an invented causal explanation.
    """
    tolerance = _number(change_tolerance, "Change tolerance", 1)
    band = _number(boundary_band, "Boundary band", 1)
    classified = classify_relationships(metrics, threshold)
    clustered = _cluster_reduction(cluster_report)
    evidence_metrics = after_exclusion if cluster_report["excluded_count"] else None
    clean, dispersion = _evidence_inputs(metrics, evidence_metrics, dispersion_ratios)
    pairs = [_explain_pair(p, classified["threshold"], tolerance, band,
                          clean, dispersion, clustered) for p in classified["pairs"]]
    counts = dict.fromkeys(classified["counts"], 0)
    for pair in pairs:
        counts[pair["status"]] += 1
    return {**classified, "pairs": pairs, "counts": counts, "change_tolerance": tolerance,
            "boundary_band": band, "causal_proof": False}
