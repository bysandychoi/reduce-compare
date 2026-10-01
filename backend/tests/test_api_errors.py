"""사용자가 조치할 수 있는 API 오류 메시지 테스트 (T066)."""
import json

import pytest
from fastapi.testclient import TestClient

from app.api import groups, jobs, runs
from app.main import app

client = TestClient(app)


def _create_job(tmp_path, monkeypatch, content: bytes = b"x,y\n1,2\n") -> str:
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    response = client.post(
        "/jobs", files={"files": ("data.csv", content, "text/csv")}
    )
    return response.json()["job_id"]


def test_empty_folder_returns_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    job_id = "a" * 32
    (tmp_path / job_id / "uploads").mkdir(parents=True)

    response = client.get(f"/jobs/{job_id}/groups")

    assert response.status_code == 422
    assert response.json()["detail"] == "읽을 수 있는 표 파일이 없습니다"


def test_malformed_csv_hides_parser_details(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch, b'x,y\n1,"unterminated\n')

    response = client.get(f"/jobs/{job_id}/groups")

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail == "CSV 형식을 해석하지 못했습니다: data.csv"
    assert "tokenizing" not in detail.lower()
    assert str(tmp_path) not in detail


def test_encoding_error_hides_codec_details(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)

    def fail_encoding(_file):
        raise UnicodeDecodeError("utf-8", b"x", 0, 1, str(tmp_path))

    monkeypatch.setattr(groups, "extract_schema", fail_encoding)
    response = client.get(f"/jobs/{job_id}/groups")

    assert response.status_code == 422
    assert response.json()["detail"] == "파일 인코딩을 읽을 수 없습니다: data.csv"
    assert str(tmp_path) not in response.json()["detail"]


@pytest.mark.parametrize("reason", ["계산할 행이 없습니다", ""])
def test_failed_run_has_stage_and_reason(tmp_path, monkeypatch, reason):
    job_id = _create_job(tmp_path, monkeypatch)

    def fail(*_args, **_kwargs):
        raise ValueError(reason)

    monkeypatch.setattr(runs, "run_folder_pipeline", fail)
    assert client.post(f"/jobs/{job_id}/run").status_code == 202
    runs.RUNS[job_id].result(timeout=5)

    status_response = client.get(f"/jobs/{job_id}/status")
    result_response = client.get(f"/jobs/{job_id}/result")
    message = status_response.json()["error"]
    expected_reason = reason or "알 수 없는 오류"
    assert message == f"축소 및 평가 단계에서 실패했습니다: {expected_reason}"
    assert result_response.status_code == 409
    assert message in result_response.json()["detail"]


def test_failed_run_hides_unexpected_exception_details(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)

    def fail(*_args, **_kwargs):
        raise RuntimeError(f"failed at {tmp_path / 'private.csv'}")

    monkeypatch.setattr(runs, "run_folder_pipeline", fail)
    client.post(f"/jobs/{job_id}/run")
    runs.RUNS[job_id].result(timeout=5)

    message = client.get(f"/jobs/{job_id}/status").json()["error"]
    assert message == "축소 및 평가 단계에서 실패했습니다: 내부 처리 오류가 발생했습니다"
    assert str(tmp_path) not in message


def test_failed_run_redacts_path_from_validation_error(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)

    def fail(*_args, **_kwargs):
        raise ValueError(f"읽기 실패: {tmp_path / 'private.csv'}")

    monkeypatch.setattr(runs, "run_folder_pipeline", fail)
    client.post(f"/jobs/{job_id}/run")
    runs.RUNS[job_id].result(timeout=5)

    message = client.get(f"/jobs/{job_id}/status").json()["error"]
    assert message == "축소 및 평가 단계에서 실패했습니다: 읽기 실패: <로컬 경로>"
    assert str(tmp_path) not in message


@pytest.mark.parametrize(
    "state", ["{broken", json.dumps({"state": "done", "progress": 101, "stage": "완료"})]
)
def test_corrupt_run_state_returns_controlled_error(tmp_path, monkeypatch, state):
    job_id = _create_job(tmp_path, monkeypatch)
    (tmp_path / job_id / "run.json").write_text(state, encoding="utf-8")

    for endpoint in ("status", "result"):
        response = client.get(f"/jobs/{job_id}/{endpoint}")
        assert response.status_code == 500
        assert response.json()["detail"] == "작업 상태를 읽을 수 없습니다"
