"""원본과 축소본을 같은 PCA/UMAP 공간에 투영한다 (T053)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.decomposition import PCA

DEFAULT_ORIGINAL_LIMIT = 20_000
SUPPORTED_METHODS = {"pca", "umap"}


@dataclass(frozen=True)
class ProjectionResult:
    """같은 모델로 변환한 원본 서브샘플과 축소본 좌표."""

    original: np.ndarray
    reduced: np.ndarray
    original_indices: np.ndarray
    method: str
    dimensions: int


def _as_feature_matrix(values: np.ndarray, name: str) -> np.ndarray:
    try:
        matrix = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 특징 행렬은 숫자여야 합니다") from exc
    if matrix.ndim != 2:
        raise ValueError(f"{name} 특징 행렬은 2차원이어야 합니다")
    if not len(matrix):
        raise ValueError(f"{name} 특징 행렬이 비어 있습니다")
    if matrix.shape[1] == 0:
        raise ValueError(f"{name} 특징 컬럼이 없습니다")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} 특징 행렬에 NaN 또는 무한대가 있습니다")
    return matrix


def _sample_indices(size: int, limit: int, seed: int) -> np.ndarray:
    if limit < 1:
        raise ValueError("원본 서브샘플 크기는 1 이상이어야 합니다")
    if size <= limit:
        return np.arange(size)
    chosen = np.random.default_rng(seed).choice(size, limit, replace=False)
    return np.sort(chosen)


def _project_pca(original: np.ndarray, reduced: np.ndarray, dimensions: int,
                 seed: int) -> tuple[np.ndarray, np.ndarray]:
    if min(original.shape) < dimensions:
        raise ValueError("PCA 투영 축 수보다 원본 행 또는 특징 수가 작습니다")
    model = PCA(n_components=dimensions, random_state=seed)
    return model.fit_transform(original), model.transform(reduced)


def _project_umap(original: np.ndarray, reduced: np.ndarray, dimensions: int,
                  seed: int) -> tuple[np.ndarray, np.ndarray]:
    minimum_rows = dimensions + 2
    if len(original) < minimum_rows:
        raise ValueError(f"{dimensions}D UMAP 투영에는 원본 행이 {minimum_rows}개 이상 필요합니다")
    import umap

    model = umap.UMAP(
        n_components=dimensions,
        n_neighbors=min(15, len(original) - 1),
        random_state=seed,
        transform_seed=seed,
        n_jobs=1,
    )
    return model.fit_transform(original), model.transform(reduced)


def project_comparison(original: np.ndarray, reduced: np.ndarray, method: str = "pca",
                       dimensions: int = 2, seed: int = 0,
                       original_limit: int = DEFAULT_ORIGINAL_LIMIT) -> ProjectionResult:
    """원본에 학습한 한 모델로 원본 서브샘플과 축소본을 함께 투영한다."""
    original_matrix = _as_feature_matrix(original, "원본")
    reduced_matrix = _as_feature_matrix(reduced, "축소본")
    if original_matrix.shape[1] != reduced_matrix.shape[1]:
        raise ValueError("원본과 축소본의 특징 수가 다릅니다")
    normalized_method = method.lower()
    if normalized_method not in SUPPORTED_METHODS:
        raise ValueError(f"지원하지 않는 투영 방식입니다: {method}")
    if dimensions not in (2, 3):
        raise ValueError("투영 차원은 2 또는 3이어야 합니다")

    indices = _sample_indices(len(original_matrix), original_limit, seed)
    sampled = original_matrix[indices]
    projector = _project_pca if normalized_method == "pca" else _project_umap
    original_coords, reduced_coords = projector(sampled, reduced_matrix, dimensions, seed)
    return ProjectionResult(
        original=np.asarray(original_coords),
        reduced=np.asarray(reduced_coords),
        original_indices=indices,
        method=normalized_method,
        dimensions=dimensions,
    )
