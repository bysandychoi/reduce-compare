"""Full-category variation, weighted distributions and composite unit overlap."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from units_set_reports import SetReports  # noqa: E402

from app.core.grouped import GroupedReduction  # noqa: E402


def args(no_plot=True):
    return SimpleNamespace(dist_top=1, no_plot=no_plot, show_dist='category')


def add(reports, index, rows, weights=None):
    weights = np.ones(len(rows)) if weights is None else np.array(weights)
    red = GroupedReduction(np.arange(len(rows)), weights, ['lot', 'step'], ['category'])
    reports.add(index, red, rows)


def test_same_distribution_can_have_no_common_units(tmp_path):
    a = pd.DataFrame({'lot': ['a', 'b'], 'step': [1, 1], 'category': ['x', 'y']})
    b = pd.DataFrame({'lot': ['c', 'd'], 'step': [1, 1], 'category': ['x', 'y']})
    reports = SetReports(pd.concat([a, b]), args(), str(tmp_path), ['category'])
    add(reports, 1, a)
    add(reports, 2, b)
    pair = reports.finish().iloc[0]
    assert pair.mean_tv == 0 and pair.unit_jaccard == 0
    assert (tmp_path / 'distributions' / 'set_001.csv').exists()
    assert not list(tmp_path.glob('*.png'))


def test_tail_categories_are_not_collapsed_for_distance(tmp_path):
    a = pd.DataFrame({'lot': ['a', 'b'], 'step': [1, 1], 'category': ['head', 'tail-a']})
    b = pd.DataFrame({'lot': ['a', 'b'], 'step': [1, 2], 'category': ['head', 'tail-b']})
    reports = SetReports(pd.concat([a, b]), args(), str(tmp_path), ['category'])
    add(reports, 1, a, [9, 1])
    add(reports, 2, b, [9, 1])
    pair = reports.finish().iloc[0]
    assert pair.mean_tv == pytest.approx(.1)
    assert pair.unit_jaccard == pytest.approx(1 / 3)
    detail = pd.read_csv(tmp_path / 'distribution_differences.csv').iloc[0]
    assert detail.max_gap_pp == pytest.approx(10)


@pytest.mark.parametrize('count', [0, 1])
def test_zero_and_one_set_have_header_only_pair_files(tmp_path, count):
    a = pd.DataFrame({'lot': ['a'], 'step': [1], 'category': ['x']})
    reports = SetReports(a, args(), str(tmp_path), ['category'])
    if count:
        add(reports, 1, a)
    assert reports.finish().empty
    assert pd.read_csv(tmp_path / 'comparisons.csv').empty


def test_plots_and_weighted_original_comparison(tmp_path):
    a = pd.DataFrame({'lot': ['a', 'b'], 'step': [1, 1], 'category': ['x', 'y']})
    reports = SetReports(a, args(False), str(tmp_path), ['category'])
    add(reports, 1, a, [3, 1])
    add(reports, 2, a, [1, 3])
    assert reports.finish().iloc[0].mean_tv == pytest.approx(.5)
    table = pd.read_csv(tmp_path / 'distributions' / 'set_001.csv')
    assert table.loc[table.value == 'x', 'reduced_ratio'].iloc[0] == .75
    assert (tmp_path / 'distributions' / 'distribution_set_001.png').stat().st_size > 100
    assert (tmp_path / 'distribution_overview.png').stat().st_size > 100
    assert (tmp_path / 'comparison.png').stat().st_size > 100



def test_comparison_matrix_blanks_the_diagonal_and_scales_to_real_range():
    from units_set_reports import _matrix, _span
    table = pd.DataFrame({'set_a': [1, 1, 2], 'set_b': [2, 3, 3],
                          'mean_tv': [.066, .069, .067]})
    values = _matrix(table, 'mean_tv', 3)
    assert np.isnan(np.diag(values)).all()          # 자기 자신은 색 범위에서 빠진다
    assert values[0, 1] == values[1, 0] == .066
    assert _span(values) == (.066, .069)            # 0~1 고정이면 전부 같은 색이 된다


def test_span_widens_when_every_pair_is_identical():
    from units_set_reports import _span
    flat = np.array([[np.nan, .2], [.2, np.nan]])
    low, high = _span(flat)
    assert low < .2 < high
    assert _span(np.array([[np.nan]])) == (0.0, 1.0)


def test_overview_values_cover_all_sets_and_missing_categories():
    from units_set_reports import _overview_values
    original = {'category': pd.Series({'x': .7, 'y': .3})}
    entries = [({'category': pd.Series({'x': .6, 'y': .4})}, set()),
               ({'category': pd.Series({'x': .8, 'z': .2})}, set())]
    values, orig, center, low, high = _overview_values(original, entries, 'category')
    assert len(values) == len(set(values)) == 3
    got = {value: tuple(series[i] for series in (orig, center, low, high))
           for i, value in enumerate(values)}
    assert got['x'] == pytest.approx((.7, .7, .6, .8))
    assert got['y'] == pytest.approx((.3, .2, 0, .4))
    assert got['z'] == pytest.approx((0, .1, 0, .2))


def test_one_set_writes_overview_but_not_pair_chart(tmp_path):
    a = pd.DataFrame({'lot': ['a', 'b'], 'step': [1, 1], 'category': ['x', 'y']})
    reports = SetReports(a, args(False), str(tmp_path), ['category'])
    add(reports, 1, a)
    reports.finish()
    assert (tmp_path / 'distribution_overview.png').stat().st_size > 100
    assert not (tmp_path / 'comparison.png').exists()


def test_cleanup_removes_report_artifacts_but_preserves_unrelated_files(tmp_path):
    from units_sets import _prepare_folder
    reports = tmp_path / 'distributions'
    reports.mkdir()
    for name in ['set_004.csv', 'distribution_set_004.png']:
        (reports / name).write_text('old')
    (reports / 'notes.txt').write_text('keep')
    (tmp_path / 'comparison.png').write_text('old')
    (tmp_path / 'distribution_overview.png').write_text('old')
    _prepare_folder(str(tmp_path))
    assert not (reports / 'set_004.csv').exists()
    assert not (reports / 'distribution_set_004.png').exists()
    assert not (tmp_path / 'comparison.png').exists()
    assert not (tmp_path / 'distribution_overview.png').exists()
    assert (reports / 'notes.txt').read_text() == 'keep'


def test_cli_writes_reports_for_each_accepted_set(tmp_path):
    from test_unit_sets import _run_sets
    _, summary, files = _run_sets(tmp_path, '--ratio', '0.2', '--sets', '3', '--target', '0')
    folder = tmp_path / 'out' / 'sets_A'
    assert len(summary) == len(files) == 3
    assert len(list((folder / 'distributions').glob('set_*.csv'))) == 3
    assert len(pd.read_csv(folder / 'comparisons.csv')) == 3
    assert not list(folder.rglob('*.png'))
