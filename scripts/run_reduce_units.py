#!/usr/bin/env python3
"""행이 묶여 있는 데이터(예: lot-공정 이력)를 단위째로 축소한다.

사용 예:
    python3 scripts/run_reduce_units.py "폴더" \\
        --unit lot_id,step_id,proc_id,proc_ver \\
        --strata step_id,proc_id,proc_ver,lot_floor \\
        --ratio 0.1

  --unit    : 이 컬럼 조합이 같은 행은 통째로 남기거나 통째로 뺀다
  --strata  : 이 조합별 비율을 원본과 같게 유지한다 (드문 조합도 최소 1개 남김)
  --ratio   : 각 층에서 남길 단위 비율 (생략하면 여러 비율을 시도해 기준 점수를 넘는 최소값)
  --combo   : 비율을 확인할 컬럼 조합 (기본: strata, 여러 번 쓸 수 있음)
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.core.catmetrics import distribution_table, grouped_similarity  # noqa: E402
from app.core.grouped import stratified_units, stratum_report, unit_table  # noqa: E402
from app.core.ingest import collect_csv_files  # noqa: E402
from app.core.prepare import merge_group  # noqa: E402
from app.core.schema import extract_schema, group_by_schema  # noqa: E402
from app.core.valuelimit import limit_summary, limit_values, parse_limits  # noqa: E402

RATIOS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5)


def split(text):
    return [c.strip() for c in text.split(",") if c.strip()]


def describe(df, unit_cols, strata_cols):
    units = unit_table(df, unit_cols, strata_cols)
    print(f"  단위 {len(units):,}개 · 층 조합 {units['stratum'].nunique():,}개 · "
          f"단위당 행 수 평균 {units['rows'].mean():.1f} (최대 {int(units['rows'].max())})")
    rare = int((units.groupby("stratum").size() <= 2).sum())
    if rare:
        print(f"  단위가 2개 이하인 드문 층 조합 {rare:,}개 (모두 최소 1개는 남깁니다)")


def try_ratio(df, args, ratio, columns, combos):
    red = stratified_units(df, args.unit_cols, args.strata_cols, ratio,
                           min_units=args.min_units, seed=args.seed)
    rows = red.rows(df)
    score = grouped_similarity(df, rows, red, columns, combos)
    return red, rows, score


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


def apply_limits(df, args, name):
    """값 종류를 줄이고 무엇이 남았는지 출력한다."""
    limits = parse_limits(args.limit)
    if not limits:
        return df, []
    df, infos = limit_values(df, limits, args.limit_mode, args.seed)
    for info in infos:
        print(f"  {limit_summary(info)}")
        head = sorted(info.kept, key=lambda k: -k["orig_ratio"])[:10]
        print(f"      {'값':<18}{'원본 비율':>10}{'남긴 뒤 비율':>14}{'행':>12}")
        for k in head:
            print(f"      {str(k['value'])[:16]:<18}{k['orig_ratio'] * 100:>9.2f}%"
                  f"{k['ratio_after_limit'] * 100:>13.2f}%{k['rows']:>12,}")
        if len(info.kept) > 10:
            print(f"      … 그 외 {len(info.kept) - 10}개 값")
    return df, [info.__dict__ for info in infos]


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


def pick_dist_columns(df, args, columns):
    """분포를 보여줄 컬럼을 고른다 (지정이 없으면 값 종류가 적은 것)."""
    if args.show_dist:
        return [c for c in split(args.show_dist) if c in df.columns]
    return [c for c in columns if df[c].nunique() <= 20]


def save(out_dir, name, df, red, rows, score, dist_table=None, limit_info=None):
    os.makedirs(out_dir, exist_ok=True)
    frame = rows.copy()
    frame.insert(0, "_weight", red.weights)
    csv_path = os.path.join(out_dir, f"reduced_{name}.csv")
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    report = {"group": name, "original_rows": len(df), "reduced_rows": len(rows),
              "units_total": red.units_total, "units_kept": red.units_kept,
              "strata_total": red.strata_total, "unit_columns": red.unit_cols,
              "strata_columns": red.strata_cols, "score": score,
              "value_limits": limit_info or []}
    json_path = os.path.join(out_dir, f"report_{name}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    strata_path = os.path.join(out_dir, f"strata_{name}.csv")
    stratum_report(df, red).to_csv(strata_path, encoding="utf-8-sig")
    paths = [csv_path, json_path, strata_path]
    if dist_table is not None and not dist_table.empty:
        dist_path = os.path.join(out_dir, f"distribution_{name}.csv")
        dist_table.to_csv(dist_path, index=False, encoding="utf-8-sig")
        paths.append(dist_path)
    return tuple(paths)


def main():
    ap = argparse.ArgumentParser(description="묶인 행을 단위째로 층화 축소한다")
    ap.add_argument("folder")
    ap.add_argument("--unit", required=True, help="축소 단위 컬럼 (쉼표 구분)")
    ap.add_argument("--strata", required=True, help="비율을 유지할 컬럼 (쉼표 구분)")
    ap.add_argument("--ratio", type=float, default=None, help="남길 단위 비율 (예: 0.1)")
    ap.add_argument("--target", type=float, default=85.0, help="자동 탐색 시 기준 점수")
    ap.add_argument("--combo", action="append", default=[], help="비율을 확인할 컬럼 조합")
    ap.add_argument("--min-units", type=int, default=1, help="층마다 남길 최소 단위 수")
    ap.add_argument("--columns", default=None, help="비율을 볼 컬럼 (기본: 전체)")
    ap.add_argument("--out", default="results")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--inspect", action="store_true", help="단위·층 구성만 확인하고 끝낸다")
    ap.add_argument("--show-dist", default=None,
                    help="분포를 화면에 표로 볼 컬럼 (쉼표 구분, 기본: 값이 20종 이하인 컬럼)")
    ap.add_argument("--dist-top", type=int, default=10, help="컬럼마다 보여줄 값 개수 (기본 10)")
    ap.add_argument("--no-plot", action="store_true", help="분포 그림을 만들지 않음")
    ap.add_argument("--limit", default=None,
                    help="컬럼의 값 종류를 줄인다 (예: eqp_id=6,mask_id=50). 단위 축소보다 먼저 적용")
    ap.add_argument("--limit-mode", default="top", choices=["top", "sample"],
                    help="top=많이 쓰인 순서, sample=원본 비율을 확률로 무작위 (기본 top)")
    args = ap.parse_args()
    args.unit_cols, args.strata_cols = split(args.unit), split(args.strata)

    files = collect_csv_files(args.folder)
    if not files:
        sys.exit(f"읽을 수 있는 표 파일이 없습니다: {args.folder}")
    groups = group_by_schema([extract_schema(f) for f in files])
    print(f"표 파일 {len(files)}개 · 컬럼 구조 {len(groups)}개 그룹")

    for i, g in enumerate(groups):
        name = chr(65 + i)
        df = merge_group(g.files)
        print(f"\n[{name}] 파일 {len(g.files)}개 · {len(df):,}행 · 컬럼 {df.shape[1]}개")
        try:
            df, limit_info = apply_limits(df, args, name)
        except ValueError as e:
            print(f"  건너뜀 — {e}")
            continue
        try:
            describe(df, args.unit_cols, args.strata_cols)
        except ValueError as e:
            print(f"  건너뜀 — {e}")
            continue
        if args.inspect:
            continue

        columns = split(args.columns) if args.columns else [
            c for c in df.columns if not c.startswith("_")]
        combos = [split(c) for c in args.combo] or [args.strata_cols]
        started = time.time()
        if args.ratio:
            red, rows, score = try_ratio(df, args, args.ratio, columns, combos)
        else:
            for ratio in RATIOS:
                red, rows, score = try_ratio(df, args, ratio, columns, combos)
                print(f"  비율 {ratio * 100:>4.0f}% → {len(rows):,}행, {score['total']:.1f}점")
                if score["total"] >= args.target:
                    break
        print_result(df, red, rows, score, time.time() - started)
        full_table = distribution_table(df, rows, columns, red.weights, top=args.dist_top)
        print_distribution(full_table, pick_dist_columns(df, args, columns))
        paths = list(save(args.out, name, df, red, rows, score, full_table, limit_info))
        if not args.no_plot:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from plot_distribution import save_distribution_chart
            sizes = (unit_table(df, args.unit_cols, args.strata_cols)["rows"].to_numpy(),
                     unit_table(rows, args.unit_cols, args.strata_cols)["rows"].to_numpy())
            paths.append(save_distribution_chart(args.out, name, full_table,
                                                 pick_dist_columns(df, args, columns), sizes))
        print("\n  저장: " + "\n        ".join(paths))


if __name__ == "__main__":
    main()
