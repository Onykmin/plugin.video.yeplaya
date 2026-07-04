# -*- coding: utf-8 -*-
# Module: favorites
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Persistent favorites: search queries, series, movies.

Persistence (atomic write, locked read, profile dir) is shared with
lib.cache. Series/movie identity is normalized via lib.keys so favorites
survive dual-name canonical_key drift the same way playback state does.
"""

import os
import json
import time

from lib.cache import (locked_read_text, atomic_write_text, profile_dir,
                       file_lock)
from lib.keys import normalize_series_key, normalize_movie_key
from lib.search import _normalize
from lib.logging import log_warning, log_error, log_debug


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


def _favorites_path():
    return os.path.join(profile_dir(), FAVORITES)


def _normalize_canonical(type_, canonical_key):
    """Normalized identity for a series/movie canonical_key.

    canonical_key drifts across fetches (dual-name detection emits a different
    pipe-prefix depending on which alias files are present). Comparing the
    NORMALIZED form — the same function the playback-state layer uses — makes
    add/remove/is_favorited drift-resistant and removes the reliance on the
    volatile display_name. Movie keys keep their trailing |year so different-
    year releases of the same title stay distinct (no wrong-year removal).
    """
    if not canonical_key:
        return canonical_key
    if type_ == 'series':
        return normalize_series_key(canonical_key)
    if type_ == 'movie':
        return normalize_movie_key(canonical_key)
    return canonical_key


def _entry_key(entry):
    """Return the dedup/identity key for an entry: (type, normalized-key).

    Search favorites key on the user-typed query (stable). Series/movie key on
    the normalized canonical_key so dual-name drift collapses to one identity.
    """
    t = entry.get('type')
    if t == 'search':
        # Normalize like search history (case/accent/whitespace-insensitive)
        # so 'Avatar' and 'avatar' are one favorite and the toggle/remove match.
        return ('search', _normalize(entry.get('query') or ''))
    if t in ('series', 'movie'):
        return (t, _normalize_canonical(t, entry.get('canonical_key')))
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


def _target_key(type_, key):
    """Identity tuple for a (type, raw key) lookup — normalized to match
    _entry_key so drifted canonical_keys still resolve to the stored entry."""
    if type_ == 'search':
        return ('search', _normalize(key or ''))
    if type_ in ('series', 'movie'):
        return (type_, _normalize_canonical(type_, key))
    return None


def _parse_favorites_raw(raw):
    """Parse stored JSON text into a list of valid entries (best-effort)."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError as e:
        log_warning("load_favorites: corrupt JSON: {}".format(e))
        return []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get('items', [])
        if not isinstance(items, list):
            log_warning("load_favorites: 'items' not a list ({}); resetting".format(
                type(items).__name__))
            return []
    else:
        log_warning("load_favorites: top-level not list/dict ({}); resetting".format(
            type(data).__name__))
        return []

    valid = []
    for entry in items:
        if _is_valid_entry(entry):
            valid.append(entry)
        else:
            log_warning("load_favorites: dropping invalid entry: {!r}".format(entry))
    log_debug("load_favorites: {} valid items".format(len(valid)))
    return valid


def _cached_list():
    """Return the in-memory favorites list WITHOUT copying (read-only callers).

    load_favorites() copies defensively for mutators; the predicate helpers
    (is_favorited / find_favorite_by_name) only read, so they use this to
    avoid allocating a fresh list per call — they are invoked once per menu
    row, so the copy churn was O(rows) for no benefit.
    """
    global _cached_items
    if _cached_items is None:
        _cached_items = _parse_favorites_raw(locked_read_text(_favorites_path()))
    return _cached_items


def load_favorites():
    """Load favorites from disk. Handles missing/corrupt/legacy formats.

    Returns a (copied) list of valid entries (may be empty). The copy lets
    callers mutate freely without disturbing the in-memory cache.
    Legacy bare-list format is accepted; rewrite happens on next save.
    Invalid individual entries are dropped with a warning.
    Caches the result in memory; invalidated by save_favorites.
    """
    return list(_cached_list())


def save_favorites(items):
    """Atomic write of envelope {version, items} to disk."""
    invalidate_cache()
    envelope = {'version': ENVELOPE_VERSION, 'items': items}
    atomic_write_text(_favorites_path(), json.dumps(envelope))


def _mutate(fn):
    """Run a read-modify-write of the favorites list under a cross-process lock.

    fn(items) receives the current list and returns (new_list, result). The
    whole load→modify→save runs while holding an exclusive lock on a sidecar
    lock file, so concurrent add/remove in separate Kodi processes cannot lose
    each other's update (last-writer-wins). The in-memory cache cannot help
    here — each Kodi action is a fresh process.
    """
    with file_lock(_favorites_path() + '.lock'):
        invalidate_cache()  # force a fresh read from disk inside the lock
        items = _parse_favorites_raw(locked_read_text(_favorites_path()))
        new_items, result = fn(items)
        if new_items is not None:
            atomic_write_text(_favorites_path(),
                              json.dumps({'version': ENVELOPE_VERSION,
                                          'items': new_items}))
        invalidate_cache()
        return result


def add_favorite(entry):
    """Add (or move-to-front) a favorite entry. Caps total at MAX_FAVORITES."""
    if not _is_valid_entry(entry):
        log_warning("add_favorite: invalid entry: {!r}".format(entry))
        return False
    entry = dict(entry)
    entry.setdefault('added_at', int(time.time()))
    key = _entry_key(entry)

    def _do(items):
        items = [it for it in items if _entry_key(it) != key]
        items.insert(0, entry)
        if len(items) > MAX_FAVORITES:
            items = items[:MAX_FAVORITES]
        return items, True

    return _mutate(_do)


def remove_favorite(type_, key):
    """Remove the favorite identified by (type, canonical_key|query)."""
    if type_ not in _VALID_TYPES or not key:
        return False
    target = _target_key(type_, key)

    def _do(items):
        new_items = [it for it in items if _entry_key(it) != target]
        if len(new_items) == len(items):
            return None, False
        return new_items, True

    return _mutate(_do)


def is_favorited(type_, key):
    """Boolean lookup, used by UI to toggle context-menu label."""
    if type_ not in _VALID_TYPES or not key:
        return False
    target = _target_key(type_, key)
    for it in _cached_list():
        if _entry_key(it) == target:
            return True
    return False


def find_favorite_by_name(type_, display_name):
    """Secondary drift fallback: match a favorite by (type, display_name).

    Returns the matching entry dict or None. The primary identity is the
    normalized canonical_key (see is_favorited / _entry_key), which is
    drift-resistant. This name match is a last resort for the fundamental
    case where the available aliases differ so much that the normalized keys
    cannot bridge (e.g. an English-only fetch keyed "the penguin" vs a
    Czech-only fetch keyed "tucnak").

    Match is case-insensitive EXACT equality — never substring. A substring
    match wrongly conflated sibling titles like "Panic" and "Panic at the
    Disco" and removed the wrong favorite. Note display_name itself can drift
    across groupings (grouping picks it by file-frequency), so this is best-
    effort only and is intentionally behind the normalized-key check.
    """
    if type_ not in ('series', 'movie') or not display_name:
        return None
    target = display_name.lower()
    for it in _cached_list():
        if it.get('type') != type_:
            continue
        existing = (it.get('display_name') or '').lower()
        if existing and existing == target:
            return it
    return None
