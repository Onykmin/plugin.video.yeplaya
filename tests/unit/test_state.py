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
