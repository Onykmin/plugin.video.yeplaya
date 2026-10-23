# -*- coding: utf-8 -*-
"""Offline regression net for the grouping pipeline.

For every recorded Webshare search (``api_responses/*.xml``) run the real
``fetch_and_group_series`` (what search_ui calls) with only the network call
mocked, and compare the observable result with ``baseline_results.json``:
group counts, series (name, seasons, episodes, versions), movies
(name, year, versions) and the ORDER of the versions inside each group
(idents, best first), so a ranking change shows up too.

A failure means grouping output changed. If the change is intended, refresh the
baseline with ``python3 tests/integration/refresh_baseline.py`` and review the diff.
"""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lib.grouping import fetch_and_group_series

HERE = Path(__file__).parent
RESPONSES = HERE / 'api_responses'
BASELINE = json.loads((HERE / 'baseline_results.json').read_text(encoding='utf-8'))['test_cases']
FIELDS = ('series_groups', 'movie_groups', 'non_series', 'series_details', 'movie_details')


def fixture_path(query):
    """Fixture file name scheme used when the responses were recorded."""
    return RESPONSES / (hashlib.md5(query.encode()).hexdigest()[:8] + '_' + query.replace(' ', '_')[:20] + '.xml')


def observe(grouped):
    """Observable summary of a grouping result, same shape as the baseline."""
    series = {}
    for key, data in grouped['series'].items():
        order = {}
        for season, eps in sorted(data['seasons'].items()):
            for ep, versions in sorted(eps.items()):
                if len(versions) > 1:
                    order['S%s:E%s' % (season, ep)] = [v['ident'] for v in versions]
        series[key] = {
            'display_name': data.get('display_name', key),
            'seasons': len(data['seasons']),
            'episodes': data['total_episodes'],
            'versions': sum(len(v) for s in data['seasons'].values() for v in s.values()),
            'version_order': order,
        }
    movies = {
        key: {
            'display_name': data.get('display_name', key),
            'year': data.get('year'),
            'versions': len(data.get('versions', [])),
            'version_order': [v['ident'] for v in data.get('versions', [])],
        }
        for key, data in grouped.get('movies', {}).items()
    }
    return {
        'series_groups': len(series),
        'movie_groups': len(movies),
        'non_series': len(grouped['non_series']),
        'series_details': series,
        'movie_details': movies,
    }


def run_pipeline(query):
    """Feed the recorded response through fetch_and_group_series; network mocked."""
    content = fixture_path(query).read_bytes()
    # Only one page is recorded; a second call "fails" so paging stops.
    with patch('lib.grouping.api', side_effect=[MagicMock(content=content), None]):
        return fetch_and_group_series('token', query, 'video', '')


def test_every_baseline_query_has_a_fixture():
    missing = [q for q in BASELINE if not fixture_path(q).exists()]
    assert not missing, 'baseline queries without fixture: %s' % missing


@pytest.mark.parametrize('query', sorted(BASELINE))
def test_grouping_matches_baseline(query):
    expected = {k: BASELINE[query][k] for k in FIELDS}
    actual = observe(run_pipeline(query))
    # Counts first for a readable failure, then the full detail.
    for field in ('series_groups', 'movie_groups', 'non_series'):
        assert actual[field] == expected[field], field
    assert actual['series_details'] == expected['series_details']
    assert actual['movie_details'] == expected['movie_details']
