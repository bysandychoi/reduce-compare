"""컬럼별 분포 비교 API — 원본·축소본 정규화 히스토그램 (T093)."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.column_data import ColumnSides, load_sides

router = APIRouter(tags=["jobs"])


class HistogramData(BaseModel):
    group: str
    column: str
    columns: list[str]
    edges: list[float]
    original_ratios: list[float]
    reduced_ratios: list[float]
    original_rows: int
    reduced_rows: int
    weighted: bool
    dropped_original: int   # 축소 전에 빠졌거나 값이 결측·무한대라 뺀 원본 행 수
    dropped_reduced: int    # 값이 결측·무한대라 뺀 축소본 대표 행 수


def _ratios(values: np.ndarray, weights: np.ndarray, edges: np.ndarray) -> list[float]:
    """구간별 비율. 가중치 합으로 나눠 원본과 축소본을 같은 축에서 비교한다."""
    total = float(weights.sum())
    if total <= 0:
        return [0.0] * (len(edges) - 1)
    counts, _ = np.histogram(values, bins=edges, weights=weights)
    return [round(float(value) / total, 6) for value in counts]


def _edges(sides: ColumnSides, bins: int) -> np.ndarray:
    """양쪽을 모두 담는 같은 구간 경계. 경계를 만들 수 없으면 422로 막는다."""
    low = float(min(sides.original.min(), sides.reduced.min()))
    high = float(max(sides.original.max(), sides.reduced.max()))
    if high <= low:
        low, high = low - 0.5, high + 0.5
    with np.errstate(over="ignore", invalid="ignore"):
        edges = np.linspace(low, high, bins + 1)
    # 폭이 너무 크면 linspace가 넘치고, 너무 좁으면 경계가 같은 값으로 뭉친다.
    if not np.isfinite(edges).all() or not (np.diff(edges) > 0).all():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "값의 범위로 구간을 만들 수 없습니다 (너무 넓거나 너무 좁습니다)",
        )
    return edges


def build_histogram(job_id: str, group_name: str, column: str | None,
                    bins: int) -> HistogramData:
    """선택한 수치형 컬럼의 원본·축소본 분포를 같은 구간으로 자른다."""
    sides = load_sides(job_id, group_name, column)
    edges = _edges(sides, bins)
    return HistogramData(
        group=group_name, column=sides.column, columns=sides.columns, edges=edges.tolist(),
        original_ratios=_ratios(sides.original, np.ones(len(sides.original)), edges),
        reduced_ratios=_ratios(sides.reduced, sides.weights, edges),
        original_rows=len(sides.original), reduced_rows=len(sides.reduced),
        weighted=sides.weighted, dropped_original=sides.dropped_original,
        dropped_reduced=sides.dropped_reduced,
    )


@router.get("/jobs/{job_id}/histogram", response_model=HistogramData)
def get_histogram(
    job_id: str,
    group: str,
    column: str | None = None,
    bins: int = Query(default=24, ge=4, le=80),
) -> HistogramData:
    return build_histogram(job_id, group, column, bins)
