"""병합과 전처리 (T024 병합, T025 결측 행 제외, T026 기준 컬럼, T027 특징 행렬)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.ingest import CsvFile, read_csv
from app.core.schema import CATEGORICAL, NUMERIC, ColumnInfo

SOURCE_COL = "_source_file"
ONEHOT_MAX_CARDINALITY = 20


@dataclass
class PrepareResult:
    """전처리 결과와 그 과정에서 생긴 정보."""

    frame: pd.DataFrame                     # 결측 행을 제외한 원본 (모든 컬럼 유지)
    features: np.ndarray                    # 축소·지표 계산용 행렬 (행 순서 보존)
    feature_names: list[str] = field(default_factory=list)
    used_columns: list[str] = field(default_factory=list)
    dropped_missing: int = 0
    notes: list[str] = field(default_factory=list)


def merge_group(files: list[CsvFile], add_source: bool = True) -> pd.DataFrame:
    """같은 구조의 파일들을 하나로 합친다 (T024). 출처 파일명을 컬럼으로 남긴다."""
    if not files:
        raise ValueError("합칠 파일이 없습니다")
    frames = []
    for f in files:
        df, _ = read_csv(f.path)
        if add_source:
            df[SOURCE_COL] = f.name
        frames.append(df)
    merged = pd.concat(frames, ignore_index=True)
    return merged


def drop_missing_rows(df: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, int]:
    """기준 컬럼에 결측이 있는 행을 제외한다 (T025). (남은 데이터, 제외 건수)."""
    cols = [c for c in columns if c in df.columns]
    if not cols:
        return df.reset_index(drop=True), 0
    mask = df[cols].notna().all(axis=1)
    return df[mask].reset_index(drop=True), int((~mask).sum())


def missing_report(df: pd.DataFrame, columns: list[str]) -> list[tuple[str, float]]:
    """기준 컬럼별 결측 비율을 큰 순서로 돌려준다."""
    cols = [c for c in columns if c in df.columns]
    ratios = [(c, float(df[c].isna().mean())) for c in cols]
    return sorted(ratios, key=lambda kv: -kv[1])


def missing_reason(df: pd.DataFrame, columns: list[str]) -> str:
    """남는 행이 0일 때, 어떤 컬럼 때문인지 알려주는 메시지를 만든다."""
    worst = [f"{c} {r * 100:.0f}%" for c, r in missing_report(df, columns)[:5] if r > 0]
    detail = ", ".join(worst) if worst else "여러 컬럼에 결측이 흩어져 있음"
    return ("결측을 제외하니 남는 행이 없습니다. 결측이 많은 컬럼: " + detail +
            "\n  → 해당 컬럼을 빼고 다시 실행하세요 (--exclude <컬럼>) "
            "또는 --max-missing 0.2 처럼 기준을 낮춰 자동으로 빼세요")


def resolve_columns(columns: list[ColumnInfo], selected: list[str] | None) -> list[str]:
    """사용자가 고른 축소 기준 컬럼을 확정한다 (T026). 비어 있으면 오류."""
    known = {c.name for c in columns}
    if selected is None:
        chosen = [c.name for c in columns if c.selected]
    else:
        unknown = [c for c in selected if c not in known]
        if unknown:
            raise ValueError(f"데이터에 없는 컬럼입니다: {', '.join(unknown)}")
        chosen = list(selected)
    if not chosen:
        raise ValueError("축소 기준 컬럼을 1개 이상 선택해야 합니다")
    return chosen


def _encode_categorical(s: pd.Series, name: str) -> tuple[np.ndarray, list[str]]:
    """저카디널리티는 원-핫, 고카디널리티는 빈도 인코딩."""
    values = s.astype(str)
    levels = values.value_counts()
    if len(levels) <= ONEHOT_MAX_CARDINALITY:
        cols, names = [], []
        for level in levels.index:
            cols.append((values == level).to_numpy(dtype=float))
            names.append(f"{name}={level}")
        return np.column_stack(cols), names
    freq = values.map(levels / len(values)).to_numpy(dtype=float)
    return freq.reshape(-1, 1), [f"{name}#freq"]


def build_features(df: pd.DataFrame, columns: list[ColumnInfo],
                   selected: list[str]) -> tuple[np.ndarray, list[str], list[str]]:
    """축소·지표 계산용 행렬을 만든다 (T027). 행 순서는 그대로 둔다."""
    kinds = {c.name: c.kind for c in columns}
    blocks: list[np.ndarray] = []
    names: list[str] = []
    notes: list[str] = []
    for name in selected:
        s = df[name]
        kind = kinds.get(name, NUMERIC if pd.api.types.is_numeric_dtype(s) else CATEGORICAL)
        if kind == NUMERIC or pd.api.types.is_numeric_dtype(s):
            values = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
            std = np.nanstd(values)
            if std == 0 or np.isnan(std):
                notes.append(f"{name}: 값이 모두 같아 계산에서 제외")
                continue
            blocks.append(((values - np.nanmean(values)) / std).reshape(-1, 1))
            names.append(name)
        else:
            block, block_names = _encode_categorical(s, name)
            blocks.append(block)
            names.extend(block_names)
    if not blocks:
        raise ValueError("계산에 쓸 수 있는 컬럼이 없습니다 (모두 상수이거나 변환 실패)")
    matrix = np.column_stack(blocks)
    return np.nan_to_num(matrix, nan=0.0), names, notes


def prepare_group(df: pd.DataFrame, columns: list[ColumnInfo],
                  selected: list[str] | None = None) -> PrepareResult:
    """병합된 데이터에 전처리를 한 번에 적용한다 (T025~T027)."""
    used = resolve_columns(columns, selected)
    clean, dropped = drop_missing_rows(df, used)
    if clean.empty:
        raise ValueError(missing_reason(df, used))
    matrix, names, notes = build_features(clean, columns, used)
    if dropped:
        notes.append(f"결측이 있는 행 {dropped:,}건 제외")
    return PrepareResult(frame=clean, features=matrix, feature_names=names,
                         used_columns=used, dropped_missing=dropped, notes=notes)
