"""컬럼별 박스플롯 비교 API 테스트 (T094)."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api import jobs, runs
from app.api.boxplots import weighted_quantiles
from app.main import app
from tests.test_distributions import _write_job

client = TestClient(app)


PROBS = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)


@pytest.mark.parametrize("values,weights", [
    ([1.0, 2.0, 3.0, 10.0], [1, 5, 1, 1]),
    ([10.0, 90.0], [99, 1]),                      # 대표 하나가 거의 전부를 대표하는 경우
    ([4.0, 1.0, 3.0, 2.0, 5.0], [1, 1, 1, 1, 1]),  # 가중치가 모두 1이면 일반 분위수
    ([5.0, 5.0, 5.0], [2, 3, 4]),                 # 값이 모두 같은 경우
    ([1.0, 2.0], [1, 1]),
])
def test_weighted_quantiles_match_expanded_values(values, weights):
    """가중치 분위수는 그만큼 행을 늘려 놓고 센 것과 같아야 한다 (inverted_cdf 정의)."""
    values, weights = np.array(values), np.array(weights, dtype=float)
    expanded = np.repeat(values, weights.astype(int))

    got = weighted_quantiles(values, weights, PROBS)
    expected = [float(np.percentile(expanded, prob * 100, method="inverted_cdf"))
                for prob in PROBS]

    for prob, left, right in zip(PROBS, got, expected):
        assert abs(left - right) < 1e-9, f"p={prob}: {left} != {right}"


def test_weighted_quantiles_follow_heavy_representative(tmp_path, monkeypatch):
    """대표 행 하나가 원본 99행을 대표하면 상자가 그 값에 붙어야 한다."""
    job_id = _write_job(tmp_path, monkeypatch, weights=[99.0, 1.0], tag="f")
    box = client.get(f"/jobs/{job_id}/boxplot", params={"group": "A"}).json()["reduced"]

    # 축소본 값은 [10, 90], 가중치 [99, 1] -> 늘리면 10이 99개라 Q1·중앙·Q3가 모두 10이다.
    assert box["q1"] == box["median"] == box["q3"] == 10.0


def test_boxplot_returns_both_sides_with_same_columns(tmp_path, monkeypatch):
    job_id = _write_job(tmp_path, monkeypatch)
    response = client.get(f"/jobs/{job_id}/boxplot", params={"group": "A"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["column"] == "price"
    assert payload["columns"] == ["price"]
    for side in ("original", "reduced"):
        box = payload[side]
        assert box["minimum"] <= box["q1"] <= box["median"] <= box["q3"] <= box["maximum"]
        assert box["low_whisker"] >= box["minimum"]
        assert box["high_whisker"] <= box["maximum"]
    assert payload["original"]["rows"] == 100
    assert payload["reduced"]["rows"] == 2


def test_boxplot_applies_representative_weights(tmp_path, monkeypatch):
    """가중치가 큰 쪽으로 축소본 중앙값이 끌려가야 한다."""
    light = _write_job(tmp_path, monkeypatch, weights=[1.0, 1.0], tag="d")
    heavy = _write_job(tmp_path, monkeypatch, weights=[99.0, 1.0], tag="e")

    balanced = client.get(f"/jobs/{light}/boxplot", params={"group": "A"}).json()
    skewed = client.get(f"/jobs/{heavy}/boxplot", params={"group": "A"}).json()

    assert balanced["weighted"] is True and skewed["weighted"] is True
    # 축소본 값은 [10, 90]. 가중치가 반반이면 Q3는 90이지만, 10 쪽에 99배로 쏠리면
    # 대표하는 100행 중 99행이 10이라 Q3도 10이다.
    assert balanced["reduced"]["q3"] == 90.0
    assert skewed["reduced"]["q3"] == 10.0


def test_boxplot_marks_outliers_outside_whiskers(tmp_path, monkeypatch):
    """1.5×IQR 밖의 값은 수염이 아니라 이상치로 나와야 한다."""
    values = [float(value) for value in range(50)] + [500.0]
    job_id = _write_job(
        tmp_path, monkeypatch, original_values=values, original_labels=["x"] * len(values),
        reduced_values=[10.0, 40.0],
    )
    payload = client.get(f"/jobs/{job_id}/boxplot", params={"group": "A"}).json()

    original = payload["original"]
    assert 500.0 in original["outliers"]
    assert original["high_whisker"] < 500.0
    assert original["maximum"] == 500.0
    assert original["outlier_count"] == 1


def test_weighted_quantiles_ignore_weight_scale():
    """실제 축소(random·stratified)는 '원본/남긴 행' 비율이라 가중치가 소수이고 크다.

    원본은 가중치가 모두 1이므로, 크기에 따라 결과가 달라지면 같은 분포인데도
    두 상자가 다르게 그려진다. 나누어떨어지지 않는 배수에서 누적합이 0.4999…가
    되어 경계에서 한 칸 밀리던 적이 있다.
    """
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    base = np.array([1.0, 2.0, 1.0, 3.0, 1.0])
    expected = weighted_quantiles(values, base, PROBS)

    rng = np.random.default_rng(3)
    factors = [0.25, 1.0, 18.2, 1000.0, 1000 / 12, 7 / 3]
    factors += list(rng.uniform(0.01, 500, 300))
    for factor in factors:
        assert weighted_quantiles(values, base * factor, PROBS) == expected, \
            f"가중치 {factor}배에서 달라졌다"


def test_weighted_quantiles_match_unweighted_for_uniform_weights():
    """대표 행마다 같은 수의 원본 행을 대표하면 가중치 1일 때와 같아야 한다.

    `random_sample`이 만드는 `원본 행 수 / 대표 수` 모양을 본다. 대표 수가 커질수록
    누적합의 오차가 쌓이므로, 작은 범위만 보면 여유를 1e-14까지 줄여도 통과해 버린다.
    """
    # size_candidates가 실제로 만드는 크기까지 본다 (MAX_SIZE 50,000).
    # eps=1e-13 회귀는 (total=99991, kept=50000)에서만 잡히므로 둘을 유지한다.
    sizes = list(range(2, 1001)) + [1500, 2236, 6300, 17748, 50000]
    mismatched = []
    for total in (1000.0, 4096.0, 99991.0, 500000.0):
        for kept in sizes:
            if kept > total:
                continue
            values = np.arange(kept, dtype=float)
            uniform = np.full(kept, total / kept)
            if weighted_quantiles(values, uniform, PROBS) != \
                    weighted_quantiles(values, np.ones(kept), PROBS):
                mismatched.append((int(total), kept))

    assert mismatched == [], f"{len(mismatched)}건이 가중치 1일 때와 달라졌다: {mismatched[:5]}"


@pytest.mark.parametrize("below,above", [
    (24995.0, 75005.0),        # 10만 행 — 여유가 1e-4면 틀린다
    (249995.0, 750005.0),      # 100만 행 — 여유가 5e-6만 돼도 틀린다
])
def test_weighted_quantiles_respect_narrow_boundary(below, above):
    """경계 비교의 여유가 너무 크면 바로 아래 구간을 잘못 고른다.

    10이 24,995행 / 400이 75,005행이면 25% 지점은 10이 아니라 400이다.
    행이 많아질수록 경계가 25%에 더 가까워져 허용 여유의 상한을 좁힌다.
    """
    values = np.array([10.0, 400.0])
    weights = np.array([below, above])

    assert weighted_quantiles(values, weights, (0.25,)) == [400.0]


def test_weighted_quantiles_handle_fractional_weights():
    """소수 가중치도 비율이 같은 정수 가중치와 같은 결과여야 한다."""
    values = np.array([1.0, 2.0, 3.0])

    assert weighted_quantiles(values, np.array([0.5, 1.5, 1.0]), PROBS) == \
        weighted_quantiles(values, np.array([1.0, 3.0, 2.0]), PROBS)


def test_boxplot_uses_one_and_a_half_iqr_fence(tmp_path, monkeypatch):
    """1.5×IQR 밖이면 이상치다 — 3×IQR처럼 느슨해지면 이 값이 수염 안으로 들어온다."""
    # 0~99 균등: Q1=24.75, Q3=74.25, IQR=49.5 -> 1.5배 울타리 148.1, 3배 울타리 222.8
    values = [float(index) for index in range(100)] + [180.0]
    job_id = _write_job(
        tmp_path, monkeypatch, original_values=values, original_labels=["x"] * len(values),
        reduced_values=[10.0, 90.0], tag="1",
    )
    box = client.get(f"/jobs/{job_id}/boxplot", params={"group": "A"}).json()["original"]

    assert box["outliers"] == [180.0], "1.5×IQR 밖의 값이 이상치로 잡히지 않았다"
    assert box["high_whisker"] == 99.0


def test_boxplot_keeps_outliers_from_both_ends(tmp_path, monkeypatch):
    """이상치를 자를 때 한쪽 끝만 남기면 반대쪽 꼬리가 통째로 사라진다."""
    low = [float(-5000 - index) for index in range(60)]
    high = [float(5000 + index) for index in range(60)]
    values = [float(index) for index in range(1000)] + low + high
    job_id = _write_job(
        tmp_path, monkeypatch, original_values=values, original_labels=["x"] * len(values),
        reduced_values=[100.0, 900.0], tag="2",
    )
    box = client.get(f"/jobs/{job_id}/boxplot", params={"group": "A"}).json()["original"]

    assert len(box["outliers"]) == 40
    assert min(box["outliers"]) < 0, "아래쪽 이상치가 빠졌다"
    assert max(box["outliers"]) > 1000, "위쪽 이상치가 빠졌다"


def test_boxplot_limits_outlier_points(tmp_path, monkeypatch):
    """이상치가 많아도 보내는 점 수는 제한하되 전체 개수는 그대로 알린다."""
    # 1000개는 0~999에 고르게, 100개만 멀리 떨어뜨려 1.5×IQR 밖으로 보낸다.
    values = ([float(index) for index in range(1000)]
              + [float(10000 + index) for index in range(100)])
    job_id = _write_job(
        tmp_path, monkeypatch, original_values=values, original_labels=["x"] * len(values),
        reduced_values=[0.0, 1000.0],
    )
    payload = client.get(f"/jobs/{job_id}/boxplot", params={"group": "A"}).json()

    original = payload["original"]
    assert original["outlier_count"] == 100
    assert len(original["outliers"]) == 40
    assert original["outliers"] == sorted(original["outliers"])


def test_boxplot_reports_unknown_and_non_numeric_columns(tmp_path, monkeypatch):
    job_id = _write_job(tmp_path, monkeypatch)

    assert client.get(
        f"/jobs/{job_id}/boxplot", params={"group": "A", "column": "없는컬럼"}
    ).status_code == 404
    assert client.get(
        f"/jobs/{job_id}/boxplot", params={"group": "A", "column": "label"}
    ).status_code == 422
    assert client.get(f"/jobs/{job_id}/boxplot", params={"group": "없는그룹"}).status_code == 404


def test_boxplot_matches_real_pipeline_output(tmp_path, monkeypatch):
    """실제 파이프라인 산출물로 가중치와 컬럼 목록이 맞물리는지 확인한다."""
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    rows = b"kind,seq,related,bucket\n" + b"".join(
        f"{'' if index % 8 == 0 else f'k{index % 3}'},{index},{index * 2},{index % 17}\n".encode()
        for index in range(160)
    )
    job_id = client.post("/jobs", files={"files": ("data.csv", rows, "text/csv")}).json()["job_id"]
    client.post(f"/jobs/{job_id}/run", json={"target": 0})
    runs.RUNS[job_id].result(timeout=60)

    result = client.get(f"/jobs/{job_id}/result").json()["groups"][0]
    payload = client.get(
        f"/jobs/{job_id}/boxplot", params={"group": result["name"]}
    ).json()

    assert payload["weighted"] is True
    assert payload["original"]["rows"] == result["prepared_rows"]
    assert payload["reduced"]["rows"] == result["reduced_rows"]
    assert "seq" not in payload["columns"]
    assert payload["original"]["q1"] <= payload["original"]["median"] <= payload["original"]["q3"]
