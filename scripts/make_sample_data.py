#!/usr/bin/env python3
"""테스트용 CSV 샘플 데이터 생성기 (T015).

축소·유사도 파이프라인을 시험할 수 있도록 군집 구조, 희소 그룹, 이상치, 결측치가
섞인 표 데이터를 만든다. 같은 구조의 파일 여러 개(그룹 A)와 다른 구조의 파일
하나(그룹 B)를 함께 만들어 폴더 구성 자동 판별도 시험할 수 있다.

사용 예:
  python3 scripts/make_sample_data.py --rows 100000 --out sample_data/sales
  python3 scripts/make_sample_data.py --rows 500000 --files 3 --encoding cp949
"""
import argparse
import os

import numpy as np
import pandas as pd

# (이름, 비율, 소득 중심, 방문 중심, 할인 중심, 재직 개월 중심)
CLUSTERS = [
    ("일반", 0.362, 4200, 8, 0.10, 30),
    ("고소득", 0.188, 9800, 12, 0.05, 44),
    ("저방문할인", 0.273, 3100, 3, 0.28, 22),
    ("신규", 0.120, 3600, 6, 0.15, 4),
    ("장기VIP", 0.037, 11500, 20, 0.08, 96),
    ("희소", 0.020, 2600, 26, 0.42, 12),
]
REGIONS = ["수도권", "영남", "호남", "충청", "기타"]
REGION_P = [0.412, 0.235, 0.129, 0.118, 0.106]
PLANS = ["basic", "plus", "pro"]
CHANNELS = ["app", "web", "store"]


def make_group_a(rows, rng, start_id=0):
    """그룹 A: 매출 데이터 14개 컬럼."""
    sizes = np.random.multinomial(rows, [c[1] for c in CLUSTERS])
    frames = []
    for (name, _, inc, vis, disc, ten), n in zip(CLUSTERS, sizes):
        if n == 0:
            continue
        income = rng.normal(inc, inc * 0.18, n).clip(500, None)
        visits = rng.normal(vis, max(1.5, vis * 0.25), n).clip(0, None)
        discount = rng.normal(disc, 0.04, n).clip(0, 0.9)
        tenure = rng.normal(ten, max(2, ten * 0.3), n).clip(0, None)
        frames.append(pd.DataFrame({
            "region": rng.choice(REGIONS, n, p=REGION_P),
            "plan": rng.choice(PLANS, n, p=[0.5, 0.35, 0.15]),
            "channel": rng.choice(CHANNELS, n, p=[0.55, 0.3, 0.15]),
            "is_member": rng.choice([True, False], n, p=[0.7, 0.3]),
            "age": rng.normal(20 + tenure * 0.25, 9).clip(18, 88).round(0),
            "income": income.round(0),
            "visits": visits.round(0),
            "score": (50 + visits * 1.1 + rng.normal(0, 9, n)).clip(0, 100).round(1),
            "tenure": tenure.round(0),
            "spend": (income * 0.22 + visits * 45 + rng.normal(0, 260, n)).clip(0, None).round(0),
            "discount_rate": discount.round(3),
            "cluster": name,
        }))
    df = pd.concat(frames, ignore_index=True)
    df = df.sample(frac=1, random_state=rng.integers(1 << 30)).reset_index(drop=True)
    df.insert(0, "store_id", [f"S{(start_id + i) % 400:03d}" for i in range(len(df))])
    df.insert(0, "date", pd.to_datetime("2024-01-01") +
              pd.to_timedelta(rng.integers(0, 365, len(df)), unit="D"))
    df["memo"] = ["-" if i % 7 else f"메모 {i}" for i in range(len(df))]
    return df


def add_outliers(df, rng, ratio=0.001):
    """극단값 행을 섞는다 (이상치 판정 시험용)."""
    n = max(1, int(len(df) * ratio))
    idx = rng.choice(len(df), n, replace=False)
    df.loc[idx, "discount_rate"] = rng.uniform(0.9, 1.0, n).round(3)
    df.loc[idx, "visits"] = rng.integers(60, 120, n)
    df.loc[idx, "spend"] = rng.integers(20000, 40000, n)
    return df


def add_missing(df, rng, ratio=0.02):
    """결측치를 섞는다 (결측 행 제외 규칙 시험용)."""
    for col in ["income", "score", "plan"]:
        idx = rng.choice(len(df), int(len(df) * ratio), replace=False)
        df.loc[idx, col] = np.nan
    return df


def make_group_b(rows, rng):
    """그룹 B: 구조가 다른 고객 데이터 9개 컬럼."""
    tier = rng.choice(["bronze", "silver", "gold"], rows, p=[0.6, 0.3, 0.1])
    ltv = np.where(tier == "gold", rng.normal(90000, 20000, rows),
                   np.where(tier == "silver", rng.normal(40000, 12000, rows),
                            rng.normal(15000, 6000, rows))).clip(0, None)
    return pd.DataFrame({
        "customer_id": [f"C{i:07d}" for i in range(rows)],
        "signup": pd.to_datetime("2022-01-01") + pd.to_timedelta(rng.integers(0, 1000, rows), unit="D"),
        "tier": tier,
        "age": rng.normal(41, 12, rows).clip(18, 90).round(0),
        "ltv": ltv.round(0),
        "orders": rng.poisson(6, rows),
        "refunds": rng.poisson(0.4, rows),
        "nps": rng.integers(0, 11, rows),
        "active": rng.choice([True, False], rows, p=[0.8, 0.2]),
    })


def write_csv(df, path, encoding):
    df.to_csv(path, index=False, encoding=encoding)
    print(f"  {path}  {len(df):,}행 × {df.shape[1]}열  ({os.path.getsize(path) / 1e6:.1f} MB, {encoding})")


def main():
    ap = argparse.ArgumentParser(description="테스트용 CSV 샘플 데이터 생성기")
    ap.add_argument("--rows", type=int, default=10000, help="그룹 A 전체 행 수 (기본 10000)")
    ap.add_argument("--files", type=int, default=3, help="그룹 A 파일 수 (기본 3)")
    ap.add_argument("--out", default="sample_data/sales", help="출력 폴더")
    ap.add_argument("--encoding", default="utf-8", help="CSV 인코딩 (utf-8, cp949 등)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-group-b", action="store_true", help="구조가 다른 파일을 만들지 않음")
    ap.add_argument("--clean", action="store_true", help="결측치·이상치를 섞지 않음")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    np.random.seed(args.seed)
    os.makedirs(args.out, exist_ok=True)
    print(f"샘플 데이터 생성: {args.out}")

    per = args.rows // args.files
    for i in range(args.files):
        n = per if i < args.files - 1 else args.rows - per * (args.files - 1)
        df = make_group_a(n, rng, start_id=i * per)
        if not args.clean:
            df = add_missing(add_outliers(df, rng), rng)
        write_csv(df, os.path.join(args.out, f"sales_2024_{i + 1:02d}.csv"), args.encoding)

    if not args.no_group_b:
        write_csv(make_group_b(max(1000, args.rows // 4), rng),
                  os.path.join(args.out, "customers.csv"), args.encoding)

    with open(os.path.join(args.out, "readme.txt"), "w", encoding="utf-8") as f:
        f.write("CSV가 아닌 파일 (폴더 스캔에서 제외되는지 확인용)\n")
    print("완료")


if __name__ == "__main__":
    main()
