# -*- coding: utf-8 -*-
"""In-memory search cache: key building, TTL expiry, eviction, fetch-on-miss."""
import threading

import pytest

import lib.cache as cache
from lib.cache import build_cache_key, cache_get, cache_set, clear_cache
from lib.keys import NONE_WHAT


@pytest.fixture(autouse=True)
def clean_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def clock(monkeypatch):
    """Fake time.time for lib.cache: advance with clock.advance(seconds)."""
    class Clock:
        now = 1000.0

        def advance(self, seconds):
            self.now += seconds

    c = Clock()
    monkeypatch.setattr(cache.time, 'time', lambda: c.now)
    return c


@pytest.mark.parametrize('a, b', [
    (('SouthPark', 'video', ''), ('southpark', 'video', '')),
    (('  southpark  ', 'video', ''), ('southpark', 'video', '')),
    ((NONE_WHAT, 'video', 'recent'), (None, 'video', 'recent')),
])
def test_equivalent_queries_share_a_key(a, b):
    assert build_cache_key(*a) == build_cache_key(*b)


@pytest.mark.parametrize('a, b', [
    (('test1', 'cat', 'sort'), ('test2', 'cat', 'sort')),
    (('test', 'cat1', 'sort'), ('test', 'cat2', 'sort')),
    (('test', 'cat', 'recent'), ('test', 'cat', 'largest')),
])
def test_different_queries_get_different_keys(a, b):
    assert build_cache_key(*a) != build_cache_key(*b)


def test_miss_returns_none():
    assert cache_get('nope') is None


def test_entry_expires_after_default_ttl(clock):
    cache_set('k', 'v')
    clock.advance(299)
    assert cache_get('k') == 'v'
    clock.advance(2)
    assert cache_get('k') is None
    assert 'k' not in cache._series_cache  # expired entries are dropped, not kept


def test_per_entry_ttl_overrides_default(clock):
    cache_set('short', 'v', ttl=10)
    clock.advance(11)
    assert cache_get('short') is None


def test_ttl_zero_never_expires(clock):
    cache_set('k', 'v', ttl=0)
    clock.advance(10 ** 6)
    assert cache_get('k') == 'v'


def test_rewrite_refreshes_timestamp_and_drops_old_custom_ttl(clock):
    cache_set('k', 'old', ttl=10)
    clock.advance(5)
    cache_set('k', 'new')  # back to default TTL
    clock.advance(100)
    assert cache_get('k') == 'new'


def test_full_cache_evicts_oldest_entry(clock):
    for i in range(cache.MAX_CACHE_ENTRIES):
        cache_set('k%d' % i, i)
        clock.advance(1)
    cache_set('new', 'x')
    assert cache_get('k0') is None
    assert cache_get('k1') == 1
    assert cache_get('new') == 'x'


def test_overwriting_existing_key_in_full_cache_evicts_nothing(clock):
    for i in range(cache.MAX_CACHE_ENTRIES):
        cache_set('k%d' % i, i)
    cache_set('k0', 'again')
    assert all(cache_get('k%d' % i) is not None for i in range(cache.MAX_CACHE_ENTRIES))


def test_clear_cache_removes_everything():
    cache_set('a', 1)
    cache_set('b', 2, ttl=0)
    clear_cache()
    assert cache_get('a') is None and cache_get('b') is None


def test_concurrent_writers_do_not_exceed_capacity_or_raise():
    errors = []

    def writer(tid):
        try:
            for i in range(100):
                cache_set('t%d_%d' % (tid, i), i)
                cache_get('t%d_%d' % (tid, i))
        except Exception as e:  # pragma: no cover - only on failure
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(cache._series_cache) <= cache.MAX_CACHE_ENTRIES


class TestGetOrFetchGrouped:
    @pytest.fixture
    def fetch(self, monkeypatch):
        calls = []

        def fake(token, what, category, sort_val):
            calls.append(what)
            return {'series': {'South Park': {}}, 'movies': {}}

        monkeypatch.setattr('lib.grouping.fetch_and_group_series', fake)
        return calls

    def test_second_lookup_is_served_from_cache(self, fetch):
        params = {'what': 'South Park'}
        cache.get_or_fetch_grouped(params, 'tok')
        key, grouped = cache.get_or_fetch_grouped({'what': 'south park'}, 'tok')
        assert fetch == ['South Park']
        assert 'South Park' in grouped['series']
        assert key == 'south park__'

    def test_missing_series_in_cached_result_triggers_refetch(self, fetch):
        cache.get_or_fetch_grouped({'what': 'x'}, 'tok')
        cache.get_or_fetch_grouped({'what': 'x'}, 'tok', check_key='Other Show')
        assert len(fetch) == 2

    def test_no_token_means_no_fetch(self, fetch):
        _, grouped = cache.get_or_fetch_grouped({'what': 'x'}, None)
        assert grouped is None and fetch == []


def test_lock_helpers_never_raise_on_broken_file():
    class BadFile:
        def fileno(self):
            raise OSError('bad fd')

    cache._flock(BadFile(), exclusive=True)
    cache._funlock(BadFile())
