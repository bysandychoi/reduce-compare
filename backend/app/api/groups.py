"""Schema-group inspection and merge-decision endpoints."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api import jobs
from app.core.ingest import collect_csv_files
from app.core.schema import SchemaGroup, extract_schema, group_by_schema

router = APIRouter(tags=["jobs"])
JOB_ID = re.compile(r"^[0-9a-f]{32}$")


class ColumnView(BaseModel):
    name: str
    kind: str
    dtype: str
    missing_ratio: float
    selected: bool
    reason: str


class GroupView(BaseModel):
    group_id: str
    files: list[str]
    columns: list[ColumnView]
    merge: bool


class GroupsView(BaseModel):
    groups: list[GroupView]


class GroupDecision(BaseModel):
    group_id: str
    merge: bool


class GroupUpdate(BaseModel):
    groups: list[GroupDecision]


def job_directory(job_id: str) -> Path:
    if not JOB_ID.fullmatch(job_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다")
    directory = jobs.JOB_ROOT / job_id
    if not directory.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다")
    return directory


def calculate_groups(job_id: str) -> tuple[Path, list[SchemaGroup]]:
    directory = job_directory(job_id)
    try:
        files = collect_csv_files(str(directory / "uploads"))
    except OSError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "업로드 폴더를 읽을 수 없습니다"
        ) from error
    if not files:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "읽을 수 있는 표 파일이 없습니다"
        )
    schemas = []
    for file in files:
        try:
            schemas.append(extract_schema(file))
        except UnicodeError as error:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"파일 인코딩을 읽을 수 없습니다: {file.name}",
            ) from error
        except ValueError as error:
            message = str(error).strip() or f"표 파일이 올바르지 않습니다: {file.name}"
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message) from error
        except OSError as error:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"표 파일을 읽을 수 없습니다: {file.name}",
            ) from error
    groups = group_by_schema(schemas)
    return directory, groups


def saved_decisions(directory: Path) -> dict[str, bool]:
    path = directory / "groups.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): bool(value) for key, value in data.items()}


def group_views(directory: Path, groups: list[SchemaGroup]) -> list[GroupView]:
    decisions = saved_decisions(directory)
    views: list[GroupView] = []
    for index, group in enumerate(groups, start=1):
        group_id = f"group-{index}"
        columns = [ColumnView(**vars(column)) for column in group.columns]
        views.append(
            GroupView(
                group_id=group_id,
                files=[file.name.replace("\\", "/") for file in group.files],
                columns=columns,
                merge=decisions.get(group_id, group.merge),
            )
        )
    return views


@router.get("/jobs/{job_id}/groups", response_model=GroupsView)
def get_groups(job_id: str) -> GroupsView:
    directory, groups = calculate_groups(job_id)
    return GroupsView(groups=group_views(directory, groups))


@router.put("/jobs/{job_id}/groups", response_model=GroupsView)
def update_groups(job_id: str, update: GroupUpdate) -> GroupsView:
    directory, groups = calculate_groups(job_id)
    expected = {f"group-{index}" for index in range(1, len(groups) + 1)}
    received = [decision.group_id for decision in update.groups]
    if len(received) != len(set(received)) or set(received) != expected:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "모든 그룹을 한 번씩 지정해야 합니다"
        )

    decisions = {decision.group_id: decision.merge for decision in update.groups}
    temporary = directory / "groups.json.tmp"
    temporary.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
    temporary.replace(directory / "groups.json")
    return GroupsView(groups=group_views(directory, groups))
