"""축소 크기 자동 결정과 방식 선택 (T050 후보, T051 최소 크기 탐색, T052 방식 추천)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.clustering import cluster_reduce, virtual_rows
from app.core.ingest import collect_csv_files
from app.core.metrics import correlation_metrics, distribution_metrics
from app.core.prepare import PrepareResult, merge_group, prepare_group
from app.core.projection import ProjectionResult, project_comparison
from app.core.sampling import Reduction, choose_stratify_column, random_sample, stratified_sample
from app.core.schema import ColumnInfo, SchemaGroup, extract_schema, group_by_schema
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


@dataclass
class GroupPipelineResult:
    """한 스키마 그룹의 준비·축소·평가·투영 결과."""

    name: str
    files: list[str]
    original_rows: int
    prepared: PrepareResult
    chosen: Attempt
    size_curve: list[dict]
    method_scores: list[dict]
    projection: ProjectionResult


@dataclass
class PipelineResult:
    """폴더 전체 실행 결과와 건너뛴 그룹 사유."""

    folder: str
    groups: list[GroupPipelineResult] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)


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


def run_group_pipeline(group: SchemaGroup, name: str, target: float = DEFAULT_TARGET,
                       seed: int = 0, projection_method: str = "pca",
                       projection_dimensions: int = 2) -> GroupPipelineResult:
    """한 스키마 그룹을 병합부터 투영까지 실행한다."""
    frame = merge_group(group.files)
    prepared = prepare_group(frame, group.columns)
    sized, curve = search_size(
        prepared.frame, prepared.features, group.columns, prepared.used_columns,
        target=target, seed=seed,
    )
    chosen, methods = choose_method(
        prepared.frame, prepared.features, group.columns, prepared.used_columns,
        sized.size, seed=seed,
    )
    reduced_features = (
        prepared.features[chosen.reduction.indices]
        if len(chosen.reduction.indices)
        else _virtual_features(prepared.features, chosen.reduction)
    )
    projection = project_comparison(
        prepared.features, reduced_features, method=projection_method,
        dimensions=projection_dimensions, seed=seed,
    )
    return GroupPipelineResult(
        name=name, files=[item.name for item in group.files], original_rows=len(frame),
        prepared=prepared, chosen=chosen, size_curve=curve, method_scores=methods,
        projection=projection,
    )


def run_folder_pipeline(folder: str, target: float = DEFAULT_TARGET, seed: int = 0,
                        projection_method: str = "pca",
                        projection_dimensions: int = 2) -> PipelineResult:
    """폴더의 표 파일을 스키마별로 묶어 전체 축소 파이프라인을 실행한다."""
    files = collect_csv_files(folder)
    if not files:
        raise ValueError(f"읽을 수 있는 표 파일을 찾지 못했습니다: {folder}")
    groups = group_by_schema([extract_schema(item) for item in files])
    result = PipelineResult(folder=folder)
    for index, group in enumerate(groups):
        name = chr(ord("A") + index) if index < 26 else f"G{index + 1}"
        try:
            completed = run_group_pipeline(
                group, name, target, seed, projection_method, projection_dimensions,
            )
            result.groups.append(completed)
        except ValueError as exc:
            result.skipped.append({"name": name, "files": [f.name for f in group.files],
                                   "reason": str(exc)})
    return result
