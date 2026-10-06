#!/usr/bin/env python3
"""입력 크기별 데이터 처리 단계 시간을 측정한다 (T110).

기본 실행은 임시 합성 CSV를 만들고 1만/10만/50만 행을 측정한다.
실제 폴더를 측정하려면 --folder 경로를 지정한다. 생성/다운로드 시간은
파이프라인 시간에 포함하지 않으며, 폴더 탐색부터 투영까지를 측정한다.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.ingest import collect_csv_files
from app.core.pipeline import _virtual_features, choose_method, search_size
from app.core.prepare import merge_group, prepare_group
from app.core.projection import project_comparison
from app.core.schema import extract_schema, group_by_schema

DEFAULT_ROWS = (10_000, 100_000, 500_000)
STAGES = ("discovery_schema", "merge_prepare", "size_search", "method_compare", "projection")


def measure(folder: str, requested_rows: int, synthetic: bool, target: float, seed: int) -> dict:
    """한 입력 폴더의 처리 단계와 총 시간을 계측한다."""
    times = {stage: 0.0 for stage in STAGES}
    total_started = time.perf_counter()
    started = time.perf_counter()
    files = collect_csv_files(folder)
    groups = group_by_schema([extract_schema(item) for item in files])
    times["discovery_schema"] = time.perf_counter() - started
    row_count = 0
    completed, skipped = 0, []
    for index, group in enumerate(groups):
        try:
            started = time.perf_counter()
            frame = merge_group(group.files)
            row_count += len(frame)
            prepared = prepare_group(frame, group.columns)
            times["merge_prepare"] += time.perf_counter() - started
            started = time.perf_counter()
            sized, _curve = search_size(prepared.frame, prepared.features, group.columns,
                                        prepared.used_columns, target=target, seed=seed)
            times["size_search"] += time.perf_counter() - started
            started = time.perf_counter()
            chosen, _methods = choose_method(prepared.frame, prepared.features, group.columns,
                                             prepared.used_columns, sized.size, seed=seed)
            times["method_compare"] += time.perf_counter() - started
            started = time.perf_counter()
            reduced = (prepared.features[chosen.reduction.indices]
                       if len(chosen.reduction.indices)
                       else _virtual_features(prepared.features, chosen.reduction))
            project_comparison(prepared.features, reduced, seed=seed)
            times["projection"] += time.perf_counter() - started
            completed += 1
        except ValueError as exc:
            skipped.append({"group": index + 1, "reason": str(exc)})
    if not files:
        raise ValueError(f"측정할 표 파일이 없습니다: {folder}")
    times["total_pipeline"] = time.perf_counter() - total_started
    return {"requested_rows": requested_rows, "total_rows": row_count,
            "files": len(files), "groups": completed, "skipped": skipped,
            "synthetic": synthetic, "seconds": times,
            "goal_seconds": 120, "goal_met": times["total_pipeline"] <= 120}


def generate(folder: Path, rows: int, seed: int) -> None:
    """기존 T015 생성기로 합성 입력을 만들고 실패를 호출자에게 전달한다."""
    command = [sys.executable, str(ROOT / "scripts" / "make_sample_data.py"),
               "--rows", str(rows), "--out", str(folder), "--seed", str(seed)]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)


def main() -> int:
    parser = argparse.ArgumentParser(description="데이터 처리 단계별 경과 시간 측정 (T110)")
    parser.add_argument("--folder", help="이미 존재하는 표 파일 폴더 (합성 데이터 생성 안 함)")
    parser.add_argument("--rows", nargs="+", type=int, default=DEFAULT_ROWS,
                        help="합성 입력의 그룹 A 행 수 (기본: 10000 100000 500000)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--target", type=float, default=85.0)
    parser.add_argument("--json", dest="json_path", help="기계 판독 가능한 JSON 보고서 저장 경로")
    args = parser.parse_args()
    if args.target <= 0 or (not args.folder and any(rows <= 0 for rows in args.rows)):
        parser.error("행 수와 목표 점수는 0보다 커야 합니다")
    results = []
    try:
        if args.folder:
            if args.json_path:
                report_path = Path(args.json_path).resolve()
                input_paths = {Path(item.path).resolve() for item in collect_csv_files(args.folder)}
                if report_path in input_paths:
                    raise ValueError("JSON 보고서 경로가 입력 데이터 파일과 겹칩니다")
            results.append(measure(args.folder, 0, False, args.target, args.seed))
        else:
            with tempfile.TemporaryDirectory(prefix="reduce-compare-benchmark-") as temp:
                for rows in args.rows:
                    folder = Path(temp) / str(rows)
                    generate(folder, rows, args.seed)
                    results.append(measure(str(folder), rows, True, args.target, args.seed))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"벤치마크 실패: {exc}\n")
    print("합성" if not args.folder else "실제 폴더", "· 단계별 시간 (초)")
    print("요청→실제 행                 전체     탐색/스키마  병합/전처리  크기 탐색  방식 비교  투영  목표")
    for result in results:
        seconds = result["seconds"]
        requested = f"{result['requested_rows']:,}" if result["requested_rows"] else "폴더"
        print(f"{requested:>9}→{result['total_rows']:<9,} {seconds['total_pipeline']:>8.2f}"
              f" {seconds['discovery_schema']:>12.2f} {seconds['merge_prepare']:>11.2f}"
              f" {seconds['size_search']:>9.2f} {seconds['method_compare']:>9.2f}"
              f" {seconds['projection']:>6.2f}  {'달성' if result['goal_met'] else '초과'}")
        for skipped in result["skipped"]:
            print(f"  건너뜀 그룹 {skipped['group']}: {skipped['reason']}")
    if args.json_path:
        report = {"environment": {"python": platform.python_version(),
                                   "platform": platform.platform(),
                                   "cpu_count": os.cpu_count()}, "results": results}
        output = Path(args.json_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
