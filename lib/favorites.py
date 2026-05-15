# -*- coding: utf-8 -*-
# Module: favorites
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Persistent favorites: search queries, series, movies.

Mirrors lib.cache search-history reliability: atomic write via tempfile +
os.replace, advisory file locking, isinstance hardening, corruption recovery.
"""

import io
import os
import json
import time
import tempfile

import xbmcaddon

from lib.cache import _flock, _funlock
from lib.logging import log_warning, log_error, log_debug

try:
    from xbmcvfs import translatePath
except ImportError:
    from xbmc import translatePath


FAVORITES = 'favorites'
ENVELOPE_VERSION = 1
MAX_FAVORITES = 200

_VALID_TYPES = ('search', 'series', 'movie')

# Per-process in-memory cache. Reset on each Kodi addon invocation
# (matches Kodi lifecycle), so cross-process staleness is not possible.
_cached_items = None


def invalidate_cache():
    """Drop the in-memory cache. Used by save_favorites and tests."""
    global _cached_items
    _cached_items = None


def _profile_path():
    addon = xbmcaddon.Addon()
    return translatePath(addon.getAddonInfo('profile'))


def _favorites_path():
    return os.path.join(_profile_path(), FAVORITES)


def _entry_key(entry):
    """Return the dedup key for an entry: (type, query|canonical_key)."""
    t = entry.get('type')
    if t == 'search':
        return ('search', entry.get('query'))
    if t in ('series', 'movie'):
        return (t, entry.get('canonical_key'))
    return None


def _is_valid_entry(entry):
    """Strict structural validation for a single favorite."""
    if not isinstance(entry, dict):
        return False
    t = entry.get('type')
    if t not in _VALID_TYPES:
        return False
    if t == 'search':
        return isinstance(entry.get('query'), str) and entry.get('query')
    if t in ('series', 'movie'):
        return (isinstance(entry.get('canonical_key'), str)
                and entry.get('canonical_key'))
    return False


def load_favorites():
    """Load favorites from disk. Handles missing/corrupt/legacy formats.

    Returns a list of valid entries (may be empty).
    Legacy bare-list format is accepted; rewrite happens on next save.
    Invalid individual entries are dropped with a warning.
    Caches the result in memory; invalidated by save_favorites.
    """
    global _cached_items
    if _cached_items is not None:
        return list(_cached_items)

    profile = _profile_path()
    try:
        os.makedirs(profile, exist_ok=True)
    except OSError as e:
        log_error("favorites: failed to create profile dir: {}".format(e))

    path = _favorites_path()
    raw = ''
    try:
        with io.open(path, 'r', encoding='utf8') as f:
            _flock(f)
            try:
                raw = f.read()
            finally:
                _funlock(f)
    except (IOError, OSError) as e:
        log_warning("load_favorites: IO error ({}): {}".format(path, e))
        _cached_items = []
        return []

    if not raw:
        _cached_items = []
        return []

    try:
        data = json.loads(raw)
    except ValueError as e:
        log_warning("load_favorites: corrupt JSON: {}".format(e))
        _cached_items = []
        return []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get('items', [])
        if not isinstance(items, list):
            log_warning("load_favorites: 'items' not a list ({}); resetting".format(
                type(items).__name__))
            _cached_items = []
            return []
    else:
        log_warning("load_favorites: top-level not list/dict ({}); resetting".format(
            type(data).__name__))
        _cached_items = []
        return []

    valid = []
    for entry in items:
        if _is_valid_entry(entry):
            valid.append(entry)
        else:
            log_warning("load_favorites: dropping invalid entry: {!r}".format(entry))
    log_debug("load_favorites: {} valid items".format(len(valid)))
    _cached_items = valid
    return list(valid)


def save_favorites(items):
    """Atomic write of envelope {version, items} to disk."""
    invalidate_cache()
    profile = _profile_path()
    try:
        os.makedirs(profile, exist_ok=True)
        path = _favorites_path()
        envelope = {'version': ENVELOPE_VERSION, 'items': items}
        fd, tmp = tempfile.mkstemp(dir=profile,
                                   prefix=FAVORITES + '.',
                                   suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf8') as f:
                f.write(json.dumps(envelope))
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
        log_error("save_favorites: write failed: {}".format(e))


def add_favorite(entry):
    """Add (or move-to-front) a favorite entry. Caps total at MAX_FAVORITES."""
    if not _is_valid_entry(entry):
        log_warning("add_favorite: invalid entry: {!r}".format(entry))
        return False
    entry = dict(entry)
    entry.setdefault('added_at', int(time.time()))

    items = load_favorites()
    key = _entry_key(entry)
    items = [it for it in items if _entry_key(it) != key]
    items.insert(0, entry)
    if len(items) > MAX_FAVORITES:
        items = items[:MAX_FAVORITES]
    save_favorites(items)
    return True


def remove_favorite(type_, key):
    """Remove the favorite identified by (type, canonical_key|query)."""
    if type_ not in _VALID_TYPES or not key:
        return False
    items = load_favorites()
    target = (type_, key)
    new_items = [it for it in items if _entry_key(it) != target]
    if len(new_items) == len(items):
        return False
    save_favorites(new_items)
    return True


def is_favorited(type_, key):
    """Boolean lookup, used by UI to toggle context-menu label."""
    if type_ not in _VALID_TYPES or not key:
        return False
    items = load_favorites()
    target = (type_, key)
    for it in items:
        if _entry_key(it) == target:
            return True
    return False


def find_favorite_by_name(type_, display_name):
    """Drift-aware favorite lookup by (type, display_name).

    Returns the matching entry dict or None. Used by the UI to detect
    "this series/movie is already favorited under a drifted canonical_key"
    so the context-menu toggle correctly shows Remove instead of Add and
    avoids creating a duplicate entry on click.

    Substring match (case-insensitive) on display_name so minor casing /
    suffix differences between the saved and current grouping resolve.
    """
    if type_ not in ('series', 'movie') or not display_name:
        return None
    target = display_name.lower()
    for it in load_favorites():
        if it.get('type') != type_:
            continue
        existing = (it.get('display_name') or '').lower()
        if existing and (target in existing or existing in target):
            return it
    return None
