"""컬럼 타입 추정과 파일 그룹핑 (T022 스키마 추출, T023 그룹핑, T028 기본 선택값)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from app.core.ingest import CsvFile, read_csv

NUMERIC = "numeric"
CATEGORICAL = "categorical"
DATETIME = "datetime"
IDENTIFIER = "identifier"
TEXT = "text"
CONSTANT = "constant"

# 축소 기준 컬럼에서 기본으로 빼는 타입
EXCLUDED_BY_DEFAULT = (DATETIME, IDENTIFIER, TEXT, CONSTANT)
SAMPLE_ROWS = 5000
# 값 종류가 이보다 많은 문자열 컬럼은 범주형이 아니라 자유 텍스트로 본다
MAX_CATEGORY_LEVELS = 200
# 결측이 이 비율을 넘는 컬럼은 기준 컬럼 기본 선택에서 뺀다 (다 빼면 남는 행이 없어진다)
MAX_MISSING_RATIO = 0.5


@dataclass
class ColumnInfo:
    name: str
    kind: str
    dtype: str
    unique_ratio: float
    missing_ratio: float
    reason: str = ""          # 기본 선택에서 빠진 이유
    selected: bool = True     # 축소 기준 컬럼 기본값 (T028)


@dataclass
class FileSchema:
    file: CsvFile
    columns: list[ColumnInfo]
    encoding: str
    rows_sampled: int

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.columns]


@dataclass
class SchemaGroup:
    """컬럼 구조가 같은 파일 묶음."""

    key: tuple[str, ...]
    files: list[CsvFile] = field(default_factory=list)
    columns: list[ColumnInfo] = field(default_factory=list)
    merge: bool = True        # 사용자가 '파일별'로 바꿀 수 있다

    @property
    def label(self) -> str:
        return f"{len(self.files)}개 파일 · {len(self.columns)}열"


ID_NAME = re.compile(r"(^|_)(id|no|num|code|key|seq|번호|코드)(_|$)", re.IGNORECASE)


def _looks_like_id(s: pd.Series, name: str, unique_ratio: float) -> bool:
    """숫자 컬럼이 ID인지 판단한다. 값이 모두 달라도 금액·점수일 수 있으므로
    이름이 ID처럼 보이거나 값이 거의 연속된 정수일 때만 ID로 본다."""
    if unique_ratio <= 0.98 or not pd.api.types.is_integer_dtype(s):
        return False
    if ID_NAME.search(name):
        return True
    values = s.dropna().sort_values().to_numpy()
    if len(values) < 3:
        return False
    return bool((pd.Series(values).diff().dropna() == 1).mean() >= 0.9)


def _looks_datetime(s: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(s):
        return True
    # pandas 3.0에서는 문자열 컬럼 dtype이 object가 아니라 str이다
    if not (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
        return False
    sample = s.dropna().astype(str).head(200)
    if sample.empty:
        return False
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    return parsed.notna().mean() >= 0.9


def classify_column(s: pd.Series, name: str) -> ColumnInfo:
    """컬럼 하나의 타입을 추정한다."""
    n = len(s)
    non_null = s.dropna()
    unique_ratio = (non_null.nunique() / len(non_null)) if len(non_null) else 0.0
    missing_ratio = 1 - (len(non_null) / n) if n else 0.0
    dtype = str(s.dtype)

    if len(non_null) and non_null.nunique() == 1:
        kind = CONSTANT
    elif _looks_datetime(s):
        kind = DATETIME
    elif pd.api.types.is_bool_dtype(s):
        kind = CATEGORICAL
    elif pd.api.types.is_numeric_dtype(s):
        kind = IDENTIFIER if _looks_like_id(s, name, unique_ratio) else NUMERIC
    elif (ID_NAME.search(name) and non_null.nunique() >= 20) or (
        unique_ratio > 0.9 and non_null.astype(str).str.len().mean() <= 40
    ):
        kind = IDENTIFIER
    elif non_null.astype(str).str.len().mean() > 40 or non_null.nunique() > MAX_CATEGORY_LEVELS:
        kind = TEXT
    else:
        kind = CATEGORICAL

    info = ColumnInfo(name=name, kind=kind, dtype=dtype,
                      unique_ratio=round(unique_ratio, 4), missing_ratio=round(missing_ratio, 4))
    if missing_ratio > MAX_MISSING_RATIO:
        info.selected = False
        info.reason = f"결측 {missing_ratio * 100:.0f}%"
    elif kind in EXCLUDED_BY_DEFAULT:
        info.selected = False
        info.reason = {
            DATETIME: "날짜로 보임", IDENTIFIER: "ID로 보임",
            TEXT: "자유 텍스트로 보임", CONSTANT: "값이 한 가지뿐",
        }[kind]
    return info


def extract_schema(file: CsvFile, sample_rows: int = SAMPLE_ROWS) -> FileSchema:
    """파일 앞부분을 표본으로 읽어 컬럼 타입을 추정한다 (T022)."""
    df, enc = read_csv(file.path, nrows=sample_rows)
    cols = [classify_column(df[c], str(c)) for c in df.columns]
    return FileSchema(file=file, columns=cols, encoding=enc, rows_sampled=len(df))


def group_by_schema(schemas: list[FileSchema]) -> list[SchemaGroup]:
    """컬럼 이름과 순서가 같은 파일끼리 묶는다 (T023)."""
    groups: dict[tuple[str, ...], SchemaGroup] = {}
    for sc in schemas:
        key = tuple(sc.names)
        g = groups.get(key)
        if g is None:
            g = SchemaGroup(key=key, columns=sc.columns)
            groups[key] = g
        g.files.append(sc.file)
    ordered = sorted(groups.values(), key=lambda g: (-len(g.files), g.key))
    for g in ordered:
        g.merge = len(g.files) > 1
    return ordered


def default_selection(columns: list[ColumnInfo]) -> list[str]:
    """축소 기준 컬럼 기본값 (T028). ID·날짜·텍스트·상수 컬럼은 빠진다."""
    return [c.name for c in columns if c.selected]
