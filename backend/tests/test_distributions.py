"""컬럼별 분포 비교 API 테스트 (T093)."""
import json

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.api import jobs, runs
from app.main import app

client = TestClient(app)


def _write_job(tmp_path, monkeypatch, weights=None, reduced_values=None,
               original_values=None, original_labels=None, tag="b"):
    """원본 CSV·축소본 CSV·결과 JSON이 갖춰진 완료 작업을 만든다."""
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    job_id = tag * 32
    directory = tmp_path / job_id
    directory.mkdir()

    uploads = directory / "uploads"
    uploads.mkdir()
    prices = (original_values if original_values is not None
              else [float(value) for value in range(100)])
    labels = (original_labels if original_labels is not None
              else ["x" if index % 2 else "y" for index in range(len(prices))])
    pd.DataFrame({"price": prices, "label": labels}).to_csv(
        uploads / "source.csv", index=False, encoding="utf-8-sig",
    )

    reduced_dir = directory / "reduced"
    reduced_dir.mkdir()
    values = reduced_values if reduced_values is not None else [10.0, 90.0]
    pd.DataFrame({"price": values, "label": ["x"] * len(values)}).to_csv(
        reduced_dir / "group-1.csv", index=False, encoding="utf-8-sig",
    )

    if weights is not None:
        projection_dir = directory / "projection-source"
        projection_dir.mkdir()
        np.savez_compressed(
            projection_dir / "group-1.npz",
            original=np.zeros((2, 2)), reduced=np.zeros((2, 2)),
            weights=np.asarray(weights, dtype=float),
        )

    group = {
        "name": "A", "files": ["source.csv"], "original_rows": len(prices),
        "prepared_rows": len(prices), "reduced_rows": len(values),
        "reduction_method": "cluster_actual",
        "score": {"total": 90, "distribution": 90, "correlation": 90, "structure": 90},
        "size_curve": [], "method_scores": [],
        "projection": {
            "method": "pca", "dimensions": 2, "original": [[0.0, 0.0]],
            "reduced": [[0.0, 0.0]], "original_indices": [0],
        },
        "detail": {"columns": [
            {"name": "price", "kind": "numeric"}, {"name": "label", "kind": "categorical"},
        ]},
    }
    (directory / "run.json").write_text(
        json.dumps({"state": "done", "progress": 100, "stage": "완료"}), encoding="utf-8",
    )
    (directory / "result.json").write_text(
        json.dumps({"folder": "uploads", "target": 85, "groups": [group], "skipped": []}),
        encoding="utf-8",
    )
    return job_id


def test_histogram_shares_edges_and_normalizes_both_sides(tmp_path, monkeypatch):
    job_id = _write_job(tmp_path, monkeypatch)
    response = client.get(f"/jobs/{job_id}/histogram", params={"group": "A", "bins": 10})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["column"] == "price"
    assert payload["columns"] == ["price"]
    assert len(payload["edges"]) == 11
    assert len(payload["original_ratios"]) == len(payload["reduced_ratios"]) == 10
    assert sum(payload["original_ratios"]) == 1.0
    assert sum(payload["reduced_ratios"]) == 1.0
    assert payload["original_rows"] == 100
    assert payload["reduced_rows"] == 2


def test_histogram_applies_representative_weights(tmp_path, monkeypatch):
    """대표 행 하나가 원본 여러 행을 대표하면 그 구간 비율이 커져야 한다."""
    job_id = _write_job(tmp_path, monkeypatch, weights=[90.0, 10.0])
    response = client.get(f"/jobs/{job_id}/histogram", params={"group": "A", "bins": 10})

    payload = response.json()
    edges = np.asarray(payload["edges"])
    heavy = int(np.clip(np.searchsorted(edges, 10.0, side="right") - 1, 0, len(edges) - 2))
    light = int(np.clip(np.searchsorted(edges, 90.0, side="right") - 1, 0, len(edges) - 2))
    assert payload["reduced_ratios"][heavy] == 0.9
    assert payload["reduced_ratios"][light] == 0.1


def test_histogram_rejects_categorical_column(tmp_path, monkeypatch):
    job_id = _write_job(tmp_path, monkeypatch)
    response = client.get(
        f"/jobs/{job_id}/histogram", params={"group": "A", "column": "label"}
    )

    assert response.status_code == 422
    assert "수치형" in response.json()["detail"]


def test_histogram_reports_unknown_group(tmp_path, monkeypatch):
    job_id = _write_job(tmp_path, monkeypatch)
    response = client.get(f"/jobs/{job_id}/histogram", params={"group": "없는그룹"})

    assert response.status_code == 404


def test_histogram_handles_constant_column(tmp_path, monkeypatch):
    """원본과 축소본 값이 모두 같으면 구간 폭이 0이 되지 않게 넓혀야 한다."""
    job_id = _write_job(
        tmp_path, monkeypatch, original_values=[5.0] * 20, reduced_values=[5.0, 5.0],
    )
    response = client.get(f"/jobs/{job_id}/histogram", params={"group": "A", "bins": 8})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["edges"][0] < payload["edges"][-1]
    assert sum(payload["original_ratios"]) == 1.0
    assert sum(payload["reduced_ratios"]) == 1.0


def test_histogram_ignores_infinite_values(tmp_path, monkeypatch):
    """무한대가 섞여도 구간 경계가 NaN이 되지 않고 제외 건수를 알려야 한다."""
    job_id = _write_job(
        tmp_path, monkeypatch,
        original_values=[float(value) for value in range(50)] + [float("inf")],
        reduced_values=[10.0, 40.0],
    )
    response = client.get(f"/jobs/{job_id}/histogram", params={"group": "A", "bins": 6})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert all(value is not None for value in payload["edges"])
    assert payload["edges"][-1] == 49.0
    assert payload["dropped_values"] == 1
    assert payload["original_rows"] == 50
    assert min(payload["original_ratios"]) >= 0


def test_histogram_excludes_rows_dropped_before_reduction(tmp_path, monkeypatch):
    """축소 때 결측으로 빠진 행은 원본 분포에도 들어가면 안 된다."""
    job_id = _write_job(
        tmp_path, monkeypatch,
        original_values=[float(value) for value in range(100)] + [100000.0],
        original_labels=["x"] * 100 + [None],
        reduced_values=[10.0, 90.0],
    )
    response = client.get(f"/jobs/{job_id}/histogram", params={"group": "A", "bins": 10})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["original_rows"] == 100
    assert payload["edges"][-1] == 99.0


def test_histogram_rejects_range_too_wide_for_bins(tmp_path, monkeypatch):
    """값이 모두 유한해도 폭이 너무 크면 구간 경계가 무너지므로 422로 막는다."""
    job_id = _write_job(
        tmp_path, monkeypatch,
        original_values=[-1e308, 0.0, 1e308], original_labels=["x"] * 3,
        reduced_values=[0.0, 1e308],
    )
    response = client.get(f"/jobs/{job_id}/histogram", params={"group": "A", "bins": 10})

    assert response.status_code == 422
    assert "구간을 만들 수 없습니다" in response.json()["detail"]


def test_histogram_reports_missing_weights(tmp_path, monkeypatch):
    """가중치가 저장되지 않은 예전 작업은 그 사실을 응답에 밝혀야 한다."""
    job_id = _write_job(tmp_path, monkeypatch)
    payload = client.get(f"/jobs/{job_id}/histogram", params={"group": "A"}).json()

    assert payload["weighted"] is False

    weighted_id = _write_job(tmp_path, monkeypatch, weights=[90.0, 10.0], tag="c")
    payload = client.get(f"/jobs/{weighted_id}/histogram", params={"group": "A"}).json()

    assert payload["weighted"] is True


def test_histogram_matches_real_pipeline_output(tmp_path, monkeypatch):
    """결측이 섞인 실제 파이프라인 산출물로 가중치·행 수·컬럼 목록이 맞물리는지 확인한다.

    결측 행 20건은 축소 전에 빠지므로 원본 분포에도 들어가면 안 된다. 기준 컬럼에서
    빠진 컬럼(일련번호성 seq)은 비교 대상이 아니므로 선택 목록에도 없어야 한다.
    """
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    lines = []
    for index in range(160):
        # 20건은 범주형 기준 컬럼이 비어 있어 축소 전에 제외된다.
        kind = "" if index % 8 == 0 else f"k{index % 3}"
        lines.append(f"{kind},{index},{index * 2},{index % 17}\n".encode())
    rows = b"kind,seq,related,bucket\n" + b"".join(lines)
    job_id = client.post("/jobs", files={"files": ("data.csv", rows, "text/csv")}).json()["job_id"]
    client.post(f"/jobs/{job_id}/run", json={"target": 0})
    runs.RUNS[job_id].result(timeout=60)

    result = client.get(f"/jobs/{job_id}/result").json()["groups"][0]
    compared = [item["name"] for item in result["detail"]["columns"] if item["kind"] == "numeric"]
    assert result["original_rows"] == 160
    assert result["prepared_rows"] == 140, "기준 컬럼이 빈 20행은 축소 전에 빠져야 한다"

    response = client.get(
        f"/jobs/{job_id}/histogram", params={"group": result["name"], "column": compared[0]}
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["weighted"] is True, "실제 실행에서는 대표 행 가중치가 저장돼 있어야 한다"
    assert payload["original_rows"] == 140, "축소 전에 빠진 행이 원본 분포에 다시 들어왔다"
    assert payload["dropped_values"] >= 20
    assert payload["reduced_rows"] == result["reduced_rows"]
    assert set(payload["columns"]) <= set(compared), "비교 대상이 아닌 컬럼은 고를 수 없어야 한다"
    assert abs(sum(payload["reduced_ratios"]) - 1.0) < 1e-4, "구간별 반올림 오차 범위 안이어야 한다"
