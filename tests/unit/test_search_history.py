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
from lib.cache import storesearch, loadsearch, savesearch, SEARCH_HISTORY


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

    def test_whitespace_term_is_stored(self):
        # "if not what" only guards falsy — whitespace is truthy and stored.
        # Document current behavior.
        storesearch('  ')
        self.assertEqual(loadsearch(), ['  '])


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


if __name__ == '__main__':
    unittest.main()
