"""대용량 투영 결과의 제한된 표본·2D 밀도 API (T065)."""
from __future__ import annotations

from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.visualization_axes import visualization_response
from app.core.projection import ProjectionResult
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
    reduced_weights: list[float] = Field(default_factory=list)
    reduced_indices: list[int] = Field(default_factory=list)
    axis_labels: list[str] = Field(default_factory=list)
    axis_columns: list[str] = Field(default_factory=list)
    projection_method: Literal["pca", "umap"]


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


def _aligned_weights(weights: np.ndarray | None, indices: list[int], total: int) -> list[float]:
    if weights is None:
        return []
    values = np.asarray(weights, dtype=float)
    if (values.ndim != 1 or len(values) != total or not np.isfinite(values).all()
            or (values <= 0).any()):
        return []
    return values[np.asarray(indices, dtype=int)].tolist()


def build_visualization(group: GroupResult, mode: Literal["sample", "density"],
                        max_points: int, bins: int, seed: int,
                        reduced_weights: np.ndarray | None = None,
                        axis_columns: list[str] | None = None) -> VisualizationData:
    """검증된 그룹 결과를 크기 제한이 있는 그래프 자료로 변환한다."""
    projection = group.projection
    reduced, reduced_indices = _sample(projection.reduced, None, max_points, seed + 1)
    aligned_weights = _aligned_weights(reduced_weights, reduced_indices, len(projection.reduced))
    common = {
        "group": group.name,
        "mode": mode,
        "dimensions": 2 if mode == "density" else projection.dimensions,
        "original_rows": group.original_rows,
        "original_projected": len(projection.original),
        "reduced_rows": group.reduced_rows,
        "reduced_points": reduced,
        "reduced_weights": aligned_weights,
        "reduced_indices": reduced_indices,
        "axis_labels": [
            f"{projection.method.upper()} {index + 1}"
            for index in range(projection.dimensions)
        ],
        "axis_columns": axis_columns or [],
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
    projection_dimensions: int | None = Query(default=None, ge=2, le=3),
    x_axis: str | None = Query(default=None, max_length=256),
    y_axis: str | None = Query(default=None, max_length=256),
    z_axis: str | None = Query(default=None, max_length=256),
) -> VisualizationData:
    return visualization_response(
        job_id, group, mode, max_points, bins, seed, projection_method,
        projection_dimensions, x_axis, y_axis, z_axis, build_visualization, _projection_model,
    )


def _projection_model(projected: ProjectionResult):
    """코어 투영을 기존 결과 모델과 같은 값 객체로 변환한다."""
    from app.models.results import ProjectionData

    return ProjectionData(
        method=projected.method, dimensions=projected.dimensions,
        original=projected.original.tolist(), reduced=projected.reduced.tolist(),
        original_indices=projected.original_indices.tolist(),
    )
