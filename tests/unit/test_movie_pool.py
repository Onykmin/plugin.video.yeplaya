#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for lib.movie_pool — persistent WDQS-backed movie title pool.

Covers:
- Pool cache / persistence round-trip through a temp profile dir (never the
  real Kodi profile).
- Corrupt JSON / wrong version / non-list items / invalid items handling.
- Czech diacritics survive the JSON round-trip (ensure_ascii=False).
- Compact envelope serialization.
- Refresh failure keeps the last good pool untouched (doc line 181).
- Dedupe on top-up (_dedupe_merge).
- Random selection + exclusion (pick_random): respects excluded, never
  mutates it, returns None when exhausted and top-up yields nothing new.

All network access (lib.wdqs.fetch_candidates) is mocked; nothing here ever
touches the real Kodi profile directory.
"""

import io
import os
import json
import shutil
import tempfile
import unittest
import unittest.mock as mock

import tests.conftest  # noqa: F401 — installs Kodi mocks

import lib.cache as cache
import lib.movie_pool as movie_pool


class MoviePoolTestBase(unittest.TestCase):
    """Per-test tmp profile dir, restored in tearDown.

    movie_pool delegates persistence to lib.cache helpers, which resolve the
    profile dir from cache._profile — same pattern as test_favorites.py.
    """

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix='yeplaya_pool_test_')
        self._saved_profile = cache._profile
        cache._profile = self._tmpdir
        movie_pool.invalidate_cache()

    def tearDown(self):
        cache._profile = self._saved_profile
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        movie_pool.invalidate_cache()

    def _path(self):
        return os.path.join(self._tmpdir, movie_pool.POOL_FILE)

    def _read_raw(self):
        with io.open(self._path(), 'r', encoding='utf8') as f:
            return f.read()

    def _write_raw(self, content):
        os.makedirs(self._tmpdir, exist_ok=True)
        with io.open(self._path(), 'w', encoding='utf8') as f:
            f.write(content)


# ---------------------------------------------------------------------------
# Round-trip persistence
# ---------------------------------------------------------------------------

class TestSaveLoadRoundtrip(MoviePoolTestBase):
    def test_round_trip_basic(self):
        items = [{'id': 'Q1', 'cs': 'a', 'en': 'b'}, {'id': 'Q2', 'cs': None, 'en': 'c'}]
        movie_pool._save_envelope(12345, items)
        self.assertEqual(movie_pool.load_pool(), items)

    def test_round_trip_uses_in_memory_cache(self):
        items = [{'id': 'Q1', 'cs': 'a', 'en': 'b'}]
        movie_pool._save_envelope(1, items)
        loaded1 = movie_pool.load_pool()
        loaded2 = movie_pool.load_pool()
        self.assertEqual(loaded1, loaded2)
        # load_pool returns a COPY each time.
        loaded1.append({'id': 'INJECTED', 'cs': 'x', 'en': 'y'})
        self.assertEqual(movie_pool.load_pool(), items)

    def test_missing_file_returns_empty_pool(self):
        self.assertEqual(movie_pool.load_pool(), [])

    def test_czech_diacritics_survive_round_trip(self):
        items = [{'id': 'Q1', 'cs': 'Tučňák', 'en': 'Penguin'},
                 {'id': 'Q2', 'cs': 'Přítelkyně', 'en': None}]
        movie_pool._save_envelope(1, items)
        loaded = movie_pool.load_pool()
        self.assertEqual(loaded, items)
        # Confirm the file is literal UTF-8, not \uXXXX-escaped (ensure_ascii=False).
        raw = self._read_raw()
        self.assertIn('Tučňák', raw)
        self.assertNotIn('\\u', raw)

    def test_envelope_written_compact(self):
        items = [{'id': 'Q1', 'cs': 'a', 'en': 'b'}]
        movie_pool._save_envelope(1, items)
        raw = self._read_raw()
        # Compact separators: no ", " or ": " padding.
        self.assertNotIn(', ', raw)
        self.assertNotIn(': ', raw)

    def test_envelope_has_version_and_fetched_at(self):
        movie_pool._save_envelope(999, [{'id': 'Q1', 'cs': 'a', 'en': None}])
        raw = self._read_raw()
        data = json.loads(raw)
        self.assertEqual(data['version'], movie_pool.ENVELOPE_VERSION)
        self.assertEqual(data['fetched_at'], 999)
        self.assertEqual(len(data['items']), 1)


# ---------------------------------------------------------------------------
# Corrupt / malformed on-disk data
# ---------------------------------------------------------------------------

class TestCorruptOnDisk(MoviePoolTestBase):
    def test_corrupt_json_returns_empty_pool(self):
        self._write_raw('{not valid json')
        self.assertEqual(movie_pool.load_pool(), [])

    def test_empty_file_returns_empty_pool(self):
        self._write_raw('')
        self.assertEqual(movie_pool.load_pool(), [])

    def test_top_level_not_dict_returns_empty(self):
        self._write_raw('[1, 2, 3]')
        self.assertEqual(movie_pool.load_pool(), [])

    def test_wrong_version_returns_empty(self):
        self._write_raw(json.dumps({'version': 999, 'fetched_at': 1, 'items': [
            {'id': 'Q1', 'cs': 'a', 'en': None}
        ]}))
        self.assertEqual(movie_pool.load_pool(), [])

    def test_missing_version_returns_empty(self):
        self._write_raw(json.dumps({'fetched_at': 1, 'items': [
            {'id': 'Q1', 'cs': 'a', 'en': None}
        ]}))
        self.assertEqual(movie_pool.load_pool(), [])

    def test_items_not_a_list_returns_empty(self):
        self._write_raw(json.dumps({'version': movie_pool.ENVELOPE_VERSION,
                                     'fetched_at': 1, 'items': 'not-a-list'}))
        self.assertEqual(movie_pool.load_pool(), [])

    def test_invalid_items_filtered_out(self):
        raw = json.dumps({'version': movie_pool.ENVELOPE_VERSION, 'fetched_at': 1, 'items': [
            {'id': 'Q1', 'cs': 'a', 'en': None},   # valid
            {'id': '', 'cs': 'a', 'en': None},      # invalid: empty id
            {'cs': 'a', 'en': None},                # invalid: no id
            {'id': 'Q2'},                           # invalid: no cs/en
            {'id': 'Q3', 'cs': None, 'en': None},   # invalid: both None
            {'id': 'Q4', 'cs': 123, 'en': None},    # invalid: cs not str
            'not-a-dict',                            # invalid: not a dict
            {'id': 'Q5', 'cs': 'ok', 'en': 'also ok'},  # valid
        ]})
        self._write_raw(raw)
        loaded = movie_pool.load_pool()
        ids = sorted(it['id'] for it in loaded)
        self.assertEqual(ids, ['Q1', 'Q5'])


# ---------------------------------------------------------------------------
# Year field ('y'): additive, optional — NOT an ENVELOPE_VERSION bump
# ---------------------------------------------------------------------------

class TestYearFieldBackwardCompatibility(MoviePoolTestBase):
    """The migration test that matters: lib.wdqs now sometimes attaches a
    'y' (int year) key, but ENVELOPE_VERSION was deliberately NOT bumped
    (see the comment on ENVELOPE_VERSION in lib/movie_pool.py) — a v1
    envelope whose records predate year support, with no 'y' key at all,
    must keep loading and picking exactly as before."""

    def test_v1_records_without_year_key_load_fine(self):
        raw = json.dumps({'version': movie_pool.ENVELOPE_VERSION, 'fetched_at': 1, 'items': [
            {'id': 'Q1', 'cs': 'Stary Film', 'en': None},
            {'id': 'Q2', 'cs': None, 'en': 'Old Movie'},
        ]})
        self._write_raw(raw)
        loaded = movie_pool.load_pool()
        self.assertEqual(len(loaded), 2)
        for it in loaded:
            self.assertNotIn('y', it)

    def test_pick_random_returns_yearless_v1_record_normally(self):
        """Old records without 'y' stay pickable — pick_random must not
        require or special-case the key."""
        raw = json.dumps({'version': movie_pool.ENVELOPE_VERSION,
                           'fetched_at': int(__import__('time').time()),
                           'items': [{'id': 'Q1', 'cs': 'Stary Film', 'en': None}]})
        self._write_raw(raw)
        with mock.patch.object(movie_pool.wdqs, 'fetch_candidates') as fetch_mock:
            picked = movie_pool.pick_random(set())
        self.assertEqual(picked, {'id': 'Q1', 'cs': 'Stary Film', 'en': None})
        fetch_mock.assert_not_called()

    def test_mixed_pool_with_and_without_year_all_valid_and_pickable(self):
        raw = json.dumps({'version': movie_pool.ENVELOPE_VERSION,
                           'fetched_at': int(__import__('time').time()),
                           'items': [
                               {'id': 'Q1', 'cs': 'a', 'en': None},
                               {'id': 'Q2', 'cs': 'b', 'en': None, 'y': 2005},
                               {'id': 'Q3', 'cs': None, 'en': 'c', 'y': 1999},
                           ]})
        self._write_raw(raw)
        loaded = movie_pool.load_pool()
        self.assertEqual(len(loaded), 3)
        with mock.patch.object(movie_pool.wdqs, 'fetch_candidates') as fetch_mock:
            excluded = {'Q2', 'Q3'}
            picked = movie_pool.pick_random(excluded)
        self.assertEqual(picked['id'], 'Q1')
        fetch_mock.assert_not_called()

    def test_new_record_with_year_round_trips(self):
        items = [{'id': 'Q1', 'cs': 'a', 'en': 'b', 'y': 1998}]
        movie_pool._save_envelope(1, items)
        self.assertEqual(movie_pool.load_pool(), items)


# ---------------------------------------------------------------------------
# Refresh failure keeps last good pool (doc line 181)
# ---------------------------------------------------------------------------

class TestRefreshFailureResilience(MoviePoolTestBase):
    def test_refresh_returns_false_and_pool_unchanged_on_fetch_failure(self):
        items = [{'id': 'Q1', 'cs': 'a', 'en': 'b'}, {'id': 'Q2', 'cs': None, 'en': 'c'}]
        movie_pool._save_envelope(111, items)
        raw_before = self._read_raw()

        with mock.patch.object(movie_pool.wdqs, 'fetch_candidates', return_value=[]):
            result = movie_pool.refresh_pool(force=True)

        self.assertFalse(result)
        raw_after = self._read_raw()
        self.assertEqual(raw_before, raw_after)
        self.assertEqual(movie_pool.load_pool(), items)

    def test_refresh_skips_when_fresh_and_not_forced(self):
        items = [{'id': 'Q1', 'cs': 'a', 'en': 'b'}]
        movie_pool._save_envelope(int(__import__('time').time()), items)
        with mock.patch.object(movie_pool.wdqs, 'fetch_candidates') as fetch_mock:
            result = movie_pool.refresh_pool(force=False)
        self.assertFalse(result)
        fetch_mock.assert_not_called()

    def test_refresh_success_merges_and_returns_true(self):
        items = [{'id': 'Q1', 'cs': 'a', 'en': 'b'}]
        movie_pool._save_envelope(1, items)  # stale (fetched_at=1)
        new_records = [{'id': 'Q2', 'cs': 'x', 'en': 'y'}]
        with mock.patch.object(movie_pool.wdqs, 'fetch_candidates', return_value=new_records):
            result = movie_pool.refresh_pool()
        self.assertTrue(result)
        loaded = movie_pool.load_pool()
        ids = sorted(it['id'] for it in loaded)
        self.assertEqual(ids, ['Q1', 'Q2'])


# ---------------------------------------------------------------------------
# Dedupe on top-up (_dedupe_merge)
# ---------------------------------------------------------------------------

class TestDedupeMerge(unittest.TestCase):
    def test_overlapping_ids_merge_without_duplicates(self):
        existing = [{'id': 'Q1', 'cs': 'a', 'en': None}, {'id': 'Q2', 'cs': 'b', 'en': None}]
        new_items = [{'id': 'Q2', 'cs': 'STALE-SHOULD-LOSE', 'en': None},
                     {'id': 'Q3', 'cs': 'c', 'en': None}]
        merged = movie_pool._dedupe_merge(existing, new_items)
        ids = [it['id'] for it in merged]
        self.assertEqual(ids, ['Q1', 'Q2', 'Q3'])

    def test_existing_entries_win_ties(self):
        existing = [{'id': 'Q1', 'cs': 'ORIGINAL', 'en': None}]
        new_items = [{'id': 'Q1', 'cs': 'REPLACEMENT', 'en': None}]
        merged = movie_pool._dedupe_merge(existing, new_items)
        self.assertEqual(merged, [{'id': 'Q1', 'cs': 'ORIGINAL', 'en': None}])

    def test_order_stable_existing_first_then_new_in_order(self):
        existing = [{'id': 'Q1', 'cs': 'a', 'en': None}]
        new_items = [{'id': 'Q3', 'cs': 'c', 'en': None},
                     {'id': 'Q2', 'cs': 'b', 'en': None}]
        merged = movie_pool._dedupe_merge(existing, new_items)
        ids = [it['id'] for it in merged]
        self.assertEqual(ids, ['Q1', 'Q3', 'Q2'])

    def test_repeated_offset_pages_can_duplicate_and_still_dedupe(self):
        """WDQS OFFSET pages are NOT disjoint (doc: same offset returned 4
        different films across 4 runs) — top-ups genuinely can duplicate
        entries already held; dedupe must still collapse them."""
        existing = [{'id': 'Q1', 'cs': 'a', 'en': None}]
        new_items = [{'id': 'Q1', 'cs': 'a', 'en': None},
                     {'id': 'Q1', 'cs': 'a', 'en': None}]
        merged = movie_pool._dedupe_merge(existing, new_items)
        self.assertEqual(len(merged), 1)

    def test_empty_existing(self):
        new_items = [{'id': 'Q1', 'cs': 'a', 'en': None}]
        merged = movie_pool._dedupe_merge([], new_items)
        self.assertEqual(merged, new_items)

    def test_empty_new(self):
        existing = [{'id': 'Q1', 'cs': 'a', 'en': None}]
        merged = movie_pool._dedupe_merge(existing, [])
        self.assertEqual(merged, existing)


# ---------------------------------------------------------------------------
# Random selection + exclusion (pick_random)
# ---------------------------------------------------------------------------

class TestPickRandom(MoviePoolTestBase):
    def _seed_pool(self, ids):
        items = [{'id': i, 'cs': i, 'en': None} for i in ids]
        movie_pool._save_envelope(int(__import__('time').time()), items)
        return items

    def test_respects_excluded(self):
        self._seed_pool(['Q1', 'Q2', 'Q3'])
        excluded = {'Q1', 'Q2'}
        with mock.patch.object(movie_pool.wdqs, 'fetch_candidates') as fetch_mock:
            picked = movie_pool.pick_random(excluded)
        self.assertEqual(picked['id'], 'Q3')
        fetch_mock.assert_not_called()

    def test_never_mutates_callers_excluded_set(self):
        self._seed_pool(['Q1', 'Q2', 'Q3'])
        excluded = {'Q1'}
        excluded_copy = set(excluded)
        with mock.patch.object(movie_pool.wdqs, 'fetch_candidates'):
            movie_pool.pick_random(excluded)
        self.assertEqual(excluded, excluded_copy)

    def test_returns_none_when_all_excluded_and_topup_yields_nothing(self):
        self._seed_pool(['Q1', 'Q2'])
        excluded = {'Q1', 'Q2'}
        with mock.patch.object(movie_pool.wdqs, 'fetch_candidates', return_value=[]):
            picked = movie_pool.pick_random(excluded)
        self.assertIsNone(picked)

    def test_topup_fetches_when_exhausted_and_returns_new_item(self):
        self._seed_pool(['Q1'])
        excluded = {'Q1'}
        new_records = [{'id': 'Q2', 'cs': 'fresh', 'en': None}]
        with mock.patch.object(movie_pool.wdqs, 'fetch_candidates', return_value=new_records):
            picked = movie_pool.pick_random(excluded)
        self.assertEqual(picked['id'], 'Q2')

    def test_topup_still_all_excluded_returns_none(self):
        self._seed_pool(['Q1'])
        excluded = {'Q1'}
        # Top-up returns something, but it's also excluded -> still None.
        new_records = [{'id': 'Q1', 'cs': 'dup', 'en': None}]
        with mock.patch.object(movie_pool.wdqs, 'fetch_candidates', return_value=new_records):
            picked = movie_pool.pick_random(excluded)
        self.assertIsNone(picked)

    def test_empty_pool_ensures_and_fetches(self):
        excluded = set()
        new_records = [{'id': 'Q1', 'cs': 'a', 'en': None}]
        with mock.patch.object(movie_pool.wdqs, 'fetch_candidates', return_value=new_records):
            picked = movie_pool.pick_random(excluded)
        self.assertEqual(picked['id'], 'Q1')

    def test_no_network_when_pool_has_remaining_items(self):
        self._seed_pool(['Q1', 'Q2'])
        with mock.patch.object(movie_pool.wdqs, 'fetch_candidates') as fetch_mock:
            movie_pool.pick_random(set())
        fetch_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
