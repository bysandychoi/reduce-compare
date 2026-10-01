"""업로드부터 완료 결과까지 공개 API 통합 흐름 테스트 (T121)."""
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import jobs, runs
from app.main import app

client = TestClient(app)


def _dataset() -> bytes:
    header = b"kind,value,related\n"
    rows = (f"{index % 4},{index},{index * 2 + index % 3}\n".encode() for index in range(80))
    return header + b"".join(rows)


def _wait_for_completion(job_id: str, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}/status")
        assert response.status_code == 200
        payload = response.json()
        if payload["state"] in {"done", "failed"}:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"작업이 {timeout}초 안에 완료되지 않았습니다")


def test_run_state_io_retries_transient_file_locks(tmp_path, monkeypatch):
    path = tmp_path / "run.json"
    original_replace = Path.replace
    replace_attempts = 0

    def locked_once(source, target):
        nonlocal replace_attempts
        replace_attempts += 1
        if replace_attempts == 1:
            raise PermissionError("reader lock")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", locked_once)
    runs._write_json(path, {"state": "done", "progress": 100, "stage": "완료"})
    monkeypatch.setattr(Path, "replace", original_replace)

    original_read = Path.read_text
    read_attempts = 0

    def locked_read(target, *args, **kwargs):
        nonlocal read_attempts
        read_attempts += 1
        if read_attempts == 1:
            raise PermissionError("writer lock")
        return original_read(target, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", locked_read)
    state = runs.read_run_status(tmp_path, "a" * 32)
    assert (replace_attempts, read_attempts) == (2, 2)
    assert (state.state, state.progress, state.stage) == ("done", 100, "완료")


def test_upload_run_and_result_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    created = client.post(
        "/jobs", files={"files": ("data.csv", _dataset(), "text/csv")}
    )
    assert created.status_code == 201
    job_id = created.json()["job_id"]
    assert created.json()["files"] == ["data.csv"]

    groups = client.get(f"/jobs/{job_id}/groups")
    assert groups.status_code == 200
    assert groups.json()["groups"][0]["files"] == ["data.csv"]
    columns_url = f"/jobs/{job_id}/groups/group-1/columns"
    assert client.get(columns_url).status_code == 200
    selected = client.put(columns_url, json={"selected": ["kind", "value"]})
    assert selected.status_code == 200
    assert [item["name"] for item in selected.json()["columns"] if item["selected"]] == [
        "kind", "value",
    ]
    decision = client.put(
        f"/jobs/{job_id}/groups",
        json={"groups": [{"group_id": "group-1", "merge": True}]},
    )
    assert decision.status_code == 200

    idle = client.get(f"/jobs/{job_id}/status")
    assert (idle.status_code, idle.json()["state"]) == (200, "idle")
    assert client.get(f"/jobs/{job_id}/result").status_code == 409
    started = client.post(f"/jobs/{job_id}/run", json={"target": 0, "seed": 7})
    assert started.status_code == 202

    final_status = _wait_for_completion(job_id)
    assert final_status == {
        "job_id": job_id, "state": "done", "progress": 100,
        "stage": "완료", "error": None,
    }
    result = client.get(f"/jobs/{job_id}/result")
    assert result.status_code == 200
    payload = result.json()
    assert payload["folder"] == "uploads"
    assert payload["skipped"] == []
    assert len(payload["groups"]) == 1
    group = payload["groups"][0]
    assert (group["name"], group["files"], group["original_rows"]) == (
        "A", ["data.csv"], 80,
    )
    assert 1 <= group["reduced_rows"] <= group["prepared_rows"] <= 80
    assert group["reduction_method"] in {
        "cluster_actual", "cluster_mean", "stratified", "random",
    }
    assert group["size_curve"] and group["method_scores"]
    assert group["projection"]["method"] == "pca"
    assert group["projection"]["dimensions"] == 2
    assert str(tmp_path) not in result.text
