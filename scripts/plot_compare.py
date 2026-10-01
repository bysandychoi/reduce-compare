"""축소 전·후 비교 그림 (run_reduce.py에서 사용)."""
from __future__ import annotations

import os

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from sklearn.decomposition import PCA  # noqa: E402

# 원본은 바탕 기준 회색, 축소본은 파란색 (회색 대비 ΔE 22.4, 색각 이상 시뮬레이션 최저 ΔE 12.3)
ORIG, RED, BG = "#8B93A1", "#2563EB", "#F7F6F2"
KOREAN_FONTS = ("Malgun Gothic", "AppleGothic", "Apple SD Gothic Neo", "NanumGothic",
                "Noto Sans CJK KR", "Noto Sans CJK JP", "IPAGothic")
LABELS_KO = {"orig": "원본", "red": "축소본", "dist": "분포 비교", "group": "그룹 비율 (%)",
             "title": "축소 전 · 후 비교"}
LABELS_EN = {"orig": "original", "red": "reduced", "dist": "distribution",
             "group": "group ratio (%)", "title": "before / after reduction"}


def _pick_font() -> dict:
    """한글 글꼴이 있으면 한글 라벨, 없으면 영문 라벨을 쓴다."""
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in KOREAN_FONTS:
        if name in available:
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            return LABELS_KO
    return LABELS_EN


def _scatter(ax, points, color, title, sizes=None, bounds=None):
    ax.scatter(points[:, 0], points[:, 1], s=sizes if sizes is not None else 2,
               c=color, alpha=0.5 if sizes is None else 0.8, linewidths=0)
    ax.set_title(title, fontsize=11)
    if bounds is not None:
        ax.set_xlim(bounds[0]), ax.set_ylim(bounds[1])


def _group_bars(ax, df, red_df, w, col, labels):
    """범주 컬럼 하나의 원본·축소본(가중) 비율을 가로 막대로 그린다."""
    orig_ratio = df[col].astype(str).value_counts(normalize=True)
    red_ratio = (pd.Series(w, index=red_df[col].astype(str).to_numpy())
                 .groupby(level=0).sum() / w.sum())
    order = list(orig_ratio.index[:12])
    y = np.arange(len(order))
    ax.barh(y + 0.2, [orig_ratio.get(c, 0) * 100 for c in order], 0.4,
            color=ORIG, label=labels["orig"])
    ax.barh(y - 0.2, [red_ratio.get(c, 0) * 100 for c in order], 0.4,
            color=RED, label=labels["red"])
    ax.set_yticks(y)
    ax.set_yticklabels(order)
    ax.invert_yaxis()
    ax.set_title(f"{labels['group']} · {col}", fontsize=11)
    ax.legend(fontsize=9)


def save_comparison(out_dir: str, name: str, prepared, best, sample: int = 20000) -> str:
    """PCA 산점도·분포·그룹 비율을 한 장으로 저장하고 경로를 돌려준다."""
    labels = _pick_font()
    df, x, w = prepared.frame, prepared.features, best.reduction.weights
    red_df = best.frame
    idx = np.random.default_rng(0).choice(len(x), min(sample, len(x)), replace=False)
    pca = PCA(2, random_state=0).fit(x)
    po = pca.transform(x[idx])
    xr = (x[best.reduction.indices] if len(best.reduction.indices)
          else np.vstack([x[m].mean(axis=0) for m in best.reduction.members]))
    pr = pca.transform(xr)
    bounds = ((po[:, 0].min(), po[:, 0].max()), (po[:, 1].min(), po[:, 1].max()))

    numeric = [c for c in prepared.used_columns
               if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    categorical = [c for c in prepared.used_columns if c not in numeric]
    fig, ax = plt.subplots(2, 2, figsize=(13, 9), facecolor=BG)
    for a in ax.ravel():
        a.set_facecolor("#FFFFFF")

    _scatter(ax[0, 0], po, ORIG, f"{labels['orig']} {len(df):,} ({len(idx):,})", bounds=bounds)
    _scatter(ax[0, 1], pr, RED, f"{labels['red']} {best.size:,} ({best.size / len(df) * 100:.2f}%)",
             sizes=np.clip(w / w.mean() * 6, 2, 40), bounds=bounds)

    if numeric:
        col = numeric[0]
        bins = np.linspace(df[col].quantile(0.001), df[col].quantile(0.999), 40)
        ax[1, 0].hist(df[col], bins=bins, density=True, color=ORIG, alpha=0.45, label=labels["orig"])
        ax[1, 0].hist(red_df[col], bins=bins, weights=w, density=True, histtype="step",
                      lw=2, color=RED, label=labels["red"])
        ax[1, 0].set_title(f"{labels['dist']} · {col}", fontsize=11)
        ax[1, 0].legend(fontsize=9)

    if categorical:
        _group_bars(ax[1, 1], df, red_df, w, categorical[0], labels)

    fig.suptitle(f"[{name}] {labels['title']} — {best.score:.1f}", fontsize=13, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"compare_{name}.png")
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
