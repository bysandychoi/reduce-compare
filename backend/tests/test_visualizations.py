"""대용량 투영 표본·밀도 API 테스트 (T065)."""
import json

from fastapi.testclient import TestClient

from app.api import jobs
from app.main import app

client = TestClient(app)


def _write_result(tmp_path, monkeypatch, count=100_000):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    job_id = "a" * 32
    directory = tmp_path / job_id
    directory.mkdir()
    points = [[float(i % 1000), float(i // 1000)] for i in range(count)]
    projection = {
        "method": "pca", "dimensions": 2, "original": points,
        "reduced": points[::100], "original_indices": list(range(count)),
    }
    group = {
        "name": "A", "files": ["large.csv"], "original_rows": count,
        "prepared_rows": count, "reduced_rows": len(projection["reduced"]),
        "reduction_method": "random",
        "score": {"total": 90, "distribution": 90, "correlation": 90, "structure": 90},
        "size_curve": [], "method_scores": [], "projection": projection, "detail": {},
    }
    (directory / "run.json").write_text(
        json.dumps({"state": "done", "progress": 100, "stage": "완료"}), encoding="utf-8"
    )
    (directory / "result.json").write_text(
        json.dumps({"folder": "uploads", "groups": [group], "skipped": []}), encoding="utf-8"
    )
    return job_id


def test_sample_mode_limits_points_and_keeps_indices(tmp_path, monkeypatch):
    job_id = _write_result(tmp_path, monkeypatch)
    response = client.get(
        f"/jobs/{job_id}/visualization", params={"group": "A", "max_points": 300, "seed": 7}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "sample"
    assert payload["original_rows"] == 100_000
    assert payload["original_projected"] == 100_000
    assert len(payload["original_points"]) == len(payload["original_indices"]) == 300
    assert len(payload["reduced_points"]) == 300
    assert len(response.content) < 50_000


def test_density_mode_has_bounded_grid_and_response(tmp_path, monkeypatch):
    job_id = _write_result(tmp_path, monkeypatch)
    response = client.get(
        f"/jobs/{job_id}/visualization",
        params={"group": "A", "mode": "density", "bins": 40, "max_points": 200},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["original_points"] == []
    assert payload["dimensions"] == 2
    assert len(payload["original_density"]["counts"]) == 40
    assert len(payload["original_density"]["counts"][0]) == 40
    assert sum(map(sum, payload["original_density"]["counts"])) == 100_000
    assert len(payload["reduced_points"]) == 200
    assert len(response.content) < 50_000


def test_visualization_validates_group_and_limits(tmp_path, monkeypatch):
    job_id = _write_result(tmp_path, monkeypatch, count=100)
    base = f"/jobs/{job_id}/visualization"
    assert client.get(base, params={"group": "missing"}).status_code == 404
    assert client.get(base, params={"group": "A", "max_points": 0}).status_code == 422
    assert client.get(base, params={"group": "A", "bins": 101}).status_code == 422
