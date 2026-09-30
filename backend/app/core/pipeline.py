"""축소 크기 자동 결정과 방식 선택 (T050 후보, T051 최소 크기 탐색, T052 방식 추천)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.clustering import cluster_reduce, virtual_rows
from app.core.metrics import correlation_metrics, distribution_metrics
from app.core.sampling import Reduction, choose_stratify_column, random_sample, stratified_sample
from app.core.schema import ColumnInfo
from app.core.structure import overall_score, structure_metrics

DEFAULT_TARGET = 85.0       # 유사도 기준치 기본값 (T003 결정)
MIN_SIZE, MAX_SIZE = 100, 50000


@dataclass
class Attempt:
    """축소 한 번의 결과."""

    method: str
    size: int
    score: float
    distribution: float
    correlation: float
    structure: float
    reduction: Reduction
    frame: pd.DataFrame
    detail: dict = field(default_factory=dict)


def size_candidates(total: int, steps: int = 7) -> list[int]:
    """원본 크기에 맞춰 로그 간격으로 후보 크기를 만든다 (T050)."""
    upper = int(min(MAX_SIZE, max(MIN_SIZE * 2, total * 0.2)))
    lower = int(min(MIN_SIZE, max(10, total // 20)))
    if upper <= lower:
        return [max(1, min(total, upper))]
    raw = np.unique(np.round(np.geomspace(lower, upper, steps)).astype(int))
    return [int(v) for v in raw if v < total]


def run_once(df: pd.DataFrame, x: np.ndarray, columns: list[ColumnInfo], selected: list[str],
             method: str, n: int, seed: int = 0) -> Attempt:
    """한 가지 방식·크기로 축소하고 점수를 매긴다."""
    if method == "random":
        red = random_sample(len(x), n, seed)
    elif method == "stratified":
        key = choose_stratify_column(df, columns, selected)
        if key is None:
            raise ValueError("층화에 쓸 범주형 컬럼이 없습니다")
        red = stratified_sample(df, n, key, seed)
    elif method in ("cluster_actual", "cluster_mean"):
        red = cluster_reduce(x, n, seed, virtual=(method == "cluster_mean"))
    else:
        raise ValueError(f"모르는 축소 방식입니다: {method}")

    frame = (virtual_rows(df, red) if method == "cluster_mean"
             else df.iloc[red.indices].reset_index(drop=True))
    dist, per_col = distribution_metrics(df, frame, columns, selected, red.weights)
    corr = correlation_metrics(df, frame, columns, selected)
    x_red = x[red.indices] if len(red.indices) else _virtual_features(x, red)
    struct = structure_metrics(x, x_red, seed)
    total = overall_score(dist, corr["score"], struct["score"])
    return Attempt(method=method, size=red.size, score=total.total, distribution=dist,
                   correlation=corr["score"], structure=struct["score"], reduction=red, frame=frame,
                   detail={"columns": [c.__dict__ for c in per_col], "correlation": corr,
                           "structure": struct, "notes": red.notes, "excluded": red.excluded})


def _virtual_features(x: np.ndarray, red: Reduction) -> np.ndarray:
    """가상 행의 특징 벡터는 소속 행의 평균으로 만든다."""
    return np.vstack([x[m].mean(axis=0) for m in (red.members or [])])


def search_size(df: pd.DataFrame, x: np.ndarray, columns: list[ColumnInfo], selected: list[str],
                target: float = DEFAULT_TARGET, method: str = "cluster_actual",
                seed: int = 0) -> tuple[Attempt, list[dict]]:
    """기준치를 넘는 가장 작은 크기를 찾는다 (T051). (선택된 결과, 크기별 점수 곡선)."""
    curve: list[dict] = []
    best: Attempt | None = None
    for n in size_candidates(len(x)):
        attempt = run_once(df, x, columns, selected, method, n, seed)
        curve.append({"size": attempt.size, "score": attempt.score,
                      "distribution": attempt.distribution, "correlation": attempt.correlation,
                      "structure": attempt.structure})
        if best is None or attempt.score > best.score:
            best = attempt
        if attempt.score >= target:
            return attempt, curve          # 기준치를 넘는 가장 작은 크기에서 멈춘다
    return best, curve                     # 끝까지 못 넘으면 가장 높은 점수를 쓴다


def choose_method(df: pd.DataFrame, x: np.ndarray, columns: list[ColumnInfo], selected: list[str],
                  size: int, seed: int = 0) -> tuple[Attempt, list[dict]]:
    """같은 크기에서 방식별 점수를 비교해 가장 높은 것을 고른다 (T052)."""
    results: list[Attempt] = []
    for method in ("cluster_actual", "cluster_mean", "stratified", "random"):
        try:
            results.append(run_once(df, x, columns, selected, method, size, seed))
        except ValueError:
            continue                        # 쓸 수 없는 방식은 건너뛴다
    best = max(results, key=lambda a: a.score)
    table = [{"method": a.method, "size": a.size, "score": a.score,
              "distribution": a.distribution, "correlation": a.correlation,
              "structure": a.structure} for a in results]
    return best, table
