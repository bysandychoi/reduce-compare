"""범주형 데이터 전용 유사도 지표 (T047).

수치형이 거의 없고 ID 컬럼으로만 이루어진 데이터를 위한 비교. 상관계수 대신
컬럼별 값 비율, 컬럼 조합 비율, 단위당 행 수 분포, 조합 커버리지를 본다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon
from scipy.stats import ks_2samp

from app.core.grouped import combo_key, unit_table


def _weighted_ratio(keys: np.ndarray, weights: np.ndarray) -> pd.Series:
    s = pd.Series(weights, index=keys).groupby(level=0).sum()
    return s / s.sum()


def ratio_similarity(orig_keys: np.ndarray, red_keys: np.ndarray,
                     weights: np.ndarray) -> dict:
    """두 비율 분포가 얼마나 같은지 (0~100). JS divergence와 최대 비율 차이를 본다."""
    p = pd.Series(orig_keys).value_counts(normalize=True)
    q = _weighted_ratio(red_keys, weights)
    levels = p.index.union(q.index)
    pv = p.reindex(levels, fill_value=0.0).to_numpy(dtype=float)
    qv = q.reindex(levels, fill_value=0.0).to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        js = float(jensenshannon(pv, qv, base=2))
    js = 0.0 if np.isnan(js) else min(max(js, 0.0), 1.0)
    max_gap = float(np.abs(pv - qv).max())
    covered = float((q.reindex(levels, fill_value=0.0) > 0).mean())
    score = 100 * (1 - min(1.0, 0.6 * js + 0.4 * max_gap))
    return {"score": round(score, 1), "js": round(js, 4), "max_gap": round(max_gap, 4),
            "levels": int(len(levels)), "coverage": round(covered, 4)}


def column_scores(orig: pd.DataFrame, red: pd.DataFrame, columns: list[str],
                  weights: np.ndarray) -> tuple[float, list[dict]]:
    """컬럼마다 값 비율을 비교한다."""
    out = []
    for c in columns:
        r = ratio_similarity(orig[c].astype(str).to_numpy(), red[c].astype(str).to_numpy(), weights)
        out.append({"name": c, **r})
    score = float(np.mean([r["score"] for r in out])) if out else 100.0
    return round(score, 1), out


def combo_scores(orig: pd.DataFrame, red: pd.DataFrame, combos: list[list[str]],
                 weights: np.ndarray) -> tuple[float, list[dict]]:
    """컬럼 조합(예: eqp_id×mask_id×eqp_floor)의 비율을 비교한다."""
    out = []
    for cols in combos:
        if any(c not in orig.columns for c in cols):
            continue
        r = ratio_similarity(combo_key(orig, cols).to_numpy(),
                             combo_key(red, cols).to_numpy(), weights)
        out.append({"columns": cols, **r})
    score = float(np.mean([r["score"] for r in out])) if out else 100.0
    return round(score, 1), out


def unit_size_score(orig: pd.DataFrame, red: pd.DataFrame, unit_cols: list[str],
                    strata_cols: list[str]) -> dict:
    """단위당 행 수 분포가 비슷한지 (예: lot 하나가 갖는 조합 개수)."""
    a = unit_table(orig, unit_cols, strata_cols)["rows"].to_numpy(dtype=float)
    b = unit_table(red, unit_cols, strata_cols)["rows"].to_numpy(dtype=float)
    if len(a) == 0 or len(b) == 0:
        return {"score": 0.0, "note": "단위를 만들 수 없습니다"}
    ks = float(ks_2samp(a, b).statistic)
    return {"score": round(100 * (1 - min(1.0, ks)), 1), "ks": round(ks, 4),
            "mean_orig": round(float(a.mean()), 3), "mean_reduced": round(float(b.mean()), 3),
            "max_orig": int(a.max()), "max_reduced": int(b.max())}


def distribution_table(orig: pd.DataFrame, red: pd.DataFrame, columns: list[str],
                       weights: np.ndarray, top: int = 10) -> pd.DataFrame:
    """컬럼별로 값마다 원본·축소 비율을 정리한 표를 만든다.

    값이 많은 컬럼은 원본 비율이 큰 것부터 top개만 남기고 나머지는 '(그 외)'로 묶는다.
    """
    rows = []
    for col in columns:
        if col not in orig.columns or col not in red.columns:
            continue
        o_cnt = orig[col].astype(str).value_counts()
        o_ratio = o_cnt / o_cnt.sum()
        r_sum = pd.Series(weights, index=red[col].astype(str).to_numpy()).groupby(level=0).sum()
        r_cnt = red[col].astype(str).value_counts()
        r_ratio = r_sum / r_sum.sum()
        head = list(o_ratio.head(top).index)
        for value in head:
            rows.append({"column": col, "value": value,
                         "orig_rows": int(o_cnt.get(value, 0)),
                         "orig_ratio": float(o_ratio.get(value, 0.0)),
                         "reduced_rows": int(r_cnt.get(value, 0)),
                         "reduced_ratio": float(r_ratio.get(value, 0.0))})
        rest = [v for v in o_ratio.index if v not in head]
        if rest:
            rows.append({"column": col, "value": f"(그 외 {len(rest):,}종)",
                         "orig_rows": int(o_cnt[rest].sum()),
                         "orig_ratio": float(o_ratio[rest].sum()),
                         "reduced_rows": int(r_cnt.reindex(rest).fillna(0).sum()),
                         "reduced_ratio": float(r_ratio.reindex(rest).fillna(0).sum())})
    table = pd.DataFrame(rows)
    if not table.empty:
        table["gap_pp"] = (table["reduced_ratio"] - table["orig_ratio"]) * 100
    return table


def grouped_similarity(orig: pd.DataFrame, red: pd.DataFrame, reduction, columns: list[str],
                       combos: list[list[str]] | None = None) -> dict:
    """범주형 데이터 종합 점수. 컬럼 비율·조합 비율·단위 크기를 1/3씩 본다."""
    combos = combos or [reduction.strata_cols]
    w = reduction.weights
    col_score, col_detail = column_scores(orig, red, columns, w)
    combo_score, combo_detail = combo_scores(orig, red, combos, w)
    size = unit_size_score(orig, red, reduction.unit_cols, reduction.strata_cols)
    total = (col_score + combo_score + size["score"]) / 3
    return {
        "total": round(total, 1), "columns": col_score, "combos": combo_score,
        "unit_size": size["score"],
        "detail": {"columns": col_detail, "combos": combo_detail, "unit_size": size,
                   "units_total": reduction.units_total, "units_kept": reduction.units_kept,
                   "strata_total": reduction.strata_total, "notes": reduction.notes},
    }
