"""컬럼 타입 추정·그룹핑·기본 선택값 테스트 (T022, T023, T028)."""
import pandas as pd

from app.core.ingest import CsvFile
from app.core.schema import (
    CATEGORICAL,
    CONSTANT,
    DATETIME,
    IDENTIFIER,
    NUMERIC,
    TEXT,
    FileSchema,
    classify_column,
    default_selection,
    extract_schema,
    group_by_schema,
)

ROWS = 300


def _frame():
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=ROWS).astype(str),
        "store_id": [f"S{i:05d}" for i in range(ROWS)],
        "region": ["수도권", "영남", "호남"] * (ROWS // 3),
        "income": [3000 + i * 7 for i in range(ROWS)],
        "flag": [True, False] * (ROWS // 2),
        "memo": ["긴 메모 " * 10 + str(i) for i in range(ROWS)],
        "fixed": ["같은값"] * ROWS,
    })


def test_classify_kinds():
    df = _frame()
    kinds = {c: classify_column(df[c], c).kind for c in df.columns}
    assert kinds["date"] == DATETIME
    assert kinds["store_id"] == IDENTIFIER
    assert kinds["region"] == CATEGORICAL
    assert kinds["income"] == NUMERIC
    assert kinds["flag"] == CATEGORICAL
    assert kinds["memo"] == TEXT
    assert kinds["fixed"] == CONSTANT


def test_default_selection_excludes_id_date_text():
    df = _frame()
    cols = [classify_column(df[c], c) for c in df.columns]
    assert default_selection(cols) == ["region", "income", "flag"]
    reasons = {c.name: c.reason for c in cols if not c.selected}
    assert reasons == {"date": "날짜로 보임", "store_id": "ID로 보임",
                       "memo": "자유 텍스트로 보임", "fixed": "값이 한 가지뿐"}


def test_numeric_id_detection():
    seq = pd.Series(range(1, ROWS + 1))                      # 1,2,3... → ID
    amount = pd.Series([3000 + i * 7 for i in range(ROWS)])  # 값은 모두 다르지만 금액
    assert classify_column(seq, "row_id").kind == IDENTIFIER
    assert classify_column(seq, "그냥이름").kind == IDENTIFIER
    assert classify_column(amount, "spend").kind == NUMERIC
    assert classify_column(amount, "order_no").kind == IDENTIFIER   # 이름이 ID처럼 보이면 ID


def test_string_id_name_and_high_cardinality():
    stores = pd.Series([f"S{i % 400:03d}" for i in range(ROWS * 10)])
    products = pd.Series([f"상품 {i % 900}" for i in range(ROWS * 10)])
    assert classify_column(stores, "store_id").kind == IDENTIFIER      # 이름이 ID
    assert classify_column(products, "product").kind == TEXT           # 값 종류가 너무 많음
    assert classify_column(pd.Series(["A", "B", "C"] * ROWS), "grade").kind == CATEGORICAL


def test_missing_ratio(tmp_path):
    df = _frame()
    df.loc[:29, "income"] = None
    info = classify_column(df["income"], "income")
    assert abs(info.missing_ratio - 0.1) < 0.01


def test_extract_schema(tmp_path):
    path = tmp_path / "s.csv"
    _frame().to_csv(path, index=False)
    sc = extract_schema(CsvFile(str(path), "s.csv", path.stat().st_size))
    assert sc.names == ["date", "store_id", "region", "income", "flag", "memo", "fixed"]
    assert sc.rows_sampled == ROWS


def _schema(name, columns):
    return FileSchema(file=CsvFile(f"/tmp/{name}", name, 1),
                      columns=[classify_column(pd.Series([1, 2, 3]), c) for c in columns],
                      encoding="utf-8", rows_sampled=3)


def test_group_same_and_different_schema():
    groups = group_by_schema([
        _schema("a.csv", ["x", "y"]), _schema("b.csv", ["x", "y"]),
        _schema("c.csv", ["p", "q", "r"]),
    ])
    assert len(groups) == 2
    assert [f.name for f in groups[0].files] == ["a.csv", "b.csv"]
    assert groups[0].merge is True          # 같은 구조 → 병합
    assert groups[1].merge is False         # 혼자면 파일별
    assert groups[1].key == ("p", "q", "r")
