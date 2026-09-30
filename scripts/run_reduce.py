#!/usr/bin/env python3
"""폴더 하나를 넣으면 축소 결과만 딱 보여주는 실행 스크립트.

사용 예:
    python3 scripts/run_reduce.py ~/data/sales
    python3 scripts/run_reduce.py ~/data/sales --target 85 --out results

하는 일:
  1. 폴더에서 CSV를 모아 컬럼 구조가 같은 것끼리 그룹으로 묶는다
  2. 그룹마다 결측 행을 빼고 축소 기준 컬럼을 정한다
  3. 기준치를 넘는 가장 작은 크기를 찾고, 축소 방식 4가지를 비교해 가장 좋은 것을 쓴다
  4. 점수를 화면에 출력하고, 축소본 CSV·리포트 JSON·비교 그림을 결과 폴더에 저장한다
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.core.ingest import collect_csv_files  # noqa: E402
from app.core.pipeline import DEFAULT_TARGET, choose_method, search_size  # noqa: E402
from app.core.prepare import merge_group, prepare_group  # noqa: E402
from app.core.schema import extract_schema, group_by_schema  # noqa: E402

METHOD_LABEL = {"cluster_actual": "군집 기반(실제 행)", "cluster_mean": "군집 기반(평균 행)",
                "stratified": "층화 샘플링", "random": "랜덤 샘플링"}


def print_group_result(name, df, best, table, curve, elapsed):
    print(f"\n{'=' * 64}\n[{name}]  원본 {len(df):,}행 → 축소 {best.size:,}행 "
          f"({best.size / len(df) * 100:.2f}%)  ·  {elapsed:.1f}초")
    print(f"  종합 유사도 {best.score:.1f}점   (분포 {best.distribution:.1f} / "
          f"상관 {best.correlation:.1f} / 구조 {best.structure:.1f})")
    print(f"  추천 방식: {METHOD_LABEL.get(best.method, best.method)}")
    for note in best.detail.get("notes", []):
        print(f"  · {note}")
    print("\n  방식별 점수")
    for row in sorted(table, key=lambda r: -r["score"]):
        mark = "←" if row["method"] == best.method else " "
        print(f"    {METHOD_LABEL.get(row['method'], row['method']):<18} {row['score']:5.1f}점 {mark}")
    print("\n  크기별 점수")
    for row in curve:
        print(f"    {row['size']:>7,}행  {row['score']:5.1f}점")
    corr = best.detail["correlation"]
    if "frobenius" in corr:
        print(f"\n  상관행렬 차이 {corr['frobenius']:.3f} · 가장 크게 바뀐 쌍 차이 {corr['max_gap']:.3f}")
    worst = sorted(best.detail["columns"], key=lambda c: c["score"])[:3]
    print("  점수가 낮은 컬럼: " + ", ".join(f"{c['name']} {c['score']:.0f}점" for c in worst))


def save_outputs(out_dir, name, best, curve, table, df):
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, f"reduced_{name}.csv")
    frame = best.frame.copy()
    frame.insert(0, "_weight", best.reduction.weights)
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    report = {
        "group": name, "original_rows": int(len(df)), "reduced_rows": int(best.size),
        "ratio": round(best.size / len(df), 6), "method": best.method,
        "score": {"total": best.score, "distribution": best.distribution,
                  "correlation": best.correlation, "structure": best.structure},
        "size_curve": curve, "methods": table, "detail": best.detail,
    }
    json_path = os.path.join(out_dir, f"report_{name}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    return csv_path, json_path


KIND_LABEL = {"numeric": "수치", "categorical": "범주", "datetime": "날짜",
              "identifier": "ID", "text": "텍스트", "constant": "상수"}


def print_columns(name, group):
    """자동 판별 결과를 표로 보여준다 (--inspect)."""
    print(f"\n[{name}] 컬럼 {len(group.columns)}개  ·  파일 {len(group.files)}개")
    print(f"  {'컬럼':<22}{'타입':<8}{'기준 사용':<10}{'결측률':<9}{'값 종류 비율':<12}사유")
    for c in group.columns:
        use = "○" if c.selected else "×"
        print(f"  {c.name:<22}{KIND_LABEL.get(c.kind, c.kind):<8}{use:<10}"
              f"{c.missing_ratio * 100:>5.1f}%   {c.unique_ratio * 100:>6.1f}%     {c.reason}")
    chosen = [c.name for c in group.columns if c.selected]
    print(f"  → 기준 컬럼 {len(chosen)}개: {', '.join(chosen) or '없음'}")


def resolve_selection(group, args):
    """--columns / --exclude / --max-missing 을 반영한 축소 기준 컬럼."""
    if args.columns:
        return [c.strip() for c in args.columns.split(",") if c.strip()]
    chosen = [c for c in group.columns if c.selected]
    if args.max_missing is not None:
        dropped = [c.name for c in chosen if c.missing_ratio > args.max_missing]
        if dropped:
            print(f"  결측 {args.max_missing * 100:.0f}% 초과로 제외: {', '.join(dropped)}")
        chosen = [c for c in chosen if c.missing_ratio <= args.max_missing]
    if args.exclude:
        drop = {c.strip() for c in args.exclude.split(",") if c.strip()}
        chosen = [c for c in chosen if c.name not in drop]
    return [c.name for c in chosen] if (args.exclude or args.max_missing is not None) else None


def main():
    ap = argparse.ArgumentParser(description="CSV 폴더를 축소하고 원본과의 유사도를 보여준다")
    ap.add_argument("folder", help="CSV가 들어 있는 폴더")
    ap.add_argument("--target", type=float, default=DEFAULT_TARGET, help="유사도 기준치 (기본 85)")
    ap.add_argument("--out", default="results", help="결과 저장 폴더 (기본 results)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-plot", action="store_true", help="비교 그림을 만들지 않음")
    ap.add_argument("--inspect", action="store_true",
                    help="축소하지 않고, 자동으로 판별한 컬럼 타입과 기본 선택만 보여준다")
    ap.add_argument("--columns", help="축소 기준 컬럼을 직접 지정 (쉼표 구분)")
    ap.add_argument("--exclude", help="자동 선택에서 뺄 컬럼 (쉼표 구분)")
    ap.add_argument("--max-missing", type=float, default=None,
                    help="결측 비율이 이 값을 넘는 컬럼은 기준에서 자동 제외 (예: 0.2)")
    args = ap.parse_args()

    files = collect_csv_files(args.folder)
    if not files:
        sys.exit(f"읽을 수 있는 표 파일(.csv/.tsv/.txt)을 찾지 못했습니다: {args.folder}")
    print(f"표 파일 {len(files)}개: " + ", ".join(f.name for f in files[:6]) +
          (" …" if len(files) > 6 else ""))

    groups = group_by_schema([extract_schema(f) for f in files])
    print(f"컬럼 구조 기준 {len(groups)}개 그룹으로 묶었습니다.")

    if args.inspect:
        for i, g in enumerate(groups):
            print_columns(chr(65 + i), g)
        print("\n컬럼을 바꾸려면 --columns 또는 --exclude 를 쓰세요. 예:")
        print("  python3 scripts/run_reduce.py <폴더> --exclude memo,store_id")
        return

    for i, g in enumerate(groups):
        name = chr(65 + i)
        started = time.time()
        df = merge_group(g.files)
        try:
            res = prepare_group(df, g.columns, resolve_selection(g, args))
        except ValueError as e:
            print(f"[{name}] 건너뜀 — {e}")
            continue
        print(f"\n[{name}] 파일 {len(g.files)}개 · {len(df):,}행 · 기준 컬럼 {len(res.used_columns)}개"
              + (f" · 결측 {res.dropped_missing:,}행 제외" if res.dropped_missing else ""))
        best, curve = search_size(res.frame, res.features, g.columns, res.used_columns,
                                  target=args.target, seed=args.seed)
        best, table = choose_method(res.frame, res.features, g.columns, res.used_columns,
                                    best.size, seed=args.seed)
        print_group_result(name, res.frame, best, table, curve, time.time() - started)
        csv_path, json_path = save_outputs(args.out, name, best, curve, table, res.frame)
        print(f"\n  저장: {csv_path}\n        {json_path}")
        if not args.no_plot:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from plot_compare import save_comparison
            png = save_comparison(args.out, name, res, best)
            print(f"        {png}")


if __name__ == "__main__":
    main()
