# -*- coding: utf-8 -*-
# Module: movie_pool
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Persistent random-movie title pool, backed by lib.wdqs.

Kodi's one-process-per-menu-action lifecycle means lib.cache's in-memory
cache_set/cache_get dies every action and cannot hold a pool across picks
(WDQS_DEEP_DIVE.md lines 124-130). This module mirrors lib.favorites' shape
exactly instead — a versioned JSON envelope written atomically to the addon
profile dir, read back under a shared lock, mutated under a cross-process
exclusive lock (doc lines 128-130 name lib.favorites as the proven
precedent for exactly this).

Shape: prefetch a 2000-title batch (one ~2.68s query, doc line 96) and
top-up live only when the pool is exhausted relative to the caller's
`excluded` set or stale past its TTL (doc lines 132-140). This keeps WDQS's
5-31s (and occasional outright failure) latency off the per-pick path.
"""

import os
import json
import time
import random

from lib.cache import (locked_read_text, atomic_write_text, profile_dir,
                       file_lock)
from lib.logging import log_warning, log_debug
from lib import wdqs


POOL_FILE = 'random_movie_pool'
# NOT bumped for the 'y' (year) field added alongside lib.wdqs's P577
# support: 'y' is purely additive/optional (see _is_valid_item — only 'id'
# + one of cs/en is required), so existing v1 on-disk records with no 'y'
# stay valid, pickable and searchable, and the pool heals naturally as
# top-ups/refreshes merge newer year-bearing records in over time. Bumping
# this would invalidate a user's live pool (measured ~792 items in
# production) outright via the version check in _parse_envelope_raw, and if
# WDQS happens to be down at that exact moment (measured 502s and a 60s
# client timeout in production) the user is left with a dead feature — a
# regression on something they currently rely on, for a display-only
# enhancement that doesn't need one.
ENVELOPE_VERSION = 1

# One 2.68s query for 2000 rows is the doc's measured sweet spot (line 96);
# ~68 KiB on disk as compact JSON. Not "as many as possible" — a bigger
# batch was not measured and the doc calls 2000 the sweet spot explicitly.
# With the 'y' field added: measured 141,576 B (~138 KiB) per 2000 compact
# records including year, vs 70,134 B for the title-only shape — same order
# of magnitude, still small for a TTL-refreshed file (DEFAULT_TTL_SECONDS
# below).
PREFETCH_BATCH = 2000

# Top-up batch when the pool runs out relative to `excluded`. Smaller than
# the initial prefetch: a top-up only needs to add enough fresh titles to
# unblock the current pick, not repeat the full prefetch cost.
TOPUP_BATCH = 200

# Refresh TTL for the whole pool. A stale pool is still a USABLE pool per
# doc line 181 (keep the last good pool on refresh failure) — this TTL only
# decides when we'd PREFER a refresh, not a hard expiry that blanks data.
DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60  # 1 week

# Per-process in-memory cache, reset every Kodi invocation (mirrors
# lib.favorites._cached_items) — never assume it survives across actions.
_cached_pool = None


def invalidate_cache():
    """Drop the in-memory cache. Used by save/refresh and tests."""
    global _cached_pool
    _cached_pool = None


def _pool_path():
    return os.path.join(profile_dir(), POOL_FILE)


def _is_valid_item(item):
    """Structural check for one pool record: needs an id and at least one
    of cs/en (mirrors the filtering lib.wdqs already does, but the on-disk
    file could in principle be hand-edited or come from an older version)."""
    if not isinstance(item, dict):
        return False
    if not isinstance(item.get('id'), str) or not item.get('id'):
        return False
    cs = item.get('cs')
    en = item.get('en')
    if cs is not None and not isinstance(cs, str):
        return False
    if en is not None and not isinstance(en, str):
        return False
    return cs or en


def _parse_envelope_raw(raw):
    """Parse stored JSON text into (fetched_at, items). Best-effort —
    missing/corrupt/wrong-version/malformed all collapse to an empty pool
    (fetched_at=0) rather than raising, matching lib.cache.loadsearch's
    documented defensiveness (catch ValueError, log with size, reset)."""
    if not raw:
        return 0, []
    try:
        data = json.loads(raw)
    except ValueError as e:
        log_warning("movie_pool: corrupt JSON (size={}): {}".format(len(raw), e))
        return 0, []

    if not isinstance(data, dict):
        log_warning("movie_pool: top-level not a dict ({}); resetting".format(
            type(data).__name__))
        return 0, []

    if data.get('version') != ENVELOPE_VERSION:
        log_warning("movie_pool: unknown envelope version {!r}; resetting".format(
            data.get('version')))
        return 0, []

    items = data.get('items', [])
    if not isinstance(items, list):
        log_warning("movie_pool: 'items' not a list ({}); resetting".format(
            type(items).__name__))
        return 0, []

    valid = [it for it in items if _is_valid_item(it)]
    if len(valid) != len(items):
        log_warning("movie_pool: dropped {} invalid item(s)".format(
            len(items) - len(valid)))

    fetched_at = data.get('fetched_at')
    if not isinstance(fetched_at, (int, float)):
        fetched_at = 0

    log_debug("movie_pool: loaded {} valid items (fetched_at={})".format(
        len(valid), fetched_at))
    return fetched_at, valid


def _cached_envelope():
    """Return (fetched_at, items) from the in-memory cache, loading once."""
    global _cached_pool
    if _cached_pool is None:
        _cached_pool = _parse_envelope_raw(locked_read_text(_pool_path()))
    return _cached_pool


def _save_envelope(fetched_at, items):
    """Atomic write of the versioned envelope. Uses compact separators and
    ensure_ascii=False (doc line 96): with Czech diacritics, ensure_ascii
    default would inflate ~70KB to ~78KB via 6-byte \\uXXXX escapes for no
    benefit — lib.cache writes UTF-8 text already (atomic_write_text opens
    with encoding='utf8'), so non-ASCII round-trips fine as literal bytes."""
    invalidate_cache()
    envelope = {'version': ENVELOPE_VERSION, 'fetched_at': int(fetched_at),
                'items': items}
    atomic_write_text(_pool_path(),
                       json.dumps(envelope, ensure_ascii=False,
                                  separators=(',', ':')))


def _dedupe_merge(existing, new_items):
    """Merge new_items into existing, deduped on id.

    WDQS OFFSET pages are NOT a stable partition of the pool — the doc's
    repeat-run probe found the SAME offset returning four DIFFERENT films
    across four calls within a minute (§2.1, doc line 119), so a top-up
    batch can both re-return already-held titles and, individually, is not
    guaranteed to be all-new. Dedupe defensively rather than assuming any
    disjointness. Existing entries win ties (stable identity for callers
    already holding a reference to that id).
    """
    seen = {it['id'] for it in existing}
    merged = list(existing)
    for it in new_items:
        if it['id'] not in seen:
            merged.append(it)
            seen.add(it['id'])
    return merged


def _mutate(fn):
    """Read-modify-write the pool file under a cross-process lock.

    Mirrors lib.favorites._mutate exactly: fn(fetched_at, items) returns
    (new_fetched_at, new_items, result); None for new_fetched_at means "no
    write" (used when a refresh fails and the last good pool must be kept
    untouched, per doc line 181).
    """
    with file_lock(_pool_path() + '.lock'):
        invalidate_cache()
        fetched_at, items = _parse_envelope_raw(locked_read_text(_pool_path()))
        new_fetched_at, new_items, result = fn(fetched_at, items)
        if new_fetched_at is not None:
            _save_envelope(new_fetched_at, new_items)
        invalidate_cache()
        return result


def _is_stale(fetched_at, ttl_seconds):
    if not fetched_at:
        return True
    return (time.time() - fetched_at) > ttl_seconds


def refresh_pool(ttl_seconds=DEFAULT_TTL_SECONDS, force=False):
    """Refresh the on-disk pool from WDQS if stale (or always, if force=True).

    Fetches PREFETCH_BATCH fresh candidates and MERGES them (deduped) into
    whatever is already on disk, rather than replacing it outright — so a
    partially-successful or small fetch still grows the pool instead of
    shrinking it.

    On WDQS failure (empty result from wdqs.fetch_candidates), the existing
    on-disk pool is left completely untouched (doc line 181: a 5xx/timeout
    at refresh time must be invisible to the user, never a reason to
    discard a usable pool). Never raises.

    Returns True if a fetch was attempted and returned at least one usable
    record, False otherwise (including "was fresh, did nothing").
    """
    fetched_at, items = _cached_envelope()
    if not force and not _is_stale(fetched_at, ttl_seconds):
        log_debug("movie_pool: refresh skipped, pool still fresh")
        return False

    new_records = wdqs.fetch_candidates(PREFETCH_BATCH)
    if not new_records:
        log_warning("movie_pool: refresh fetch returned nothing; keeping "
                    "existing pool ({} items)".format(len(items)))
        return False

    def _do(cur_fetched_at, cur_items):
        merged = _dedupe_merge(cur_items, new_records)
        return int(time.time()), merged, True

    return _mutate(_do)


def _topup(ttl_seconds=DEFAULT_TTL_SECONDS):
    """Fetch one top-up batch and merge it in. Internal helper for pick_random
    when the pool is exhausted relative to the caller's excluded set."""
    new_records = wdqs.fetch_candidates(TOPUP_BATCH)
    if not new_records:
        log_warning("movie_pool: top-up fetch returned nothing")
        return False

    def _do(cur_fetched_at, cur_items):
        merged = _dedupe_merge(cur_items, new_records)
        # Preserve fetched_at if we already had one (a top-up isn't a full
        # refresh); only stamp a fresh time if the pool was previously empty.
        stamp = cur_fetched_at or int(time.time())
        return stamp, merged, True

    return _mutate(_do)


def load_pool():
    """Return a (copied) list of pool items: [{'id','cs','en'}, ...], each
    optionally carrying a 'y' (int year) key when lib.wdqs resolved one.

    'y' is present-but-optional, not guaranteed: older items fetched before
    lib.wdqs started selecting P577, or films with no P577 on Wikidata,
    simply have no 'y' key at all (never 'y': None) — see
    lib.wdqs._parse_bindings. Callers must use .get('y'), never item['y'].

    Does not fetch or refresh — pure disk read (via the in-memory cache).
    Empty list if the file is missing/corrupt/wrong-version.
    """
    _, items = _cached_envelope()
    return list(items)


def ensure_pool(ttl_seconds=DEFAULT_TTL_SECONDS):
    """Make sure a usable pool exists on disk, fetching if empty or stale.

    Call this explicitly before a pick — never on import (doc requirement:
    Kodi imports modules on every menu action, so an import-time network
    call would stall every action, not just random-movie ones).

    Returns the (possibly freshly fetched) list of pool items. On total
    failure (empty pool AND fetch failed) returns [].
    """
    items = load_pool()
    if not items:
        refresh_pool(ttl_seconds=ttl_seconds, force=True)
        items = load_pool()
    elif _is_stale(_cached_envelope()[0], ttl_seconds):
        refresh_pool(ttl_seconds=ttl_seconds)
        items = load_pool()
    return items


def pick_random(excluded, ttl_seconds=DEFAULT_TTL_SECONDS):
    """Pick a uniformly-random pool item whose id is not in `excluded`.

    Mirrors lib.series_ui._pick_random's convention (commit d6723f3,
    lib/series_ui.py:424-435): uniform random.choice over the remaining
    candidates, NEVER mutates `excluded`, and NEVER auto-resets it — the
    caller (UI layer) owns the reroll-until-exhausted lifecycle and decides
    whether to offer "start over".

    Unlike the episode picker, this pool can be topped up: if every
    currently-held item is excluded, one live top-up batch is fetched and
    merged in (hybrid shape, doc lines 132-140) before giving up. If the
    top-up also yields nothing new (or the fetch fails), returns None —
    exhausted relative to `excluded`.

    Returns an item dict {'id','cs','en'}, optionally with a 'y' (int year)
    key (see load_pool's docstring — absent, not None, when unknown), or
    None.
    """
    items = ensure_pool(ttl_seconds=ttl_seconds)
    remaining = [it for it in items if it['id'] not in excluded]
    if remaining:
        return random.choice(remaining)

    # Exhausted against the current pool — try one live top-up before
    # reporting exhaustion, per the hybrid design.
    if _topup(ttl_seconds=ttl_seconds):
        items = load_pool()
        remaining = [it for it in items if it['id'] not in excluded]
        if remaining:
            return random.choice(remaining)

    log_debug("movie_pool: pick_random exhausted ({} excluded)".format(
        len(excluded)))
    return None
