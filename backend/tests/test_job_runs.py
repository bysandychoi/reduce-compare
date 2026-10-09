"""백그라운드 축소 실행 API 테스트 (T062)."""
import json
import threading
from types import SimpleNamespace

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


def test_run_returns_before_blocked_worker_finishes(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)
    started = threading.Event()
    release = threading.Event()

    def blocked(*_args):
        started.set()
        release.wait(timeout=5)

    monkeypatch.setattr(runs, "_execute", blocked)
    response = client.post(f"/jobs/{job_id}/run", json={"target": 80})
    try:
        assert response.status_code == 202
        assert response.json() == {"job_id": job_id, "state": "queued"}
        assert started.wait(timeout=1)
        assert not release.is_set()
    finally:
        release.set()


def test_run_rejects_duplicate_while_worker_is_active(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)
    release = threading.Event()
    monkeypatch.setattr(runs, "_execute", lambda *_args: release.wait(timeout=5))
    first = client.post(f"/jobs/{job_id}/run")
    try:
        second = client.post(f"/jobs/{job_id}/run")
        assert first.status_code == 202
        assert second.status_code == 409
    finally:
        release.set()


def test_run_uses_saved_column_and_group_configuration(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)
    captured = {}

    def fake_pipeline(_folder, **options):
        captured.update(options)
        raise ValueError("stop after capture")

    monkeypatch.setattr(runs, "run_folder_pipeline", fake_pipeline)
    client.put(
        f"/jobs/{job_id}/groups/group-1/columns", json={"selected": ["value"]}
    )
    client.put(
        f"/jobs/{job_id}/groups", json={"groups": [{"group_id": "group-1", "merge": False}]}
    )
    response = client.post(f"/jobs/{job_id}/run")
    runs.RUNS[job_id].result(timeout=5)

    assert response.status_code == 202
    assert captured["selections"] == {"group-1": ["value"]}
    assert captured["merge_decisions"] == {"group-1": False}
    state = json.loads((tmp_path / job_id / "run.json").read_text(encoding="utf-8"))
    assert state["state"] == "failed"
    assert state["progress"] == 20


def test_background_run_writes_result_and_done_state(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)

    response = client.post(f"/jobs/{job_id}/run", json={"target": 0})
    runs.RUNS[job_id].result(timeout=30)

    assert response.status_code == 202
    directory = tmp_path / job_id
    state = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    assert state == {"state": "done", "progress": 100, "stage": "완료"}
    assert result["folder"] == "uploads"
    assert result["groups"][0]["original_rows"] == 80


def test_save_failure_reports_result_saving_stage(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)

    def completed(_folder, progress_callback, **_options):
        progress_callback("파이프라인 분석 완료", 1.0)
        return SimpleNamespace(folder="", groups=[])

    def fail_save(*_args):
        raise OSError("write failed")

    monkeypatch.setattr(runs, "run_folder_pipeline", completed)
    monkeypatch.setattr(runs, "_save_reduced_frames", fail_save)
    client.post(f"/jobs/{job_id}/run")
    runs.RUNS[job_id].result(timeout=5)

    state = json.loads((tmp_path / job_id / "run.json").read_text(encoding="utf-8"))
    assert state["state"] == "failed"
    assert state["progress"] == 90
    assert state["error"] == (
        "결과 저장 단계에서 실패했습니다: 입력 또는 결과 파일을 읽고 쓰지 못했습니다"
    )


def test_run_rejects_missing_job(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    response = client.post(f"/jobs/{'0' * 32}/run")
    assert response.status_code == 404
