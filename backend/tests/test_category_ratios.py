"""범주 비율 비교 API 테스트 (T095)."""
import json

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.api import jobs, runs
from app.main import app

client = TestClient(app)


def _write_job(tmp_path, monkeypatch, original, reduced, weights=None, tag="a"):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    job_id = tag * 32
    directory = tmp_path / job_id
    uploads, reduced_dir = directory / "uploads", directory / "reduced"
    uploads.mkdir(parents=True)
    reduced_dir.mkdir()
    pd.DataFrame({"label": original, "price": range(len(original))}).to_csv(
        uploads / "source.csv", index=False, encoding="utf-8-sig",
    )
    pd.DataFrame({"label": reduced, "price": range(len(reduced))}).to_csv(
        reduced_dir / "group-1.csv", index=False, encoding="utf-8-sig",
    )
    if weights is not None:
        projection = directory / "projection-source"
        projection.mkdir()
        np.savez_compressed(projection / "group-1.npz", weights=np.asarray(weights))
    group = {
        "name": "A", "files": ["source.csv"], "original_rows": len(original),
        "prepared_rows": len(original), "reduced_rows": len(reduced),
        "reduction_method": "random", "size_curve": [], "method_scores": [],
        "score": {"total": 90, "distribution": 90, "correlation": 90, "structure": 90},
        "projection": {"method": "pca", "dimensions": 2, "original": [[0, 0]],
                       "reduced": [[0, 0]], "original_indices": [0]},
        "detail": {"columns": [
            {"name": "label", "kind": "categorical"},
            {"name": "price", "kind": "numeric"},
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


def test_category_ratios_use_union_and_representative_weights(tmp_path, monkeypatch):
    job_id = _write_job(tmp_path, monkeypatch, ["x", "x", "y"], ["x", "z"], [1, 3])
    response = client.get(f"/jobs/{job_id}/category-ratios", params={"group": "A"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["categories"] == ["x", "y", "z"]
    assert payload["original_ratios"] == [2 / 3, 1 / 3, 0]
    assert payload["reduced_ratios"] == [.25, 0, .75]
    assert payload["weighted"] is True


def test_category_ratios_report_fallback_and_reduced_missing(tmp_path, monkeypatch):
    job_id = _write_job(tmp_path, monkeypatch, ["x", "y"], ["x", None])
    payload = client.get(f"/jobs/{job_id}/category-ratios", params={"group": "A"}).json()

    assert payload["weighted"] is False
    assert payload["reduced_rows"] == 1
    assert payload["dropped_reduced"] == 1
    assert sum(payload["reduced_ratios"]) == 1


def test_category_ratios_distinguish_column_errors(tmp_path, monkeypatch):
    job_id = _write_job(tmp_path, monkeypatch, ["x", "y"], ["x", "y"])
    numeric = client.get(
        f"/jobs/{job_id}/category-ratios", params={"group": "A", "column": "price"}
    )
    absent = client.get(
        f"/jobs/{job_id}/category-ratios", params={"group": "A", "column": "none"}
    )

    assert numeric.status_code == 422
    assert absent.status_code == 404
    assert client.get(
        f"/jobs/{job_id}/category-ratios", params={"group": "none"}
    ).status_code == 404


def test_category_ratios_report_when_no_categorical_column(tmp_path, monkeypatch):
    job_id = _write_job(tmp_path, monkeypatch, ["x", "y"], ["x", "y"])
    result_path = tmp_path / job_id / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["groups"][0]["detail"]["columns"] = [{"name": "price", "kind": "numeric"}]
    result_path.write_text(json.dumps(result), encoding="utf-8")

    response = client.get(f"/jobs/{job_id}/category-ratios", params={"group": "A"})

    assert response.status_code == 422
    assert "범주형 컬럼" in response.json()["detail"]


def test_category_ratios_match_real_pipeline_output(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    rows = b"kind,value\n" + b"".join(
        f"k{index % 3},{index % 11}\n".encode() for index in range(180)
    )
    job_id = client.post("/jobs", files={"files": ("data.csv", rows, "text/csv")}).json()["job_id"]
    client.post(f"/jobs/{job_id}/run", json={"target": 0})
    runs.RUNS[job_id].result(timeout=60)
    group = client.get(f"/jobs/{job_id}/result").json()["groups"][0]

    response = client.get(
        f"/jobs/{job_id}/category-ratios", params={"group": group["name"], "column": "kind"}
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["weighted"] is True
    assert set(payload["categories"]) == {"k0", "k1", "k2"}
    assert abs(sum(payload["original_ratios"]) - 1) < 1e-12
    assert abs(sum(payload["reduced_ratios"]) - 1) < 1e-12
