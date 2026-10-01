"""run_reduce_units.py --sets: 기준 점수를 넘는 서로 다른 무작위 축소 세트를 N개 만든다.

seed를 하나씩 바꿔 가며 같은 조건으로 다시 축소한다.
  - 단위 컬럼 limit(예: lot_id=100)이 있으면 세트마다 lot을 원본 비율 확률로 무작위로 다시 뽑는다.
  - 없으면 본 실행에서 쓴 단위 비율(--ratio 또는 자동 탐색 결과)로 층마다 단위를 무작위로 뽑는다.
점수가 --target 미만이거나 이미 나온 세트와 같은 세트는 버린다. --max-tries에 닿으면 멈춘다.
"""
from __future__ import annotations

import hashlib
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from units_limits import pick_unit_values
from units_set_reports import SetReports

from app.core.catmetrics import grouped_similarity
from app.core.grouped import stratified_units, units_by_values
from app.core.valuelimit import parse_limits, split_limits


def one_set(df, args, seed, unit_limits, ratio, columns, combos):
    """seed 하나로 축소 세트 하나를 만들고 점수를 매긴다."""
    if unit_limits:
        keep, _ = pick_unit_values(df, unit_limits, args, mode="sample", seed=seed, quiet=True)
        red = units_by_values(df, args.unit_cols, args.strata_cols, keep)
    else:
        red = stratified_units(df, args.unit_cols, args.strata_cols, ratio,
                               min_units=args.min_units, seed=seed)
    rows = red.rows(df)
    return red, rows, grouped_similarity(df, rows, red, columns, combos)


def _save_set(folder, index, red, rows):
    frame = rows.copy()
    frame.insert(0, "_weight", red.weights)
    path = os.path.join(folder, f"set_{index:03d}.csv")
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


# 기준을 넘었는데 이미 나온 세트만 연속으로 이만큼 나오면 더 만들 수 없다고 본다.
STALE_LIMIT = 50
COLUMNS = ["set", "seed", "rows", "units", "total", "columns", "combos", "unit_size", "file"]


def _prepare_folder(folder):
    """세트 폴더를 만들고, 이전 실행이 남긴 set_*.csv를 지운다 (요약표와 파일 수를 맞추기 위해)."""
    os.makedirs(folder, exist_ok=True)
    old = [f for f in os.listdir(folder) if f.startswith("set_") and f.endswith(".csv")]
    for f in old:
        os.remove(os.path.join(folder, f))
    for name in ('comparisons.csv', 'distribution_differences.csv', 'comparison.png',
                 'distribution_overview.png'):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            os.remove(path)
    reports = os.path.join(folder, 'distributions')
    if os.path.isdir(reports):
        for name in os.listdir(reports):
            if ((name.startswith('set_') and name.endswith('.csv'))
                    or (name.startswith('distribution_set_') and name.endswith('.png'))):
                os.remove(os.path.join(reports, name))
    if old:
        print(f"  이전 실행의 세트 파일 {len(old)}개를 지웠습니다 ({folder})")


def _single_possible(df, unit_limits, ratio):
    """무작위로 뽑아도 결과가 하나뿐인 경우 그 이유를 돌려준다 (아니면 None)."""
    if unit_limits:
        if all(n >= df[c].nunique() for c, n in unit_limits.items()):
            return "단위 컬럼 limit이 남은 값 수 이상이라 매번 같은 값을 모두 고릅니다"
        return None
    if ratio is not None and ratio >= 1:
        return "단위 비율이 100%라 매번 모든 단위를 고릅니다"
    return None


def make_sets(df, args, name, ratio, columns, combos, main_score=None):
    """기준을 넘는 서로 다른 세트를 args.sets개 모아 저장하고 요약표를 남긴다."""
    unit_limits = split_limits(parse_limits(args.limit), args.unit_cols)[1]
    max_tries = args.max_tries if args.max_tries is not None else args.sets * 20
    folder = os.path.join(args.out, f"sets_{name}")
    _prepare_folder(folder)
    how = (f"단위 컬럼 limit({', '.join(unit_limits)}) 값을 세트마다 무작위로 다시 뽑음"
           if unit_limits else f"층마다 단위 {ratio * 100:g}%를 무작위로 뽑음")
    print(f"\n  세트 {args.sets}개 만들기 - {how}, 기준 {args.target:g}점, 시도 상한 {max_tries}회")
    if main_score is not None and main_score < args.target:
        print(f"  주의: 본 실행 점수 {main_score:.1f}점이 기준 {args.target:g}점보다 낮아 "
              f"기준을 넘는 세트가 드물 수 있습니다")
    single = _single_possible(df, unit_limits, ratio)
    if single:
        print(f"  서로 다른 세트를 만들 수 없습니다 - {single}. 세트 1개만 만듭니다")
        max_tries = min(max_tries, 1)
    summary, stats = _collect(df, args, unit_limits, ratio, columns, combos, folder, max_tries)
    table = pd.DataFrame(summary, columns=COLUMNS)
    summary_path = os.path.join(args.out, f"sets_{name}.csv")
    table.to_csv(summary_path, index=False, encoding="utf-8-sig")
    _print_sets_result(args, table, stats, single, folder, summary_path)
    return table


def _collect(df, args, unit_limits, ratio, columns, combos, folder, max_tries):
    """seed를 바꿔 가며 기준을 넘는 서로 다른 세트를 모은다."""
    seen, summary = set(), []
    reports = SetReports(df, args, folder, columns)
    stats = {"tries": 0, "below": 0, "dup": 0, "stale": False}
    run = 0          # 기준을 넘었지만 중복인 결과가 연속된 횟수
    while len(summary) < args.sets and stats["tries"] < max_tries:
        seed = args.seed + stats["tries"]
        stats["tries"] += 1
        red, rows, score = one_set(df, args, seed, unit_limits, ratio, columns, combos)
        if score["total"] < args.target:
            stats["below"] += 1
            continue
        key = hashlib.sha1(red.indices.tobytes()).hexdigest()
        if key in seen:
            stats["dup"] += 1
            run += 1
            if run >= STALE_LIMIT:
                stats["stale"] = True
                break
            continue
        run = 0
        seen.add(key)
        reports.add(len(summary) + 1, red, rows)
        path = _save_set(folder, len(summary) + 1, red, rows)
        summary.append({"set": len(summary) + 1, "seed": seed, "rows": len(rows),
                        "units": red.units_kept, "total": score["total"],
                        "columns": score["columns"], "combos": score["combos"],
                        "unit_size": score["unit_size"], "file": os.path.basename(path)})
        if len(summary) % 10 == 0:
            print(f"    {len(summary)}/{args.sets}개 완료 (시도 {stats['tries']}회)")
    reports.finish()
    return summary, stats


def _print_sets_result(args, table, stats, single, folder, summary_path):
    done = len(table)
    print(f"  세트 {done}/{args.sets}개 저장 · 시도 {stats['tries']}회 "
          f"(기준 미달 {stats['below']}회, 중복 {stats['dup']}회)")
    if done:
        min_rows, max_rows = table['rows'].min(), table['rows'].max()
        print(f"  점수 {table['total'].min():.1f} ~ {table['total'].max():.1f}점 "
              f"(평균 {table['total'].mean():.1f}) · 행 {min_rows:,} ~ {max_rows:,}")
    if done < args.sets and not single:
        print("  " + _stop_reason(stats))
    print(f"  저장: {folder}/set_###.csv\n        {summary_path}")


def _stop_reason(stats):
    """모자란 이유를 실제로 많이 일어난 쪽에 맞춰 알려 준다."""
    if stats["stale"] or stats["dup"] > stats["below"]:
        return ("서로 다른 세트가 더 나오지 않아 멈췄습니다 - 가능한 조합이 적습니다. "
                "lot 수(--limit)나 단위 비율(--ratio)을 줄이거나 세트 수를 줄이세요")
    return (f"시도 상한 {stats['tries']}회에 닿아 멈췄습니다 - 대부분 기준 점수 미달입니다. "
            "--target을 낮추거나 --max-tries를 늘리세요")
