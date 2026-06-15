#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for search history (storesearch / loadsearch / savesearch).

Covers:
- Add below/at/above cap
- Dedup + move-to-front
- Empty / whitespace term no-op
- Bad shistory setting fallback (empty, "0", "-5", non-numeric)
- Corrupted JSON on disk
- 50 consecutive stores
- Atomic write: no partial file on disk
"""

import sys
import os
import io
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import lib.cache as cache
from lib.cache import storesearch, loadsearch, savesearch, removesearch, SEARCH_HISTORY


class _FakeAddon(object):
    """Minimal addon stub for shistory setting."""

    def __init__(self, shistory='20'):
        self._settings = {'shistory': shistory}

    def getSetting(self, key):
        return self._settings.get(key, '')

    def setSetting(self, key, value):
        self._settings[key] = value

    def getAddonInfo(self, key):
        return 'TestAddon'

    def getLocalizedString(self, sid):
        return 'String_{}'.format(sid)


class SearchHistoryTestBase(unittest.TestCase):
    """Per-test tmp profile + addon stub, restored in tearDown."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp(prefix='yeplaya_test_')
        self._saved_profile = cache._profile
        self._saved_addon = cache._addon
        cache._profile = self._tmpdir
        cache._addon = _FakeAddon(shistory='20')

    def tearDown(self):
        import shutil
        cache._profile = self._saved_profile
        cache._addon = self._saved_addon
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _history_path(self):
        return os.path.join(self._tmpdir, SEARCH_HISTORY)

    def _read_raw(self):
        with io.open(self._history_path(), 'r', encoding='utf8') as f:
            return f.read()


class TestStoreSearchCap(SearchHistoryTestBase):
    """Cap behavior."""

    def test_add_below_cap(self):
        for t in ['a', 'b', 'c']:
            storesearch(t)
        self.assertEqual(loadsearch(), ['c', 'b', 'a'])

    def test_add_at_cap(self):
        cache._addon = _FakeAddon(shistory='3')
        for t in ['a', 'b', 'c']:
            storesearch(t)
        self.assertEqual(loadsearch(), ['c', 'b', 'a'])

    def test_add_above_cap_drops_oldest(self):
        cache._addon = _FakeAddon(shistory='3')
        for t in ['a', 'b', 'c', 'd']:
            storesearch(t)
        self.assertEqual(loadsearch(), ['d', 'c', 'b'])

    def test_truncate_when_list_grows_past_cap(self):
        cache._addon = _FakeAddon(shistory='5')
        for t in ['a', 'b', 'c', 'd', 'e', 'f', 'g']:
            storesearch(t)
        history = loadsearch()
        self.assertEqual(len(history), 5)
        self.assertEqual(history[0], 'g')
        self.assertEqual(history[-1], 'c')


class TestStoreSearchDedup(SearchHistoryTestBase):
    """Deduplication and move-to-front."""

    def test_readding_moves_to_front(self):
        for t in ['a', 'b', 'c']:
            storesearch(t)
        storesearch('a')
        history = loadsearch()
        self.assertEqual(history, ['a', 'c', 'b'])
        self.assertEqual(len(history), 3)

    def test_readding_does_not_grow_list(self):
        cache._addon = _FakeAddon(shistory='3')
        for t in ['a', 'b', 'c']:
            storesearch(t)
        for _ in range(10):
            storesearch('b')
        history = loadsearch()
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0], 'b')


class TestStoreSearchNoOp(SearchHistoryTestBase):
    """Empty / whitespace behavior."""

    def test_empty_term_no_op(self):
        storesearch('a')
        storesearch('')
        storesearch(None)
        self.assertEqual(loadsearch(), ['a'])

    def test_whitespace_only_term_no_op(self):
        # Whitespace-only terms are stripped to empty and skipped.
        storesearch('a')
        storesearch('  ')
        storesearch('\t\n')
        self.assertEqual(loadsearch(), ['a'])

    def test_surrounding_whitespace_stripped(self):
        storesearch('  avatar  ')
        self.assertEqual(loadsearch(), ['avatar'])


class TestStoreSearchNormalizedDedup(SearchHistoryTestBase):
    """Case/accent/whitespace-insensitive dedup."""

    def test_case_insensitive_dedup_keeps_newest_casing(self):
        storesearch('Avatar')
        storesearch('avatar')
        history = loadsearch()
        self.assertEqual(history, ['avatar'])

    def test_accent_insensitive_dedup(self):
        storesearch('avatar')
        storesearch('avatár')
        self.assertEqual(loadsearch(), ['avatár'])

    def test_whitespace_variant_dedup(self):
        storesearch('avatar')
        storesearch('  avatar ')
        self.assertEqual(loadsearch(), ['avatar'])

    def test_normalized_dedup_moves_to_front(self):
        for t in ['a', 'b', 'c']:
            storesearch(t)
        storesearch('A')  # case-variant of 'a'
        self.assertEqual(loadsearch(), ['A', 'c', 'b'])
        self.assertEqual(len(loadsearch()), 3)

    def test_remove_is_case_insensitive(self):
        storesearch('Avatar')
        removesearch('avatar')
        self.assertEqual(loadsearch(), [])


class TestBadShistorySetting(SearchHistoryTestBase):
    """Fallback when shistory setting is malformed."""

    def test_empty_string_falls_back_to_20(self):
        cache._addon = _FakeAddon(shistory='')
        for i in range(25):
            storesearch('t{}'.format(i))
        self.assertEqual(len(loadsearch()), 20)

    def test_zero_falls_back_to_20(self):
        cache._addon = _FakeAddon(shistory='0')
        for i in range(25):
            storesearch('t{}'.format(i))
        self.assertEqual(len(loadsearch()), 20)

    def test_negative_falls_back_to_20(self):
        cache._addon = _FakeAddon(shistory='-5')
        for i in range(25):
            storesearch('t{}'.format(i))
        self.assertEqual(len(loadsearch()), 20)

    def test_nonnumeric_falls_back_to_20(self):
        cache._addon = _FakeAddon(shistory='abc')
        for i in range(25):
            storesearch('t{}'.format(i))
        self.assertEqual(len(loadsearch()), 20)

    def test_bad_setting_does_not_wipe_history(self):
        cache._addon = _FakeAddon(shistory='20')
        for t in ['a', 'b', 'c']:
            storesearch(t)
        cache._addon = _FakeAddon(shistory='')
        storesearch('d')
        history = loadsearch()
        self.assertIn('a', history)
        self.assertEqual(history[0], 'd')


class TestCorruptedJSON(SearchHistoryTestBase):
    """Handle pre-existing bad file on disk."""

    def test_corrupted_json_returns_empty(self):
        with io.open(self._history_path(), 'w', encoding='utf8') as f:
            f.write('{not valid json')
        self.assertEqual(loadsearch(), [])

    def test_corrupted_json_overwritten_on_next_store(self):
        with io.open(self._history_path(), 'w', encoding='utf8') as f:
            f.write('garbage!')
        storesearch('first')
        self.assertEqual(loadsearch(), ['first'])
        raw = self._read_raw()
        self.assertEqual(json.loads(raw), ['first'])

    def test_empty_file_returns_empty(self):
        with io.open(self._history_path(), 'w', encoding='utf8') as f:
            f.write('')
        self.assertEqual(loadsearch(), [])

    def test_null_json_returns_empty(self):
        with io.open(self._history_path(), 'w', encoding='utf8') as f:
            f.write('null')
        self.assertEqual(loadsearch(), [])

    def test_object_json_returns_empty(self):
        with io.open(self._history_path(), 'w', encoding='utf8') as f:
            f.write('{"a": 1}')
        self.assertEqual(loadsearch(), [])

    def test_scalar_json_returns_empty(self):
        for content in ['123', 'true', '"hello"']:
            with io.open(self._history_path(), 'w', encoding='utf8') as f:
                f.write(content)
            self.assertEqual(loadsearch(), [], 'failed for: {}'.format(content))

    def test_non_list_overwritten_on_next_store(self):
        with io.open(self._history_path(), 'w', encoding='utf8') as f:
            f.write('null')
        storesearch('first')
        self.assertEqual(loadsearch(), ['first'])

    def test_non_string_items_filtered(self):
        # Older/corrupt files may hold non-strings; loadsearch drops them.
        with io.open(self._history_path(), 'w', encoding='utf8') as f:
            f.write('["ok", 123, null, "fine", {"x": 1}]')
        self.assertEqual(loadsearch(), ['ok', 'fine'])


class TestReproducerScenario(SearchHistoryTestBase):
    """50 consecutive stores — user's bug scenario."""

    def test_50_stores_caps_at_20(self):
        cache._addon = _FakeAddon(shistory='20')
        for i in range(50):
            storesearch('term_{:02d}'.format(i))
        history = loadsearch()
        self.assertEqual(len(history), 20)
        self.assertEqual(history[0], 'term_49')
        self.assertEqual(history[-1], 'term_30')

    def test_50_stores_file_is_valid_json(self):
        cache._addon = _FakeAddon(shistory='20')
        for i in range(50):
            storesearch('term_{:02d}'.format(i))
        raw = self._read_raw()
        parsed = json.loads(raw)
        self.assertEqual(len(parsed), 20)


class TestAtomicWrite(SearchHistoryTestBase):
    """Verify no .tmp leftover after success and file is always valid."""

    def test_no_tmp_leftover_after_store(self):
        storesearch('a')
        storesearch('b')
        files = os.listdir(self._tmpdir)
        self.assertIn(SEARCH_HISTORY, files)
        # Unique tmp names use prefix SEARCH_HISTORY + '.'; none should survive
        for f in files:
            self.assertFalse(f.endswith('.tmp'),
                             'leftover tmp file: {}'.format(f))

    def test_file_always_parses_after_each_store(self):
        for i in range(30):
            storesearch('x{}'.format(i))
            raw = self._read_raw()
            self.assertIsInstance(json.loads(raw), list)

    def test_profile_dir_autocreated(self):
        import shutil
        shutil.rmtree(self._tmpdir)
        self.assertFalse(os.path.exists(self._tmpdir))
        storesearch('a')
        self.assertTrue(os.path.exists(self._history_path()))


class TestConcurrentSave(SearchHistoryTestBase):
    """Concurrent savesearch must not corrupt the history file.

    Reproducer for the race that produced '[\"X\", \"Y\"] \"C\", ...' JSON.
    """

    def test_concurrent_writes_yield_valid_json(self):
        import threading

        def writer(idx):
            for i in range(5):
                savesearch(['t_{}_{}_{}'.format(idx, i, j) for j in range(20)])

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        raw = self._read_raw()
        data = json.loads(raw)  # must not raise
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 20)

    def test_concurrent_no_tmp_leftover(self):
        import threading

        def writer(idx):
            for i in range(3):
                savesearch(['x_{}_{}'.format(idx, i)])

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        leftovers = [f for f in os.listdir(self._tmpdir) if f.endswith('.tmp')]
        self.assertEqual(leftovers, [])


class TestSearchUIWritesHistory(SearchHistoryTestBase):
    """Regression: search() with what= must write/bump history.

    Covers b0178fe regression — storesearch was dropped from the
    history-item-click / deep-link / pseudo-entry path.
    """

    def setUp(self):
        super(TestSearchUIWritesHistory, self).setUp()
        # Stub heavy deps so search_ui.search() runs without hitting Kodi/network.
        # search_ui caches _addon/_handle at import — patch via the module.
        import lib.search_ui as search_ui
        from lib.ui import NONE_WHAT
        self._search_ui = search_ui
        self._NONE_WHAT = NONE_WHAT

        # Bind search_ui's cached _addon to our fake addon for search() to consume.
        # Populate numeric settings consumed by search() (scategory/ssort/slimit).
        cache._addon.setSetting('scategory', '0')
        cache._addon.setSetting('ssort', '0')
        cache._addon.setSetting('slimit', '50')
        self._saved_ui_addon = search_ui._addon
        search_ui._addon = cache._addon

        # Neutralize side-effecty calls inside search().
        self._saved_revalidate = search_ui.revalidate
        self._saved_dosearch = search_ui.dosearch
        search_ui.revalidate = lambda: 'fake-token'
        self._dosearch_calls = []
        def _fake_dosearch(token, what, category, sort, limit, offset, action,
                           params=None, **kwargs):
            self._dosearch_calls.append((what, offset))
        search_ui.dosearch = _fake_dosearch

    def tearDown(self):
        self._search_ui._addon = self._saved_ui_addon
        self._search_ui.revalidate = self._saved_revalidate
        self._search_ui.dosearch = self._saved_dosearch
        super(TestSearchUIWritesHistory, self).tearDown()

    def test_search_with_what_appends_history(self):
        self._search_ui.search({'action': 'search', 'what': 'foo'})
        self.assertEqual(loadsearch(), ['foo'])

    def test_reclick_existing_term_moves_to_front(self):
        storesearch('a')
        storesearch('b')
        storesearch('c')
        # history is now ['c', 'b', 'a']
        self._search_ui.search({'action': 'search', 'what': 'a'})
        self.assertEqual(loadsearch(), ['a', 'c', 'b'])

    def test_none_what_not_stored(self):
        self._search_ui.search({'action': 'search', 'what': self._NONE_WHAT})
        self.assertNotIn(self._NONE_WHAT, loadsearch())
        self.assertEqual(loadsearch(), [])

    def test_offset_gt_zero_not_stored(self):
        self._search_ui.search({'action': 'search', 'what': 'foo', 'offset': '25'})
        self.assertEqual(loadsearch(), [])


if __name__ == '__main__':
    unittest.main()
