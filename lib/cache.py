# -*- coding: utf-8 -*-
# Module: cache
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import io
import os
import json
import time
import tempfile
import threading
import xbmcaddon
from lib.logging import log_warning, log_error, log_debug

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

try:
    from xbmcvfs import translatePath
except ImportError:
    from xbmc import translatePath

_addon = xbmcaddon.Addon()
_profile = translatePath(_addon.getAddonInfo('profile'))

SEARCH_HISTORY = 'search_history'

# Module-level cache for series navigation
# Thread safety: Kodi plugins typically run single-threaded per invocation,
# but we use a lock for safety in case of background service threads.
_series_cache = {}
_cache_timestamps = {}
_cache_ttls = {}
_cache_lock = threading.Lock()
_csfd_db = None

# Default TTL: 5 minutes (300 seconds)
DEFAULT_CACHE_TTL = 300
MAX_CACHE_ENTRIES = 50


def get_series_cache():
    """Get series cache dict (for backward compatibility)."""
    return _series_cache


def cache_set(key, value, ttl=None):
    """Thread-safe cache write with optional TTL."""
    with _cache_lock:
        # Evict oldest entries if cache is full
        while len(_series_cache) >= MAX_CACHE_ENTRIES and key not in _series_cache:
            if not _cache_timestamps:
                break
            oldest_key = min(_cache_timestamps, key=_cache_timestamps.get)
            _series_cache.pop(oldest_key, None)
            _cache_timestamps.pop(oldest_key, None)
            _cache_ttls.pop(oldest_key, None)
            log_debug("Cache evicted: {}".format(oldest_key))

        _series_cache[key] = value
        _cache_timestamps[key] = time.time()
        if ttl is not None:
            _cache_ttls[key] = ttl
        elif key in _cache_ttls:
            del _cache_ttls[key]
        log_debug("Cache set: {} (ttl={})".format(key, ttl or 'default'))


def cache_get(key, ttl=None):
    """Thread-safe cache read with TTL check.

    Args:
        key: Cache key
        ttl: Time-to-live in seconds (None = use default, 0 = no expiry)

    Returns:
        Cached value or None if missing/expired
    """
    with _cache_lock:
        if key not in _series_cache:
            return None

        # Use per-item TTL if stored, then parameter, then default
        effective_ttl = _cache_ttls.get(key, DEFAULT_CACHE_TTL if ttl is None else ttl)

        # Check TTL if set
        if effective_ttl > 0:
            cached_time = _cache_timestamps.get(key, 0)
            if time.time() - cached_time > effective_ttl:
                log_debug("Cache expired: {}".format(key))
                _series_cache.pop(key, None)
                _cache_timestamps.pop(key, None)
                _cache_ttls.pop(key, None)
                return None

        return _series_cache[key]


def clear_cache():
    """Clear all cached series data. Call on new search session."""
    with _cache_lock:
        _series_cache.clear()
        _cache_timestamps.clear()
        _cache_ttls.clear()
        log_debug("Cache cleared")


def build_cache_key(what, category='', sort_val=''):
    """Build consistent cache key from search parameters."""
    return '{0}_{1}_{2}'.format(what, category, sort_val)


def get_or_fetch_grouped(params, token, check_key=None, check_type='series'):
    """Get grouped data from cache or fetch if missing."""
    from lib.grouping import fetch_and_group_series

    category = params.get('category', '')
    sort_val = params.get('sort', '')
    cache_key = build_cache_key(params['what'], category, sort_val)
    grouped = cache_get(cache_key)

    needs_fetch = not grouped
    if check_key and grouped:
        if check_type == 'series':
            needs_fetch = check_key not in grouped.get('series', {})
        elif check_type == 'movies':
            needs_fetch = check_key not in grouped.get('movies', {})

    if needs_fetch and token:
        grouped = fetch_and_group_series(token, params['what'], category, sort_val)
        if grouped:
            cache_set(cache_key, grouped)

    return cache_key, grouped


def _flock(f, exclusive=False):
    """Acquire file lock if available (Unix). No-op on Windows/Android."""
    if _HAS_FCNTL:
        fcntl.flock(f, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)


def _funlock(f):
    """Release file lock if available."""
    if _HAS_FCNTL:
        fcntl.flock(f, fcntl.LOCK_UN)


def loadsearch():
    """Load search history from disk (with file locking)."""
    history = []
    try:
        os.makedirs(_profile, exist_ok=True)
    except OSError as e:
        log_error("Failed to create profile directory: " + str(e))

    path = os.path.join(_profile, SEARCH_HISTORY)
    try:
        with io.open(path, 'r', encoding='utf8') as f:
            _flock(f)
            try:
                raw = f.read()
            finally:
                _funlock(f)
        history = json.loads(raw) if raw else []
        log_debug("loadsearch: {} items, file={} bytes".format(len(history), len(raw)))
    except (IOError, OSError) as e:
        log_warning("loadsearch: IO error ({}): {}".format(path, e))
    except ValueError as e:
        try:
            sz = os.path.getsize(path)
        except OSError:
            sz = -1
        log_warning("loadsearch: corrupt JSON (size={}): {}".format(sz, e))

    return history


def savesearch(history):
    """Save search history to disk atomically (unique tmp + os.replace).

    Each call uses a unique tmp file (via tempfile.mkstemp) so concurrent
    writers cannot corrupt a shared tmp.
    """
    try:
        os.makedirs(_profile, exist_ok=True)
        path = os.path.join(_profile, SEARCH_HISTORY)
        fd, tmp = tempfile.mkstemp(dir=_profile,
                                   prefix=SEARCH_HISTORY + '.',
                                   suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf8') as f:
                f.write(json.dumps(history))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except (IOError, OSError) as e:
        log_error("Failed to save search history: " + str(e))


def storesearch(what):
    """Add search term to history."""
    if not what:
        return
    try:
        size = int(_addon.getSetting('shistory'))
    except (ValueError, TypeError):
        size = 20
    if size <= 0:
        size = 20
    history = loadsearch()
    if what in history:
        history.remove(what)
    history = [what] + history
    if len(history) > size:
        history = history[:size]
    log_debug("storesearch: writing {} items (cap={})".format(len(history), size))
    savesearch(history)


def removesearch(what):
    """Remove search term from history."""
    if what:
        history = loadsearch()
        if what in history:
            history.remove(what)
            savesearch(history)
