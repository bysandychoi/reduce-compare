"""폴더 입력부터 축소·평가·투영까지 전체 파이프라인 테스트 (T054)."""
import numpy as np
import pandas as pd
import pytest

from app.core.pipeline import run_folder_pipeline


def _write_sample(folder, name, seed):
    rng = np.random.default_rng(seed)
    rows = 70
    base = rng.normal(size=rows)
    frame = pd.DataFrame({
        "group": rng.choice(["A", "B", "C"], rows),
        "value": base,
        "related": base * 0.8 + rng.normal(scale=0.2, size=rows),
    })
    frame.to_csv(folder / name, index=False)


def test_folder_pipeline_returns_end_to_end_group_result(tmp_path):
    _write_sample(tmp_path, "first.csv", 1)
    _write_sample(tmp_path, "second.csv", 2)

    result = run_folder_pipeline(str(tmp_path), target=0, seed=5)

    assert result.folder == str(tmp_path)
    assert result.skipped == []
    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.files == ["first.csv", "second.csv"]
    assert group.original_rows == 140
    assert len(group.prepared.frame) == 140
    assert group.chosen.size == len(group.projection.reduced)
    assert group.projection.original.shape == (140, 2)
    assert {row["method"] for row in group.method_scores} >= {"random", "cluster_actual"}
    assert group.size_curve


def test_invalid_group_is_reported_without_hiding_valid_group(tmp_path):
    _write_sample(tmp_path, "valid.csv", 3)
    pd.DataFrame({"constant": [1] * 20}).to_csv(tmp_path / "invalid.csv", index=False)

    result = run_folder_pipeline(str(tmp_path), target=0)

    assert len(result.groups) == 1
    assert len(result.skipped) == 1
    assert result.skipped[0]["files"] == ["invalid.csv"]
    assert "1개 이상" in result.skipped[0]["reason"]


def test_folder_pipeline_rejects_folder_without_tables(tmp_path):
    with pytest.raises(ValueError, match="표 파일을 찾지 못했습니다"):
        run_folder_pipeline(str(tmp_path))
