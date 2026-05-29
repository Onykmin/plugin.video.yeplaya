# -*- coding: utf-8 -*-
# Module: state
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Playback-state persistence (watched + resume points).

Keyed per-episode / per-movie / per-file — all quality variants of a single
episode or movie share the same state_key.
"""

import os
import time
import sqlite3
import threading
import xbmc
import xbmcaddon
import xbmcvfs

from lib.keys import normalize_series_key as _normalize_series_key
from lib.keys import normalize_movie_key as _normalize_movie_key

try:
    from xbmcvfs import translatePath
except ImportError:
    from xbmc import translatePath


_LOG = "YAWsP.state: "
_WATCHED_THRESHOLD = 0.90
_SCHEMA_VERSION = 2

_db_lock = threading.RLock()
_conn = None
_db_path = None
_cache = {}


def _get_db_path():
    """Build DB path in the addon profile dir."""
    profile = translatePath('special://profile/addon_data/plugin.video.yeplaya/')
    if not xbmcvfs.exists(profile):
        xbmcvfs.mkdirs(profile)
    return os.path.join(profile, 'state.db')


def _connect():
    """Open (or reopen) the SQLite connection."""
    global _conn, _db_path
    if _conn is not None:
        return _conn
    _db_path = _get_db_path()
    _conn = sqlite3.connect(_db_path, check_same_thread=False, timeout=5.0)
    _conn.execute('PRAGMA journal_mode=WAL')
    _migrate(_conn)
    return _conn


def _migrate(conn):
    """Create schema if absent; idempotent."""
    cur = conn.cursor()
    cur.execute('PRAGMA user_version')
    ver = cur.fetchone()[0]
    if ver < 1:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS playback_state (
                state_key TEXT PRIMARY KEY,
                watched INTEGER NOT NULL DEFAULT 0,
                resume_seconds INTEGER NOT NULL DEFAULT 0,
                total_seconds INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            )
        ''')
        cur.execute('PRAGMA user_version = 1')
        conn.commit()
    if ver < 2:
        _migrate_normalize_keys(cur)
        cur.execute('PRAGMA user_version = 2')
        conn.commit()


def _migrate_normalize_keys(cur):
    """v1→v2: rewrite legacy un-normalized ep:/mv: keys in place.

    Pre-v2 rows stored the raw (dual-prefixed) canonical_key, e.g.
    "ep:mestecko|south park|S01E05". state_key_for now strips the dual-name
    prefix, so those rows would be orphaned. Rewrite each legacy key to its
    normalized form; if the normalized key already exists (a row written by
    a newer code path), keep whichever was updated most recently.
    """
    cur.execute('SELECT state_key, watched, resume_seconds, total_seconds, '
                'updated_at FROM playback_state')
    rows = cur.fetchall()
    for state_key, watched, resume, total, updated_at in rows:
        new_key = _renormalize_state_key(state_key)
        if new_key is None or new_key == state_key:
            continue
        cur.execute('SELECT updated_at FROM playback_state WHERE state_key=?',
                    (new_key,))
        existing = cur.fetchone()
        if existing is not None and existing[0] >= updated_at:
            # A fresher normalized row already exists; drop the stale legacy one.
            cur.execute('DELETE FROM playback_state WHERE state_key=?', (state_key,))
            continue
        # Move the legacy row onto the normalized key (replace if present).
        cur.execute('DELETE FROM playback_state WHERE state_key=?', (state_key,))
        cur.execute('''
            INSERT INTO playback_state
                (state_key, watched, resume_seconds, total_seconds, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET
                watched=excluded.watched,
                resume_seconds=excluded.resume_seconds,
                total_seconds=excluded.total_seconds,
                updated_at=excluded.updated_at
        ''', (new_key, watched, resume, total, updated_at))


def _renormalize_state_key(state_key):
    """Return the normalized form of a legacy ep:/mv: key, or None if N/A."""
    if not state_key:
        return None
    if state_key.startswith('ep:'):
        # "ep:{series}|S00E00" — normalize only the series part.
        body = state_key[3:]
        marker_at = body.rfind('|S')
        if marker_at == -1:
            return None
        series, marker = body[:marker_at], body[marker_at + 1:]
        return "ep:{0}|{1}".format(_normalize_series_key(series), marker)
    if state_key.startswith('mv:'):
        return "mv:{0}".format(_normalize_movie_key(state_key[3:]))
    return None


def _reset_for_tests(path=None):
    """Test helper: close connection and clear cache."""
    global _conn, _db_path, _cache
    with _db_lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
        _conn = None
        _db_path = path
        _cache = {}


def build_mv_state_key(canonical_key):
    """Build a stable movie state key from a (possibly drift-prone) canonical_key."""
    return "mv:{0}".format(_normalize_movie_key(canonical_key))


def state_key_for(file_dict):
    """Derive a stable state key for a file dict.

    Priority: episode → movie → file fallback. series_name and canonical_key
    are normalized to strip dual-name prefixes so the SAME content yields
    the SAME state key across re-groupings (canonical_key drift).
    """
    series = file_dict.get('series_name')
    season = file_dict.get('season')
    episode = file_dict.get('episode')
    if series and season is not None and episode is not None:
        try:
            s = int(season)
            e = int(episode)
            return "ep:{0}|S{1:02d}E{2:02d}".format(
                _normalize_series_key(series), s, e)
        except (ValueError, TypeError):
            pass
    canonical = file_dict.get('canonical_key')
    if canonical:
        return "mv:{0}".format(_normalize_movie_key(canonical))
    ident = file_dict.get('ident')
    if ident:
        return "file:{0}".format(ident)
    return None


def _upsert_locked(key, watched, resume, total):
    """UPSERT body; caller must hold _db_lock."""
    conn = _connect()
    conn.execute('''
        INSERT INTO playback_state (state_key, watched, resume_seconds, total_seconds, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(state_key) DO UPDATE SET
            watched=excluded.watched,
            resume_seconds=excluded.resume_seconds,
            total_seconds=excluded.total_seconds,
            updated_at=excluded.updated_at
    ''', (key, int(watched), int(resume), int(total), int(time.time())))
    conn.commit()
    _cache.pop(key, None)


def _upsert(key, watched, resume, total):
    """Single UPSERT; invalidates cache entry."""
    with _db_lock:
        _upsert_locked(key, watched, resume, total)


def record_playback(key, pos, total):
    """Write playback state at stop/end.

    Short-circuits when total < 10s (live stream / error).
    pos/total >= 90% → watched=1, resume=0; else resume=pos, watched=0.
    """
    if not key:
        return
    try:
        pos = float(pos or 0)
        total = float(total or 0)
    except (ValueError, TypeError):
        return
    if total < 10:
        xbmc.log(_LOG + "skip (total=%s)" % total, xbmc.LOGDEBUG)
        return
    if pos / total >= _WATCHED_THRESHOLD:
        _upsert(key, 1, 0, int(total))
        xbmc.log(_LOG + "watched: %s (%.0fs/%.0fs)" % (key, pos, total), xbmc.LOGINFO)
    else:
        _upsert(key, 0, int(pos), int(total))
        xbmc.log(_LOG + "resume: %s @%.0fs/%.0fs" % (key, pos, total), xbmc.LOGINFO)


def mark_watched(key):
    if not key:
        return
    with _db_lock:
        conn = _connect()
        cur = conn.execute('SELECT total_seconds FROM playback_state WHERE state_key=?', (key,))
        row = cur.fetchone()
        total = row[0] if row else 0
        _upsert_locked(key, 1, 0, total)


def mark_unwatched(key):
    if not key:
        return
    _upsert(key, 0, 0, 0)


def clear_resume(key):
    if not key:
        return
    with _db_lock:
        conn = _connect()
        cur = conn.execute(
            'SELECT watched, total_seconds FROM playback_state WHERE state_key=?', (key,))
        row = cur.fetchone()
        if row is None:
            return
        _upsert_locked(key, row[0], 0, row[1])


def get_state(key):
    """Return {'watched', 'resume_seconds', 'total_seconds'} or None."""
    if not key:
        return None
    with _db_lock:
        if key in _cache:
            return _cache[key]
        conn = _connect()
        cur = conn.execute(
            'SELECT watched, resume_seconds, total_seconds FROM playback_state WHERE state_key=?',
            (key,))
        row = cur.fetchone()
        if row is None:
            _cache[key] = None
            return None
        state = {
            'watched': int(row[0]),
            'resume_seconds': int(row[1]),
            'total_seconds': int(row[2]),
        }
        _cache[key] = state
        return state


def get_states(keys):
    """Batch read; returns {key: state_dict} only for stored keys.

    Also primes _cache so subsequent get_state() calls hit memory.
    """
    if not keys:
        return {}
    unique = list({k for k in keys if k})
    if not unique:
        return {}
    placeholders = ','.join('?' * len(unique))
    with _db_lock:
        conn = _connect()
        cur = conn.execute(
            'SELECT state_key, watched, resume_seconds, total_seconds '
            'FROM playback_state WHERE state_key IN (%s)' % placeholders,
            unique)
        rows = cur.fetchall()
        result = {}
        for r in rows:
            result[r[0]] = {
                'watched': int(r[1]),
                'resume_seconds': int(r[2]),
                'total_seconds': int(r[3]),
            }
        for k in unique:
            _cache[k] = result.get(k)
    return result
