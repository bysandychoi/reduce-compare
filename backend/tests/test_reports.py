"""반영 리포트 API 테스트 (T142)."""
import json

from fastapi.testclient import TestClient

from app.api import jobs
from app.main import app

client = TestClient(app)


def _job(tmp_path, monkeypatch, *, cluster=True, bad=False, bad_points=False):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    job_id = "e" * 32
    directory = tmp_path / job_id
    directory.mkdir()
    metrics = {
        "columns": ["a", "b", "constant"], "method": "pearson",
        "matrix_original": [[1, .6, 0], [.6, 1, 0], [0, 0, 0]],
        "matrix_reduced": [[1, .4, 0], [.4, 1, 0], [0, 0, 0]],
        "undefined_original": [[False, False, True], [False, False, True], [True, True, True]],
        "undefined_reduced": [[False, False, True], [False, False, True], [True, True, True]],
    }
    report = {
        "original_count": 100, "representative_count": 20, "excluded_count": 0,
        "clusters": [{"cluster_id": 0, "original_count": 100, "original_ratio": 1,
                      "representative_count": 20, "representative_ratio": 1,
                      "excluded_count": 0, "covered_count": 100, "minimum_target": 0,
                      "status": "반영", "reason": "군집 대표 선택"}],
    }
    detail = {"correlation": "broken" if bad else metrics}
    if cluster:
        detail["cluster_report"] = report
    group = {
        "name": "A", "files": ["source.csv"], "original_rows": 120,
        "prepared_rows": 100, "reduced_rows": 20,
        "reduction_method": "cluster_actual" if cluster else "random",
        "score": {"total": 90, "distribution": 90, "correlation": 90, "structure": 90},
        "size_curve": [], "method_scores": [],
        "projection": {"method": "pca", "dimensions": 2,
                       "original": [[0] if bad_points else [0, 0], [1, 1]],
                       "reduced": [[.2, .2]],
                       "original_indices": [0, 1]},
        "detail": detail,
    }
    (directory / "run.json").write_text(
        json.dumps({"state": "done", "progress": 100, "stage": "완료"}), encoding="utf-8",
    )
    (directory / "result.json").write_text(json.dumps(
        {"folder": "uploads", "target": 85, "groups": [group], "skipped": []},
    ), encoding="utf-8")
    return job_id


def test_report_returns_saved_points_clusters_and_relationships(tmp_path, monkeypatch):
    job_id = _job(tmp_path, monkeypatch)
    response = client.get(f"/jobs/{job_id}/report", params={"group": "A", "threshold": .5})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["size"] == {
        "original_rows": 120, "prepared_rows": 100, "reduced_rows": 20,
        "average_rows_per_representative": 5,
    }
    assert payload["points"]["original"] == [[0, 0], [1, 1]]
    assert payload["cluster_report"]["clusters"][0]["covered_count"] == 100
    pair = next(p for p in payload["relationships"]["pairs"]
                if p["column_a"] == "a" and p["column_b"] == "b")
    assert pair["result"] == "lost"
    assert payload["relationships"]["causal_proof"] is False
    assert any(p["undefined"] for p in payload["relationships"]["pairs"])


def test_report_builds_noncluster_summary(tmp_path, monkeypatch):
    job_id = _job(tmp_path, monkeypatch, cluster=False)
    payload = client.get(f"/jobs/{job_id}/report", params={"group": "A"}).json()
    row = payload["cluster_report"]["clusters"][0]
    assert row["reason"] == "군집 기반 축소가 아님"
    assert row["covered_count"] == row["representative_count"] == 20


def test_report_rejects_bad_result_group_and_threshold(tmp_path, monkeypatch):
    job_id = _job(tmp_path, monkeypatch, bad=True)
    assert client.get(f"/jobs/{job_id}/report", params={"group": "A"}).status_code == 422
    assert client.get(f"/jobs/{job_id}/report", params={"group": "missing"}).status_code == 404
    assert client.get(
        f"/jobs/{job_id}/report", params={"group": "A", "threshold": 2},
    ).status_code == 422


def test_report_rejects_missing_cluster_detail_and_bad_point_dimensions(tmp_path, monkeypatch):
    job_id = _job(tmp_path, monkeypatch, cluster=False)
    path = tmp_path / job_id / "result.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    result["groups"][0]["reduction_method"] = "cluster_actual"
    path.write_text(json.dumps(result), encoding="utf-8")
    assert client.get(f"/jobs/{job_id}/report", params={"group": "A"}).status_code == 422

    result["groups"][0]["reduction_method"] = "random"
    result["groups"][0]["projection"]["original"] = [[0], [1, 1]]
    path.write_text(json.dumps(result), encoding="utf-8")
    assert client.get(f"/jobs/{job_id}/report", params={"group": "A"}).status_code == 422
