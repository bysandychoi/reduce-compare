"""완료된 축소 결과 조회 API 테스트 (T064)."""
import json

from fastapi.testclient import TestClient

from app.api import jobs, runs
from app.main import app

client = TestClient(app)


def _create_job(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    rows = b"kind,value,related\n" + b"".join(
        f"{i % 3},{i},{i * 2}\n".encode() for i in range(80)
    )
    response = client.post("/jobs", files={"files": ("data.csv", rows, "text/csv")})
    return response.json()["job_id"]


def test_result_returns_completed_pipeline_schema(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)
    client.post(f"/jobs/{job_id}/run", json={"target": 0})
    runs.RUNS[job_id].result(timeout=30)

    response = client.get(f"/jobs/{job_id}/result")

    assert response.status_code == 200
    payload = response.json()
    assert payload["folder"] == "uploads"
    assert payload["target"] == 0
    assert payload["groups"][0]["original_rows"] == 80
    assert payload["groups"][0]["size_curve"]
    assert payload["groups"][0]["method_scores"]
    assert payload["groups"][0]["projection"]["original"]


def test_result_rejects_not_started_and_failed_run(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)
    url = f"/jobs/{job_id}/result"
    assert client.get(url).status_code == 409

    directory = tmp_path / job_id
    (directory / "run.json").write_text(
        json.dumps({"state": "failed", "progress": 20, "stage": "실패", "error": "boom"}),
        encoding="utf-8",
    )
    failed = client.get(url)
    assert failed.status_code == 409
    assert "boom" in failed.json()["detail"]


def test_result_rejects_missing_or_invalid_completed_file(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)
    directory = tmp_path / job_id
    (directory / "run.json").write_text(
        json.dumps({"state": "done", "progress": 100, "stage": "완료"}), encoding="utf-8"
    )
    url = f"/jobs/{job_id}/result"
    assert client.get(url).status_code == 500

    (directory / "result.json").write_text("{}", encoding="utf-8")
    assert client.get(url).status_code == 500


def test_result_rejects_missing_job(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    assert client.get(f"/jobs/{'0' * 32}/result").status_code == 404
