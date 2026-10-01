"""분포·상관 지표 (T040 수치형, T041 범주형, T042 상관 보존)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon
from scipy.stats import ks_2samp

from app.core.schema import CATEGORICAL, NUMERIC, ColumnInfo


@dataclass
class ColumnMetric:
    """컬럼 하나의 비교 결과. score는 0~100, 높을수록 비슷하다."""

    name: str
    kind: str
    score: float
    detail: dict[str, float] = field(default_factory=dict)


def _weighted_mean_std(values: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    mean = float(np.average(values, weights=w))
    var = float(np.average((values - mean) ** 2, weights=w))
    return mean, float(np.sqrt(var))


def numeric_metrics(orig: pd.Series, red: pd.Series, weights: np.ndarray) -> ColumnMetric:
    """평균·표준편차 차이와 KS 통계량 (T040). KS는 대표 행을 그대로 비교한다."""
    a = pd.to_numeric(orig, errors="coerce").dropna().to_numpy(dtype=float)
    b = pd.to_numeric(red, errors="coerce").to_numpy(dtype=float)
    ok = ~np.isnan(b)
    b, w = b[ok], weights[ok]
    if len(a) == 0 or len(b) == 0:
        return ColumnMetric(orig.name, NUMERIC, 0.0, {"note": float("nan")})

    mean_o, std_o = float(a.mean()), float(a.std())
    mean_r, std_r = _weighted_mean_std(b, w)
    scale = abs(mean_o) if abs(mean_o) > 1e-9 else 1.0
    mean_diff = abs(mean_r - mean_o) / scale
    std_diff = abs(std_r - std_o) / (std_o if std_o > 1e-9 else 1.0)
    ks = float(ks_2samp(a, b).statistic)
    score = 100 * (1 - min(1.0, 0.5 * ks + 0.25 * min(mean_diff, 1) + 0.25 * min(std_diff, 1)))
    return ColumnMetric(str(orig.name), NUMERIC, round(score, 1), {
        "mean_diff_ratio": round(mean_diff, 4), "std_diff_ratio": round(std_diff, 4),
        "ks": round(ks, 4),
    })


def categorical_metrics(orig: pd.Series, red: pd.Series, weights: np.ndarray) -> ColumnMetric:
    """범주 비율 차이와 Jensen-Shannon divergence (T041)."""
    a = orig.astype(str)
    b = red.astype(str)
    levels = sorted(set(a.unique()) | set(b.unique()))
    p = np.array([(a == lv).mean() for lv in levels], dtype=float)
    total_w = weights.sum()
    q = np.array([weights[(b == lv).to_numpy()].sum() / total_w for lv in levels], dtype=float)
    p, q = np.clip(p, 0, None), np.clip(q, 0, None)
    p, q = p / max(p.sum(), 1e-12), q / max(q.sum(), 1e-12)
    with np.errstate(invalid="ignore"):          # p≈q일 때 반올림으로 음수가 되는 경우가 있다
        js = float(jensenshannon(p, q, base=2))
    js = 0.0 if np.isnan(js) else min(max(js, 0.0), 1.0)
    max_gap = float(np.abs(p - q).max())
    score = 100 * (1 - min(1.0, 0.7 * js + 0.3 * max_gap))
    return ColumnMetric(str(orig.name), CATEGORICAL, round(score, 1), {
        "js_divergence": round(js, 4), "max_ratio_gap": round(max_gap, 4),
        "levels": float(len(levels)),
    })


def distribution_metrics(orig: pd.DataFrame, red: pd.DataFrame, columns: list[ColumnInfo],
                         selected: list[str],
                         weights: np.ndarray) -> tuple[float, list[ColumnMetric]]:
    """선택된 컬럼 전체의 분포 비교 (T040+T041). (0~100 점수, 컬럼별 결과)."""
    kinds = {c.name: c.kind for c in columns}
    out: list[ColumnMetric] = []
    for name in selected:
        if name not in orig.columns or name not in red.columns:
            continue
        if kinds.get(name) == NUMERIC or pd.api.types.is_numeric_dtype(orig[name]):
            out.append(numeric_metrics(orig[name], red[name], weights))
        else:
            out.append(categorical_metrics(orig[name], red[name], weights))
    score = float(np.mean([m.score for m in out])) if out else 0.0
    return round(score, 1), out


def _numeric_columns(df: pd.DataFrame, columns: list[ColumnInfo], selected: list[str]) -> list[str]:
    kinds = {c.name: c.kind for c in columns}
    return [c for c in selected if c in df.columns
            and (kinds.get(c) == NUMERIC or pd.api.types.is_numeric_dtype(df[c]))]


def correlation_metrics(orig: pd.DataFrame, red: pd.DataFrame, columns: list[ColumnInfo],
                        selected: list[str], method: str = "pearson") -> dict:
    """상관 보존 지표와 호환 행렬, 별도의 undefined 마스크를 제공한다."""
    if method not in ("pearson", "spearman"):
        raise ValueError("Correlation method must be pearson or spearman")
    cols = _numeric_columns(orig, columns, selected)
    co = orig[cols].corr(method=method).to_numpy()
    cr = red[cols].corr(method=method).to_numpy()
    undefined_o, undefined_r = ~np.isfinite(co), ~np.isfinite(cr)
    co, cr = np.nan_to_num(co), np.nan_to_num(cr)
    iu = np.triu_indices(len(cols), k=1)
    pairs_o, pairs_r = co[iu], cr[iu]
    frob = float(np.linalg.norm(co - cr))
    max_gap = float(np.abs(pairs_o - pairs_r).max()) if len(pairs_o) else 0.0
    mean_gap = float(np.abs(pairs_o - pairs_r).mean()) if len(pairs_o) else 0.0
    agree = 1.0 if np.array_equal(pairs_o, pairs_r) or len(pairs_o) < 2 else 0.0
    if len(pairs_o) > 1 and np.std(pairs_o) > 0 and np.std(pairs_r) > 0:
        agree = float(np.corrcoef(pairs_o, pairs_r)[0, 1])
    score = 100 * (1 - min(1.0, 0.6 * mean_gap + 0.4 * max_gap))
    result = {
        "score": round(score, 1), "columns": cols, "method": method,
        "frobenius": round(frob, 4), "mean_gap": round(mean_gap, 4),
        "max_gap": round(max_gap, 4), "corr_of_corr": round(agree, 4),
        "matrix_original": co.round(4).tolist(), "matrix_reduced": cr.round(4).tolist(),
        "undefined_original": undefined_o.tolist(), "undefined_reduced": undefined_r.tolist(),
    }
    if len(cols) < 2:
        result["note"] = "수치형 컬럼이 2개 미만이라 비교하지 않음"
    return result
