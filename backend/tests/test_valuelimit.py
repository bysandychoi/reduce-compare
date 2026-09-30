"""컬럼 값 종류 줄이기 테스트."""
import numpy as np
import pandas as pd
import pytest

from app.core.valuelimit import choose_values, limit_values, parse_limits


def _frame():
    # A 50%, B 25%, C 15%, D 7%, E 3%
    values = ["A"] * 500 + ["B"] * 250 + ["C"] * 150 + ["D"] * 70 + ["E"] * 30
    return pd.DataFrame({"eqp": values, "row": range(len(values))})


def test_parse_limits():
    assert parse_limits("eqp_id=6, mask_id=50") == {"eqp_id": 6, "mask_id": 50}
    assert parse_limits(None) == {}
    with pytest.raises(ValueError, match="형식"):
        parse_limits("eqp_id")
    with pytest.raises(ValueError, match="숫자"):
        parse_limits("eqp_id=여섯")


def test_top_mode_picks_most_frequent():
    df = _frame()
    assert choose_values(df["eqp"], 3) == ["A", "B", "C"]


def test_keep_n_larger_than_levels():
    df = _frame()
    assert set(choose_values(df["eqp"], 99)) == set("ABCDE")


def test_relative_ratio_is_preserved():
    df = _frame()
    out, infos = limit_values(df, {"eqp": 3})
    info = infos[0]
    assert info.levels_before == 5 and info.levels_after == 3
    assert info.rows_after == 900 and info.row_coverage == 0.9
    # 남은 값끼리의 비율은 원본 비율의 상대 관계 그대로 (A:B:C = 500:250:150)
    ratio = out["eqp"].value_counts(normalize=True)
    assert abs(ratio["A"] - 500 / 900) < 1e-9
    assert abs(ratio["B"] - 250 / 900) < 1e-9
    assert [k["value"] for k in info.kept] == ["A", "B", "C"]


def test_sample_mode_returns_requested_count():
    df = _frame()
    picked = choose_values(df["eqp"], 3, mode="sample", seed=1)
    assert len(set(picked)) == 3
    assert set(picked) <= set("ABCDE")


def test_multiple_columns():
    df = _frame()
    df["mask"] = np.where(df["row"] % 2 == 0, "M1", np.where(df["row"] % 3 == 0, "M2", "M3"))
    out, infos = limit_values(df, {"eqp": 2, "mask": 1})
    assert [i.column for i in infos] == ["eqp", "mask"]
    assert out["eqp"].nunique() == 2 and out["mask"].nunique() == 1


def test_errors():
    df = _frame()
    with pytest.raises(ValueError, match="없는 컬럼"):
        limit_values(df, {"없음": 2})
    with pytest.raises(ValueError, match="1 이상"):
        limit_values(df, {"eqp": 0})
    with pytest.raises(ValueError, match="모르는 방식"):
        choose_values(df["eqp"], 2, mode="wrong")
