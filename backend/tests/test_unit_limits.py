"""--limit 적용 순서와 단위 컬럼 개수 보장 테스트 (T069)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core.grouped import units_by_values
from app.core.valuelimit import split_limits

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_reduce_units.py"
UNIT = ["lot_id", "step_id"]
STRATA = ["step_id", "lot_floor"]


def _lots(n_lots=300, seed=1):
    """lot마다 여러 공정(step)을 거치고, 행마다 장비·마스크가 무작위인 데이터."""
    rng = np.random.default_rng(seed)
    rows = []
    for lot in range(n_lots):
        floor = rng.choice(["F1", "F2"])
        for step in rng.choice(12, 4, replace=False):
            for _ in range(rng.integers(1, 4)):
                rows.append({"lot_id": f"L{lot:04d}", "step_id": f"S{step:02d}", "lot_floor": floor,
                             "eqp_id": f"E{rng.integers(0, 40):02d}",
                             "mask_id": f"M{rng.integers(0, 30):02d}"})
    return pd.DataFrame(rows)


def test_split_limits_separates_unit_columns():
    rows, unit = split_limits({"lot_id": 100, "eqp_id": 6, "mask_id": 6}, UNIT)
    assert rows == {"eqp_id": 6, "mask_id": 6}
    assert unit == {"lot_id": 100}
    assert split_limits({}, UNIT) == ({}, {})


def test_units_by_values_keeps_whole_units_and_restores_strata():
    df = _lots()
    picked = sorted(df["lot_id"].unique())[:50]
    red = units_by_values(df, UNIT, STRATA, {"lot_id": picked})
    rows = red.rows(df)
    assert rows["lot_id"].nunique() == 50
    # 고른 lot의 행은 모두 남는다
    assert len(rows) == int(df["lot_id"].isin(picked).sum())
    # 층별 가중 합이 원본 층별 행 수와 같다 (남은 층 기준)
    kept = pd.Series(red.weights).groupby(
        rows[STRATA].astype(str).agg("|".join, axis=1).to_numpy()).sum()
    orig = df[STRATA].astype(str).agg("|".join, axis=1).value_counts()
    assert np.allclose(kept.to_numpy(), orig[kept.index].to_numpy())
    assert "--ratio 단위 축소 생략" in red.notes[0]


def test_units_by_values_errors():
    df = _lots(20)
    with pytest.raises(ValueError, match="단위 컬럼이 아닙니다"):
        units_by_values(df, UNIT, STRATA, {"eqp_id": ["E01"]})
    with pytest.raises(ValueError, match="해당하는 행이 없습니다"):
        units_by_values(df, UNIT, STRATA, {"lot_id": ["없는 lot"]})


def _run_process(tmp_path, *extra):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    _lots().to_csv(data / "lots.csv", index=False)
    out = tmp_path / "out"
    cmd = [sys.executable, str(SCRIPT), str(data), "--unit", ",".join(UNIT),
           "--strata", ",".join(STRATA), "--no-plot", "--out", str(out), *extra]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp949"
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="cp949", env=env, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    return proc, out


def _run(tmp_path, *extra):
    proc, out = _run_process(tmp_path, *extra)
    produced = sorted(out.glob("reduced_*.csv"))   # 건너뛴 그룹은 파일이 없다
    assert len(produced) == 1, proc.stdout
    return proc.stdout, pd.read_csv(produced[0])


def test_cli_inspect_prints_under_cp949(tmp_path):
    proc, out = _run_process(tmp_path, "--inspect")
    assert "표 파일 1개" in proc.stdout
    assert "단위" in proc.stdout and "층 조합" in proc.stdout
    assert not out.exists()


def test_cli_unit_limit_is_final_count_after_row_filters(tmp_path):
    stdout, reduced = _run(tmp_path, "--limit", "lot_id=100,eqp_id=10,mask_id=10", "--ratio", "0.2")
    assert reduced["lot_id"].nunique() == 100
    assert reduced["eqp_id"].nunique() <= 10 and reduced["mask_id"].nunique() <= 10
    assert "--ratio 단위 축소는 하지 않습니다" in stdout


def test_cli_unit_limit_larger_than_available_keeps_all(tmp_path):
    _, reduced = _run(tmp_path, "--limit", "lot_id=100000,eqp_id=3", "--ratio", "0.2")
    df = _lots()
    df = df[df["eqp_id"].isin(df["eqp_id"].value_counts().head(3).index)]
    assert reduced["lot_id"].nunique() == df["lot_id"].nunique()


def test_cli_multiple_unit_limits_report_actual_counts(tmp_path):
    stdout, reduced = _run(tmp_path, "--limit", "lot_id=100,step_id=3", "--ratio", "0.2")
    report = json.loads((tmp_path / "out" / "report_A.json").read_text(encoding="utf-8"))
    after = {v["column"]: v["levels_after"] for v in report["value_limits"]}
    # 실제로 남은 개수를 그대로 기록하고, 마지막에 적은 컬럼(step_id)은 정확히 맞는다
    assert after["lot_id"] == reduced["lot_id"].nunique()
    assert after["step_id"] == reduced["step_id"].nunique() == 3
    if after["lot_id"] < 100:
        assert "--limit 마지막에 적으세요" in stdout
    _, last = _run(tmp_path, "--limit", "step_id=3,lot_id=100", "--ratio", "0.2")
    assert last["lot_id"].nunique() == 100


def test_cli_group_without_limit_column_is_skipped(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "other.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    stdout, reduced = _run(tmp_path, "--limit", "lot_id=50", "--ratio", "0.2")
    assert "건너뜀 - 데이터에 없는 컬럼입니다: lot_id" in stdout
    assert reduced["lot_id"].nunique() == 50
