"""Accepted-set distributions and pairwise variation (T079)."""
from __future__ import annotations

import os
from itertools import combinations

import numpy as np
import pandas as pd

from app.core.catmetrics import distribution_table

PAIR_COLUMNS = ['set_a', 'set_b', 'mean_tv', 'max_tv', 'unit_jaccard']
DETAIL_COLUMNS = ['set_a', 'set_b', 'column', 'tv_distance', 'max_gap_pp']


def _ratios(rows, weights, columns):
    return {c: pd.Series(weights, index=rows[c].astype(str)).groupby(level=0).sum()
            / np.sum(weights) for c in columns}


def _units(rows, columns):
    # Tagged tokens avoid conflating a missing value with the literal string 'nan'.
    return {tuple(('missing', '') if pd.isna(v) else (type(v).__name__, str(v)) for v in row)
            for row in rows[columns].itertuples(index=False, name=None)}


class SetReports:
    """Keep compact full-category ratios and unit identities, not full frames."""

    def __init__(self, original, args, folder, columns):
        self.original, self.args, self.folder = original, args, folder
        self.columns = columns
        self.shown = ([c.strip() for c in args.show_dist.split(',') if c.strip() in columns]
                      if args.show_dist else [c for c in columns if original[c].nunique() <= 20])
        self.original_ratios = _ratios(original, np.ones(len(original)), columns)
        self.entries = []
        self.distributions = os.path.join(folder, "distributions")
        os.makedirs(self.distributions, exist_ok=True)

    def add(self, index, red, rows):
        table = distribution_table(self.original, rows, self.columns, red.weights,
                                   top=self.args.dist_top)
        table.to_csv(os.path.join(self.distributions, f'set_{index:03d}.csv'),
                     index=False, encoding='utf-8-sig')
        if not self.args.no_plot:
            from plot_distribution import save_distribution_chart

            from app.core.grouped import unit_table
            sizes = (unit_table(self.original, red.unit_cols, red.strata_cols)['rows'].to_numpy(),
                     unit_table(rows, red.unit_cols, red.strata_cols)['rows'].to_numpy())
            save_distribution_chart(self.distributions, f'set_{index:03d}', table,
                                    self.shown, sizes)
        self.entries.append((_ratios(rows, red.weights, self.columns),
                             _units(rows, red.unit_cols)))

    def finish(self):
        pairs, details = [], []
        for i, j in combinations(range(len(self.entries)), 2):
            a, units_a = self.entries[i]
            b, units_b = self.entries[j]
            distances = []
            for col in self.columns:
                x, y = a[col].align(b[col], fill_value=0)
                gap = (x - y).abs()
                tv = float(gap.sum() / 2)
                distances.append(tv)
                details.append([i + 1, j + 1, col, tv, float(gap.max() * 100)])
            union = units_a | units_b
            overlap = len(units_a & units_b) / len(union) if union else 1.0
            pairs.append([i + 1, j + 1, float(np.mean(distances)) if distances else 0,
                          max(distances, default=0), overlap])
        table = pd.DataFrame(pairs, columns=PAIR_COLUMNS)
        table.to_csv(os.path.join(self.folder, 'comparisons.csv'),
                     index=False, encoding='utf-8-sig')
        pd.DataFrame(details, columns=DETAIL_COLUMNS).to_csv(
            os.path.join(self.folder, 'distribution_differences.csv'),
            index=False, encoding='utf-8-sig')
        if not self.args.no_plot and self.entries:
            _overview_chart(self.folder, self.original_ratios, self.entries, self.shown)
            if len(self.entries) > 1:
                _comparison_chart(self.folder, table, min(40, len(self.entries)))
        print(f"  세트별 분포와 세트 쌍 비교: {self.folder}")
        return table


def _matrix(table, key, count):
    """세트 쌍 값을 대칭 행렬로 편다. 자기 자신 칸은 비워 색 범위를 잡아먹지 않게 한다."""
    values = np.full((count, count), np.nan)
    for row in table.itertuples(index=False):
        if row.set_a <= count and row.set_b <= count:
            values[row.set_a - 1, row.set_b - 1] = getattr(row, key)
            values[row.set_b - 1, row.set_a - 1] = getattr(row, key)
    return values


def _span(values):
    """비대각 값의 실제 범위. 0~1 고정이면 비슷한 세트가 모두 같은 색으로 보인다."""
    if not np.isfinite(values).any():
        return 0.0, 1.0
    low, high = float(np.nanmin(values)), float(np.nanmax(values))
    return (low - 0.005, high + 0.005) if high - low < 1e-12 else (low, high)


def _draw(ax, values, title, count, cmap):
    low, high = _span(values)
    im = ax.imshow(values, vmin=low, vmax=high, cmap=cmap)
    ax.set_title(title, fontsize=11)
    ax.set_xlabel('Set')
    ax.set_ylabel('Set')
    if count > 10:
        return im
    ax.set_xticks(range(count), range(1, count + 1))
    ax.set_yticks(range(count), range(1, count + 1))
    for i, j in np.ndindex(values.shape):
        if np.isfinite(values[i, j]):
            dark = (values[i, j] - low) / (high - low) < 0.55
            ax.text(j, i, f"{values[i, j]:.3f}", ha='center', va='center',
                    fontsize=7, color='#FFFFFF' if dark else '#111111')
    return im


def _comparison_chart(folder, table, count):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cmap = matplotlib.colormaps['viridis'].with_extremes(bad='#E5E5E5')
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    titles = ['Distribution difference (mean TV)', 'Selected-unit overlap (Jaccard)']
    for ax, key, title in zip(axes, ['mean_tv', 'unit_jaccard'], titles):
        fig.colorbar(_draw(ax, _matrix(table, key, count), title, count, cmap), ax=ax)
    fig.suptitle(f'Set comparison (first {count} sets; CSV includes all pairs)\n'
                 'Color scale spans each panel\'s own range, not 0 to 1', fontsize=11)
    fig.tight_layout(rect=[0, 0.03, 1, 0.92])
    fig.savefig(os.path.join(folder, 'comparison.png'), dpi=120)
    plt.close(fig)


def _overview_values(original, entries, column, limit=12):
    reduced = [entry[0][column] for entry in entries]
    values = original[column].index.union(pd.Index(np.concatenate([x.index for x in reduced])))
    matrix = np.array([[series.get(value, 0.0) for value in values] for series in reduced])
    center = np.median(matrix, axis=0)
    orig = original[column].reindex(values, fill_value=0).to_numpy()
    order = np.argsort(np.maximum(orig, matrix.max(axis=0)))[::-1]
    order = order[:limit]
    return (values[order], orig[order], center[order], matrix[:, order].min(axis=0),
            matrix[:, order].max(axis=0))


def _overview_chart(folder, original, entries, columns):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    shown = columns[:6]
    if not shown:
        return
    rows = int(np.ceil(len(shown) / 2))
    fig, axes = plt.subplots(rows, 2, figsize=(13, 3.8 * rows), squeeze=False)
    for ax, column in zip(axes.ravel(), shown):
        values, orig, center, low, high = _overview_values(original, entries, column)
        x = np.arange(len(values))
        ax.fill_between(x, low * 100, high * 100, color='#54A7E8', alpha=.25,
                        label='set min–max')
        ax.plot(x, center * 100, color='#1976B9', marker='o', label='set median')
        ax.plot(x, orig * 100, color='#62676D', marker='s', linestyle='--', label='original')
        ax.set_title(column)
        ax.set_ylabel('%')
        ax.set_xticks(x, [str(value)[:18] for value in values], rotation=35, ha='right')
    for ax in axes.ravel()[len(shown):]:
        ax.axis('off')
    axes.ravel()[0].legend(fontsize=9)
    fig.suptitle(f'Distribution overview across {len(entries)} accepted sets')
    fig.tight_layout(rect=[0, 0, 1, .96])
    fig.savefig(os.path.join(folder, 'distribution_overview.png'), dpi=120)
    plt.close(fig)
