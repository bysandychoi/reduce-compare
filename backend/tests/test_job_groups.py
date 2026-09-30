"""Job schema-group API tests."""

from fastapi.testclient import TestClient

from app.api import jobs
from app.main import app

client = TestClient(app)


def create_grouped_job(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    response = client.post(
        "/jobs",
        files=[
            ("files", ("a.csv", b"x,y\n1,A\n2,B\n", "text/csv")),
            ("files", ("nested/b.csv", b"x,y\n3,A\n4,B\n", "text/csv")),
            ("files", ("c.csv", b"z\n10\n20\n", "text/csv")),
        ],
    )
    return response.json()["job_id"]


def test_get_groups_detects_matching_schemas(tmp_path, monkeypatch):
    job_id = create_grouped_job(tmp_path, monkeypatch)
    response = client.get(f"/jobs/{job_id}/groups")

    assert response.status_code == 200
    groups = response.json()["groups"]
    assert [group["group_id"] for group in groups] == ["group-1", "group-2"]
    assert groups[0]["files"] == ["a.csv", "nested/b.csv"]
    assert groups[0]["merge"] is True
    assert [column["name"] for column in groups[0]["columns"]] == ["x", "y"]
    assert groups[1]["files"] == ["c.csv"]
    assert groups[1]["merge"] is False


def test_put_groups_persists_decisions(tmp_path, monkeypatch):
    job_id = create_grouped_job(tmp_path, monkeypatch)
    payload = {
        "groups": [
            {"group_id": "group-1", "merge": False},
            {"group_id": "group-2", "merge": True},
        ]
    }
    response = client.put(f"/jobs/{job_id}/groups", json=payload)

    assert response.status_code == 200
    assert [group["merge"] for group in response.json()["groups"]] == [False, True]
    repeated = client.get(f"/jobs/{job_id}/groups")
    assert [group["merge"] for group in repeated.json()["groups"]] == [False, True]


def test_put_rejects_incomplete_update_without_overwrite(tmp_path, monkeypatch):
    job_id = create_grouped_job(tmp_path, monkeypatch)
    response = client.put(
        f"/jobs/{job_id}/groups",
        json={"groups": [{"group_id": "group-1", "merge": False}]},
    )
    assert response.status_code == 422
    assert not (tmp_path / job_id / "groups.json").exists()


def test_groups_reject_missing_job(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    response = client.get(f"/jobs/{'0' * 32}/groups")
    assert response.status_code == 404


def test_groups_reject_job_without_tabular_files(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    job_id = "a" * 32
    uploads = tmp_path / job_id / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "readme.txt").write_text("not a table", encoding="utf-8")
    response = client.get(f"/jobs/{job_id}/groups")
    assert response.status_code == 422
