"""원본·축소본 상관 네트워크 API 테스트 (T098)."""
import json

from fastapi.testclient import TestClient

from app.api import jobs
from app.main import app

client = TestClient(app)


def _write_job(tmp_path, monkeypatch, correlation=None):
    monkeypatch.setattr(jobs, "JOB_ROOT", tmp_path)
    job_id = "d" * 32
    directory = tmp_path / job_id
    directory.mkdir()
    metrics = correlation or {
        "columns": ["a", "b", "c", "constant"], "method": "pearson",
        "matrix_original": [[1, .8, -.5, 0], [.8, 1, 0, 0], [-.5, 0, 1, 0], [0, 0, 0, 0]],
        "matrix_reduced": [[1, .4, -.7, 0], [.4, 1, .6, 0], [-.7, .6, 1, 0], [0, 0, 0, 0]],
        "undefined_original": [[False, False, False, True], [False, False, False, True],
                               [False, False, False, True], [True, True, True, True]],
        "undefined_reduced": [[False, False, False, True], [False, False, False, True],
                              [False, False, False, True], [True, True, True, True]],
    }
    group = {
        "name": "A", "files": ["source.csv"], "original_rows": 100,
        "prepared_rows": 100, "reduced_rows": 20, "reduction_method": "random",
        "score": {"total": 90, "distribution": 90, "correlation": 90, "structure": 90},
        "size_curve": [], "method_scores": [],
        "projection": {"method": "pca", "dimensions": 2, "original": [[0, 0]],
                       "reduced": [[0, 0]], "original_indices": [0]},
        "detail": {"correlation": metrics},
    }
    (directory / "run.json").write_text(
        json.dumps({"state": "done", "progress": 100, "stage": "완료"}), encoding="utf-8",
    )
    (directory / "result.json").write_text(
        json.dumps({"folder": "uploads", "target": 85, "groups": [group], "skipped": []}),
        encoding="utf-8",
    )
    return job_id


def test_networks_share_nodes_and_apply_threshold_to_both_sides(tmp_path, monkeypatch):
    job_id = _write_job(tmp_path, monkeypatch)
    response = client.get(
        f"/jobs/{job_id}/correlation-network", params={"group": "A", "threshold": .5}
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["original"]["nodes"] == payload["reduced"]["nodes"]
    assert {(e["source"], e["target"]) for e in payload["original"]["edges"]} == {
        ("a", "b"), ("a", "c"),
    }
    assert {(e["source"], e["target"]) for e in payload["reduced"]["edges"]} == {
        ("a", "c"), ("b", "c"),
    }
    assert payload["original"]["threshold"] == payload["reduced"]["threshold"] == .5


def test_networks_restore_undefined_mask_before_zero_threshold(tmp_path, monkeypatch):
    job_id = _write_job(tmp_path, monkeypatch)
    payload = client.get(
        f"/jobs/{job_id}/correlation-network", params={"group": "A", "threshold": 0}
    ).json()

    assert all("constant" not in (edge["source"], edge["target"])
               for graph in (payload["original"], payload["reduced"])
               for edge in graph["edges"])
    assert any(edge["weight"] == 0 for edge in payload["original"]["edges"])


def test_networks_reject_bad_result_threshold_and_group(tmp_path, monkeypatch):
    bad = {"columns": ["a", "b"], "method": "pearson",
           "matrix_original": [[1, .5], [.5, 1]], "matrix_reduced": [[1, .5], [.5, 1]],
           "undefined_original": [["false", "false"], ["false", "false"]],
           "undefined_reduced": [[False, False], [False, False]]}
    job_id = _write_job(tmp_path, monkeypatch, bad)

    assert client.get(
        f"/jobs/{job_id}/correlation-network", params={"group": "A"}
    ).status_code == 422
    assert client.get(
        f"/jobs/{job_id}/correlation-network", params={"group": "A", "threshold": 1.1}
    ).status_code == 422
    assert client.get(
        f"/jobs/{job_id}/correlation-network", params={"group": "missing"}
    ).status_code == 404
