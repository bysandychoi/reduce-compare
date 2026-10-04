"""완료 결과의 반영 리포트 데이터 API (T142)."""
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.column_data import locate_group
from app.api.results import get_result
from app.core.relationship_causes import explain_relationship_changes
from app.models.results import ProjectionData

router = APIRouter(tags=["jobs"])


class ReportSize(BaseModel):
    original_rows: int = Field(ge=1)
    prepared_rows: int = Field(ge=1)
    reduced_rows: int = Field(ge=1)
    average_rows_per_representative: float = Field(ge=0)


class RepresentationReport(BaseModel):
    group: str
    reduction_method: str
    size: ReportSize
    points: ProjectionData
    point_metadata: dict[str, list]
    cluster_report: dict[str, Any]
    relationships: dict[str, Any]


def _fallback_cluster_report(original: int, reduced: int) -> dict:
    return {
        "original_count": original, "representative_count": reduced, "excluded_count": 0,
        "clusters": [{
            "cluster_id": 0, "original_count": original, "original_ratio": 1.0,
            "representative_count": reduced, "representative_ratio": 1.0,
            "excluded_count": 0, "covered_count": reduced, "minimum_target": 0,
            "status": "반영", "reason": "군집 기반 축소가 아님",
        }],
    }


def _report_inputs(group) -> tuple[dict, dict]:
    metrics = group.detail.get("correlation")
    cluster_report = group.detail.get("cluster_report")
    if not isinstance(metrics, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "상관관계 결과가 없습니다")
    if cluster_report is None:
        if group.reduction_method in ("cluster_actual", "cluster_mean"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "군집 반영 상세 결과가 없습니다",
            )
        cluster_report = _fallback_cluster_report(group.prepared_rows, group.reduced_rows)
    if not isinstance(cluster_report, dict):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "군집 반영 결과가 올바르지 않습니다",
        )
    return metrics, cluster_report


def _validate_projection(group) -> None:
    projection = group.projection
    points = [*projection.original, *projection.reduced]
    if any(len(point) != projection.dimensions for point in points):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "투영 점 결과의 차원이 올바르지 않습니다",
        )


def _point_metadata(group, report: dict) -> tuple[dict, dict]:
    raw = report.get("point_metadata")
    summary = {key: value for key, value in report.items() if key != "point_metadata"}
    if raw is None:
        return {
            "original_clusters": [0] * len(group.projection.original),
            "reduced_clusters": [0] * len(group.projection.reduced),
            "original_outliers": [False] * len(group.projection.original),
            "reduced_outliers": [False] * len(group.projection.reduced),
        }, summary
    keys = ("original_clusters", "reduced_clusters", "original_outliers", "reduced_outliers")
    if not isinstance(raw, dict) or any(not isinstance(raw.get(key), list) for key in keys):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "점 메타데이터가 올바르지 않습니다",
        )
    clusters = [*raw["original_clusters"], *raw["reduced_clusters"]]
    outliers = [*raw["original_outliers"], *raw["reduced_outliers"]]
    if (any(isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in clusters)
            or any(type(value) is not bool for value in outliers)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "점 메타데이터 값이 올바르지 않습니다",
        )
    indices = group.projection.original_indices
    if (len(raw["original_clusters"]) != group.prepared_rows
            or len(raw["original_outliers"]) != group.prepared_rows
            or len(raw["reduced_clusters"]) != len(group.projection.reduced)
            or len(raw["reduced_outliers"]) != len(group.projection.reduced)
            or any(index < 0 or index >= group.prepared_rows for index in indices)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "점 메타데이터 크기가 맞지 않습니다",
        )
    aligned = {
        "original_clusters": [raw["original_clusters"][index] for index in indices],
        "original_outliers": [raw["original_outliers"][index] for index in indices],
        "reduced_clusters": raw["reduced_clusters"],
        "reduced_outliers": raw["reduced_outliers"],
    }
    return aligned, summary


@router.get("/jobs/{job_id}/report", response_model=RepresentationReport)
def get_report(
    job_id: str, group: str, threshold: float = Query(.5, ge=0, le=1),
) -> RepresentationReport:
    _, result_group = locate_group(get_result(job_id), group)
    metrics, cluster_report = _report_inputs(result_group)
    _validate_projection(result_group)
    point_metadata, cluster_summary = _point_metadata(result_group, cluster_report)
    try:
        relationships = explain_relationship_changes(metrics, cluster_report, threshold)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "반영 리포트 결과가 올바르지 않습니다",
        ) from error
    size = ReportSize(
        original_rows=result_group.original_rows, prepared_rows=result_group.prepared_rows,
        reduced_rows=result_group.reduced_rows,
        average_rows_per_representative=round(
            result_group.prepared_rows / result_group.reduced_rows, 4,
        ),
    )
    return RepresentationReport(
        group=group, reduction_method=result_group.reduction_method, size=size,
        points=result_group.projection, point_metadata=point_metadata,
        cluster_report=cluster_summary,
        relationships=relationships,
    )
