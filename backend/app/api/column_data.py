"""컬럼별 비교 그래프가 함께 쓰는 자료 읽기 (T093 히스토그램, T094 박스플롯).

원본은 업로드 파일을 다시 읽어 축소 때와 같은 기준으로 결측 행을 빼고, 축소본은
저장된 CSV와 대표 행 가중치를 읽는다. 그래프마다 다른 계산은 각 라우터가 한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import HTTPException, status

from app.api.groups import job_directory
from app.api.results import get_result
from app.core.ingest import read_csv
from app.core.prepare import SOURCE_COL, drop_missing_rows
from app.core.schema import CATEGORICAL, NUMERIC
from app.models.results import GroupResult


@dataclass
class ColumnSides:
    """한 컬럼의 원본·축소본 값과 그 과정에서 뺀 건수."""

    column: str
    columns: list[str]        # 고를 수 있는 수치형 컬럼
    original: np.ndarray
    reduced: np.ndarray
    weights: np.ndarray       # 축소본 대표 행이 각각 원본 몇 행을 대표하는지
    weighted: bool            # 저장된 가중치를 실제로 썼는지
    dropped_original: int
    dropped_reduced: int


@dataclass
class CategorySides:
    """범주형 컬럼의 원본·축소본 값과 대표 행 가중치."""

    column: str
    columns: list[str]
    original: np.ndarray
    reduced: np.ndarray
    weights: np.ndarray
    weighted: bool
    dropped_original: int
    dropped_reduced: int


def locate_group(result, name: str) -> tuple[int, GroupResult]:
    for index, group in enumerate(result.groups):
        if group.name == name:
            return index, group
    raise HTTPException(status.HTTP_404_NOT_FOUND, "결과 그룹을 찾을 수 없습니다")


def compared_columns(group: GroupResult) -> list[dict]:
    return [item for item in (group.detail.get("columns") or []) if item.get("name")]


def numeric_columns(group: GroupResult) -> list[str]:
    return [str(item["name"]) for item in compared_columns(group)
            if item.get("kind") == NUMERIC]


def categorical_columns(group: GroupResult) -> list[str]:
    return [str(item["name"]) for item in compared_columns(group)
            if item.get("kind") == CATEGORICAL]


def reduced_path(job_id: str, index: int) -> Path:
    path = job_directory(job_id) / "reduced" / f"group-{index + 1}.csv"
    if not path.is_file():
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "축소본 CSV 파일이 없습니다")
    return path


def present_columns(job_id: str, index: int) -> set[str]:
    """축소본 CSV의 헤더만 읽어 데이터에 실제로 있는 컬럼을 확인한다."""
    try:
        header = pd.read_csv(reduced_path(job_id, index), encoding="utf-8-sig", nrows=0)
    except (OSError, UnicodeError, ValueError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "축소본 컬럼 목록을 읽지 못했습니다"
        ) from error
    # 파이프라인이 붙인 출처 컬럼은 원본 데이터에 없던 것이라 선택 대상이 아니다.
    return {str(name) for name in header.columns} - {SOURCE_COL}


def pick_column(group: GroupResult, column: str | None,
                present: set[str]) -> tuple[str, list[str]]:
    """고를 수 있는 컬럼은 축소 기준으로 쓰인 수치형 컬럼뿐이다.

    데이터에 아예 없는 컬럼(404)과, 있지만 비교 대상이 아닌 컬럼(422)을 구분해서 알린다.
    """
    # 존재 여부를 먼저 본다 — 그래야 수치형 컬럼이 하나도 없는 그룹에서도 없는 컬럼이 404가 된다.
    if column and column not in present:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{column}' 컬럼이 없습니다")
    numeric = numeric_columns(group)
    if not numeric:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "수치형 컬럼이 없습니다")
    chosen = column or numeric[0]
    if chosen not in numeric:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"'{chosen}'은(는) 축소 기준으로 쓰인 수치형 컬럼이 아니라 분포를 비교할 수 없습니다",
        )
    return chosen, numeric


def pick_category(group: GroupResult, column: str | None,
                  present: set[str]) -> tuple[str, list[str]]:
    if column and column not in present:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{column}' 컬럼이 없습니다")
    categories = categorical_columns(group)
    if not categories:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "범주형 컬럼이 없습니다")
    chosen = column or categories[0]
    if chosen not in categories:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"'{chosen}'은(는) 축소 기준으로 쓰인 범주형 컬럼이 아닙니다",
        )
    return chosen, categories


def _values(frame: pd.DataFrame, column: str) -> np.ndarray:
    if column not in frame.columns:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{column}' 컬럼이 없습니다")
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)


def _original_frame(job_id: str, group: GroupResult) -> tuple[pd.DataFrame, int]:
    """업로드 원본을 다시 읽고, 축소 때와 같은 기준으로 결측 행을 뺀다. (프레임, 뺀 행 수)."""
    uploads = job_directory(job_id) / "uploads"
    frames = []
    for name in group.files:
        path = uploads / name
        if not path.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"원본 파일이 없습니다: {name}")
        frame, _ = read_csv(str(path))
        frames.append(frame)
    merged = pd.concat(frames, ignore_index=True)
    used = [str(item["name"]) for item in compared_columns(group)]
    return drop_missing_rows(merged, used)


def representative_weights(job_id: str, index: int, size: int) -> tuple[np.ndarray, bool]:
    """대표 행이 각각 원본 몇 행을 대표하는지. 없으면 모두 1로 보고 그 사실을 함께 돌려준다."""
    path = job_directory(job_id) / "projection-source" / f"group-{index + 1}.npz"
    if path.is_file():
        with np.load(path) as source:
            if "weights" in source.files:
                saved = np.asarray(source["weights"], dtype=float)
                if (len(saved) == size and np.isfinite(saved).all()
                        and (saved >= 0).all() and saved.sum() > 0):
                    return saved, True
    return np.ones(size, dtype=float), False


def load_sides(job_id: str, group_name: str, column: str | None) -> ColumnSides:
    """선택한 컬럼의 원본·축소본 값을 읽고 비교할 수 없는 값을 뺀다."""
    index, group = locate_group(get_result(job_id), group_name)
    chosen, numeric = pick_column(group, column, present_columns(job_id, index))
    try:
        frame, missing = _original_frame(job_id, group)
        reduced_frame = pd.read_csv(reduced_path(job_id, index), encoding="utf-8-sig")
    except (OSError, UnicodeError, ValueError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "분포를 계산할 원본 자료를 읽지 못했습니다"
        ) from error

    original = _values(frame, chosen)
    reduced = _values(reduced_frame, chosen)
    weights, weighted = representative_weights(job_id, index, len(reduced))
    keep = np.isfinite(reduced)
    sides = ColumnSides(
        column=chosen, columns=numeric,
        original=original[np.isfinite(original)], reduced=reduced[keep],
        weights=weights[keep], weighted=weighted,
        dropped_original=missing + int((~np.isfinite(original)).sum()),
        dropped_reduced=int((~keep).sum()),
    )
    if len(sides.original) == 0 or len(sides.reduced) == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "비교할 값이 없습니다")
    return sides


def load_category_sides(job_id: str, group_name: str,
                        column: str | None) -> CategorySides:
    """선택한 범주형 컬럼을 읽고 결측값을 양쪽에서 제외한다."""
    index, group = locate_group(get_result(job_id), group_name)
    chosen, columns = pick_category(group, column, present_columns(job_id, index))
    try:
        frame, missing = _original_frame(job_id, group)
        reduced_frame = pd.read_csv(reduced_path(job_id, index), encoding="utf-8-sig")
    except (OSError, UnicodeError, ValueError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "분포를 계산할 원본 자료를 읽지 못했습니다"
        ) from error
    if chosen not in frame.columns:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{chosen}' 컬럼이 없습니다")
    original, reduced = frame[chosen], reduced_frame[chosen]
    weights, weighted = representative_weights(job_id, index, len(reduced))
    original_ok, reduced_ok = original.notna().to_numpy(), reduced.notna().to_numpy()
    sides = CategorySides(
        column=chosen, columns=columns,
        original=original[original_ok].astype(str).to_numpy(),
        reduced=reduced[reduced_ok].astype(str).to_numpy(),
        weights=weights[reduced_ok], weighted=weighted,
        dropped_original=missing + int((~original_ok).sum()),
        dropped_reduced=int((~reduced_ok).sum()),
    )
    if len(sides.original) == 0 or len(sides.reduced) == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "비교할 값이 없습니다")
    return sides
