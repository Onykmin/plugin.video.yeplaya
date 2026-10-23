#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression: series_ui._resolve_drifted_key resolves a drifted favorite key
to the right live bucket WITHOUT the bidirectional-substring sibling collision.
"""

import unittest

import tests.conftest  # noqa: F401 — installs Kodi mocks


def _series(*keys_displays):
    return {k: {'display_name': d} for k, d in keys_displays}


class TestResolveDriftedKey(unittest.TestCase):
    def setUp(self):
        # Import inside setUp so the autouse mock-restore fixture (which may
        # purge lib.* after integration-test pollution) takes effect first.
        from lib.series_ui import _resolve_drifted_key
        from lib.keys import normalize_series_key, normalize_movie_key
        self._resolve = _resolve_drifted_key
        self.norm_series = normalize_series_key
        self.norm_movie = normalize_movie_key
    def test_dual_name_drift_resolves_via_normalized_key(self):
        # Stored "mestecko|south park"; live bucket keyed "tucnak cz|south park".
        bucket = _series(('tucnak cz|south park', 'South Park'))
        out = self._resolve(bucket, 'mestecko|south park', 'South Park',
                            self.norm_series)
        self.assertEqual(out, 'tucnak cz|south park')

    def test_no_substring_sibling_collision(self):
        # Stored "panic"; live bucket only has the sibling "panic at the disco".
        bucket = _series(('panic at the disco', 'Panic at the Disco'))
        out = self._resolve(bucket, 'panic', 'Panic', self.norm_series)
        # Must NOT resolve to the sibling — returns the original stored key.
        self.assertEqual(out, 'panic')

    def test_no_substring_collision_other_direction(self):
        bucket = _series(('panic', 'Panic'))
        out = self._resolve(bucket, 'panic at the disco',
                            'Panic at the Disco', self.norm_series)
        self.assertEqual(out, 'panic at the disco')

    def test_exact_display_name_fallback(self):
        # Keys can't bridge (English-only vs Czech-only), but display matches.
        bucket = _series(('tucnak', 'South Park'))
        out = self._resolve(bucket, 'the penguin', 'South Park',
                            self.norm_series)
        self.assertEqual(out, 'tucnak')

    def test_movie_normalized_keeps_year(self):
        bucket = {'alias cz|penguin|2022': {'display_name': 'Penguin'}}
        out = self._resolve(bucket, 'tucnak|penguin|2022', 'Penguin',
                            self.norm_movie)
        self.assertEqual(out, 'alias cz|penguin|2022')

    def test_favorite_under_an_old_season_marker_key_resolves_through_aliases(self):
        bucket = {'dragon ball z': {'display_name': 'Dragon Ball Z',
                                    'aliases': ['dragon ball z s01', 'dragon ball z s05']},
                  'dragon ball gt': {'display_name': 'Dragon Ball GT', 'aliases': []}}
        for stored in ('dragon ball z s05', 'dragon ball z s01'):
            self.assertEqual(self._resolve(bucket, stored, 'Dragon Ball Z S05', self.norm_series),
                             'dragon ball z')
        # an old key that is no alias of any live group stays unresolved
        self.assertEqual(self._resolve(bucket, 'dragon ball z s07', 'x', self.norm_series), 'dragon ball z s07')

    def test_empty_bucket_returns_stored(self):
        self.assertEqual(
            self._resolve({}, 'x', 'X', self.norm_series), 'x')

    def test_no_match_returns_stored(self):
        bucket = _series(('breaking bad', 'Breaking Bad'))
        out = self._resolve(bucket, 'south park', 'South Park',
                            self.norm_series)
        self.assertEqual(out, 'south park')


if __name__ == '__main__':
    unittest.main()
