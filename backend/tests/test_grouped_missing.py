"""그룹 단위 축소의 결측 층 범주 처리 테스트 (T068)."""
import numpy as np
import pandas as pd

from app.core.grouped import (
    MISSING_CATEGORY,
    SEP,
    combo_key,
    stratified_units,
    stratum_report,
)


def _missing_strata_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "unit": [f"u{index}" for index in range(8)],
        "region": pd.Series(pd.Categorical([
            "north", "north", np.nan, None, pd.NA, "south", "south", "south",
        ])),
        "plan": ["basic", "basic", "plus", "plus", "plus", "basic", "basic", "basic"],
    })


def test_combo_key_maps_all_missing_values_to_one_category():
    frame = pd.DataFrame({
        "left": ["A", np.nan, None, pd.NA],
        "right": [1, 2, 2, 2],
    })

    keys = combo_key(frame, ["left", "right"])

    assert keys.tolist() == [
        f"A{SEP}1", f"{MISSING_CATEGORY}{SEP}2",
        f"{MISSING_CATEGORY}{SEP}2", f"{MISSING_CATEGORY}{SEP}2",
    ]
    assert keys.map(type).eq(str).all()


def test_missing_stratum_is_sampled_weighted_and_reported():
    frame = _missing_strata_frame()

    reduction = stratified_units(
        frame, ["unit"], ["region", "plan"], ratio=0.5, min_units=1, seed=7,
    )
    rows = reduction.rows(frame)
    original_keys = combo_key(frame, ["region", "plan"])
    reduced_keys = combo_key(rows, ["region", "plan"])
    weighted = pd.Series(reduction.weights).groupby(reduced_keys.to_numpy()).sum()
    original = original_keys.value_counts()

    assert reduction.strata_total == 3
    assert np.isfinite(reduction.weights).all()
    assert np.allclose(weighted.to_numpy(), original[weighted.index].to_numpy())
    missing_key = f"{MISSING_CATEGORY}{SEP}plus"
    assert original[missing_key] == 3
    assert missing_key in weighted.index

    report = stratum_report(frame, reduction)
    assert missing_key in report.index
    assert report.loc[missing_key, "units_orig"] == 3
    assert report.loc[missing_key, "units_red"] >= 1
