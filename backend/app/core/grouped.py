"""그룹 단위 층화 축소 (T039).

행이 서로 묶여 있는 데이터를 위한 축소기. 예를 들어 같은 lot이 여러 장비·마스크
조합을 갖는 경우, 행을 따로 뽑으면 그 조합 구조가 깨진다. 그래서 '단위'(unit)를
정해 단위째로 뽑고, '층'(strata) 조합별 비율은 원본과 같게 맞춘다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

SEP = "\x1f"        # 컬럼 값을 이어붙일 때 쓰는 구분자 (데이터에 나올 일이 없는 문자)
MISSING_CATEGORY = "(결측)"


@dataclass
class GroupedReduction:
    """단위째로 뽑은 축소 결과."""

    indices: np.ndarray              # 선택된 원본 행 위치
    weights: np.ndarray              # 행마다: 이 행이 대표하는 원본 행 수
    unit_cols: list[str]
    strata_cols: list[str]
    units_total: int = 0
    units_kept: int = 0
    strata_total: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.indices)

    def rows(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.iloc[self.indices].reset_index(drop=True)


def combo_key(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    """여러 컬럼 값을 하나의 문자열 키로 만든다."""
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"데이터에 없는 컬럼입니다: {', '.join(missing)}")
    if not columns:
        raise ValueError("컬럼을 1개 이상 지정하세요")
    selected = df[columns].astype(object)
    parts = selected.mask(selected.isna(), MISSING_CATEGORY).astype(str)
    # 행마다 join을 부르면 수만 행에서 초 단위로 느려져, 열 단위로 이어 붙인다 (결과 문자열은 같다).
    # 같은 컬럼이 두 번 들어와도 Series가 되도록 위치로 꺼낸다.
    key = parts.iloc[:, 0]
    for i in range(1, parts.shape[1]):
        key = key + SEP + parts.iloc[:, i]
    return key.rename(None)


def unit_table(df: pd.DataFrame, unit_cols: list[str], strata_cols: list[str]) -> pd.DataFrame:
    """단위별로 (층, 행 수)를 정리한 표를 만든다."""
    table = pd.DataFrame({
        "unit": combo_key(df, unit_cols).to_numpy(),
        "stratum": combo_key(df, strata_cols).to_numpy(),
    })
    grouped = table.groupby("unit", sort=False).agg(
        stratum=("stratum", "first"),
        rows=("stratum", "size"),
        mixed=("stratum", "nunique"),
    )
    return grouped.reset_index()


def _take_count(total: int, ratio: float, min_units: int) -> int:
    return int(min(total, max(min_units, round(total * ratio))))


def stratified_units(df: pd.DataFrame, unit_cols: list[str], strata_cols: list[str],
                     ratio: float, min_units: int = 1, seed: int = 0) -> GroupedReduction:
    """층 조합별 비율을 유지하며 단위를 뽑는다 (T039).

    ratio: 각 층에서 남길 단위 비율 (0~1). 드문 층도 min_units개는 남긴다.
    """
    if not 0 < ratio <= 1:
        raise ValueError("ratio는 0보다 크고 1 이하여야 합니다")
    units = unit_table(df, unit_cols, strata_cols)
    notes: list[str] = []
    mixed = int((units["mixed"] > 1).sum())
    if mixed:
        notes.append(f"단위 {mixed}개가 여러 층에 걸쳐 있어 첫 층 기준으로 묶었습니다")

    rng = np.random.default_rng(seed)
    chosen: list[str] = []
    lifted = 0
    for _stratum, block in units.groupby("stratum", sort=False):
        take = _take_count(len(block), ratio, min_units)
        if take > round(len(block) * ratio):
            lifted += 1
        picked = rng.choice(block["unit"].to_numpy(), take, replace=False)
        chosen.extend(picked.tolist())
    if lifted:
        notes.append(f"드문 층 {lifted}개는 최소 {min_units}개 단위를 남겼습니다")

    unit_of_row = combo_key(df, unit_cols).to_numpy()
    keep = np.isin(unit_of_row, np.array(chosen, dtype=object))
    indices = np.flatnonzero(keep)
    if len(indices) == 0:
        raise ValueError("남은 행이 없습니다. ratio를 키우거나 단위 컬럼을 확인하세요")

    weights = _row_weights(df, strata_cols, keep)
    return GroupedReduction(indices=indices, weights=weights, unit_cols=list(unit_cols),
                            strata_cols=list(strata_cols), units_total=len(units),
                            units_kept=len(chosen), strata_total=units["stratum"].nunique(),
                            notes=notes)


def units_by_values(df: pd.DataFrame, unit_cols: list[str], strata_cols: list[str],
                    keep: dict[str, list[str]]) -> GroupedReduction:
    """단위 컬럼 값(예: 고른 lot 100개)을 가진 행을 통째로 남긴다. 비율 축소는 하지 않는다."""
    missing = [c for c in keep if c not in unit_cols]
    if missing:
        raise ValueError(f"단위 컬럼이 아닙니다: {', '.join(missing)}")
    mask = np.ones(len(df), dtype=bool)
    for col, values in keep.items():
        mask &= df[col].astype(str).isin([str(v) for v in values]).to_numpy()
    indices = np.flatnonzero(mask)
    if len(indices) == 0:
        raise ValueError("고른 값에 해당하는 행이 없습니다")
    units = unit_table(df, unit_cols, strata_cols)
    kept = unit_table(df.iloc[indices], unit_cols, strata_cols)
    picked = ", ".join(f"{c} {len(v):,}개" for c, v in keep.items())
    notes = [f"{picked}를 골라 그 단위를 모두 남겼습니다 (--ratio 단위 축소 생략)"]
    return GroupedReduction(indices=indices, weights=_row_weights(df, strata_cols, mask),
                            unit_cols=list(unit_cols), strata_cols=list(strata_cols),
                            units_total=len(units), units_kept=len(kept),
                            strata_total=units["stratum"].nunique(), notes=notes)


def _row_weights(df: pd.DataFrame, strata_cols: list[str], keep: np.ndarray) -> np.ndarray:
    """층마다 (원본 행 수 / 남긴 행 수)를 가중치로 준다. 층별 행 비율이 그대로 복원된다."""
    stratum = combo_key(df, strata_cols).to_numpy()
    total = pd.Series(stratum).value_counts()
    kept = pd.Series(stratum[keep]).value_counts()
    factor = (total / kept).to_dict()
    return np.array([factor[s] for s in stratum[keep]], dtype=float)


def stratum_report(df: pd.DataFrame, reduction: GroupedReduction) -> pd.DataFrame:
    """층별로 원본과 축소본의 단위 수·행 수·비율을 비교한 표 (반영 리포트용)."""
    units = unit_table(df, reduction.unit_cols, reduction.strata_cols)
    kept_units = unit_table(reduction.rows(df), reduction.unit_cols, reduction.strata_cols)
    orig = units.groupby("stratum").agg(units_orig=("unit", "size"), rows_orig=("rows", "sum"))
    red = kept_units.groupby("stratum").agg(units_red=("unit", "size"), rows_red=("rows", "sum"))
    out = orig.join(red, how="left").fillna(0)
    out["unit_ratio_orig"] = out["units_orig"] / out["units_orig"].sum()
    out["unit_ratio_red"] = out["units_red"] / max(out["units_red"].sum(), 1)
    out["ratio_gap"] = (out["unit_ratio_red"] - out["unit_ratio_orig"]).abs()
    return out.sort_values("units_orig", ascending=False)
