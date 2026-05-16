# -*- coding: utf-8 -*-
"""Tests for state module (watched + resume persistence)."""
import os
import tempfile
import threading
import pytest
import sys

# Ensure conftest mocks are loaded first
from tests.conftest import get_mock_addon, reset_mock_addon


class _StateHarness:
    """Initialise a fresh state module bound to a tempfile DB."""

    def __init__(self):
        self.tmpdir = tempfile.mkdtemp()
        self.dbpath = os.path.join(self.tmpdir, 'state.db')
        # Reset the state module so get_db_path is re-called
        if 'lib.state' in sys.modules:
            del sys.modules['lib.state']
        from lib import state as _state
        # Override the internal path discovery
        _state._reset_for_tests(self.dbpath)
        _state._get_db_path = lambda: self.dbpath  # type: ignore
        self.state = _state

    def cleanup(self):
        self.state._reset_for_tests()
        try:
            os.remove(self.dbpath)
        except OSError:
            pass
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass


@pytest.fixture
def harness():
    h = _StateHarness()
    yield h
    h.cleanup()


class TestStateKeyFor:
    def test_episode(self, harness):
        key = harness.state.state_key_for({
            'series_name': 'south park', 'season': 5, 'episode': 3, 'ident': 'abc',
        })
        assert key == 'ep:south park|S05E03'

    def test_episode_strings(self, harness):
        key = harness.state.state_key_for({
            'series_name': 'show', 'season': '1', 'episode': '12', 'ident': 'x',
        })
        assert key == 'ep:show|S01E12'

    def test_movie(self, harness):
        key = harness.state.state_key_for({'canonical_key': 'inception|2010', 'ident': 'z'})
        assert key == 'mv:inception|2010'

    def test_file_fallback(self, harness):
        key = harness.state.state_key_for({'ident': 'deadbeef'})
        assert key == 'file:deadbeef'

    def test_empty(self, harness):
        assert harness.state.state_key_for({}) is None


class TestStateKeyDriftNormalization:
    """State keys must survive dual-name canonical_key drift.

    Dual-name detection in grouping.py produces different canonical_keys
    across fetches when different alias files are present. If state keys
    drifted with them, resume/watched would split across multiple rows.
    Normalization strips the dual-name prefix (everything before the last
    "|" in a series key; preserves trailing |year for movies).
    """

    def test_episode_simple_key_unchanged(self, harness):
        key = harness.state.state_key_for({
            'series_name': 'south park', 'season': 1, 'episode': 5,
        })
        assert key == 'ep:south park|S01E05'

    def test_episode_dual_name_prefix_stripped(self, harness):
        """mestecko|south park drifts to pandemic special cz|south park;
        both must yield the SAME normalized state key."""
        k1 = harness.state.state_key_for({
            'series_name': 'mestecko|south park', 'season': 1, 'episode': 5,
        })
        k2 = harness.state.state_key_for({
            'series_name': 'pandemic special cz|south park', 'season': 1, 'episode': 5,
        })
        assert k1 == k2 == 'ep:south park|S01E05'

    def test_movie_simple_key_unchanged(self, harness):
        key = harness.state.state_key_for({'canonical_key': 'inception|2010'})
        assert key == 'mv:inception|2010'

    def test_movie_dual_name_prefix_stripped_preserves_year(self, harness):
        k1 = harness.state.state_key_for({'canonical_key': 'tucnak|penguin|2022'})
        k2 = harness.state.state_key_for({'canonical_key': 'penguin tucnak alias|penguin|2022'})
        assert k1 == k2 == 'mv:penguin|2022'

    def test_build_mv_state_key_helper(self, harness):
        assert harness.state.build_mv_state_key('inception|2010') == 'mv:inception|2010'
        assert harness.state.build_mv_state_key('tucnak|penguin|2022') == 'mv:penguin|2022'


class TestMigration:
    def test_idempotent(self, harness):
        harness.state._connect()
        harness.state._reset_for_tests(harness.dbpath)
        harness.state._get_db_path = lambda: harness.dbpath
        # Second connect should not error
        harness.state._connect()
        conn = harness.state._connect()
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='playback_state'")
        assert cur.fetchone() is not None


class TestRecordPlayback:
    def test_short_video_skip(self, harness):
        harness.state.record_playback('ep:x|S01E01', 5, 9)
        assert harness.state.get_state('ep:x|S01E01') is None

    def test_half_way_resume(self, harness):
        harness.state.record_playback('ep:x|S01E01', 500, 1000)
        st = harness.state.get_state('ep:x|S01E01')
        assert st['watched'] == 0
        assert st['resume_seconds'] == 500
        assert st['total_seconds'] == 1000

    def test_ninety_percent_watched(self, harness):
        harness.state.record_playback('ep:x|S01E01', 900, 1000)
        st = harness.state.get_state('ep:x|S01E01')
        assert st['watched'] == 1
        assert st['resume_seconds'] == 0

    def test_ninety_five_percent_watched(self, harness):
        harness.state.record_playback('ep:x|S01E01', 950, 1000)
        st = harness.state.get_state('ep:x|S01E01')
        assert st['watched'] == 1

    def test_overwrites(self, harness):
        harness.state.record_playback('ep:x|S01E01', 300, 1000)
        harness.state.record_playback('ep:x|S01E01', 600, 1000)
        st = harness.state.get_state('ep:x|S01E01')
        assert st['resume_seconds'] == 600


class TestMarkOps:
    def test_mark_watched(self, harness):
        harness.state.mark_watched('ep:x|S01E01')
        st = harness.state.get_state('ep:x|S01E01')
        assert st['watched'] == 1

    def test_mark_unwatched(self, harness):
        harness.state.mark_watched('ep:x|S01E01')
        harness.state.mark_unwatched('ep:x|S01E01')
        st = harness.state.get_state('ep:x|S01E01')
        assert st['watched'] == 0
        assert st['resume_seconds'] == 0

    def test_clear_resume(self, harness):
        harness.state.record_playback('ep:x|S01E01', 300, 1000)
        harness.state.clear_resume('ep:x|S01E01')
        st = harness.state.get_state('ep:x|S01E01')
        assert st['resume_seconds'] == 0
        assert st['watched'] == 0
        assert st['total_seconds'] == 1000

    def test_clear_resume_missing(self, harness):
        # Should not raise
        harness.state.clear_resume('ep:never|S01E01')
        assert harness.state.get_state('ep:never|S01E01') is None


class TestGetStates:
    def test_batch(self, harness):
        harness.state.record_playback('ep:a|S01E01', 500, 1000)
        harness.state.mark_watched('ep:b|S01E01')
        keys = ['ep:a|S01E01', 'ep:b|S01E01', 'ep:c|S01E01']
        result = harness.state.get_states(keys)
        assert len(result) == 2
        assert result['ep:a|S01E01']['resume_seconds'] == 500
        assert result['ep:b|S01E01']['watched'] == 1
        assert 'ep:c|S01E01' not in result

    def test_empty(self, harness):
        assert harness.state.get_states([]) == {}
        assert harness.state.get_states([None, '']) == {}

    def test_populates_cache_for_hits_and_misses(self, harness):
        """get_states must prime _cache so a subsequent get_state hits memory
        — both for stored rows (state dict) and unknown keys (None)."""
        harness.state.record_playback('ep:a|S01E01', 500, 1000)
        harness.state._cache.clear()
        harness.state.get_states(['ep:a|S01E01', 'ep:missing|S01E01'])
        assert 'ep:a|S01E01' in harness.state._cache
        assert harness.state._cache['ep:a|S01E01']['resume_seconds'] == 500
        assert 'ep:missing|S01E01' in harness.state._cache
        assert harness.state._cache['ep:missing|S01E01'] is None


class TestMarkWatchedAtomicity:
    """mark_watched must perform read+upsert atomically under one lock so a
    concurrent record_playback cannot insert a new total between the SELECT
    and the upsert (TOCTOU race)."""

    def test_read_and_write_share_single_lock_acquisition(self, harness):
        state = harness.state
        # Seed a known total so SELECT path is exercised.
        state.record_playback('ep:atom|S01E01', 500, 1000)
        state._cache.clear()

        events = []
        real_lock = state._db_lock

        class TrackingLock:
            def __enter__(self_inner):
                events.append('acquire')
                real_lock.acquire()
                return self_inner

            def __exit__(self_inner, *exc):
                real_lock.release()
                events.append('release')

            def acquire(self_inner, *a, **kw):
                events.append('acquire')
                return real_lock.acquire(*a, **kw)

            def release(self_inner):
                real_lock.release()
                events.append('release')

        state._db_lock = TrackingLock()
        try:
            state.mark_watched('ep:atom|S01E01')
        finally:
            state._db_lock = real_lock

        # Single contiguous critical section: acquire then release, no
        # interleaving release/acquire pair between SELECT and upsert.
        assert events == ['acquire', 'release'], (
            "mark_watched must hold the lock across SELECT+upsert, "
            "got events={}".format(events))
        # And the watched flag actually landed.
        st = state.get_state('ep:atom|S01E01')
        assert st['watched'] == 1
        assert st['total_seconds'] == 1000


class TestThreadSafety:
    def test_concurrent_upserts(self, harness):
        errors = []

        def writer(k):
            try:
                for i in range(50):
                    harness.state.record_playback(k, i * 20, 1000)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=writer, args=('ep:a|S01E01',))
        t2 = threading.Thread(target=writer, args=('ep:a|S01E01',))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        assert not errors, "thread errors: %s" % errors
        st = harness.state.get_state('ep:a|S01E01')
        assert st is not None


class TestCacheInvalidation:
    def test_cache_cleared_on_write(self, harness):
        harness.state.record_playback('ep:x|S01E01', 300, 1000)
        first = harness.state.get_state('ep:x|S01E01')
        assert first['resume_seconds'] == 300
        harness.state.mark_watched('ep:x|S01E01')
        second = harness.state.get_state('ep:x|S01E01')
        assert second['watched'] == 1
        assert second['resume_seconds'] == 0


class TestGetStateLockOrder:
    def test_cache_read_under_lock(self, harness):
        """get_state must read _cache only while holding _db_lock.

        Detect by replacing _db_lock with a wrapper that records acquisition,
        then asserting that the cache hit was returned only after acquire().
        """
        import threading as _th
        state = harness.state

        # Prime cache with a known entry.
        state.record_playback('ep:lock|S01E01', 100, 1000)
        _ = state.get_state('ep:lock|S01E01')  # populates _cache

        events = []
        real_lock = state._db_lock

        class TrackingLock:
            def __enter__(self):
                events.append('acquire')
                real_lock.acquire()
                return self
            def __exit__(self, *exc):
                real_lock.release()
                events.append('release')
            def acquire(self, *a, **kw):
                events.append('acquire')
                return real_lock.acquire(*a, **kw)
            def release(self):
                real_lock.release()
                events.append('release')

        state._db_lock = TrackingLock()
        try:
            result = state.get_state('ep:lock|S01E01')
            assert result is not None
            # Lock must have been acquired before returning the cached value.
            assert events and events[0] == 'acquire', \
                "expected lock acquired before cache read, got events={}".format(events)
        finally:
            state._db_lock = real_lock
