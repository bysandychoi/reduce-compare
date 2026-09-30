"""샘플링 축소기 (T029 층화 기준 선택, T030 공통 인터페이스, T031 랜덤, T032 층화)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.schema import CATEGORICAL, ColumnInfo

# 층화 기준으로 쓸 수 있는 범주 수의 범위
STRATIFY_MIN_LEVELS = 2
STRATIFY_MAX_LEVELS = 50


@dataclass
class Reduction:
    """축소 결과. 모든 축소기가 이 형태로 돌려준다 (T030).

    indices: 대표로 뽑힌 원본 행 위치 (가상 행이면 비어 있다)
    weights: 각 대표가 대표하는 원본 행 수 (합 = 원본 행 수 - 제외 건수)
    frame:   가상 행을 쓸 때만 채워지는 대표 데이터
    """

    indices: np.ndarray
    weights: np.ndarray
    method: str
    frame: pd.DataFrame | None = None
    excluded: int = 0
    notes: list[str] = field(default_factory=list)
    members: list[np.ndarray] | None = None   # 대표별 소속 원본 행 (군집 축소기에서 채움)

    @property
    def size(self) -> int:
        return len(self.weights)

    def rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """원본에서 대표 행을 꺼낸다 (가상 행이면 만들어 둔 frame)."""
        if self.frame is not None:
            return self.frame
        return df.iloc[self.indices].reset_index(drop=True)


def _check_size(n: int, total: int) -> int:
    if n <= 0:
        raise ValueError("축소 크기는 1 이상이어야 합니다")
    return min(n, total)


def random_sample(total: int, n: int, seed: int = 0) -> Reduction:
    """단순 랜덤 샘플링 (T031). 비교 기준선으로 쓴다."""
    n = _check_size(n, total)
    rng = np.random.default_rng(seed)
    idx = np.sort(rng.choice(total, n, replace=False))
    weights = np.full(n, total / n, dtype=float)
    return Reduction(indices=idx, weights=weights, method="random")


def choose_stratify_column(df: pd.DataFrame, columns: list[ColumnInfo],
                           selected: list[str]) -> str | None:
    """층화 기준 컬럼을 자동으로 고른다 (T029).

    선택된 범주형 중 범주 수가 2~50인 컬럼 가운데, 가장 고르게 퍼진 것을 쓴다.
    쓸 만한 컬럼이 없으면 None (층화 샘플링은 건너뛴다).
    """
    kinds = {c.name: c.kind for c in columns}
    best, best_entropy = None, -1.0
    for name in selected:
        if kinds.get(name) != CATEGORICAL or name not in df.columns:
            continue
        counts = df[name].astype(str).value_counts(normalize=True)
        if not (STRATIFY_MIN_LEVELS <= len(counts) <= STRATIFY_MAX_LEVELS):
            continue
        entropy = float(-(counts * np.log(counts)).sum())
        if entropy > best_entropy:
            best, best_entropy = name, entropy
    return best


def _allocate(counts: np.ndarray, n: int) -> np.ndarray:
    """비율대로 나누되 각 그룹에 최소 1개를 주고 합이 정확히 n이 되게 맞춘다."""
    raw = counts / counts.sum() * n
    alloc = np.maximum(1, np.floor(raw)).astype(int)
    alloc = np.minimum(alloc, counts)
    while alloc.sum() != n:
        if alloc.sum() < n:
            room = counts - alloc
            if not room.any():
                break
            alloc[np.argmax(np.where(room > 0, raw - alloc, -np.inf))] += 1
        else:
            shrinkable = np.where(alloc > 1, alloc - raw, -np.inf)
            if not np.isfinite(shrinkable).any():
                break
            alloc[np.argmax(shrinkable)] -= 1
    return alloc


def stratified_sample(df: pd.DataFrame, n: int, key: str, seed: int = 0) -> Reduction:
    """층화 샘플링 (T032). key 컬럼의 범주 비율을 유지한다."""
    total = len(df)
    n = _check_size(n, total)
    rng = np.random.default_rng(seed)
    labels = df[key].astype(str).to_numpy()
    levels, counts = np.unique(labels, return_counts=True)
    alloc = _allocate(counts, n)

    picked: list[np.ndarray] = []
    weights: list[np.ndarray] = []
    for level, take, size in zip(levels, alloc, counts):   # 길이는 np.unique가 보장
        pool = np.flatnonzero(labels == level)
        chosen = rng.choice(pool, take, replace=False)
        picked.append(chosen)
        weights.append(np.full(take, size / take, dtype=float))
    order = np.argsort(np.concatenate(picked))
    idx = np.concatenate(picked)[order]
    w = np.concatenate(weights)[order]
    return Reduction(indices=idx, weights=w, method="stratified",
                     notes=[f"층화 기준 컬럼: {key} ({len(levels)}개 범주)"])
