"""범주형 컬럼의 원본·축소본 비율 비교 API (T095)."""
from collections import Counter

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from app.api.column_data import load_category_sides

router = APIRouter(tags=["jobs"])


class CategoryRatioData(BaseModel):
    group: str
    column: str
    columns: list[str]
    categories: list[str]
    original_ratios: list[float]
    reduced_ratios: list[float]
    original_rows: int
    reduced_rows: int
    weighted: bool
    dropped_original: int
    dropped_reduced: int


def build_category_ratios(job_id: str, group_name: str,
                          column: str | None) -> CategoryRatioData:
    sides = load_category_sides(job_id, group_name, column)
    original_counts = Counter(str(value) for value in sides.original)
    reduced_counts: dict[str, float] = {}
    for value, weight in zip(sides.reduced, sides.weights):
        label = str(value)
        reduced_counts[label] = reduced_counts.get(label, 0.0) + float(weight)
    categories = sorted(
        original_counts.keys() | reduced_counts.keys(),
        key=lambda label: (
            0 if original_counts[label] else 1,
            -original_counts[label], -reduced_counts.get(label, 0.0), label,
        ),
    )
    original_total = float(sum(original_counts.values()))
    reduced_total = float(np.sum(sides.weights))
    return CategoryRatioData(
        group=group_name, column=sides.column, columns=sides.columns,
        categories=categories,
        original_ratios=[original_counts[label] / original_total for label in categories],
        reduced_ratios=[reduced_counts.get(label, 0.0) / reduced_total for label in categories],
        original_rows=len(sides.original), reduced_rows=len(sides.reduced),
        weighted=sides.weighted, dropped_original=sides.dropped_original,
        dropped_reduced=sides.dropped_reduced,
    )


@router.get("/jobs/{job_id}/category-ratios", response_model=CategoryRatioData)
def get_category_ratios(job_id: str, group: str,
                        column: str | None = None) -> CategoryRatioData:
    return build_category_ratios(job_id, group, column)
