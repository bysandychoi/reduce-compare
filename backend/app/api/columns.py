"""그룹별 축소 기준 컬럼 조회·저장 API (T067)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.groups import calculate_groups
from app.core.prepare import drop_missing_rows, merge_group
from app.core.sampling import choose_stratify_column
from app.core.schema import ColumnInfo, SchemaGroup

router = APIRouter(tags=["jobs"])


class ColumnChoice(BaseModel):
    name: str
    kind: str
    dtype: str
    missing_ratio: float
    default_selected: bool
    selected: bool
    reason: str


class ColumnChoices(BaseModel):
    group_id: str
    columns: list[ColumnChoice]
    stratify_column: str | None


class ColumnSelectionUpdate(BaseModel):
    selected: list[str]


def _find_group(job_id: str, group_id: str) -> tuple[Path, SchemaGroup]:
    directory, groups = calculate_groups(job_id)
    for index, group in enumerate(groups, start=1):
        if group_id == f"group-{index}":
            return directory, group
    raise HTTPException(status.HTTP_404_NOT_FOUND, "그룹을 찾을 수 없습니다")


def _selection_path(directory: Path, group_id: str) -> Path:
    return directory / "column-selections" / f"{group_id}.json"


def _selected_names(directory: Path, group_id: str, columns: list[ColumnInfo]) -> list[str]:
    path = _selection_path(directory, group_id)
    if not path.is_file():
        return [column.name for column in columns if column.selected]
    data = json.loads(path.read_text(encoding="utf-8"))
    return [str(name) for name in data["selected"]]


def _view(directory: Path, group_id: str, group: SchemaGroup) -> ColumnChoices:
    selected_names = _selected_names(directory, group_id, group.columns)
    selected = set(selected_names)
    choices = [
        ColumnChoice(
            name=column.name,
            kind=column.kind,
            dtype=column.dtype,
            missing_ratio=column.missing_ratio,
            default_selected=column.selected,
            selected=column.name in selected,
            reason=column.reason,
        )
        for column in group.columns
    ]
    try:
        frame = merge_group(group.files, add_source=False)
    except (OSError, UnicodeError, ValueError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "층화 기준을 계산할 수 없습니다"
        ) from error
    prepared, _dropped = drop_missing_rows(frame, selected_names)
    return ColumnChoices(
        group_id=group_id,
        columns=choices,
        stratify_column=choose_stratify_column(prepared, group.columns, selected_names),
    )


def _validate_selection(selected: list[str], group: SchemaGroup) -> None:
    if not selected:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "컬럼을 1개 이상 선택해야 합니다")
    if len(selected) != len(set(selected)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "같은 컬럼이 중복되었습니다")
    unknown = sorted(set(selected) - {column.name for column in group.columns})
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"데이터에 없는 컬럼입니다: {', '.join(unknown)}",
        )


@router.get("/jobs/{job_id}/groups/{group_id}/columns", response_model=ColumnChoices)
def get_columns(job_id: str, group_id: str) -> ColumnChoices:
    directory, group = _find_group(job_id, group_id)
    return _view(directory, group_id, group)


@router.put("/jobs/{job_id}/groups/{group_id}/columns", response_model=ColumnChoices)
def update_columns(job_id: str, group_id: str,
                   update: ColumnSelectionUpdate) -> ColumnChoices:
    directory, group = _find_group(job_id, group_id)
    _validate_selection(update.selected, group)
    path = _selection_path(directory, group_id)
    path.parent.mkdir(exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"selected": update.selected}, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)
    return _view(directory, group_id, group)
