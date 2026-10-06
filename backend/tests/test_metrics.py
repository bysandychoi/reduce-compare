"""유사도 지표 테스트 (T046): 분포·상관·구조·종합 점수."""
import numpy as np
import pandas as pd
import pytest

from app.core.metrics import (
    categorical_metrics,
    correlation_metrics,
    distribution_metrics,
    numeric_metrics,
)
from app.core.schema import classify_column
from app.core.structure import (
    COVERAGE_SUBSAMPLE,
    TRUST_SUBSAMPLE,
    coverage_metrics,
    overall_score,
    trustworthiness_score,
)

ROWS = 2000


def _frame(seed=0):
    rng = np.random.default_rng(seed)
    a = rng.normal(100, 15, ROWS)
    return pd.DataFrame({
        "a": a,
        "b": a * 0.8 + rng.normal(0, 5, ROWS),     # a와 강한 상관
        "c": rng.normal(50, 10, ROWS),             # 상관 없음
        "g": rng.choice(["x", "y", "z"], ROWS, p=[0.6, 0.3, 0.1]),
    })


def _columns(df):
    return [classify_column(df[c], c) for c in df.columns]


def test_identical_data_scores_full():
    df = _frame()
    w = np.ones(len(df))
    m = numeric_metrics(df["a"], df["a"], w)
    assert m.detail["ks"] == 0
    assert m.score == 100
    c = categorical_metrics(df["g"], df["g"], w)
    assert c.detail["js_divergence"] == 0
    assert c.score == 100


def test_shifted_distribution_scores_lower():
    df = _frame()
    w = np.ones(len(df))
    same = numeric_metrics(df["a"], df["a"], w).score
    shifted = numeric_metrics(df["a"], df["a"] + 40, w).score
    assert shifted < same - 20


def test_weights_are_used():
    df = _frame()
    red = df.head(200).copy()
    heavy = np.where(red["g"] == "x", 10.0, 1.0)
    flat = np.ones(len(red))
    a = categorical_metrics(df["g"], red["g"], flat).detail["max_ratio_gap"]
    b = categorical_metrics(df["g"], red["g"], heavy).detail["max_ratio_gap"]
    assert a != b            # 가중치가 비율 계산에 반영된다


def test_distribution_metrics_covers_all_columns():
    df = _frame()
    cols = _columns(df)
    score, per_col = distribution_metrics(df, df, cols, ["a", "b", "c", "g"], np.ones(len(df)))
    assert score == 100
    assert [m.name for m in per_col] == ["a", "b", "c", "g"]


def test_correlation_identical_and_broken():
    df = _frame()
    cols = _columns(df)
    same = correlation_metrics(df, df, cols, ["a", "b", "c"])
    assert same["score"] == 100
    assert abs(same["frobenius"]) < 1e-9

    broken = df.copy()
    broken["b"] = np.random.default_rng(1).normal(80, 12, ROWS)   # 상관을 깨뜨린다
    worse = correlation_metrics(df, broken, cols, ["a", "b", "c"])
    assert worse["score"] < same["score"] - 20
    assert worse["max_gap"] > 0.5


def test_correlation_needs_two_numeric_columns():
    df = _frame()
    out = correlation_metrics(df, df, _columns(df), ["a"])
    assert out["score"] == 100 and "수치형" in out["note"]


def test_trustworthiness_range():
    rng = np.random.default_rng(0)
    x = np.hstack([rng.normal(0, 1, (800, 2)), rng.normal(0, 0.05, (800, 6))])
    t = trustworthiness_score(x, seed=0)
    assert 0.8 <= t <= 1.0          # 사실상 2차원 데이터는 투영해도 이웃이 잘 지켜진다


@pytest.mark.parametrize("rows", [100, TRUST_SUBSAMPLE + 10])
def test_trustworthiness_respects_subsample_limit(monkeypatch, rows):
    seen = []

    def record_sample(original, projected, n_neighbors):
        seen.append(len(original))
        return 0.9

    monkeypatch.setattr("app.core.structure.trustworthiness", record_sample)
    x = np.random.default_rng(2).normal(size=(rows, 3))

    assert trustworthiness_score(x, seed=5) == 0.9
    assert seen == [min(rows, TRUST_SUBSAMPLE)]


def test_coverage_closer_is_better():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, (3000, 4))
    near = coverage_metrics(x, x[rng.choice(3000, 600, replace=False)])
    far = coverage_metrics(x, rng.normal(6, 0.2, (600, 4)))
    assert near["score"] > far["score"] + 20
    assert near["mean_distance"] < far["mean_distance"]


@pytest.mark.parametrize("rows", [1000, COVERAGE_SUBSAMPLE + 10])
def test_coverage_respects_subsample_limit(rows):
    rng = np.random.default_rng(3)
    original = rng.normal(size=(rows, 3))
    reduced = original[:100]

    result = coverage_metrics(original, reduced, seed=4)

    assert result["sampled"] == min(rows, COVERAGE_SUBSAMPLE)


def test_coverage_needs_points():
    with pytest.raises(ValueError):
        coverage_metrics(np.zeros((10, 2)), np.zeros((0, 2)))


def test_overall_score_is_equal_weighted():
    s = overall_score(90, 60, 30)
    assert s.total == 60.0
    assert (s.distribution, s.correlation, s.structure) == (90.0, 60.0, 30.0)


def test_overall_score_rejects_out_of_range():
    with pytest.raises(ValueError):
        overall_score(120, 50, 50)
