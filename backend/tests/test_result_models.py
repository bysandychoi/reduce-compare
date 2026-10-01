"""파이프라인 결과 Pydantic/JSON 스키마 테스트 (T055)."""
import json

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.core.pipeline import run_folder_pipeline
from app.models.results import PipelineResults, ScoreSummary


def _sample_csv(path):
    rng = np.random.default_rng(55)
    value = rng.normal(size=80)
    pd.DataFrame({
        "kind": rng.choice(["A", "B", "C"], len(value)),
        "value": value,
        "related": value + rng.normal(scale=0.1, size=len(value)),
    }).to_csv(path, index=False)


def test_core_result_serializes_to_json_schema(tmp_path):
    _sample_csv(tmp_path / "sample.csv")
    core = run_folder_pipeline(str(tmp_path), target=0, seed=4)

    result = PipelineResults.from_core(core)
    payload = json.loads(result.model_dump_json())

    assert payload["folder"] == str(tmp_path)
    assert payload["skipped"] == []
    assert payload["groups"][0]["original_rows"] == 80
    assert payload["groups"][0]["reduced_rows"] > 0
    assert len(payload["groups"][0]["projection"]["original"][0]) == 2
    reduced = payload["groups"][0]["projection"]["reduced"]
    assert len(reduced) == payload["groups"][0]["reduced_rows"]
    assert payload["groups"][0]["size_curve"]
    assert payload["groups"][0]["method_scores"]


def test_score_schema_rejects_out_of_range_values():
    with pytest.raises(ValidationError):
        ScoreSummary(total=101, distribution=90, correlation=90, structure=90)
