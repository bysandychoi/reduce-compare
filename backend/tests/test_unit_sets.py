"""run_reduce_units.py --sets 테스트 (T078)."""
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from test_unit_limits import STRATA, UNIT, _lots

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_reduce_units.py"


def _run_sets(tmp_path, *extra, n_lots=300):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    _lots(n_lots).to_csv(data / "lots.csv", index=False)
    out = tmp_path / "out"
    cmd = [sys.executable, str(SCRIPT), str(data), "--unit", ",".join(UNIT),
           "--strata", ",".join(STRATA), "--no-plot", "--out", str(out), *extra]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr
    summary = pd.read_csv(out / "sets_A.csv", encoding="utf-8-sig")
    files = sorted((out / "sets_A").glob("set_*.csv"))
    return proc.stdout, summary, files


def _signature(path):
    frame = pd.read_csv(path, encoding="utf-8-sig")
    return frozenset(map(tuple, frame[UNIT].astype(str).to_numpy()))


def test_sets_ratio_path_saves_distinct_sets_above_target(tmp_path):
    stdout, summary, files = _run_sets(tmp_path, "--ratio", "0.2", "--sets", "5", "--target", "60")
    assert len(files) == 5 and len(summary) == 5
    assert (summary["total"] >= 60).all()
    assert summary["seed"].is_unique
    assert len({_signature(f) for f in files}) == 5
    first = pd.read_csv(files[0], encoding="utf-8-sig")
    assert first.columns[0] == "_weight"
    assert list(summary["file"]) == [f.name for f in files]
    assert "세트 5/5개 저장" in stdout


def test_sets_with_unit_limit_draw_different_lots(tmp_path):
    _, summary, files = _run_sets(tmp_path, "--limit", "lot_id=40", "--sets", "4", "--target", "0")
    lots = [frozenset(pd.read_csv(f, encoding="utf-8-sig")["lot_id"]) for f in files]
    assert len(files) == 4
    assert {len(lot) for lot in lots} == {40}
    assert len(set(lots)) == 4


def test_sets_stop_at_max_tries(tmp_path):
    stdout, summary, files = _run_sets(tmp_path, "--ratio", "0.05", "--sets", "5",
                                       "--target", "100.1", "--max-tries", "3")
    assert len(files) == 0 and summary.empty
    assert list(summary.columns)[:3] == ["set", "seed", "rows"]
    assert "시도 상한 3회에 닿아 멈췄습니다" in stdout


def test_combo_key_matches_row_join():
    from app.core.grouped import SEP, combo_key
    df = _lots(50)
    df["num"] = range(len(df))
    df["num"] = df["num"] * 1.5
    cols = ["lot_id", "step_id", "num"]
    expected = df[cols].astype(str).agg(SEP.join, axis=1)
    assert combo_key(df, cols).equals(expected)
    assert combo_key(df, ["lot_id"]).equals(df[["lot_id"]].astype(str).agg(SEP.join, axis=1))


def test_combo_key_duplicate_columns_stay_series():
    from app.core.grouped import SEP, combo_key
    df = _lots(5)
    key = combo_key(df, ["lot_id", "lot_id"])
    assert key.equals(df[["lot_id", "lot_id"]].astype(str).agg(SEP.join, axis=1))


def test_rerun_removes_old_set_files(tmp_path):
    _run_sets(tmp_path, "--ratio", "0.2", "--sets", "4", "--target", "0")
    stdout, summary, files = _run_sets(tmp_path, "--ratio", "0.2", "--sets", "2", "--target", "0")
    assert len(files) == len(summary) == 2
    assert "이전 실행의 세트 파일 4개를 지웠습니다" in stdout


@pytest.mark.parametrize("extra", [["--ratio", "1.0"], ["--limit", "lot_id=100000"]])
def test_single_possible_set_is_made_once(tmp_path, extra):
    stdout, summary, files = _run_sets(tmp_path, *extra, "--sets", "3", "--target", "0")
    assert len(files) == len(summary) == 1
    assert "서로 다른 세트를 만들 수 없습니다" in stdout
    assert "닿아 멈췄습니다" not in stdout and "더 나오지 않아" not in stdout


def test_stops_when_only_duplicates_remain(tmp_path):
    # lot 5개 중 4개 → 가능한 조합 5가지뿐
    stdout, summary, files = _run_sets(tmp_path, "--limit", "lot_id=4", "--sets", "10",
                                       "--target", "0", n_lots=5)
    assert len(files) == len(summary) <= 5
    assert "서로 다른 세트가 더 나오지 않아 멈췄습니다" in stdout


@pytest.mark.parametrize("extra", [["--sets", "-1"], ["--sets", "2", "--max-tries", "0"]])
def test_invalid_set_arguments(tmp_path, extra):
    cmd = [sys.executable, str(SCRIPT), str(tmp_path), "--unit", "a", "--strata", "b", *extra]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2 and "이상이어야 합니다" in proc.stderr
