"""컬럼별 박스플롯 비교 API — 가중치를 반영한 원본·축소본 사분위수 (T094)."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from app.api.column_data import load_sides

router = APIRouter(tags=["jobs"])

OUTLIER_LIMIT = 40   # 이상치는 많아도 이 개수만 보낸다 (화면이 점으로 뒤덮이지 않게)


class BoxSummary(BaseModel):
    """상자 하나. 수염은 1.5×IQR 안에 실제로 있는 값의 최솟값·최댓값이다."""

    minimum: float
    q1: float
    median: float
    q3: float
    maximum: float
    low_whisker: float
    high_whisker: float
    outliers: list[float]
    outlier_count: int
    rows: int


class BoxplotData(BaseModel):
    group: str
    column: str
    columns: list[str]
    original: BoxSummary
    reduced: BoxSummary
    weighted: bool
    dropped_original: int
    dropped_reduced: int


def weighted_quantiles(values: np.ndarray, weights: np.ndarray,
                       probs: tuple[float, ...]) -> list[float]:
    """가중치를 반영한 분위수. np.percentile은 가중치를 받지 못해 직접 계산한다.

    대표 행 하나가 원본 여러 행을 대표하므로, 가중치를 빼면 축소본 상자가
    실제보다 좁거나 넓게 그려진다.

    누적 비율이 p 이상이 되는 첫 값을 고른다 (numpy의 `inverted_cdf`와 같은 정의).
    정수 가중치면 그만큼 행을 늘려 놓고 `np.percentile(..., method="inverted_cdf")`를
    쓴 것과 정확히 같다.

    가중치에 **비례만 하고 크기에는 영향받지 않는** 정의를 쓰는 게 중요하다. 원본은
    가중치가 모두 1이고 축소본은 `원본 행 수 / 남긴 행 수`(소수)라서, 크기에 따라
    달라지는 정의를 쓰면 같은 분포인데도 두 상자가 다르게 그려진다.
    """
    order = np.argsort(values, kind="stable")
    sorted_values, sorted_weights = values[order], weights[order]
    total = float(sorted_weights.sum())
    if total <= 0:
        return [float(sorted_values[0])] * len(probs)
    cumulative = np.cumsum(sorted_weights) / total
    cumulative[-1] = 1.0   # 부동소수 오차로 마지막이 1에 못 미치는 것을 막는다
    # 가중치가 total/kept처럼 나누어떨어지지 않으면 누적이 0.5 대신 0.4999…가 되어
    # 경계에서 한 칸 뒤를 고른다. 아주 작은 여유를 둬서 가중치 1일 때와 같게 만든다.
    found = np.searchsorted(cumulative + 1e-9, np.asarray(probs), side="left")
    return [float(sorted_values[min(int(index), len(sorted_values) - 1)]) for index in found]


def summarize(values: np.ndarray, weights: np.ndarray) -> BoxSummary:
    q1, median, q3 = weighted_quantiles(values, weights, (0.25, 0.5, 0.75))
    gap = q3 - q1
    low_limit, high_limit = q1 - 1.5 * gap, q3 + 1.5 * gap
    inside = values[(values >= low_limit) & (values <= high_limit)]
    outside = values[(values < low_limit) | (values > high_limit)]
    shown = np.sort(outside)
    if len(shown) > OUTLIER_LIMIT:
        # 양 끝이 가장 눈여겨볼 값이라 아래위에서 절반씩 고른다.
        half = OUTLIER_LIMIT // 2
        shown = np.concatenate([shown[:half], shown[-half:]])
    return BoxSummary(
        minimum=float(values.min()), q1=q1, median=median, q3=q3,
        maximum=float(values.max()),
        low_whisker=float(inside.min()) if len(inside) else q1,
        high_whisker=float(inside.max()) if len(inside) else q3,
        outliers=[float(value) for value in shown], outlier_count=len(outside),
        rows=len(values),
    )


def build_boxplot(job_id: str, group_name: str, column: str | None) -> BoxplotData:
    """선택한 수치형 컬럼의 원본·축소본 상자 요약을 만든다."""
    sides = load_sides(job_id, group_name, column)
    return BoxplotData(
        group=group_name, column=sides.column, columns=sides.columns,
        original=summarize(sides.original, np.ones(len(sides.original))),
        reduced=summarize(sides.reduced, sides.weights),
        weighted=sides.weighted, dropped_original=sides.dropped_original,
        dropped_reduced=sides.dropped_reduced,
    )


@router.get("/jobs/{job_id}/boxplot", response_model=BoxplotData)
def get_boxplot(job_id: str, group: str, column: str | None = None) -> BoxplotData:
    return build_boxplot(job_id, group, column)
