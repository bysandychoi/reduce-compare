"""병합·전처리·특징 행렬 테스트 (T024~T027)."""
import numpy as np
import pandas as pd
import pytest

from app.core.ingest import CsvFile
from app.core.prepare import (
    SOURCE_COL,
    build_features,
    drop_missing_rows,
    merge_group,
    prepare_group,
)
from app.core.schema import classify_column

ROWS = 120


def _frame(seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "region": rng.choice(["수도권", "영남", "호남"], ROWS),
        "income": rng.normal(4000, 800, ROWS).round(0),
        "visits": rng.integers(0, 30, ROWS),
        "memo": ["긴 메모 " * 12] * ROWS,
    })


def _columns(df):
    return [classify_column(df[c], c) for c in df.columns]


def test_merge_group_row_count(tmp_path):
    files = []
    for i in range(3):
        p = tmp_path / f"f{i}.csv"
        _frame(i).to_csv(p, index=False)
        files.append(CsvFile(str(p), p.name, p.stat().st_size))
    merged = merge_group(files)
    assert len(merged) == ROWS * 3
    assert set(merged[SOURCE_COL]) == {"f0.csv", "f1.csv", "f2.csv"}


def test_merge_group_empty():
    with pytest.raises(ValueError):
        merge_group([])


def test_drop_missing_rows_counts():
    df = _frame()
    df.loc[:9, "income"] = None
    clean, dropped = drop_missing_rows(df, ["region", "income"])
    assert dropped == 10
    assert len(clean) == ROWS - 10
    assert clean["income"].notna().all()


def test_features_shape_and_order():
    df = _frame()
    cols = _columns(df)
    matrix, names, _ = build_features(df, cols, ["region", "income", "visits"])
    assert matrix.shape[0] == ROWS                 # 행 순서·개수 보존
    assert matrix.shape[1] == 3 + 2                # 수치 2 + 범주 3수준
    assert "income" in names and any(n.startswith("region=") for n in names)
    assert abs(matrix[:, names.index("income")].mean()) < 1e-9   # 표준화됨


def test_features_high_cardinality_uses_frequency():
    df = pd.DataFrame({"code": [f"C{i % 50}" for i in range(ROWS)], "v": range(ROWS)})
    cols = _columns(df)
    cols[0].kind = "categorical"
    _matrix, names, _ = build_features(df, cols, ["code", "v"])
    assert "code#freq" in names


def test_features_needs_a_usable_column():
    df = pd.DataFrame({"same": [1] * ROWS})
    with pytest.raises(ValueError, match="계산에 쓸 수 있는"):
        build_features(df, _columns(df), ["same"])


def test_prepare_group_end_to_end():
    df = _frame()
    df.loc[:4, "income"] = None
    cols = _columns(df)
    res = prepare_group(df, cols)                   # 기본 선택: memo 제외
    assert res.used_columns == ["region", "income", "visits"]
    assert res.dropped_missing == 5
    assert res.features.shape[0] == ROWS - 5
    assert len(res.frame) == ROWS - 5
    assert any("결측" in n for n in res.notes)


def test_prepare_group_rejects_unknown_column():
    df = _frame()
    with pytest.raises(ValueError, match="데이터에 없는"):
        prepare_group(df, _columns(df), ["없는컬럼"])


def test_prepare_group_rejects_empty_selection():
    df = _frame()
    with pytest.raises(ValueError, match="1개 이상"):
        prepare_group(df, _columns(df), [])
