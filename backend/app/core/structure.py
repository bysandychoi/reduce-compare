"""구조 보존 지표와 종합 점수 (T043 trustworthiness, T044 커버리지, T045 종합)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.decomposition import PCA
from sklearn.manifold import trustworthiness
from sklearn.neighbors import NearestNeighbors

TRUST_SUBSAMPLE = 3000      # trustworthiness는 O(n²)이라 서브샘플로 계산한다
COVERAGE_SUBSAMPLE = 20000
WEIGHTS = {"distribution": 1 / 3, "correlation": 1 / 3, "structure": 1 / 3}


@dataclass
class OverallScore:
    """종합 점수와 구성 요소 (T045). 세 축을 1/3씩 가중 평균한다."""

    total: float
    distribution: float
    correlation: float
    structure: float
    detail: dict = field(default_factory=dict)


def _subsample(x: np.ndarray, limit: int, seed: int) -> np.ndarray:
    if len(x) <= limit:
        return np.arange(len(x))
    return np.random.default_rng(seed).choice(len(x), limit, replace=False)


def trustworthiness_score(x: np.ndarray, seed: int = 0, n_neighbors: int = 10,
                          limit: int = TRUST_SUBSAMPLE) -> float:
    """원본 서브샘플을 2차원으로 투영했을 때 이웃 관계가 얼마나 지켜지는지 (T043).

    0~1 값. 투영으로 가까워진 척하는 점이 적을수록 1에 가깝다.
    """
    idx = _subsample(x, limit, seed)
    sub = x[idx]
    if len(sub) <= n_neighbors + 1:
        return 1.0
    proj = PCA(n_components=2, random_state=seed).fit_transform(sub)
    return float(trustworthiness(sub, proj, n_neighbors=n_neighbors))


def _nearest_distances(points: np.ndarray, targets: np.ndarray) -> np.ndarray:
    nn = NearestNeighbors(n_neighbors=1).fit(targets)
    dist, _ = nn.kneighbors(points)
    return dist.ravel()


def coverage_metrics(x_orig: np.ndarray, x_red: np.ndarray, seed: int = 0,
                     limit: int = COVERAGE_SUBSAMPLE) -> dict:
    """원본의 각 점에서 가장 가까운 축소본 점까지의 거리 (T044).

    거리 자체는 차원 수에 따라 크게 달라지므로, 같은 크기의 랜덤 샘플이 만드는
    거리를 기준으로 삼는다. 랜덤만큼 고르게 덮으면 100점, 그보다 멀면 낮아진다.
    """
    if len(x_red) == 0:
        raise ValueError("축소본이 비어 있어 커버리지를 계산할 수 없습니다")
    idx = _subsample(x_orig, limit, seed)
    sub = x_orig[idx]
    dist = _nearest_distances(sub, x_red)

    rng = np.random.default_rng(seed + 1)
    base_idx = rng.choice(len(x_orig), min(len(x_red), len(x_orig)), replace=False)
    base = _nearest_distances(sub, x_orig[base_idx])
    mean_d, base_mean = float(dist.mean()), float(base.mean())
    ratio = base_mean / mean_d if mean_d > 1e-12 else 1.0
    score = 100 * min(1.0, ratio)
    scale = base_mean if base_mean > 1e-12 else 1.0
    return {"score": round(score, 1), "mean_distance": round(mean_d / scale, 4),
            "p95_distance": round(float(np.quantile(dist, 0.95)) / scale, 4),
            "vs_random": round(ratio, 4), "sampled": int(len(sub))}


def structure_metrics(x_orig: np.ndarray, x_red: np.ndarray, seed: int = 0) -> dict:
    """구조 보존 지표 묶음 (T043+T044)."""
    trust = trustworthiness_score(x_orig, seed)
    cover = coverage_metrics(x_orig, x_red, seed)
    score = 100 * (0.5 * trust) + 0.5 * cover["score"]
    return {"score": round(score, 1), "trustworthiness": round(trust, 4), "coverage": cover}


def overall_score(distribution: float, correlation: float, structure: float,
                  detail: dict | None = None) -> OverallScore:
    """세 축을 1/3씩 가중 평균한 0~100 점수 (T045)."""
    for name, value in (("분포", distribution), ("상관", correlation), ("구조", structure)):
        if not 0 <= value <= 100:
            raise ValueError(f"{name} 점수는 0~100이어야 합니다 (받은 값: {value})")
    total = (WEIGHTS["distribution"] * distribution + WEIGHTS["correlation"] * correlation
             + WEIGHTS["structure"] * structure)
    return OverallScore(total=round(total, 1), distribution=round(distribution, 1),
                        correlation=round(correlation, 1), structure=round(structure, 1),
                        detail=detail or {})
