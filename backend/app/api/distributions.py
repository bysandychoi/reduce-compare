"""컬럼별 분포 비교 API — 원본·축소본 정규화 히스토그램 (T093)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.groups import job_directory
from app.api.results import get_result
from app.core.ingest import read_csv
from app.core.prepare import SOURCE_COL, drop_missing_rows
from app.core.schema import NUMERIC
from app.models.results import GroupResult

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


def _locate(result, name: str) -> tuple[int, GroupResult]:
    for index, group in enumerate(result.groups):
        if group.name == name:
            return index, group
    raise HTTPException(status.HTTP_404_NOT_FOUND, "결과 그룹을 찾을 수 없습니다")


def _compared_columns(group: GroupResult) -> list[dict]:
    return [item for item in (group.detail.get("columns") or []) if item.get("name")]


def _numeric_columns(group: GroupResult) -> list[str]:
    return [str(item["name"]) for item in _compared_columns(group)
            if item.get("kind") == NUMERIC]


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
    used = [str(item["name"]) for item in _compared_columns(group)]
    prepared, dropped = drop_missing_rows(merged, used)
    return prepared, dropped


def _weights(job_id: str, index: int, size: int) -> tuple[np.ndarray, bool]:
    """대표 행이 각각 원본 몇 행을 대표하는지. 없으면 모두 1로 보고 그 사실을 함께 돌려준다."""
    path = job_directory(job_id) / "projection-source" / f"group-{index + 1}.npz"
    if path.is_file():
        with np.load(path) as source:
            if "weights" in source.files:
                saved = np.asarray(source["weights"], dtype=float)
                if len(saved) == size and np.isfinite(saved).all():
                    return saved, True
    return np.ones(size, dtype=float), False


def _ratios(values: np.ndarray, weights: np.ndarray, edges: np.ndarray) -> list[float]:
    """구간별 비율. 가중치 합으로 나눠 원본과 축소본을 같은 축에서 비교한다."""
    total = float(weights.sum())
    if total <= 0:
        return [0.0] * (len(edges) - 1)
    counts, _ = np.histogram(values, bins=edges, weights=weights)
    return [round(float(value) / total, 6) for value in counts]


def _reduced_path(job_id: str, index: int) -> Path:
    path = job_directory(job_id) / "reduced" / f"group-{index + 1}.csv"
    if not path.is_file():
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "축소본 CSV 파일이 없습니다")
    return path


def _pick_column(group: GroupResult, column: str | None,
                 present: set[str]) -> tuple[str, list[str]]:
    """고를 수 있는 컬럼은 축소 기준으로 쓰인 수치형 컬럼뿐이다.

    데이터에 아예 없는 컬럼(404)과, 있지만 비교 대상이 아닌 컬럼(422)을 구분해서 알린다.
    """
    # 존재 여부를 먼저 본다 — 그래야 수치형 컬럼이 하나도 없는 그룹에서도 없는 컬럼이 404가 된다.
    if column and column not in present:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{column}' 컬럼이 없습니다")
    numeric = _numeric_columns(group)
    if not numeric:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "수치형 컬럼이 없습니다")
    chosen = column or numeric[0]
    if chosen not in numeric:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"'{chosen}'은(는) 축소 기준으로 쓰인 수치형 컬럼이 아니라 분포를 비교할 수 없습니다",
        )
    return chosen, numeric


def _read_sides(job_id: str, index: int, group: GroupResult,
                column: str) -> tuple[np.ndarray, np.ndarray, int]:
    """(원본 값, 축소본 값, 축소 전에 결측으로 빠진 행 수)."""
    try:
        frame, missing = _original_frame(job_id, group)
        reduced_frame = pd.read_csv(_reduced_path(job_id, index), encoding="utf-8-sig")
    except (OSError, UnicodeError, ValueError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "분포를 계산할 원본 자료를 읽지 못했습니다"
        ) from error
    return _values(frame, column), _values(reduced_frame, column), missing


def _present_columns(job_id: str, index: int) -> set[str]:
    """축소본 CSV의 헤더만 읽어 데이터에 실제로 있는 컬럼을 확인한다."""
    try:
        header = pd.read_csv(_reduced_path(job_id, index), encoding="utf-8-sig", nrows=0)
    except (OSError, UnicodeError, ValueError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "축소본 컬럼 목록을 읽지 못했습니다"
        ) from error
    # 파이프라인이 붙인 출처 컬럼은 원본 데이터에 없던 것이라 선택 대상이 아니다.
    return {str(name) for name in header.columns} - {SOURCE_COL}


def _edges(original: np.ndarray, reduced: np.ndarray, bins: int) -> np.ndarray:
    """양쪽을 모두 담는 같은 구간 경계. 경계를 만들 수 없으면 422로 막는다."""
    low = float(min(original.min(), reduced.min()))
    high = float(max(original.max(), reduced.max()))
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
    index, group = _locate(get_result(job_id), group_name)
    chosen, numeric = _pick_column(group, column, _present_columns(job_id, index))
    original, reduced, missing = _read_sides(job_id, index, group, chosen)

    weights, weighted = _weights(job_id, index, len(reduced))
    # 결측·무한대는 구간 경계를 망가뜨리므로(linspace가 NaN이 된다) 양쪽에서 뺀다.
    keep = np.isfinite(reduced)
    dropped_original = missing + int((~np.isfinite(original)).sum())
    dropped_reduced = int((~keep).sum())
    reduced, weights = reduced[keep], weights[keep]
    original = original[np.isfinite(original)]
    if len(original) == 0 or len(reduced) == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "비교할 값이 없습니다")

    edges = _edges(original, reduced, bins)
    return HistogramData(
        group=group_name, column=chosen, columns=numeric, edges=edges.tolist(),
        original_ratios=_ratios(original, np.ones(len(original)), edges),
        reduced_ratios=_ratios(reduced, weights, edges),
        original_rows=len(original), reduced_rows=len(reduced),
        weighted=weighted, dropped_original=dropped_original, dropped_reduced=dropped_reduced,
    )


@router.get("/jobs/{job_id}/histogram", response_model=HistogramData)
def get_histogram(
    job_id: str,
    group: str,
    column: str | None = None,
    bins: int = Query(default=24, ge=4, le=80),
) -> HistogramData:
    return build_histogram(job_id, group, column, bins)
