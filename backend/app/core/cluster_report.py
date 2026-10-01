"""Observed cluster representation counts and allocation provenance (T140)."""

from __future__ import annotations

import numpy as np


def _integer_vector(values: object, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1 or (array.size and not np.issubdtype(array.dtype, np.integer)):
        raise ValueError(f"{name} must be a one-dimensional integer array")
    return array.astype(np.int64)


def _representations(labels: np.ndarray, members: list, excluded: np.ndarray) -> dict:
    seen = np.zeros(len(labels), dtype=bool)
    counts: dict[int, int] = {}
    covered: dict[int, int] = {}
    for member in members:
        indices = _integer_vector(member, "Members")
        if not len(indices) or np.any(indices < 0) or np.any(indices >= len(labels)):
            raise ValueError("Members must contain valid nonempty row indices")
        if len(np.unique(indices)) != len(indices) or seen[indices].any():
            raise ValueError("Representative groups must not overlap")
        if excluded[indices].any() or len(np.unique(labels[indices])) != 1:
            raise ValueError("Members must belong to one retained cluster")
        seen[indices] = True
        cluster = int(labels[indices[0]])
        counts[cluster] = counts.get(cluster, 0) + 1
        covered[cluster] = covered.get(cluster, 0) + len(indices)
    return {"representatives": counts, "covered": covered}


def _row(cluster: int, size: int, excluded: int, count: int, covered: int,
         target: int, total: int, representatives: int) -> dict:
    guaranteed = target > 0 and count >= target
    status = "미반영" if not count else "최소 보장" if guaranteed else "반영"
    reason = ("이상치 제외로 남은 행 없음" if size == excluded else "대표가 선택되지 않음")
    if count:
        reason = "최소 대표 수 보장 적용" if guaranteed else "군집 대표 선택"
        if target and count < target:
            reason = "최소 보장 목표 미달"
    return {"cluster_id": cluster, "original_count": size,
            "original_ratio": size / total, "representative_count": count,
            "representative_ratio": count / representatives if representatives else 0.0,
            "excluded_count": excluded, "covered_count": covered,
            "minimum_target": target, "status": status, "reason": reason}


def cluster_representation_report(labels: object, members: list,
                                  excluded_mask: object = None,
                                  minimum_targets: dict[int, int] | None = None) -> dict:
    """Use full original labels and disjoint representative membership groups.

    Ratios use all original rows and all representative rows respectively.
    minimum_targets contains only clusters actually lifted by allocation floors.
    """
    labels = _integer_vector(labels, "Labels")
    mask = np.zeros(len(labels), dtype=bool) if excluded_mask is None else np.asarray(excluded_mask)
    if mask.shape != labels.shape or mask.dtype != np.dtype(bool):
        raise ValueError("Excluded mask must be a matching boolean array")
    targets = minimum_targets or {}
    if any(isinstance(v, bool) or not isinstance(v, (int, np.integer)) or v <= 0
           for v in targets.values()) or any(k not in labels for k in targets):
        raise ValueError("Minimum targets must be positive integers for known clusters")
    groups = _representations(labels, members, mask)
    levels, inverse, sizes = np.unique(labels, return_inverse=True, return_counts=True)
    exclusions = np.bincount(inverse[mask], minlength=len(levels))
    rows = [_row(int(c), int(sizes[i]), int(exclusions[i]),
                 groups["representatives"].get(int(c), 0), groups["covered"].get(int(c), 0),
                 int(targets.get(int(c), 0)), len(labels), len(members))
            for i, c in enumerate(levels)]
    return {"original_count": len(labels), "representative_count": len(members),
            "excluded_count": int(mask.sum()), "clusters": rows}
