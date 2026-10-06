"""축 변수 선택을 투영 표본 좌표에 정렬한다 (T104)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Literal

import numpy as np
import pandas as pd
from fastapi import HTTPException, status

from app.api.column_data import _original_frame, _values, numeric_columns, reduced_path
from app.api.groups import job_directory
from app.api.results import get_result
from app.core.projection import project_comparison
from app.models.results import GroupResult


def _load_weights(path: Path) -> np.ndarray | None:
    if not path.is_file():
        return None
    try:
        with np.load(path) as source:
            return np.asarray(source["weights"], dtype=float) if "weights" in source.files else None
    except (OSError, ValueError):
        return None


def _axis_label(axis: str, method: str, dimensions: int, columns: list[str]) -> str:
    if axis.startswith("projection:"):
        try:
            dimension = int(axis.split(":", maxsplit=1)[1])
        except ValueError as error:
            raise HTTPException(422, "투영축 지정이 올바르지 않습니다") from error
        if 0 <= dimension < dimensions:
            return f"{method.upper()} {dimension + 1}"
        raise HTTPException(422, "선택한 투영축이 없습니다")
    if axis.startswith("column:"):
        column = axis.removeprefix("column:")
        if column in columns:
            return column
    raise HTTPException(422, "선택한 축 변수를 사용할 수 없습니다")


def _map_axes(job_id: str, index: int, group: GroupResult, payload,
              axes: list[str], columns: list[str]):
    labels = [
        _axis_label(axis, payload.projection_method, payload.dimensions, columns)
        for axis in axes
    ]
    if any(axis.startswith("column:") for axis in axes) and payload.mode != "sample":
        raise HTTPException(422, "밀도 모드에서는 컬럼 축을 지원하지 않습니다")
    if not any(axis.startswith("column:") for axis in axes):
        return payload.model_copy(update={"axis_labels": labels})
    try:
        original_frame, _ = _original_frame(job_id, group)
        reduced_frame = pd.read_csv(reduced_path(job_id, index), encoding="utf-8-sig")
    except (OSError, UnicodeError, ValueError) as error:
        raise HTTPException(422, "축 변수 데이터를 읽지 못했습니다") from error
    original_points = [list(point) for point in payload.original_points]
    reduced_points = [list(point) for point in payload.reduced_points]
    original_indices = np.asarray(payload.original_indices, dtype=int)
    reduced_indices = np.asarray(payload.reduced_indices, dtype=int)
    for dimension, axis in enumerate(axes):
        if axis.startswith("projection:"):
            continue
        column = axis.removeprefix("column:")
        original_values = _values(original_frame, column)
        reduced_values = _values(reduced_frame, column)
        if (np.any(original_indices < 0) or np.any(original_indices >= len(original_values))
                or np.any(reduced_indices < 0) or np.any(reduced_indices >= len(reduced_values))):
            raise HTTPException(422, "축 변수와 그래프 표본 행이 맞지 않습니다")
        original_axis = original_values[original_indices]
        reduced_axis = reduced_values[reduced_indices]
        if not np.isfinite(original_axis).all() or not np.isfinite(reduced_axis).all():
            raise HTTPException(422, "선택한 축 변수에 결측 또는 무한 값이 있습니다")
        for point, value in zip(original_points, original_axis, strict=True):
            point[dimension] = float(value)
        for point, value in zip(reduced_points, reduced_axis, strict=True):
            point[dimension] = float(value)
    return payload.model_copy(update={
        "original_points": original_points, "reduced_points": reduced_points, "axis_labels": labels,
    })


def visualization_response(
    job_id: str, group_name: str, mode: Literal["sample", "density"], max_points: int,
    bins: int, seed: int, method: str | None, dimensions: int | None,
    x_axis: str | None, y_axis: str | None, z_axis: str | None,
    builder: Callable, projection_model: Callable,
):
    result = get_result(job_id)
    index = next((i for i, item in enumerate(result.groups) if item.name == group_name), None)
    if index is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "결과 그룹을 찾을 수 없습니다")
    group = result.groups[index]
    source_path = job_directory(job_id) / "projection-source" / f"group-{index + 1}.npz"
    weights = _load_weights(source_path)
    selected_method = method or group.projection.method
    selected_dimensions = dimensions or group.projection.dimensions
    if (selected_method != group.projection.method
            or selected_dimensions != group.projection.dimensions):
        if not source_path.is_file():
            raise HTTPException(status.HTTP_409_CONFLICT, "투영 방식 전환 자료가 없습니다")
        with np.load(source_path) as source:
            projected = project_comparison(
                source["original"], source["reduced"], selected_method, selected_dimensions, seed,
            )
        group = group.model_copy(update={"projection": projection_model(projected)})
    columns = numeric_columns(group)
    payload = builder(group, mode, max_points, bins, seed, weights, columns)
    if z_axis is not None and payload.dimensions != 3:
        raise HTTPException(422, "Z축은 3D 산점도에서만 선택할 수 있습니다")
    axes = [x_axis or "projection:0", y_axis or "projection:1"]
    if payload.dimensions == 3:
        axes.append(z_axis or "projection:2")
    return _map_axes(job_id, index, group, payload, axes, columns)
