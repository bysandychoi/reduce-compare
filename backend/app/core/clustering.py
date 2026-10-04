"""군집 기반 대표 추출 (T033 대표 선택, T034 가중치, T036 최소 보장, T037 이상치, T038 평균 행)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import MiniBatchKMeans

from app.core.cluster_report import cluster_representation_report
from app.core.sampling import Reduction, _allocate

MIN_PER_CLUSTER = 30        # 희소 군집 최소 대표 수 (T007 결정)
OUTLIER_RATIO = 0.001       # 군집 중심 거리 상위 0.1%를 이상치로 본다
BASE_CLUSTERS = (5, 50)     # 1단계 군집 수의 하한·상한


def _fit(x: np.ndarray, k: int, seed: int) -> MiniBatchKMeans:
    k = max(1, min(k, len(x)))
    model = MiniBatchKMeans(n_clusters=k, random_state=seed, n_init=3, batch_size=1024)
    model.fit(x)
    return model


def detect_outliers(x: np.ndarray, seed: int = 0, ratio: float = OUTLIER_RATIO) -> np.ndarray:
    """군집 중심에서 먼 상위 ratio 비율을 이상치로 표시한다 (T037)."""
    if len(x) < 10 or ratio <= 0:
        return np.zeros(len(x), dtype=bool)
    k = int(np.clip(round(np.sqrt(len(x)) / 4), *BASE_CLUSTERS))
    model = _fit(x, k, seed)
    dist = np.linalg.norm(x - model.cluster_centers_[model.labels_], axis=1)
    return dist > np.quantile(dist, 1 - ratio)


def _split_cluster(x: np.ndarray, pool: np.ndarray, take: int, seed: int) -> list[np.ndarray]:
    """군집 하나를 take개로 더 쪼개, 대표마다 소속 원본 인덱스를 돌려준다."""
    if take >= len(pool):
        return [np.array([i]) for i in pool]
    model = _fit(x[pool], take, seed)
    return [pool[model.labels_ == c] for c in range(take) if (model.labels_ == c).any()]


def _pick_actual(x: np.ndarray, members: np.ndarray) -> int:
    """소속 행의 평균에 가장 가까운 실제 행을 대표로 고른다."""
    center = x[members].mean(axis=0)
    return int(members[np.argmin(np.linalg.norm(x[members] - center, axis=1))])


def _plan_allocation(sizes: np.ndarray, n: int,
                     min_per_cluster: int) -> tuple[np.ndarray, np.ndarray]:
    """군집 크기에 비례해 대표 수를 나누고, 희소 군집은 최소치를 보장한다 (T036)."""
    alloc = np.minimum(_allocate(np.maximum(sizes, 1), n), sizes.astype(int))
    floor = np.minimum(min_per_cluster, sizes.astype(int))
    return np.maximum(alloc, floor), alloc < floor


def _representation_report(x: np.ndarray, live: np.ndarray, base: MiniBatchKMeans,
                           groups: list[np.ndarray], lifted: np.ndarray,
                           min_per_cluster: int) -> dict:
    mask = np.ones(len(x), dtype=bool)
    mask[live] = False
    labels = np.empty(len(x), dtype=int)
    labels[live] = base.labels_
    if mask.any():
        labels[mask] = base.predict(x[mask])
    sizes = np.bincount(base.labels_, minlength=base.n_clusters)
    targets = {int(c): int(min(min_per_cluster, sizes[c])) for c in np.flatnonzero(lifted)}
    report = cluster_representation_report(labels, groups, mask, targets)
    report["excluded_label_source"] = "nearest_retained_cluster_center"
    report["point_metadata"] = {
        "original_clusters": labels.tolist(),
        "reduced_clusters": [int(labels[group[0]]) for group in groups],
        "original_outliers": mask.tolist(),
        "reduced_outliers": [False] * len(groups),
    }
    return report


def cluster_reduce(x: np.ndarray, n: int, seed: int = 0, virtual: bool = False,
                   min_per_cluster: int = MIN_PER_CLUSTER,
                   drop_outliers: bool = True) -> Reduction:
    """군집 크기에 비례해 대표를 뽑는다 (T033·T034·T036·T038).

    virtual=False면 군집 중심에 가장 가까운 실제 행을, True면 군집 평균을 대표로 쓴다.
    """
    total = len(x)
    if n <= 0:
        raise ValueError("축소 크기는 1 이상이어야 합니다")
    n = min(n, total)
    notes: list[str] = []

    live = np.arange(total)
    if drop_outliers:
        outliers = detect_outliers(x, seed)
        live = np.flatnonzero(~outliers)
        if outliers.any():
            notes.append(f"이상치 {int(outliers.sum()):,}건 제외 (군집 중심 거리 상위 0.1%)")

    k = int(np.clip(round(n / max(min_per_cluster, 1)), *BASE_CLUSTERS))
    base = _fit(x[live], k, seed)
    k = base.n_clusters
    sizes = np.bincount(base.labels_, minlength=k).astype(float)
    alloc, lifted = _plan_allocation(sizes, n, min_per_cluster)
    if lifted.any():
        notes.append(f"희소 군집 {int(lifted.sum())}개에 최소 {min_per_cluster}행 보장")

    groups: list[np.ndarray] = []
    for c in range(k):
        pool = live[base.labels_ == c]
        if len(pool) == 0:
            continue
        groups.extend(_split_cluster(x, pool, int(max(1, min(alloc[c], len(pool)))), seed))

    weights = np.array([len(g) for g in groups], dtype=float)
    indices = np.array([] if virtual else [_pick_actual(x, g) for g in groups], dtype=int)
    return Reduction(indices=indices, weights=weights,
                     method="cluster_mean" if virtual else "cluster_actual",
                     excluded=total - len(live), notes=notes, members=groups,
                     cluster_report=_representation_report(x, live, base, groups,
                                                           lifted, min_per_cluster))


def virtual_rows(df: pd.DataFrame, reduction: Reduction) -> pd.DataFrame:
    """가상 행(군집 평균)을 원본 컬럼 형태로 만든다 (T038).

    수치형은 소속 행의 평균, 그 밖의 컬럼은 최빈값을 쓴다.
    """
    if not reduction.members:
        raise ValueError("소속 행 정보가 없어 가상 행을 만들 수 없습니다")
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    others = [c for c in df.columns if c not in numeric]
    rows = []
    for members in reduction.members:
        block = df.iloc[members]
        row = block[numeric].mean(numeric_only=True).to_dict()
        for c in others:
            mode = block[c].mode()
            row[c] = mode.iloc[0] if len(mode) else None
        rows.append(row)
    return pd.DataFrame(rows, columns=list(df.columns))
