"""run_reduce_units.py의 화면 출력 함수 모음."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.core.grouped import unit_table  # noqa: E402
from app.core.valuelimit import limit_summary  # noqa: E402


def describe(df, unit_cols, strata_cols, sampling=True):
    """단위·층 구성을 출력한다. sampling=False면 비율 축소 없이 그대로 남는 경우(드문 층 안내 생략)."""
    units = unit_table(df, unit_cols, strata_cols)
    label = "" if sampling else "결과 "
    print(f"  {label}단위 {len(units):,}개 · 층 조합 {units['stratum'].nunique():,}개 · "
          f"단위당 행 수 평균 {units['rows'].mean():.1f} (최대 {int(units['rows'].max())})")
    rare = int((units.groupby("stratum").size() <= 2).sum())
    if rare and sampling:
        print(f"  단위가 2개 이하인 드문 층 조합 {rare:,}개 (모두 최소 1개는 남깁니다)")


def print_limit(info):
    """행 필터 limit 하나의 결과와 남은 값을 출력한다."""
    print(f"  {limit_summary(info)}")
    head = sorted(info.kept, key=lambda k: -k["orig_ratio"])[:10]
    print(f"      {'값':<18}{'원본 비율':>10}{'남긴 뒤 비율':>14}{'행':>12}")
    for k in head:
        print(f"      {str(k['value'])[:16]:<18}{k['orig_ratio'] * 100:>9.2f}%"
              f"{k['ratio_after_limit'] * 100:>13.2f}%{k['rows']:>12,}")
    if len(info.kept) > 10:
        print(f"      … 그 외 {len(info.kept) - 10}개 값")


def print_unit_pick(col, before, picked, final, mode):
    """단위 컬럼 limit(예: lot_id=100)으로 고른 결과를 출력한다. final은 실제로 남은 값 수."""
    how = "많이 쓰인 순서" if mode == "top" else "원본 비율 확률로 무작위"
    print(f"  {col}: 값 {before:,}종 중 {picked:,}종 선택 ({how}) → 결과에 {final:,}종 남음")
    if final < picked:
        print(f"      뒤에 적은 단위 컬럼 limit 때문에 {picked - final:,}종이 빠졌습니다. "
              f"개수를 꼭 맞출 컬럼을 --limit 마지막에 적으세요")


def print_result(df, red, rows, score, elapsed):
    print(f"\n{'=' * 64}")
    print(f"원본 {len(df):,}행 / 단위 {red.units_total:,}개 → "
          f"축소 {len(rows):,}행 ({len(rows) / len(df) * 100:.2f}%) / 단위 {red.units_kept:,}개"
          f"  ·  {elapsed:.1f}초")
    print(f"  종합 유사도 {score['total']:.1f}점  "
          f"(컬럼 비율 {score['columns']:.1f} / 조합 비율 {score['combos']:.1f} / "
          f"단위 크기 {score['unit_size']:.1f})")
    for note in red.notes:
        print(f"  · {note}")
    print("\n  컬럼별 비율 점수")
    for c in sorted(score["detail"]["columns"], key=lambda r: r["score"])[:10]:
        print(f"    {c['name']:<16} {c['score']:5.1f}점  값 {c['levels']:>6,}종  "
              f"최대 비율차 {c['max_gap'] * 100:5.2f}%p  값 커버리지 {c['coverage'] * 100:5.1f}%")
    print("\n  조합별 비율 점수")
    for c in score["detail"]["combos"]:
        print(f"    {'×'.join(c['columns']):<46} {c['score']:5.1f}점  "
              f"조합 {c['levels']:,}종  커버리지 {c['coverage'] * 100:.1f}%")
    us = score["detail"]["unit_size"]
    print(f"\n  단위당 행 수: 원본 평균 {us['mean_orig']} (최대 {us['max_orig']}) / "
          f"축소본 평균 {us['mean_reduced']} (최대 {us['max_reduced']})")


def print_distribution(table, columns):
    """컬럼별 값 분포를 원본·축소 비율로 나란히 출력한다."""
    if table.empty:
        return
    print("\n  값 분포 비교 (원본 % → 축소 %)")
    for col in columns:
        block = table[table["column"] == col]
        if block.empty:
            continue
        print(f"\n    [{col}]")
        print(f"      {'값':<22}{'원본':>12}{'축소':>12}{'차이':>10}")
        for _, r in block.iterrows():
            print(f"      {str(r['value'])[:20]:<22}"
                  f"{r['orig_ratio'] * 100:>10.2f}% {r['reduced_ratio'] * 100:>10.2f}% "
                  f"{r['gap_pp']:>+9.2f}%p")
