#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for cache module.

Tests:
- Cache key consistency
- TTL expiration
- Thread safety
- Cache clearing on new search session
"""

import sys
import os
import time
import threading
import unittest

# Add parent directory for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Mock Kodi modules before any imports
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3

    @staticmethod
    def log(msg, level=0):
        pass


class MockXBMCAddon:
    class Addon:
        def __init__(self):
            self._settings = {'shistory': '10'}

        def getSetting(self, key):
            return self._settings.get(key, '')

        def getAddonInfo(self, key):
            return '/tmp/test_profile'


class MockXBMCVFS:
    @staticmethod
    def translatePath(path):
        return path


sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcaddon'] = MockXBMCAddon()
sys.modules['xbmcvfs'] = MockXBMCVFS()

# Now import cache module
from lib.cache import (
    build_cache_key, cache_set, cache_get, clear_cache,
    _series_cache, _cache_timestamps, _cache_lock, DEFAULT_CACHE_TTL
)


class TestCacheKeyConsistency(unittest.TestCase):
    """Test cache key generation is consistent."""

    def test_basic_key_format(self):
        """Cache key should have format: what_category_sort."""
        key = build_cache_key('southpark', 'video', 'recent')
        self.assertEqual(key, 'southpark_video_recent')

    def test_empty_category_sort(self):
        """Empty category and sort should produce valid key."""
        key = build_cache_key('query', '', '')
        self.assertEqual(key, 'query__')

    def test_key_with_special_chars(self):
        """Key should handle special characters in search term."""
        key = build_cache_key('game.of.thrones', 'video', '')
        self.assertEqual(key, 'game.of.thrones_video_')

    def test_key_consistency(self):
        """Same inputs should always produce same key."""
        key1 = build_cache_key('test', 'cat', 'sort')
        key2 = build_cache_key('test', 'cat', 'sort')
        self.assertEqual(key1, key2)

    def test_different_inputs_different_keys(self):
        """Different inputs should produce different keys."""
        key1 = build_cache_key('test1', 'cat', 'sort')
        key2 = build_cache_key('test2', 'cat', 'sort')
        self.assertNotEqual(key1, key2)


class TestCacheTTL(unittest.TestCase):
    """Test cache TTL (time-to-live) functionality."""

    def setUp(self):
        """Clear cache before each test."""
        clear_cache()

    def tearDown(self):
        """Clear cache after each test."""
        clear_cache()

    def test_cache_set_get(self):
        """Basic set and get should work."""
        cache_set('test_key', {'data': 'value'})
        result = cache_get('test_key', ttl=0)  # No expiry
        self.assertEqual(result, {'data': 'value'})

    def test_cache_miss_returns_none(self):
        """Missing key should return None."""
        result = cache_get('nonexistent_key')
        self.assertIsNone(result)

    def test_cache_expiry(self):
        """Cache should expire after TTL."""
        # Set with very short TTL
        cache_set('expiring_key', {'data': 'value'})

        # Manipulate timestamp to simulate expiry
        with _cache_lock:
            _cache_timestamps['expiring_key'] = time.time() - 400  # 400 seconds ago

        # Should be expired (default TTL is 300 seconds)
        result = cache_get('expiring_key')
        self.assertIsNone(result, "Expired cache should return None")

    def test_cache_not_expired(self):
        """Cache should not expire before TTL."""
        cache_set('fresh_key', {'data': 'value'})

        # Entry is fresh, should not be expired
        result = cache_get('fresh_key')
        self.assertEqual(result, {'data': 'value'})

    def test_cache_no_ttl(self):
        """Cache with ttl=0 should never expire."""
        cache_set('permanent_key', {'data': 'value'})

        # Manipulate timestamp to simulate old entry
        with _cache_lock:
            _cache_timestamps['permanent_key'] = time.time() - 10000

        # With ttl=0, should not expire
        result = cache_get('permanent_key', ttl=0)
        self.assertEqual(result, {'data': 'value'})

    def test_clear_cache(self):
        """clear_cache should remove all entries."""
        cache_set('key1', 'value1')
        cache_set('key2', 'value2')

        clear_cache()

        self.assertIsNone(cache_get('key1', ttl=0))
        self.assertIsNone(cache_get('key2', ttl=0))


class TestCacheThreadSafety(unittest.TestCase):
    """Test cache thread safety."""

    def setUp(self):
        """Clear cache before each test."""
        clear_cache()

    def tearDown(self):
        """Clear cache after each test."""
        clear_cache()

    def test_concurrent_writes(self):
        """Concurrent writes should not corrupt cache."""
        errors = []
        write_count = 100

        def writer(thread_id):
            try:
                for i in range(write_count):
                    key = 'thread_{}_{}'.format(thread_id, i)
                    cache_set(key, {'thread': thread_id, 'index': i})
            except Exception as e:
                errors.append(e)

        # Start multiple writer threads
        threads = []
        for t_id in range(5):
            t = threading.Thread(target=writer, args=(t_id,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # No errors should have occurred
        self.assertEqual(len(errors), 0, "Concurrent writes caused errors: {}".format(errors))

        # Verify some entries exist
        result = cache_get('thread_0_0', ttl=0)
        self.assertIsNotNone(result)

    def test_concurrent_read_write(self):
        """Concurrent reads and writes should not corrupt cache."""
        errors = []
        iterations = 50

        def writer():
            try:
                for i in range(iterations):
                    cache_set('shared_key', {'iteration': i})
            except Exception as e:
                errors.append(('writer', e))

        def reader():
            try:
                for i in range(iterations):
                    result = cache_get('shared_key', ttl=0)
                    # Result should be None or a valid dict
                    if result is not None and not isinstance(result, dict):
                        errors.append(('reader', 'Invalid result type: {}'.format(type(result))))
            except Exception as e:
                errors.append(('reader', e))

        # Start reader and writer threads
        writer_thread = threading.Thread(target=writer)
        reader_threads = [threading.Thread(target=reader) for _ in range(3)]

        writer_thread.start()
        for t in reader_threads:
            t.start()

        writer_thread.join()
        for t in reader_threads:
            t.join()

        self.assertEqual(len(errors), 0, "Concurrent read/write caused errors: {}".format(errors))


class TestCacheIntegration(unittest.TestCase):
    """Integration tests for cache with search session."""

    def setUp(self):
        """Clear cache before each test."""
        clear_cache()

    def tearDown(self):
        """Clear cache after each test."""
        clear_cache()

    def test_new_search_clears_cache(self):
        """New search session should clear old cache data."""
        # Simulate old search session
        cache_set('old_search__', {'series': {'OldShow': {}}})

        # New search session clears cache
        clear_cache()

        # Old data should be gone
        result = cache_get('old_search__', ttl=0)
        self.assertIsNone(result)

    def test_cache_survives_pagination(self):
        """Cache should survive during pagination within session."""
        # Set cache for search
        cache_set('southpark_video_', {'series': {'Southpark': {'seasons': {1: {}}}}})

        # Pagination should still find cache
        result = cache_get('southpark_video_', ttl=0)
        self.assertIsNotNone(result)
        self.assertIn('Southpark', result['series'])


if __name__ == '__main__':
    unittest.main()
