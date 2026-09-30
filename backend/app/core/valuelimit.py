"""컬럼의 값 종류를 줄인다 (예: eqp_id 60개 → 6개).

단위 축소(grouped.py)보다 먼저 적용한다. 남길 값을 고르는 방법은 두 가지다.
  top    : 원본에서 많이 나온 순서대로 N개 (기본)
  sample : 원본 비율을 확률로 삼아 N개를 무작위로 (특정 값에 치우치지 않게 하고 싶을 때)
남기지 않은 값의 행은 버린다. 남은 값들끼리의 비율은 원본 비율 그대로다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class LimitInfo:
    """값 종류를 줄인 결과 요약."""

    column: str
    levels_before: int
    levels_after: int
    rows_before: int
    rows_after: int
    kept: list[dict] = field(default_factory=list)   # 값별 원본 비율·남긴 뒤 비율

    @property
    def row_coverage(self) -> float:
        return self.rows_after / self.rows_before if self.rows_before else 0.0


def parse_limits(text: str | None) -> dict[str, int]:
    """'eqp_id=6,mask_id=50' 형태를 딕셔너리로 바꾼다."""
    out: dict[str, int] = {}
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"형식이 잘못됐습니다: '{part}' (예: eqp_id=6)")
        col, num = part.split("=", 1)
        try:
            out[col.strip()] = int(num)
        except ValueError as e:
            raise ValueError(f"개수는 숫자여야 합니다: '{part}'") from e
    return out


def choose_values(series: pd.Series, keep_n: int, mode: str = "top",
                  seed: int = 0) -> list[str]:
    """남길 값을 고른다."""
    counts = series.astype(str).value_counts()
    if keep_n >= len(counts):
        return list(counts.index)
    if mode == "top":
        return list(counts.head(keep_n).index)
    if mode == "sample":
        rng = np.random.default_rng(seed)
        probs = (counts / counts.sum()).to_numpy()
        picked = rng.choice(counts.index.to_numpy(), keep_n, replace=False, p=probs)
        return list(picked)
    raise ValueError(f"모르는 방식입니다: {mode} (top 또는 sample)")


def limit_values(df: pd.DataFrame, limits: dict[str, int], mode: str = "top",
                 seed: int = 0) -> tuple[pd.DataFrame, list[LimitInfo]]:
    """지정한 컬럼들의 값 종류를 줄이고, 줄인 내용을 함께 돌려준다."""
    missing = [c for c in limits if c not in df.columns]
    if missing:
        raise ValueError(f"데이터에 없는 컬럼입니다: {', '.join(missing)}")
    out, infos = df, []
    for col, keep_n in limits.items():
        if keep_n < 1:
            raise ValueError(f"{col}: 남길 개수는 1 이상이어야 합니다")
        before_rows, before_levels = len(out), out[col].nunique()
        values = choose_values(out[col], keep_n, mode, seed)
        orig_ratio = out[col].astype(str).value_counts(normalize=True)
        out = out[out[col].astype(str).isin(values)].reset_index(drop=True)
        after_ratio = out[col].astype(str).value_counts(normalize=True)
        kept = [{"value": v, "orig_ratio": round(float(orig_ratio.get(v, 0.0)), 6),
                 "ratio_after_limit": round(float(after_ratio.get(v, 0.0)), 6),
                 "rows": int((out[col].astype(str) == v).sum())} for v in values]
        infos.append(LimitInfo(column=col, levels_before=before_levels,
                               levels_after=out[col].nunique(), rows_before=before_rows,
                               rows_after=len(out), kept=kept))
        if out.empty:
            raise ValueError(f"{col}의 값을 {keep_n}개로 줄이니 남는 행이 없습니다")
    return out, infos


def limit_summary(info: LimitInfo) -> str:
    """사람이 읽을 한 줄 요약."""
    return (f"{info.column}: 값 {info.levels_before:,}종 → {info.levels_after:,}종, "
            f"행 {info.rows_before:,} → {info.rows_after:,} "
            f"({info.row_coverage * 100:.1f}% 유지)")
