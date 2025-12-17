# -*- coding: utf-8 -*-
# Module: cache
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import io
import os
import json
import xbmcaddon
from lib.logging import log_warning, log_error

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
_series_cache = {}
_csfd_db = None


def get_series_cache():
    """Get series cache dict."""
    return _series_cache


def build_cache_key(what, category='', sort_val=''):
    """Build consistent cache key from search parameters."""
    return '{0}_{1}_{2}'.format(what, category, sort_val)


def get_or_fetch_grouped(params, token, check_key=None, check_type='series'):
    """Get grouped data from cache or fetch if missing."""
    from lib.grouping import fetch_and_group_series
    
    category = params.get('category', '')
    sort_val = params.get('sort', '')
    cache_key = build_cache_key(params['what'], category, sort_val)
    grouped = _series_cache.get(cache_key, {})

    needs_fetch = not grouped
    if check_key and grouped:
        if check_type == 'series':
            needs_fetch = check_key not in grouped.get('series', {})
        elif check_type == 'movies':
            needs_fetch = check_key not in grouped.get('movies', {})

    if needs_fetch and token:
        grouped = fetch_and_group_series(token, params['what'], category, sort_val)
        if grouped:
            _series_cache[cache_key] = grouped

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
