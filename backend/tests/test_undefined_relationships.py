"""Regression: undefined is not a measured zero."""
import json

import pandas as pd
import pytest

from app.core.metrics import correlation_metrics
from app.core.relationship_causes import explain_relationship_changes
from app.core.relationships import classify_relationships, rank_correlation_pairs
from app.core.schema import classify_column


def compare(a, b, method):
    return correlation_metrics(a, b, [classify_column(a[c], c) for c in a], list(a), method)


def report(excluded=0):
    return {"original_count": 8, "representative_count": 3, "excluded_count": excluded,
            "clusters": [{"original_count": 8, "representative_count": 3,
                          "excluded_count": excluded, "covered_count": 8 - excluded}]}


@pytest.mark.parametrize('method', ['pearson', 'spearman'])
@pytest.mark.parametrize('side', ['original', 'reduced', 'both'])
def test_constant_sides_have_no_rank_or_causes(method, side):
    a = pd.DataFrame({'x': range(8), 'y': range(8), 'z': range(8, 0, -1)})
    b = a.iloc[:3].copy()
    if side in ('original', 'both'):
        a['y'] = 0
    if side in ('reduced', 'both'):
        b['y'] = 0
    metrics = compare(a, b, method)
    pairs = rank_correlation_pairs(metrics)['pairs']
    assert (pairs[0]['column_a'], pairs[0]['column_b']) == ('x', 'z')
    for p in pairs[1:]:
        assert p['undefined'] and p['difference'] is None and p['abs_difference'] is None
        assert (p['original_r'] is None) == (side in ('original', 'both'))
        assert (p['reduced_r'] is None) == (side in ('reduced', 'both'))
    assert classify_relationships(metrics)['counts']['undefined'] == 2
    explained = explain_relationship_changes(metrics, report(), dispersion_ratios={('x', 'y'): .1})
    for p in explained['pairs'][1:]:
        assert p['status'] == p['result'] == 'undefined'
        assert p['causes'] == p['evidence'] == []
    json.dumps(explained, allow_nan=False)


@pytest.mark.parametrize('method', ['pearson', 'spearman'])
def test_post_exclusion_constant_does_not_override_measured_results(method):
    a = pd.DataFrame({'x': [0, 1, 2, 3, 4, 5, 20, 30],
                      'y': [0, 0, 0, 0, 0, 0, 20, 30],
                      'z': [3, 1, 5, 2, 4, 0, 7, 6]})
    retained = a.iloc[:6]
    for b in [a.iloc[[0, 6, 7]], retained.iloc[:3]]:
        metrics = compare(a, b, method)
        classified = classify_relationships(metrics)
        result = explain_relationship_changes(metrics, report(2),
                                             after_exclusion=compare(retained, b, method),
                                             dispersion_ratios={('x', 'y'): .1})
        assert result['counts'] == classified['counts']
        for p in result['pairs']:
            if 'y' in (p['column_a'], p['column_b']):
                assert p['after_exclusion_undefined']
                assert 'outlier_exclusion' not in p['causes']
                if p['reduced_undefined']:
                    assert p['status'] == p['result'] == 'undefined'
                    assert p['causes'] == p['evidence'] == []
                else:
                    assert not p['undefined'] and p['difference'] is not None


@pytest.mark.parametrize('mask', [[[False]], [[0, 1], [1, 0]],
                                  [[False, True], [False, False]]])
def test_invalid_mask_rejected(mask):
    frame = pd.DataFrame({'x': [1, 2, 3], 'y': [3, 2, 1]})
    metrics = compare(frame, frame, 'pearson')
    metrics['undefined_original'] = mask
    with pytest.raises(ValueError, match='Undefined masks'):
        rank_correlation_pairs(metrics)


@pytest.mark.parametrize('excluded', [0, 2])
def test_post_exclusion_is_optional_and_preserves_measured_result(excluded):
    a = pd.DataFrame({'x': [1, 2, 3, 4], 'y': [1, 3, 2, 4]})
    b = a.copy()
    retained = a.copy()
    retained['y'] = 0
    result = explain_relationship_changes(compare(a, b, 'pearson'), report(excluded),
                                         after_exclusion=compare(retained, b, 'pearson'),
                                         dispersion_ratios={('x', 'y'): .1})
    p = result['pairs'][0]
    assert p['undefined_sources'] == (['after_exclusion'] if excluded else [])
    assert p['after_exclusion_undefined'] == bool(excluded)
    assert p['result'] == p['status'] == 'maintained'
    assert not p['undefined'] and p['difference'] == 0
    assert p['causes'] == ['no_material_change'] and p['evidence'] == []
    assert result['counts']['undefined'] == 0


def test_real_zero_is_measured_and_not_undefined():
    a = pd.DataFrame({'x': [0, 1, 2, 3, 4], 'y': [0, 1, -2, 1, 0]})
    result = explain_relationship_changes(compare(a, a, 'pearson'), report())
    p = result['pairs'][0]
    assert p['original_r'] == p['reduced_r'] == 0
    assert not p['undefined'] and p['undefined_sources'] == []
    assert p['result'] == p['status'] == 'absent'
    assert p['causes'] == ['no_material_change']


@pytest.mark.parametrize('method', ['pearson', 'spearman'])
def test_claude_measured_loss_survives_undefined_exclusion_evidence(method):
    a = pd.DataFrame({'x': [0, 1, 2, 3, 4, 5, 20, 30],
                      'y': [0, 0, 0, 0, 0, 0, 20, 30]})
    b = pd.DataFrame({'x': [0, 5, 4, 1], 'y': [0, 0, 20, 0]})
    metrics = compare(a, b, method)
    expected = classify_relationships(metrics)
    result = explain_relationship_changes(metrics, report(2),
                                         after_exclusion=compare(a.iloc[:6], b, method))
    p = result['pairs'][0]
    assert expected['pairs'][0]['status'] == p['status'] == p['result'] == 'lost'
    assert result['counts'] == expected['counts']
    assert not p['undefined'] and p['difference'] == expected['pairs'][0]['difference']
    assert p['after_exclusion_undefined'] and p['causes'] == ['unresolved']
    assert p['evidence'] == []


def test_no_exclusions_ignores_even_malformed_optional_evidence():
    a = pd.DataFrame({'x': [1, 2, 3], 'y': [3, 1, 2]})
    metrics = compare(a, a, 'pearson')
    assert explain_relationship_changes(metrics, report(), after_exclusion={'invalid': True}) == (
        explain_relationship_changes(metrics, report()))


@pytest.mark.parametrize('a,b,cause', [(0.49, 0.51, 'threshold_boundary'),
                                       (0.6, 0.9, 'cluster_representation')])
def test_undefined_exclusion_does_not_suppress_other_valid_causes(a, b, cause):
    metrics = {'method': 'pearson', 'columns': ['x', 'y'],
               'matrix_original': [[1, a], [a, 1]], 'matrix_reduced': [[1, b], [b, 1]]}
    after = {**metrics, 'matrix_original': [[1, 0], [0, 0]],
             'undefined_original': [[False, True], [True, True]]}
    result = explain_relationship_changes(metrics, report(2), after_exclusion=after,
                                         dispersion_ratios={('x', 'y'): .1})
    p = result['pairs'][0]
    assert not p['undefined'] and p['after_exclusion_undefined']
    assert cause in p['causes'] and 'outlier_exclusion' not in p['causes']
    assert all(e['cause'] != 'outlier_exclusion' for e in p['evidence'])
