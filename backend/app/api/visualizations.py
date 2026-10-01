"""대용량 투영 결과의 제한된 표본·2D 밀도 API (T065)."""
from __future__ import annotations

from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.results import get_result
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
) -> VisualizationData:
    result = get_result(job_id)
    return build_visualization(_group(result, group), mode, max_points, bins, seed)
