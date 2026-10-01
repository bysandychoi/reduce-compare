"""run_reduce_units.py의 --limit 처리 (행 필터 → 단위 컬럼 선택 순서)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.core.valuelimit import choose_values, limit_values, parse_limits, split_limits  # noqa: E402
from units_report import print_limit, print_unit_pick  # noqa: E402


def apply_limits(df, args):
    """--limit을 적용한다. 행 필터(예: eqp_id)를 먼저, 단위 컬럼(예: lot_id)은 그 뒤에 고른다.

    돌려주는 keep은 단위 컬럼별로 고른 값 목록이다. keep이 있으면 --ratio 축소 대신 그 값의
    단위를 모두 남긴다 (lot_id=100이면 결과 lot이 정확히 100개).
    """
    limits = parse_limits(args.limit)
    missing = [c for c in limits if c not in df.columns]
    if missing:
        raise ValueError(f"데이터에 없는 컬럼입니다: {', '.join(missing)}")
    row_limits, unit_limits = split_limits(limits, args.unit_cols)
    infos = []
    if row_limits:
        df, row_infos = limit_values(df, row_limits, args.limit_mode, args.seed)
        for info in row_infos:
            print_limit(info)
        infos = [info.__dict__ for info in row_infos]
    keep, unit_infos = pick_unit_values(df, unit_limits, args)
    return df, keep, infos + unit_infos


def pick_unit_values(df, unit_limits, args):
    """단위 컬럼 limit을 적힌 순서대로 고른다. 뒤 컬럼이 앞 컬럼 값을 줄일 수 있어,
    개수가 정확히 보장되는 것은 마지막에 적은 컬럼이다. 화면과 기록에는 실제로 남은 개수를 쓴다."""
    for col, keep_n in unit_limits.items():
        if keep_n < 1:
            raise ValueError(f"{col}: 남길 개수는 1 이상이어야 합니다")
    keep, before, pool = {}, {}, df
    for col, keep_n in unit_limits.items():
        before[col] = pool[col].nunique()
        keep[col] = choose_values(pool[col], keep_n, args.limit_mode, args.seed)
        pool = pool[pool[col].astype(str).isin(keep[col])]
    if keep and pool.empty:
        raise ValueError("단위 컬럼 limit으로 고른 값이 겹치지 않아 남는 행이 없습니다")
    infos = []
    for col in keep:
        final = sorted(pool[col].astype(str).unique())
        print_unit_pick(col, before[col], len(keep[col]), len(final), args.limit_mode)
        keep[col] = final
        infos.append({"column": col, "unit_column": True, "levels_before": before[col],
                      "levels_picked": unit_limits[col], "levels_after": len(final),
                      "mode": args.limit_mode, "kept": final})
    return keep, infos
