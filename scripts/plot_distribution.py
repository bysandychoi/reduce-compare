"""컬럼별 값 분포 비교 그림 (run_reduce_units.py에서 사용)."""
from __future__ import annotations

import os

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from plot_compare import BG, ORIG, RED, _pick_font  # noqa: E402

MAX_PANELS = 6
MAX_VALUES = 12


def _panel(ax, block, col, labels):
    """컬럼 하나의 값별 비율을 가로 막대로 그린다."""
    block = block.head(MAX_VALUES).iloc[::-1]
    y = np.arange(len(block))
    ax.barh(y + 0.2, block["orig_ratio"] * 100, 0.4, color=ORIG, label=labels["orig"])
    ax.barh(y - 0.2, block["reduced_ratio"] * 100, 0.4, color=RED, label=labels["red"])
    ax.set_yticks(y)
    ax.set_yticklabels([str(v)[:18] for v in block["value"]], fontsize=9)
    ax.set_title(col, fontsize=11)
    ax.set_xlabel("%", fontsize=9)
    worst = block["gap_pp"].abs().max()
    ax.text(0.98, 0.02, f"max {worst:.2f}%p", transform=ax.transAxes, ha="right",
            fontsize=9, color="#555A61")


def save_distribution_chart(out_dir: str, name: str, table, columns: list[str],
                            unit_rows: tuple[np.ndarray, np.ndarray] | None = None) -> str:
    """값 분포 비교 그림을 저장하고 경로를 돌려준다."""
    labels = _pick_font()
    cols = [c for c in columns if not table[table["column"] == c].empty][:MAX_PANELS]
    panels = len(cols) + (1 if unit_rows is not None else 0)
    if panels == 0:
        raise ValueError("그릴 컬럼이 없습니다")
    ncol = 2 if panels > 1 else 1
    nrow = int(np.ceil(panels / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(6.5 * ncol, 3.4 * nrow), facecolor=BG)
    axes = np.atleast_1d(axes).ravel()
    for ax in axes:
        ax.set_facecolor("#FFFFFF")

    for ax, col in zip(axes, cols):
        _panel(ax, table[table["column"] == col], col, labels)
    axes[0].legend(fontsize=9)

    if unit_rows is not None:
        ax = axes[len(cols)]
        a, b = unit_rows
        bins = np.arange(0.5, max(a.max(), b.max()) + 1.5)
        ax.hist(a, bins=bins, density=True, color=ORIG, alpha=0.5, label=labels["orig"])
        ax.hist(b, bins=bins, density=True, histtype="step", lw=2, color=RED, label=labels["red"])
        ax.set_title("단위당 행 수" if labels is not None and "원본" in labels["orig"]
                     else "rows per unit", fontsize=11)
        ax.legend(fontsize=9)

    for ax in axes[panels:]:
        ax.axis("off")
    fig.suptitle(f"[{name}] {labels['title']}", fontsize=13, y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"distribution_{name}.png")
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
