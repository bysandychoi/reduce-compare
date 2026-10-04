"""원본·축소본 상관 네트워크 API (T098)."""
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.column_data import locate_group
from app.api.results import get_result
from app.core.network import correlation_network

router = APIRouter(tags=["jobs"])


class NetworkNode(BaseModel):
    id: str
    label: str


class NetworkEdge(BaseModel):
    source: str
    target: str
    correlation: float
    weight: float
    sign: Literal["positive", "negative", "zero"]


class NetworkGraph(BaseModel):
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]
    threshold: float


class CorrelationNetworks(BaseModel):
    group: str
    method: str
    original: NetworkGraph
    reduced: NetworkGraph


def _boolean_mask(value: object, size: int) -> np.ndarray:
    if (not isinstance(value, list) or len(value) != size
            or any(not isinstance(row, list) or len(row) != size for row in value)
            or any(type(cell) is not bool for row in value for cell in row)):
        raise ValueError("Undefined mask must contain booleans and match columns")
    return np.asarray(value, dtype=bool)


def _network(metrics: dict, matrix_key: str, mask_key: str, threshold: float) -> dict:
    columns = metrics.get("columns")
    matrix, mask = metrics.get(matrix_key), metrics.get(mask_key)
    if not isinstance(columns, list) or not isinstance(matrix, list) or not isinstance(mask, list):
        raise ValueError("Correlation result is incomplete")
    values = np.asarray(matrix, dtype=float)
    undefined = _boolean_mask(mask, len(columns))
    expected = (len(columns), len(columns))
    if values.shape != expected:
        raise ValueError("Correlation matrix and mask shapes must match columns")
    values[undefined] = np.nan
    return correlation_network(columns, values, threshold)


def build_networks(job_id: str, group_name: str, threshold: float) -> CorrelationNetworks:
    _, group = locate_group(get_result(job_id), group_name)
    metrics = group.detail.get("correlation")
    if not isinstance(metrics, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "상관행렬 결과가 없습니다")
    try:
        original = _network(metrics, "matrix_original", "undefined_original", threshold)
        reduced = _network(metrics, "matrix_reduced", "undefined_reduced", threshold)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "상관행렬 결과가 올바르지 않습니다"
        ) from error
    return CorrelationNetworks(
        group=group_name, method=str(metrics.get("method", "pearson")),
        original=NetworkGraph(**original), reduced=NetworkGraph(**reduced),
    )


@router.get("/jobs/{job_id}/correlation-network", response_model=CorrelationNetworks)
def get_correlation_network(
    job_id: str, group: str, threshold: float = Query(0.5, ge=0, le=1),
) -> CorrelationNetworks:
    return build_networks(job_id, group, threshold)
