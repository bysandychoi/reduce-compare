#!/usr/bin/env python3
"""유사도 지표 설명 그림을 만든다 (T126).

지표마다 '잘 줄인 예'와 '잘못 줄인 예'를 실제 지표 함수로 계산하고, 그 점수를 그림에 적는다.
    python scripts/make_metric_figures.py --font NanumGothic.ttf   # 결과: docs/images/metrics/*.png
--font가 없으면 설치된 글꼴 중 한글 글리프가 실제로 있는 것을 찾고, 없으면 그림을 쓰기 전에 멈춘다.
(글꼴 파일은 저장소에 넣지 않는다.)
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
sys.path.insert(0, HERE)

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager, ft2font  # noqa: E402
from plot_compare import BG, ORIG, RED  # noqa: E402

from app.core.catmetrics import unit_size_score  # noqa: E402
from app.core.metrics import categorical_metrics, correlation_metrics, numeric_metrics  # noqa: E402
from app.core.structure import overall_score, structure_metrics  # noqa: E402

RNG = np.random.default_rng(7)
INK, MUTED = "#2B2F36", "#6B7280"


def _fig(ncols, title, width=5.2):
    fig, axes = plt.subplots(1, ncols, figsize=(width * ncols, 3.9), facecolor=BG)
    axes = np.atleast_1d(axes)
    for ax in axes:
        ax.set_facecolor("#FFFFFF")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.suptitle(title, fontsize=13, color=INK, y=0.99)
    return fig, axes


def _save(fig, out, name):
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    path = os.path.join(out, name)
    fig.savefig(path, dpi=110)
    plt.close(fig)
    print("  저장:", path)


def overview(out):
    """종합 점수가 어떤 점수들의 평균인지 보여 준다."""
    fig, ax = plt.subplots(figsize=(10.4, 3.6), facecolor=BG)
    ax.axis("off")
    rows = [("행 단위 축소 (run_reduce.py)", ["분포", "상관", "구조"]),
            ("묶음 단위 축소 (run_reduce_units.py)", ["컬럼 비율", "조합 비율", "단위 크기"])]
    for r, (label, parts) in enumerate(rows):
        y = 0.68 - r * 0.5
        ax.text(0.0, y + 0.13, label, fontsize=12, color=INK, transform=ax.transAxes)
        for i, part in enumerate(parts):
            x = 0.02 + i * 0.25
            ax.add_patch(plt.Rectangle((x, y - 0.08), 0.22, 0.16, transform=ax.transAxes,
                                       color=RED, alpha=0.12 + 0.1 * i, ec="none"))
            ax.text(x + 0.11, y, f"{part}\n× 1/3", ha="center", va="center", fontsize=11,
                    color=INK, transform=ax.transAxes)
            ax.text(x + 0.235, y, "+" if i < 2 else "=", ha="center", va="center",
                    fontsize=14, color=MUTED, transform=ax.transAxes)
        ax.text(0.80, y, "종합 유사도\n0~100점", ha="left", va="center", fontsize=12,
                color=INK, transform=ax.transAxes)
    ex = overall_score(94.6, 83.1, 91.5)
    ax.text(0.0, -0.08, f"예: 종합 = (분포 {ex.distribution} + 상관 {ex.correlation} + 구조 {ex.structure}) "
            f"÷ 3 = {ex.total}점 (overall_score 계산)", fontsize=10, color=MUTED, transform=ax.transAxes)
    fig.suptitle("종합 유사도는 세 점수의 평균", fontsize=13, color=INK)
    _save(fig, out, "overview.png")


def numeric(out):
    """수치형: 분포 모양(KS)과 평균·표준편차가 같은지."""
    orig = pd.Series(RNG.gamma(3.0, 12.0, 6000), name="age")
    good = orig.sample(300, random_state=1)
    bad = orig[orig > orig.median()].sample(300, random_state=1)
    fig, axes = _fig(2, "수치형 분포 — 막대 모양과 평균·표준편차가 같은가")
    bins = np.linspace(0, orig.quantile(0.995), 35)
    for ax, red, label in zip(axes, (good, bad), ("잘 줄인 예: 무작위 300행", "잘못 줄인 예: 큰 값만 300행")):
        m = numeric_metrics(orig, red.reset_index(drop=True), np.ones(len(red)))
        ax.hist(orig, bins=bins, density=True, color=ORIG, alpha=0.5, label="원본")
        ax.hist(red, bins=bins, density=True, histtype="step", lw=2, color=RED, label="축소본")
        ax.set_title(f"{label}\n{m.score:.1f}점 · KS {m.detail['ks']:.2f} · "
                     f"평균 차 {m.detail['mean_diff_ratio'] * 100:.0f}% · "
                     f"표준편차 차 {m.detail['std_diff_ratio'] * 100:.0f}%", fontsize=10, color=INK)
        ax.legend(fontsize=9, frameon=False)
    _save(fig, out, "numeric.png")


def categorical(out):
    """범주형: 값마다 비율이 같은지 (JS 거리, 최대 비율 차)."""
    levels = np.array(["A", "B", "C", "D"])
    orig = pd.Series(RNG.choice(levels, 4000, p=[0.5, 0.3, 0.15, 0.05]), name="grade")
    good = orig.sample(200, random_state=2)
    bad = pd.Series(RNG.choice(levels[:3], 200, p=[0.7, 0.2, 0.1]), name="grade")
    fig, axes = _fig(2, "범주형 비율 — 값마다 차지하는 비율이 같은가")
    y = np.arange(len(levels))
    for ax, red, label in zip(axes, (good, bad), ("잘 줄인 예", "잘못 줄인 예: D가 빠지고 A가 많음")):
        m = categorical_metrics(orig, red.reset_index(drop=True), np.ones(len(red)))
        p = orig.value_counts(normalize=True).reindex(levels, fill_value=0) * 100
        q = red.value_counts(normalize=True).reindex(levels, fill_value=0) * 100
        ax.barh(y - 0.2, p, 0.4, color=ORIG, label="원본")       # 뒤집은 축에서 원본이 위
        ax.barh(y + 0.2, q, 0.4, color=RED, label="축소본")
        ax.set_yticks(y, levels)
        ax.invert_yaxis()
        ax.set_xlabel("%")
        ax.set_title(f"{label}\n{m.score:.1f}점 · JS 거리 {m.detail['js_divergence']:.2f} · "
                     f"최대 비율 차 {m.detail['max_ratio_gap'] * 100:.1f}%p", fontsize=10, color=INK)
        ax.legend(fontsize=9, frameon=False, loc="lower right")
    _save(fig, out, "categorical.png")


def correlation(out):
    """상관: 컬럼끼리 함께 움직이는 관계가 남았는지."""
    n = 3000
    x = RNG.normal(0, 1, n)
    df = pd.DataFrame({"방문": x, "구매": 0.8 * x + RNG.normal(0, 0.6, n),
                       "할인": -0.5 * x + RNG.normal(0, 0.9, n), "나이": RNG.normal(0, 1, n)})
    good = df.sample(200, random_state=3)
    bad = df[df["방문"].between(-0.3, 0.3)].sample(200, random_state=3)
    fig, axes = _fig(3, "상관 보존 — 컬럼끼리의 관계(상관계수)가 그대로인가", width=4.2)
    cols = list(df.columns)
    for ax, red, label in zip(axes, (df, good, bad),
                              ("원본", "잘 줄인 예", "잘못 줄인 예: 방문이 비슷한 행만")):
        m = correlation_metrics(df, red, [], cols)
        mat = np.array(m["matrix_reduced"])
        ax.imshow(mat, cmap="PRGn", vmin=-1, vmax=1)
        ax.set_xticks(range(len(cols)), cols, fontsize=9)
        ax.set_yticks(range(len(cols)), cols, fontsize=9)
        for i in range(len(cols)):
            for j in range(len(cols)):
                ax.text(j, i, f"{round(mat[i, j], 1) + 0.0:.1f}", ha="center", va="center", fontsize=9,
                        color="white" if abs(mat[i, j]) > 0.6 else INK)
        sub = "" if red is df else f"\n{m['score']:.1f}점 · 평균 차 {m['mean_gap']:.2f} · 최대 차 {m['max_gap']:.2f}"
        ax.set_title(label + sub, fontsize=10, color=INK)
    _save(fig, out, "correlation.png")


def structure(out):
    """구조: 축소본 점이 원본 점들을 고르게 덮는지 (커버리지)."""
    centers = np.array([[0, 0], [6, 1], [2, 6]])
    x = np.vstack([RNG.normal(c, [1.2, 0.8], (n, 2)) for c, n in zip(centers, (1800, 900, 300))])
    good = x[RNG.choice(len(x), 120, replace=False)]
    bad = x[:1800][RNG.choice(1800, 120, replace=False)]
    fig, axes = _fig(2, "구조 보존 — 축소본 점(파랑)이 원본(회색)을 고르게 덮는가")
    for ax, red, label in zip(axes, (good, bad), ("잘 줄인 예", "잘못 줄인 예: 한 무리에서만")):
        m = structure_metrics(x, red)
        score, cov, trust = m["score"], m["coverage"], m["trustworthiness"]
        ax.scatter(x[:, 0], x[:, 1], s=3, color=ORIG, alpha=0.35, linewidths=0, label="원본")
        ax.scatter(red[:, 0], red[:, 1], s=14, color=RED, alpha=0.9, linewidths=0, label="축소본")
        ax.set_title(f"{label}\n구조 {score:.1f}점 = 커버리지 {cov['score']:.1f} × ½ "
                     f"+ 투영 신뢰도 {trust * 100:.1f} × ½\n(2차원 예제라 투영 신뢰도는 항상 100)",
                     fontsize=10, color=INK)
        ax.legend(fontsize=9, frameon=False, markerscale=2)
        ax.set_xticks([]), ax.set_yticks([])
    _save(fig, out, "structure.png")


def unit_size(out):
    """단위 크기: 묶음 하나가 갖는 행 수의 분포가 같은지."""
    sizes = RNG.choice(np.arange(1, 9), 600, p=[0.25, 0.2, 0.15, 0.12, 0.1, 0.08, 0.06, 0.04])
    df = pd.DataFrame({"lot": np.repeat(np.arange(len(sizes)), sizes), "층": "S"})
    good_lots = RNG.choice(len(sizes), 120, replace=False)
    bad_lots = np.flatnonzero(sizes >= 4)[:120]
    fig, axes = _fig(2, "단위 크기 — 묶음 하나가 몇 행인지의 분포가 같은가")
    bins = np.arange(0.5, 9.5)
    for ax, lots, label in zip(axes, (good_lots, bad_lots), ("잘 줄인 예", "잘못 줄인 예: 큰 묶음만")):
        red = df[df["lot"].isin(lots)]
        m = unit_size_score(df, red, ["lot"], ["층"])
        ax.hist(sizes, bins=bins, density=True, color=ORIG, alpha=0.5, label="원본")
        ax.hist(sizes[lots], bins=bins, density=True, histtype="step", lw=2, color=RED, label="축소본")
        ax.set_xlabel("묶음 하나의 행 수")
        ax.set_title(f"{label}\n{m['score']:.1f}점 · KS {m['ks']:.2f} · 평균 행 수 원본 {m['mean_orig']:.1f} / "
                     f"축소 {m['mean_reduced']:.1f}", fontsize=10, color=INK)
        ax.legend(fontsize=9, frameon=False)
    _save(fig, out, "unit_size.png")


def _has_hangul(path):
    """글꼴 파일에 한글 글리프가 실제로 있는지 확인한다.

    LastResort처럼 모든 글자에 같은 대체 글리프를 넣은 글꼴을 거르려고, 서로 다른 한글 글자가
    서로 다른 글리프를 갖는지도 본다.
    """
    try:
        face = ft2font.FT2Font(path)
    except (OSError, RuntimeError, ValueError):
        return False
    glyphs = [face.get_char_index(ord(ch)) for ch in "원본가"]
    return all(glyphs) and len(set(glyphs)) == len(glyphs)


def main():
    ap = argparse.ArgumentParser(description="유사도 지표 설명 그림 생성")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "docs", "images", "metrics"))
    ap.add_argument("--font", default=None, help="한글 글꼴 파일(.ttf) 경로")
    args = ap.parse_args()
    font = args.font or next((f.fname for f in font_manager.fontManager.ttflist
                              if _has_hangul(f.fname)), None)
    if not font or not _has_hangul(font):
        sys.exit("한글 글리프가 있는 글꼴이 없습니다. --font로 한글 .ttf를 지정하세요 (예: NanumGothic.ttf)")
    font_manager.fontManager.addfont(font)
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=font).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    print("  글꼴:", font)
    os.makedirs(args.out, exist_ok=True)
    for make in (overview, numeric, categorical, correlation, structure, unit_size):
        make(args.out)


if __name__ == "__main__":
    main()
