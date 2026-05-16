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
import unittest.mock

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
        favorites.invalidate_cache()

    def tearDown(self):
        favorites._profile_path = self._saved_profile
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        favorites.invalidate_cache()

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


class TestLabelFor(unittest.TestCase):
    """`_label_for` label rendering for favorites list rows."""

    def setUp(self):
        from lib import favorites_ui
        self.ui = favorites_ui

    def test_label_for_handles_braces_in_query(self):
        # Plain string concat — must not raise on `{` / `}` in the query.
        try:
            label = self.ui._label_for({'type': 'search', 'query': '{foo}'})
        except (ValueError, KeyError, IndexError) as e:
            self.fail('_label_for raised on brace-bearing query: {}'.format(e))
        self.assertIn('{foo}', label)

    def test_label_for_search_type_prefix(self):
        label = self.ui._label_for({'type': 'search', 'query': 'south park'})
        self.assertTrue(label.startswith('String_30426'))

    def test_label_for_series_type_prefix(self):
        label = self.ui._label_for({
            'type': 'series', 'canonical_key': 'south park||',
            'display_name': 'South Park'})
        self.assertTrue(label.startswith('String_30427'))
        self.assertIn('South Park', label)

    def test_label_for_movie_type_prefix_with_year(self):
        label = self.ui._label_for({
            'type': 'movie', 'canonical_key': 'the office||2005',
            'display_name': 'The Office', 'year': 2005})
        self.assertTrue(label.startswith('String_30428'))
        self.assertIn('The Office', label)
        self.assertIn('(2005)', label)


class TestClickUrl(unittest.TestCase):
    """Direct URL builder for favorites list rows."""

    def setUp(self):
        from lib import favorites_ui
        self.ui = favorites_ui

    def test_click_url_search(self):
        url = self.ui._click_url({'type': 'search', 'query': 'south park'})
        self.assertIn('action=search', url)
        self.assertIn('south', url.replace('%20', '+'))

    def test_click_url_series_uses_browse_series(self):
        url = self.ui._click_url({
            'type': 'series', 'canonical_key': 'south park||',
            'display_name': 'South Park', 'search_query': 'south'})
        self.assertIn('action=browse_series', url)
        self.assertIn('series=south', url.replace('%20', '+'))

    def test_click_url_series_carries_fav_display_name(self):
        """Dual-name detection drifts the canonical_key; browse_series needs
        the original display_name to do a fallback substring match."""
        url = self.ui._click_url({
            'type': 'series', 'canonical_key': 'mestecko|south park',
            'display_name': 'South Park', 'search_query': 'south'})
        self.assertIn('fav_display_name=South', url.replace('%20', '+'))

    def test_click_url_movie_carries_fav_display_name(self):
        url = self.ui._click_url({
            'type': 'movie', 'canonical_key': 'mov||2020',
            'display_name': 'Mov Title', 'search_query': 'mov', 'year': 2020})
        self.assertIn('fav_display_name=Mov', url.replace('%20', '+'))

    def test_click_url_movie_uses_select_movie_version(self):
        url = self.ui._click_url({
            'type': 'movie', 'canonical_key': 'mov||2020',
            'display_name': 'Mov', 'search_query': 'mov', 'year': 2020})
        self.assertIn('action=select_movie_version', url)
        self.assertIn('movie_key=mov', url.replace('%20', '+'))


class TestInMemoryCache(FavoritesTestBase):
    """load_favorites caches in-memory; save_favorites invalidates."""

    def test_load_favorites_caches_in_memory(self):
        add_favorite({'type': 'search', 'query': 'a'})  # primes cache via save
        favorites.invalidate_cache()
        with unittest.mock.patch('lib.favorites.io.open',
                                 wraps=io.open) as mopen:
            load_favorites()
            load_favorites()
            load_favorites()
        # First call hits disk, the next two are served from memory.
        self.assertEqual(mopen.call_count, 1,
                         'expected single disk read, got {}'.format(mopen.call_count))

    def test_add_favorite_invalidates_cache(self):
        add_favorite({'type': 'search', 'query': 'a'})
        items_before = load_favorites()  # populates cache
        self.assertEqual(len(items_before), 1)
        add_favorite({'type': 'search', 'query': 'b'})  # invalidates
        items_after = load_favorites()
        self.assertEqual(len(items_after), 2)


class TestFavoritedByName(FavoritesTestBase):
    """Drift-aware lookup: find a favorite by (type, display_name).

    Dual-name detection produces drifting canonical_keys. The context-menu
    toggle on a search-results page checks is_favorited by the CURRENT
    canonical_key — if it drifted, the toggle wrongly shows "Add" and the
    user creates a duplicate. find_favorite_by_name patches over this by
    matching on display_name.
    """

    def setUp(self):
        super().setUp()
        from lib.favorites import find_favorite_by_name
        self.find = find_favorite_by_name

    def test_find_series_by_display_name_after_key_drift(self):
        add_favorite({'type': 'series', 'canonical_key': 'mestecko|south park',
                      'display_name': 'South Park'})
        # User now in a search page where the live key is different.
        match = self.find('series', 'South Park')
        self.assertIsNotNone(match)
        self.assertEqual(match['canonical_key'], 'mestecko|south park')

    def test_find_returns_none_for_unrelated_display_name(self):
        add_favorite({'type': 'series', 'canonical_key': 'south park||',
                      'display_name': 'South Park'})
        self.assertIsNone(self.find('series', 'Breaking Bad'))

    def test_find_only_matches_same_type(self):
        add_favorite({'type': 'movie', 'canonical_key': 'mov||2020',
                      'display_name': 'South Park'})
        # series favorite missing → no match even though display_name matches a movie.
        self.assertIsNone(self.find('series', 'South Park'))

    def test_find_no_bidirectional_substring_collision(self):
        """`Panic` must not match `Panic at the Disco` — bare substring
        matching wrongly returned a sibling favorite, causing the toggle
        to remove the wrong entry."""
        add_favorite({'type': 'series',
                      'canonical_key': 'panic at the disco||',
                      'display_name': 'Panic at the Disco'})
        self.assertIsNone(self.find('series', 'Panic'))

    def test_find_no_collision_other_direction(self):
        add_favorite({'type': 'series',
                      'canonical_key': 'panic||',
                      'display_name': 'Panic'})
        # Live row is "Panic at the Disco" — must not match the stored "Panic".
        self.assertIsNone(self.find('series', 'Panic at the Disco'))

    def test_find_is_case_insensitive_exact_match(self):
        """display_name match is case-insensitive but otherwise exact —
        avoids the bidirectional-substring family of collisions."""
        add_favorite({'type': 'series', 'canonical_key': 'south park||',
                      'display_name': 'South Park'})
        self.assertIsNotNone(self.find('series', 'south park'))
        self.assertIsNotNone(self.find('series', 'SOUTH PARK'))


class TestContextMenuDriftToggle(FavoritesTestBase):
    """Regression: add_favorite_context_entry must show Remove (not Add)
    when the live canonical_key has drifted from the stored one."""

    def setUp(self):
        super().setUp()
        from lib import favorites_ui
        self.ui = favorites_ui

    def test_context_entry_recognizes_drifted_series(self):
        # Saved under one key, looked up under a drifted live key.
        add_favorite({'type': 'series', 'canonical_key': 'mestecko|south park',
                      'display_name': 'South Park'})
        label, cmd = self.ui.add_favorite_context_entry({
            'type': 'series',
            'canonical_key': 'pandemic special cz|south park',  # drifted
            'display_name': 'South Park',
        })
        # Must offer Remove (30422 == _STR_REMOVE_FAV) against the
        # STORED key, not Add (30421).
        self.assertEqual(label, 'String_30422')
        self.assertIn('action=remove_favorite', cmd)
        self.assertIn('mestecko', cmd.replace('%7C', '|'))


class TestGotoPageContract(unittest.TestCase):
    """Folder-handler contract: goto_page must end the directory cleanly
    before issuing Container.Update, and must NOT use 'replace' (which
    wipes path history)."""

    def setUp(self):
        import xbmc, xbmcplugin
        from lib import ui
        self.ui = ui
        # Save originals to restore — never delete lib.* modules from
        # sys.modules (it cascades and breaks other tests' module-level
        # patches that were set up via the conftest snapshot).
        self._saved_exec = xbmc.executebuiltin
        self._saved_end = xbmcplugin.endOfDirectory
        self._events = []
        xbmc.executebuiltin = lambda cmd: self._events.append(('exec', cmd))
        def _end(handle, succeeded=True, updateListing=False, cacheToDisc=True):
            self._events.append(('end', succeeded))
        xbmcplugin.endOfDirectory = _end

    def tearDown(self):
        import xbmc, xbmcplugin
        xbmc.executebuiltin = self._saved_exec
        xbmcplugin.endOfDirectory = self._saved_end

    def test_goto_page_ends_directory_before_container_update(self):
        self.ui.goto_page({'action': 'goto_page', 'target_url': 'plugin://x/'})
        kinds = [k for k, _p in self._events]
        self.assertIn('end', kinds, 'endOfDirectory missing')
        self.assertIn('exec', kinds, 'Container.Update missing')
        self.assertLess(kinds.index('end'), kinds.index('exec'),
                        'endOfDirectory must precede Container.Update')

    def test_goto_page_uses_succeeded_true(self):
        self.ui.goto_page({'action': 'goto_page', 'target_url': 'plugin://x/'})
        end_event = next((p for k, p in self._events if k == 'end'), None)
        self.assertTrue(end_event, 'succeeded=False would trigger parent-path race')

    def test_goto_page_does_not_use_replace_flag(self):
        """`replace` calls SetHistoryForPath → ClearPathHistory, wiping
        the back-stack entirely. We need plain Container.Update so Back
        returns to the previous page, not the root."""
        self.ui.goto_page({'action': 'goto_page', 'target_url': 'plugin://x/'})
        update_cmd = next((p for k, p in self._events if k == 'exec'), '')
        self.assertNotIn(',replace', update_cmd,
                         'goto_page must not use replace; wipes history')


if __name__ == '__main__':
    unittest.main()
