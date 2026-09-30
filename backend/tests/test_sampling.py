"""축소기 테스트 (T035): 랜덤·층화·군집 공통 규칙."""
import numpy as np
import pandas as pd
import pytest

from app.core.clustering import cluster_reduce, detect_outliers, virtual_rows
from app.core.sampling import choose_stratify_column, random_sample, stratified_sample
from app.core.schema import classify_column

ROWS = 4000


def _data(seed=0):
    rng = np.random.default_rng(seed)
    centers = np.array([[0, 0], [6, 6], [-5, 4]])
    pick = rng.choice(3, ROWS, p=[0.7, 0.25, 0.05])
    x = centers[pick] + rng.normal(0, 0.7, (ROWS, 2))
    df = pd.DataFrame({
        "group": ["A", "B", "C"][0:1] * 0 + [["A", "B", "C"][p] for p in pick],
        "v1": x[:, 0], "v2": x[:, 1],
    })
    return x, df


def _columns(df):
    return [classify_column(df[c], c) for c in df.columns]


def test_random_sample_is_reproducible():
    a = random_sample(ROWS, 200, seed=1)
    b = random_sample(ROWS, 200, seed=1)
    c = random_sample(ROWS, 200, seed=2)
    assert a.size == 200
    assert np.array_equal(a.indices, b.indices)
    assert not np.array_equal(a.indices, c.indices)
    assert abs(a.weights.sum() - ROWS) < 1e-6      # 가중치 합 = 원본 행 수


def test_size_larger_than_data_is_capped():
    r = random_sample(50, 500)
    assert r.size == 50


def test_zero_size_rejected():
    with pytest.raises(ValueError):
        random_sample(100, 0)


def test_stratified_keeps_ratio():
    _x, df = _data()
    r = stratified_sample(df, 300, "group", seed=0)
    orig = df["group"].value_counts(normalize=True)
    got = df.iloc[r.indices]["group"].value_counts(normalize=True)
    for level in orig.index:
        assert abs(orig[level] - got[level]) < 0.01      # 1%p 이내
    assert r.size == 300
    assert abs(r.weights.sum() - len(df)) < 1e-6


def test_choose_stratify_column_picks_categorical():
    _x, df = _data()
    cols = _columns(df)
    assert choose_stratify_column(df, cols, ["group", "v1", "v2"]) == "group"
    assert choose_stratify_column(df, cols, ["v1", "v2"]) is None   # 범주형이 없으면 없음


def test_cluster_reduce_keeps_weights_and_min_guarantee():
    x, _df = _data()
    r = cluster_reduce(x, 300, seed=0, min_per_cluster=30)
    assert r.size >= 300                                    # 최소 보장으로 조금 커질 수 있다
    assert r.weights.sum() + r.excluded == ROWS             # 모든 행이 어딘가에 속한다
    assert len(np.unique(r.indices)) == len(r.indices)      # 대표 행은 중복되지 않는다
    assert all(len(m) > 0 for m in r.members)


def test_cluster_reduce_excludes_outliers():
    x, _df = _data()
    x = np.vstack([x, np.array([[60.0, 60.0], [-70.0, 55.0]])])
    r = cluster_reduce(x, 200, seed=0)
    assert r.excluded >= 1
    far = {len(x) - 1, len(x) - 2}
    assert not far & set(r.indices.tolist())                # 극단값은 대표로 뽑히지 않는다


def test_detect_outliers_ratio():
    x, _df = _data()
    mask = detect_outliers(x, seed=0, ratio=0.01)
    assert 0 < mask.sum() <= ROWS * 0.02


def test_virtual_rows_average_and_mode():
    x, df = _data()
    r = cluster_reduce(x, 200, seed=0, virtual=True)
    rows = virtual_rows(df, r)
    assert len(rows) == r.size
    assert list(rows.columns) == list(df.columns)
    assert rows["group"].isin(["A", "B", "C"]).all()        # 범주형은 최빈값
    assert abs(rows["v1"].mean() - df["v1"].mean()) < 0.5   # 수치형은 평균
