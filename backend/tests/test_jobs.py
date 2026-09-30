"""Upload-backed job creation API tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import jobs
from app.main import app

client = TestClient(app)


def test_create_job_saves_multiple_files(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    response = client.post(
        "/jobs",
        files=[
            ("files", ("north/a.csv", b"x,y\n1,2\n", "text/csv")),
            ("files", ("south/b.tsv", b"x\ty\n3\t4\n", "text/tab-separated-values")),
            ("files", ("notes.md", b"ignore", "text/markdown")),
        ],
    )

    assert response.status_code == 201
    body = response.json()
    assert body["files"] == ["north/a.csv", "south/b.tsv"]
    upload_dir = tmp_path / body["job_id"] / "uploads"
    assert (upload_dir / "north/a.csv").read_bytes() == b"x,y\n1,2\n"
    assert (upload_dir / "south/b.tsv").read_bytes() == b"x\ty\n3\t4\n"


def test_create_job_rejects_unsupported_only(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    response = client.post("/jobs", files={"files": ("readme.md", b"text", "text/plain")})
    assert response.status_code == 400
    assert list(tmp_path.iterdir()) == []


def test_create_job_rejects_unsafe_path(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    response = client.post("/jobs", files={"files": ("../secret.csv", b"x\n1", "text/csv")})
    assert response.status_code == 400
    assert list(tmp_path.iterdir()) == []


def test_create_job_rejects_duplicate_path(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    response = client.post(
        "/jobs",
        files=[
            ("files", ("same.csv", b"x\n1", "text/csv")),
            ("files", ("same.csv", b"x\n2", "text/csv")),
        ],
    )
    assert response.status_code == 409
    assert list(tmp_path.iterdir()) == []


def test_job_id_is_unique(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    first = client.post("/jobs", files={"files": ("a.csv", b"x\n1", "text/csv")})
    second = client.post("/jobs", files={"files": ("a.csv", b"x\n1", "text/csv")})
    assert first.json()["job_id"] != second.json()["job_id"]
    assert all(Path(tmp_path / response.json()["job_id"]).is_dir() for response in (first, second))
