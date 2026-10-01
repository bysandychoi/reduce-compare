"""축소 파이프라인 결과의 API/JSON 스키마 (T055)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScoreSummary(BaseModel):
    total: float = Field(ge=0, le=100)
    distribution: float = Field(ge=0, le=100)
    correlation: float = Field(ge=0, le=100)
    structure: float = Field(ge=0, le=100)


class ScorePoint(BaseModel):
    size: int = Field(ge=1)
    score: float = Field(ge=0, le=100)
    distribution: float = Field(ge=0, le=100)
    correlation: float = Field(ge=0, le=100)
    structure: float = Field(ge=0, le=100)


class MethodScore(ScorePoint):
    method: str


class ProjectionData(BaseModel):
    method: str
    dimensions: int = Field(ge=2, le=3)
    original: list[list[float]]
    reduced: list[list[float]]
    original_indices: list[int]


class GroupResult(BaseModel):
    name: str
    files: list[str]
    original_rows: int = Field(ge=1)
    prepared_rows: int = Field(ge=1)
    reduced_rows: int = Field(ge=1)
    reduction_method: str
    score: ScoreSummary
    size_curve: list[ScorePoint]
    method_scores: list[MethodScore]
    projection: ProjectionData
    detail: dict[str, Any]


class SkippedGroup(BaseModel):
    name: str
    files: list[str]
    reason: str


class PipelineResults(BaseModel):
    folder: str
    groups: list[GroupResult]
    skipped: list[SkippedGroup]

    @classmethod
    def from_core(cls, result: Any) -> PipelineResults:
        """T054 내부 결과를 NumPy 값 없는 JSON 안전 모델로 바꾼다."""
        groups = [_group_from_core(group) for group in result.groups]
        return cls(folder=result.folder, groups=groups, skipped=result.skipped)


def _group_from_core(group: Any) -> GroupResult:
    chosen = group.chosen
    projection = group.projection
    return GroupResult(
        name=group.name,
        files=group.files,
        original_rows=group.original_rows,
        prepared_rows=len(group.prepared.frame),
        reduced_rows=chosen.size,
        reduction_method=chosen.method,
        score=ScoreSummary(
            total=chosen.score,
            distribution=chosen.distribution,
            correlation=chosen.correlation,
            structure=chosen.structure,
        ),
        size_curve=group.size_curve,
        method_scores=group.method_scores,
        projection=ProjectionData(
            method=projection.method,
            dimensions=projection.dimensions,
            original=projection.original.tolist(),
            reduced=projection.reduced.tolist(),
            original_indices=projection.original_indices.tolist(),
        ),
        detail=chosen.detail,
    )
