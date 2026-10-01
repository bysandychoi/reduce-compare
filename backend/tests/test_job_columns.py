"""그룹별 축소 기준 컬럼 API 테스트 (T067)."""
from fastapi.testclient import TestClient

from app.api import jobs
from app.main import app

client = TestClient(app)


def _create_job(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    response = client.post(
        "/jobs",
        files=[("files", ("data.csv", b"id,value,kind\n1,10,A\n2,20,B\n3,30,A\n", "text/csv"))],
    )
    return response.json()["job_id"]


def test_get_columns_returns_types_defaults_and_reasons(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)
    response = client.get(f"/jobs/{job_id}/groups/group-1/columns")

    assert response.status_code == 200
    payload = response.json()
    assert payload["group_id"] == "group-1"
    columns = {column["name"]: column for column in payload["columns"]}
    assert columns["value"]["kind"] == "numeric"
    assert columns["value"]["default_selected"] is True
    assert columns["value"]["selected"] is True
    assert columns["id"]["default_selected"] is False
    assert columns["id"]["reason"]


def test_put_columns_persists_selection(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)
    url = f"/jobs/{job_id}/groups/group-1/columns"

    response = client.put(url, json={"selected": ["kind"]})

    assert response.status_code == 200
    selected = [column["name"] for column in response.json()["columns"] if column["selected"]]
    assert selected == ["kind"]
    repeated = client.get(url)
    assert [c["name"] for c in repeated.json()["columns"] if c["selected"]] == ["kind"]


def test_put_columns_rejects_empty_unknown_and_duplicate(tmp_path, monkeypatch):
    job_id = _create_job(tmp_path, monkeypatch)
    url = f"/jobs/{job_id}/groups/group-1/columns"

    assert client.put(url, json={"selected": []}).status_code == 400
    assert client.put(url, json={"selected": ["missing"]}).status_code == 422
    assert client.put(url, json={"selected": ["value", "value"]}).status_code == 422
    assert not (tmp_path / job_id / "column-selections" / "group-1.json").exists()


def test_columns_reject_missing_job_and_group(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    missing = client.get(f"/jobs/{'0' * 32}/groups/group-1/columns")
    assert missing.status_code == 404

    job_id = _create_job(tmp_path, monkeypatch)
    unknown = client.get(f"/jobs/{job_id}/groups/group-99/columns")
    assert unknown.status_code == 404
