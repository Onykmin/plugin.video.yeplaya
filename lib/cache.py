# -*- coding: utf-8 -*-
# Module: cache
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import io
import os
import json
import time
import threading
import xbmcaddon
from lib.logging import log_warning, log_error, log_debug

try:
    from xbmcvfs import translatePath
except ImportError:
    from xbmc import translatePath

_addon = xbmcaddon.Addon()
_profile = translatePath(_addon.getAddonInfo('profile'))
try:
    _profile = _profile.decode("utf-8")
except (AttributeError, UnicodeDecodeError):
    pass

SEARCH_HISTORY = 'search_history'

# Module-level cache for series navigation
# Thread safety: Kodi plugins typically run single-threaded per invocation,
# but we use a lock for safety in case of background service threads.
_series_cache = {}
_cache_timestamps = {}
_cache_lock = threading.Lock()
_csfd_db = None

# Default TTL: 5 minutes (300 seconds)
DEFAULT_CACHE_TTL = 300


def get_series_cache():
    """Get series cache dict (for backward compatibility)."""
    return _series_cache


def cache_set(key, value, ttl=None):
    """Thread-safe cache write with optional TTL."""
    with _cache_lock:
        _series_cache[key] = value
        _cache_timestamps[key] = time.time()
        log_debug("Cache set: {} (ttl={})".format(key, ttl or 'default'))


def cache_get(key, ttl=None):
    """Thread-safe cache read with TTL check.

    Args:
        key: Cache key
        ttl: Time-to-live in seconds (None = use default, 0 = no expiry)

    Returns:
        Cached value or None if missing/expired
    """
    effective_ttl = DEFAULT_CACHE_TTL if ttl is None else ttl
    with _cache_lock:
        if key not in _series_cache:
            return None

        # Check TTL if set
        if effective_ttl > 0:
            cached_time = _cache_timestamps.get(key, 0)
            if time.time() - cached_time > effective_ttl:
                log_debug("Cache expired: {}".format(key))
                del _series_cache[key]
                del _cache_timestamps[key]
                return None

        return _series_cache[key]


def clear_cache():
    """Clear all cached series data. Call on new search session."""
    with _cache_lock:
        _series_cache.clear()
        _cache_timestamps.clear()
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


def loadsearch():
    """Load search history from disk."""
    history = []
    try:
        if not os.path.exists(_profile):
            os.makedirs(_profile)
    except OSError as e:
        log_error("Failed to create profile directory: " + str(e))

    try:
        with io.open(os.path.join(_profile, SEARCH_HISTORY), 'r', encoding='utf8') as file:
            fdata = file.read()
            file.close()
            history = json.loads(fdata)
    except (IOError, OSError, ValueError) as e:
        log_warning("Failed to load search history: " + str(e))

    return history


def savesearch(history):
    """Save search history to disk."""
    try:
        with io.open(os.path.join(_profile, SEARCH_HISTORY), 'w', encoding='utf8') as file:
            try:
                data = json.dumps(history).decode('utf8')
            except AttributeError:
                data = json.dumps(history)
            file.write(data)
            file.close()
    except (IOError, OSError) as e:
        log_error("Failed to save search history: " + str(e))


def storesearch(what):
    """Add search term to history."""
    if what:
        size = int(_addon.getSetting('shistory'))
        history = loadsearch()

        if what in history:
            history.remove(what)

        history = [what] + history

        if len(history) > size:
            history = history[:size]

        savesearch(history)


def removesearch(what):
    """Remove search term from history."""
    if what:
        history = loadsearch()
        if what in history:
            history.remove(what)
            savesearch(history)
