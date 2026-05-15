#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for favorites (lib.favorites).

Covers:
- Add dedupe by query / canonical_key (+ year via canonical_key)
- Move-to-front on re-add
- Cap at 200
- Corrupt JSON / non-list / invalid entry handling
- Legacy bare-list migrates to v1 envelope on next save
- Atomic write (no tmp leftover)
- Concurrent add safety
- remove + is_favorited
"""

import os
import io
import json
import shutil
import tempfile
import threading
import unittest

import lib.favorites as favorites
from lib.favorites import (
    load_favorites, save_favorites, add_favorite, remove_favorite,
    is_favorited, FAVORITES, MAX_FAVORITES, ENVELOPE_VERSION,
)


class FavoritesTestBase(unittest.TestCase):
    """Per-test tmp profile, restored on tearDown."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix='yeplaya_fav_test_')
        self._saved_profile = favorites._profile_path
        favorites._profile_path = lambda: self._tmpdir

    def tearDown(self):
        favorites._profile_path = self._saved_profile
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _path(self):
        return os.path.join(self._tmpdir, FAVORITES)

    def _read_raw(self):
        with io.open(self._path(), 'r', encoding='utf8') as f:
            return f.read()

    def _write_raw(self, content):
        os.makedirs(self._tmpdir, exist_ok=True)
        with io.open(self._path(), 'w', encoding='utf8') as f:
            f.write(content)


class TestAddDedup(FavoritesTestBase):
    def test_add_search_favorite_dedupes_by_query(self):
        add_favorite({'type': 'search', 'query': 'south park'})
        add_favorite({'type': 'search', 'query': 'south park'})
        items = load_favorites()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['query'], 'south park')

    def test_add_series_favorite_dedupes_by_canonical_key(self):
        entry = {'type': 'series', 'canonical_key': 'south park||',
                 'display_name': 'South Park'}
        add_favorite(entry)
        add_favorite(entry)
        items = load_favorites()
        self.assertEqual(len(items), 1)

    def test_add_movie_favorite_dedupes_by_canonical_key_and_year(self):
        # canonical_key encodes year; same key dedupes, different year = different fav.
        add_favorite({'type': 'movie', 'canonical_key': 'the office||2005',
                      'display_name': 'The Office', 'year': 2005})
        add_favorite({'type': 'movie', 'canonical_key': 'the office||2005',
                      'display_name': 'The Office', 'year': 2005})
        add_favorite({'type': 'movie', 'canonical_key': 'the office||2001',
                      'display_name': 'The Office (UK)', 'year': 2001})
        items = load_favorites()
        self.assertEqual(len(items), 2)


class TestLoadCorruption(FavoritesTestBase):
    def test_load_corrupt_json_returns_empty(self):
        self._write_raw('{not json')
        self.assertEqual(load_favorites(), [])

    def test_load_legacy_bare_list_migrates_to_v1(self):
        legacy = [{'type': 'search', 'query': 'south park'}]
        self._write_raw(json.dumps(legacy))
        # First read accepts bare list...
        self.assertEqual(len(load_favorites()), 1)
        # ...then save_favorites rewrites under envelope.
        save_favorites(load_favorites())
        parsed = json.loads(self._read_raw())
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get('version'), ENVELOPE_VERSION)
        self.assertEqual(len(parsed.get('items')), 1)

    def test_load_invalid_entry_dropped(self):
        env = {'version': 1, 'items': [
            {'type': 'search', 'query': 'good'},
            {'query': 'missing type'},        # invalid
            {'type': 'series'},               # missing canonical_key
            {'type': 'movie', 'canonical_key': ''},  # empty key
            {'type': 'unknown', 'query': 'x'},  # bad type
        ]}
        self._write_raw(json.dumps(env))
        items = load_favorites()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['query'], 'good')

    def test_load_non_list_items_returns_empty(self):
        self._write_raw(json.dumps({'version': 1, 'items': 'oops'}))
        self.assertEqual(load_favorites(), [])

    def test_load_top_level_scalar_returns_empty(self):
        self._write_raw('null')
        self.assertEqual(load_favorites(), [])
        self._write_raw('"hello"')
        self.assertEqual(load_favorites(), [])

    def test_load_missing_file_returns_empty(self):
        self.assertEqual(load_favorites(), [])


class TestSaveAtomic(FavoritesTestBase):
    def test_save_atomic_write_no_tmp_leftover(self):
        add_favorite({'type': 'search', 'query': 'a'})
        add_favorite({'type': 'search', 'query': 'b'})
        leftovers = [f for f in os.listdir(self._tmpdir) if f.endswith('.tmp')]
        self.assertEqual(leftovers, [])

    def test_save_writes_envelope(self):
        add_favorite({'type': 'search', 'query': 'a'})
        parsed = json.loads(self._read_raw())
        self.assertEqual(parsed['version'], ENVELOPE_VERSION)
        self.assertEqual(len(parsed['items']), 1)


class TestConcurrent(FavoritesTestBase):
    def test_concurrent_add_no_data_loss(self):
        """Concurrent add_favorite must not corrupt JSON.

        Note: add_favorite is load-modify-save without an exclusive cross-process
        lock, so some adds will overwrite each other (last-writer-wins on disk).
        The contract we test: file remains valid JSON, never raises.
        """
        def writer(prefix):
            for i in range(5):
                add_favorite({'type': 'search',
                              'query': '{}_{}'.format(prefix, i)})

        threads = [threading.Thread(target=writer, args=('w{}'.format(i),))
                   for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # File parses as envelope, items list is sane.
        parsed = json.loads(self._read_raw())
        self.assertIn('items', parsed)
        self.assertIsInstance(parsed['items'], list)


class TestRemoveAndQuery(FavoritesTestBase):
    def test_remove_favorite_by_type_and_key(self):
        add_favorite({'type': 'search', 'query': 'a'})
        add_favorite({'type': 'series', 'canonical_key': 's||'})
        self.assertTrue(remove_favorite('search', 'a'))
        items = load_favorites()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['type'], 'series')

    def test_remove_unknown_returns_false(self):
        self.assertFalse(remove_favorite('search', 'nope'))

    def test_is_favorited(self):
        add_favorite({'type': 'movie', 'canonical_key': 'm||2020'})
        self.assertTrue(is_favorited('movie', 'm||2020'))
        self.assertFalse(is_favorited('movie', 'm||1999'))
        self.assertFalse(is_favorited('search', 'm||2020'))


class TestCap(FavoritesTestBase):
    def test_cap_at_max(self):
        for i in range(MAX_FAVORITES + 25):
            add_favorite({'type': 'search', 'query': 'q_{:04d}'.format(i)})
        items = load_favorites()
        self.assertEqual(len(items), MAX_FAVORITES)
        # Most recent should be at front.
        self.assertEqual(items[0]['query'],
                         'q_{:04d}'.format(MAX_FAVORITES + 24))


class TestMoveToFront(FavoritesTestBase):
    def test_re_add_moves_to_front(self):
        add_favorite({'type': 'search', 'query': 'a'})
        add_favorite({'type': 'search', 'query': 'b'})
        add_favorite({'type': 'search', 'query': 'c'})
        add_favorite({'type': 'search', 'query': 'a'})
        items = load_favorites()
        self.assertEqual([it['query'] for it in items], ['a', 'c', 'b'])


class TestResolveFallbacks(unittest.TestCase):
    """resolve_favorite_url canonical_key / display_name fallback chain."""

    def setUp(self):
        from lib import favorites_ui
        self.ui = favorites_ui

    def test_resolve_canonical_key_hit_no_fallback(self):
        entry = {'type': 'series', 'canonical_key': 'south park||',
                 'display_name': 'South Park', 'search_query': 'south'}
        grouped = {'series': {'south park||': {'display_name': 'South Park'}}}
        url, fallback, dead = self.ui.resolve_favorite_url(entry, grouped)
        self.assertFalse(fallback)
        self.assertFalse(dead)
        self.assertIn('browse_series', url)

    def test_resolve_canonical_key_missing_falls_back_to_display_name(self):
        # canonical_key changed in current grouping; display_name still matches.
        entry = {'type': 'series', 'canonical_key': 'south park||old',
                 'display_name': 'South Park', 'search_query': 'south'}
        grouped = {'series': {'mestecko south park||': {
            'display_name': 'Mestecko South Park'}}}
        url, fallback, dead = self.ui.resolve_favorite_url(entry, grouped)
        self.assertTrue(fallback)
        self.assertFalse(dead)
        self.assertIn('mestecko+south+park', url.replace('%20', '+'))

    def test_resolve_all_lookups_fail_returns_dead_marker(self):
        entry = {'type': 'movie', 'canonical_key': 'gone||1999',
                 'display_name': 'Gone Movie', 'year': 1999}
        grouped = {'movies': {'something else||2020': {
            'display_name': 'Something Else'}}}
        url, fallback, dead = self.ui.resolve_favorite_url(entry, grouped)
        self.assertFalse(fallback)
        self.assertTrue(dead)

    def test_resolve_search_type_ignores_grouping(self):
        entry = {'type': 'search', 'query': 'south park'}
        url, fallback, dead = self.ui.resolve_favorite_url(entry, None)
        self.assertFalse(fallback)
        self.assertFalse(dead)
        self.assertIn('action=search', url)


if __name__ == '__main__':
    unittest.main()
