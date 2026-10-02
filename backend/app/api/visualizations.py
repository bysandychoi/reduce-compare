"""대용량 투영 결과의 제한된 표본·2D 밀도 API (T065)."""
from __future__ import annotations

from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.groups import job_directory
from app.api.results import get_result
from app.core.projection import ProjectionResult, project_comparison
from app.models.results import GroupResult

router = APIRouter(tags=["jobs"])


class DensityGrid(BaseModel):
    x_edges: list[float]
    y_edges: list[float]
    counts: list[list[int]]


class VisualizationData(BaseModel):
    group: str
    mode: Literal["sample", "density"]
    dimensions: int
    original_rows: int
    original_projected: int
    reduced_rows: int
    original_points: list[list[float]] = Field(default_factory=list)
    original_indices: list[int] = Field(default_factory=list)
    original_density: DensityGrid | None = None
    reduced_points: list[list[float]]
    projection_method: Literal["pca", "umap"]


def _group(result, name: str) -> GroupResult:
    for group in result.groups:
        if group.name == name:
            return group
    raise HTTPException(status.HTTP_404_NOT_FOUND, "결과 그룹을 찾을 수 없습니다")


def _sample(points: list[list[float]], indices: list[int] | None,
            limit: int, seed: int) -> tuple[list[list[float]], list[int]]:
    if len(points) <= limit:
        chosen = np.arange(len(points))
    else:
        chosen = np.sort(np.random.default_rng(seed).choice(len(points), limit, replace=False))
    sampled = [points[int(index)] for index in chosen]
    source = indices if indices is not None else list(range(len(points)))
    return sampled, [source[int(index)] for index in chosen]


def _density(points: list[list[float]], bins: int) -> DensityGrid:
    matrix = np.asarray(points, dtype=float)
    if matrix.ndim != 2 or len(matrix) == 0 or matrix.shape[1] < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "2D 밀도 좌표가 없습니다")
    counts, x_edges, y_edges = np.histogram2d(matrix[:, 0], matrix[:, 1], bins=bins)
    return DensityGrid(
        x_edges=x_edges.tolist(), y_edges=y_edges.tolist(), counts=counts.astype(int).tolist(),
    )


def build_visualization(group: GroupResult, mode: Literal["sample", "density"],
                        max_points: int, bins: int, seed: int) -> VisualizationData:
    """검증된 그룹 결과를 크기 제한이 있는 그래프 자료로 변환한다."""
    projection = group.projection
    reduced, _ = _sample(projection.reduced, None, max_points, seed + 1)
    common = {
        "group": group.name,
        "mode": mode,
        "dimensions": 2 if mode == "density" else projection.dimensions,
        "original_rows": group.original_rows,
        "original_projected": len(projection.original),
        "reduced_rows": group.reduced_rows,
        "reduced_points": reduced,
        "projection_method": projection.method,
    }
    if mode == "density":
        return VisualizationData(**common, original_density=_density(projection.original, bins))
    original, indices = _sample(
        projection.original, projection.original_indices, max_points, seed,
    )
    return VisualizationData(**common, original_points=original, original_indices=indices)


@router.get("/jobs/{job_id}/visualization", response_model=VisualizationData)
def get_visualization(
    job_id: str,
    group: str,
    mode: Literal["sample", "density"] = "sample",
    max_points: int = Query(default=5000, ge=1, le=10000),
    bins: int = Query(default=50, ge=5, le=100),
    seed: int = 0,
    projection_method: Literal["pca", "umap"] | None = None,
) -> VisualizationData:
    result = get_result(job_id)
    selected = _group(result, group)
    if projection_method is not None and projection_method != selected.projection.method:
        index = next(i for i, item in enumerate(result.groups) if item.name == group)
        path = job_directory(job_id) / "projection-source" / f"group-{index + 1}.npz"
        if not path.is_file():
            raise HTTPException(status.HTTP_409_CONFLICT, "투영 방식 전환 자료가 없습니다")
        with np.load(path) as source:
            projected = project_comparison(
                source["original"], source["reduced"], projection_method, 2, seed,
            )
        selected = selected.model_copy(update={"projection": _projection_model(projected)})
    return build_visualization(selected, mode, max_points, bins, seed)


def _projection_model(projected: ProjectionResult):
    """코어 투영을 기존 결과 모델과 같은 값 객체로 변환한다."""
    from app.models.results import ProjectionData

    return ProjectionData(
        method=projected.method, dimensions=projected.dimensions,
        original=projected.original.tolist(), reduced=projected.reduced.tolist(),
        original_indices=projected.original_indices.tolist(),
    )
