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
import contextlib
import xbmcaddon
from lib.keys import NONE_WHAT as _NONE_WHAT
from lib.logging import log_warning, log_error, log_debug
from lib.search import _normalize

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

try:
    import msvcrt
    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False

try:
    from xbmcvfs import translatePath
except ImportError:
    from xbmc import translatePath

_addon = xbmcaddon.Addon()
_profile = translatePath(_addon.getAddonInfo('profile'))


def refresh_cache_addon():
    """Re-bind module-level _addon. Call from SettingsMonitor on settings change."""
    global _addon
    _addon = xbmcaddon.Addon()

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
    """Build consistent cache key from search parameters.

    NONE_WHAT (the Newest/Biggest browse sentinel) and None collapse to ''
    so all such requests share one cache entry. Lowercase + strip on `what`
    prevents fragmentation across casing differences.
    """
    if what is None or what == _NONE_WHAT:
        what = ''
    else:
        what = str(what).lower().strip()
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


# Windows msvcrt.locking takes a byte count from the CURRENT file position,
# not an absolute range. We always seek(0) before lock/unlock so the locked
# region is well-defined and the unlock targets the same region. Use max
# int32 to cover the whole file rather than the original 1-byte lock.
_MSVCRT_LOCK_LEN = 0x7FFFFFFF


def profile_dir():
    """Addon profile directory (created on demand). Shared by all stores."""
    try:
        os.makedirs(_profile, exist_ok=True)
    except OSError as e:
        log_error("Failed to create profile directory: " + str(e))
    return _profile


def _flock(f, exclusive=True):
    """Acquire a whole-file lock if available. Best-effort; never crashes.

    Defaults to an exclusive, BLOCKING lock: msvcrt has no shared mode, and a
    non-blocking lock would silently fall through to an unprotected read on
    contention. fcntl uses LOCK_EX/LOCK_SH; msvcrt is always exclusive.
    """
    try:
        if _HAS_FCNTL:
            fcntl.flock(f, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        elif _HAS_MSVCRT:
            f.seek(0)
            # LK_LOCK blocks (retries ~10s) instead of failing open.
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, _MSVCRT_LOCK_LEN)
    except (OSError, IOError, ValueError):
        pass


def _funlock(f):
    """Release the whole-file lock if available. Best-effort.

    msvcrt unlocks relative to the file pointer, so we seek(0) first to match
    the region _flock locked (a prior read may have advanced the pointer).
    """
    try:
        if _HAS_FCNTL:
            fcntl.flock(f, fcntl.LOCK_UN)
        elif _HAS_MSVCRT:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, _MSVCRT_LOCK_LEN)
    except (OSError, IOError, ValueError):
        pass


# Per-process locks for each sidecar path. fcntl/msvcrt locks are
# process-level (per open file description), so two THREADS in one process
# wouldn't serialize on the file lock alone — pair it with a threading lock.
_file_locks = {}
_file_locks_guard = threading.Lock()


def _thread_lock_for(lock_path):
    with _file_locks_guard:
        lk = _file_locks.get(lock_path)
        if lk is None:
            lk = threading.Lock()
            _file_locks[lock_path] = lk
        return lk


@contextlib.contextmanager
def file_lock(lock_path):
    """Hold an exclusive lock for a read-modify-write cycle.

    Serializes both threads (in-process threading.Lock) and separate Kodi
    processes (advisory lock on a dedicated sidecar file — never the data
    file, whose inode is swapped by os.replace, so the lock survives an atomic
    write done inside the block). Best-effort on the cross-process half: if no
    lock primitive is available the block still runs.
    """
    profile_dir()
    thread_lock = _thread_lock_for(lock_path)
    thread_lock.acquire()
    f = None
    try:
        try:
            f = io.open(lock_path, 'a+', encoding='utf8')
            _flock(f, exclusive=True)
        except (IOError, OSError) as e:
            log_warning("file_lock: could not open {}: {}".format(lock_path, e))
            f = None
        yield
    finally:
        if f is not None:
            try:
                _funlock(f)
            finally:
                f.close()
        thread_lock.release()


def locked_read_text(path):
    """Read a UTF-8 text file under a shared/whole-file lock. Returns '' on miss."""
    profile_dir()
    try:
        with io.open(path, 'r', encoding='utf8') as f:
            _flock(f, exclusive=False)
            try:
                return f.read()
            finally:
                _funlock(f)
    except (IOError, OSError) as e:
        log_warning("locked_read_text: IO error ({}): {}".format(path, e))
        return ''


def atomic_write_text(path, text):
    """Atomically write UTF-8 text via a unique tmp file + os.replace.

    A unique tmp (tempfile.mkstemp) means concurrent writers never share a
    tmp; os.replace is atomic so readers never see a torn file.
    """
    directory = os.path.dirname(path) or _profile
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory,
                                   prefix=os.path.basename(path) + '.',
                                   suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf8') as f:
                f.write(text)
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
        log_error("atomic_write_text: write failed ({}): {}".format(path, e))


def loadsearch():
    """Load search history from disk (with file locking)."""
    path = os.path.join(_profile, SEARCH_HISTORY)
    raw = locked_read_text(path)
    if not raw:
        return []
    try:
        history = json.loads(raw)
    except ValueError as e:
        try:
            sz = os.path.getsize(path)
        except OSError:
            sz = -1
        log_warning("loadsearch: corrupt JSON (size={}): {}".format(sz, e))
        return []
    if not isinstance(history, list):
        log_warning("loadsearch: non-list JSON on disk ({}), resetting".format(
            type(history).__name__))
        return []
    # Defend against non-string items on disk (older/corrupt files): downstream
    # display and dedup assume strings.
    history = [s for s in history if isinstance(s, str)]
    log_debug("loadsearch: {} items, file={} bytes".format(len(history), len(raw)))
    return history


def savesearch(history):
    """Save search history to disk atomically (unique tmp + os.replace)."""
    atomic_write_text(os.path.join(_profile, SEARCH_HISTORY), json.dumps(history))


def storesearch(what):
    """Add search term to history.

    Dedup is case/accent/whitespace-insensitive (via _normalize): re-searching
    "Avatar", "avatar", or " avatár " all collapse to one entry, keeping the
    newest casing at the front.
    """
    if not what:
        return
    what = what.strip()
    if not what:
        return
    try:
        size = int(_addon.getSetting('shistory'))
    except (ValueError, TypeError):
        size = 20
    if size <= 0:
        size = 20
    key = _normalize(what)
    history = [s for s in loadsearch() if _normalize(s) != key]
    history = [what] + history
    if len(history) > size:
        history = history[:size]
    log_debug("storesearch: writing {} items (cap={})".format(len(history), size))
    savesearch(history)


def removesearch(what):
    """Remove search term from history (case/accent/whitespace-insensitive)."""
    if not what:
        return
    key = _normalize(what)
    history = loadsearch()
    pruned = [s for s in history if _normalize(s) != key]
    if len(pruned) != len(history):
        savesearch(pruned)
