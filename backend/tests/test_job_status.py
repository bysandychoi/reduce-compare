"""백그라운드 작업 진행 상태 API 테스트 (T063)."""
import threading

from fastapi.testclient import TestClient

from app.api import jobs, runs
from app.main import app

client = TestClient(app)


def _create_job(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    rows = b"kind,value,related\n" + b"".join(
        f"{i % 3},{i},{i * 2}\n".encode() for i in range(50)
    )
    response = client.post("/jobs", files={"files": ("data.csv", rows, "text/csv")})
    return response.json()["job_id"]


def test_status_is_idle_before_run(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)
    response = client.get(f"/jobs/{job_id}/status")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": job_id, "state": "idle", "progress": 0,
        "stage": "실행 전", "error": None,
    }


def test_status_reports_running_stage_and_failure(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)
    entered = threading.Event()
    release = threading.Event()

    def blocked(*_args, **_kwargs):
        entered.set()
        release.wait(timeout=5)
        raise ValueError("의도한 실패")

    def progressing(_folder, progress_callback, **_options):
        progress_callback("그룹 A · 크기 탐색 중", 0.4)
        return blocked()

    monkeypatch.setattr(runs, "run_folder_pipeline", progressing)
    client.post(f"/jobs/{job_id}/run")
    assert entered.wait(timeout=1)
    running = client.get(f"/jobs/{job_id}/status").json()
    assert (running["state"], running["progress"], running["stage"]) == (
        "running", 46, "그룹 A · 크기 탐색 중",
    )

    release.set()
    runs.RUNS[job_id].result(timeout=5)
    failed = client.get(f"/jobs/{job_id}/status").json()
    assert failed["state"] == "failed"
    assert failed["progress"] == 46
    assert failed["stage"] == "실패"
    assert failed["error"] == "그룹 A · 크기 탐색 중 단계에서 실패했습니다: 의도한 실패"


def test_status_rejects_missing_job(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    response = client.get(f"/jobs/{'0' * 32}/status")
    assert response.status_code == 404
