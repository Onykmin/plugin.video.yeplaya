# -*- coding: utf-8 -*-
# Module: favorites_ui
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Favorites top-level list view + add/remove actions."""

import xbmc
import xbmcgui
import xbmcplugin

from lib.utils import get_url, popinfo, get_handle, get_addon
from lib.favorites import (
    load_favorites, add_favorite, remove_favorite, is_favorited,
)
from lib.logging import log_debug

_handle = get_handle()
_addon = get_addon()


# Localized string IDs (defined in resources/language/.../strings.po)
_STR_FAVORITES = 30420
_STR_ADD_FAV = 30421
_STR_REMOVE_FAV = 30422
_STR_FAV_GONE = 30423
_STR_NO_FAVORITES = 30424
_STR_SAVED_SEARCH_PREFIX = 30425


def _label_for(entry):
    """Human-readable label for a favorite list row."""
    t = entry.get('type')
    if t == 'search':
        return _addon.getLocalizedString(_STR_SAVED_SEARCH_PREFIX).format(entry.get('query', ''))
    if t == 'series':
        return entry.get('display_name') or entry.get('canonical_key', '')
    if t == 'movie':
        name = entry.get('display_name') or entry.get('canonical_key', '')
        year = entry.get('year')
        return '{} ({})'.format(name, year) if year else name
    return entry.get('canonical_key') or entry.get('query', '')


def _icon_for(entry):
    t = entry.get('type')
    if t == 'search':
        return 'DefaultAddonsSearch.png'
    if t == 'series':
        return 'DefaultTVShows.png'
    if t == 'movie':
        return 'DefaultVideo.png'
    return 'DefaultFolder.png'


def _click_url(entry):
    """Build the URL Kodi follows when the user clicks a favorite row."""
    t = entry.get('type')
    if t == 'search':
        return get_url(action='search', what=entry.get('query', ''))
    if t == 'series':
        return get_url(action='browse_series',
                       series=entry.get('canonical_key', ''),
                       what=entry.get('search_query', '') or entry.get('display_name', ''))
    if t == 'movie':
        return get_url(action='select_movie_version',
                       movie_key=entry.get('canonical_key', ''),
                       what=entry.get('search_query', '') or entry.get('display_name', ''))
    return get_url(action='favorites')


def _remove_url(entry):
    t = entry.get('type')
    if t == 'search':
        return get_url(action='remove_favorite', type=t, key=entry.get('query', ''))
    return get_url(action='remove_favorite', type=t, key=entry.get('canonical_key', ''))


def favorites(params):
    """Top-level favorites list view."""
    log_debug("favorites() called with params: {}".format(params))
    xbmcplugin.setPluginCategory(_handle,
        '{} \\ {}'.format(_addon.getAddonInfo('name'),
                          _addon.getLocalizedString(_STR_FAVORITES)))
    items = load_favorites()

    if not items:
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(_STR_NO_FAVORITES))
        listitem.setArt({'icon': 'DefaultFolder.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='favorites'), listitem, False)
        xbmcplugin.endOfDirectory(_handle, cacheToDisc=False)
        return

    is_folder_by_type = {'search': True, 'series': True, 'movie': False}
    for entry in items:
        listitem = xbmcgui.ListItem(label=_label_for(entry))
        listitem.setArt({'icon': _icon_for(entry)})
        commands = [(
            _addon.getLocalizedString(_STR_REMOVE_FAV),
            'Container.Update(' + _remove_url(entry) + ')'
        )]
        listitem.addContextMenuItems(commands)
        is_folder = is_folder_by_type.get(entry.get('type'), True)
        xbmcplugin.addDirectoryItem(_handle, _click_url(entry), listitem, is_folder)

    xbmcplugin.endOfDirectory(_handle, cacheToDisc=False)


def add_favorite_action(params):
    """Add-favorite route handler.

    Accepts params: type, query|key, display_name, search_query, year.
    """
    t = params.get('type')
    entry = {'type': t}
    if t == 'search':
        entry['query'] = params.get('query') or params.get('key', '')
    else:
        entry['canonical_key'] = params.get('key', '')
        entry['display_name'] = params.get('display_name', '')
        if params.get('search_query'):
            entry['search_query'] = params['search_query']
        if t == 'movie' and params.get('year'):
            try:
                entry['year'] = int(params['year'])
            except (ValueError, TypeError):
                pass

    if add_favorite(entry):
        xbmc.executebuiltin('Container.Refresh')


def remove_favorite_action(params):
    """Remove-favorite route handler."""
    t = params.get('type')
    key = params.get('key') or params.get('query', '')
    if remove_favorite(t, key):
        xbmc.executebuiltin('Container.Refresh')


def resolve_favorite_url(entry, grouped=None):
    """Resolve a favorite to its click URL with availability check + fallback.

    `grouped` is the current grouping (cached/fetched by caller). When the
    canonical_key is missing, attempts a display_name substring match in the
    grouped buckets. Returns (url, fallback_used, dead) tuple.

    - fallback_used=True means the canonical_key did not match but a similar
      entry (by display_name substring) was found.
    - dead=True means neither match worked: caller should popinfo + offer remove.
    """
    t = entry.get('type')
    if t == 'search':
        return _click_url(entry), False, False
    if not grouped:
        return _click_url(entry), False, False

    bucket_name = 'series' if t == 'series' else 'movies'
    bucket = grouped.get(bucket_name, {}) or {}
    key = entry.get('canonical_key', '')

    if key in bucket:
        return _click_url(entry), False, False

    target = (entry.get('display_name') or '').lower()
    if target:
        for k, v in bucket.items():
            display = (v.get('display_name') or '').lower()
            if display and (target in display or display in target):
                resolved = dict(entry)
                resolved['canonical_key'] = k
                return _click_url(resolved), True, False

    return _click_url(entry), False, True


def maybe_announce_dead(entry):
    """Notify the user that a favorite no longer resolves."""
    popinfo(_addon.getLocalizedString(_STR_FAV_GONE),
            icon=xbmcgui.NOTIFICATION_WARNING)
    log_debug("favorite dead: {!r}".format(entry))


def add_favorite_context_entry(entry):
    """Build a Kodi context-menu tuple to add (or remove if already) a favorite.

    Returns (label, command) suitable for listitem.addContextMenuItems().
    """
    t = entry.get('type')
    key_field = 'query' if t == 'search' else 'canonical_key'
    key = entry.get(key_field, '')

    if is_favorited(t, key):
        return (
            _addon.getLocalizedString(_STR_REMOVE_FAV),
            'Container.Update(' + get_url(action='remove_favorite',
                                          type=t, key=key) + ')'
        )

    url_params = {'action': 'add_favorite', 'type': t, 'key': key}
    if entry.get('display_name'):
        url_params['display_name'] = entry['display_name']
    if entry.get('search_query'):
        url_params['search_query'] = entry['search_query']
    if entry.get('year'):
        url_params['year'] = str(entry['year'])
    return (
        _addon.getLocalizedString(_STR_ADD_FAV),
        'RunPlugin(' + get_url(**url_params) + ')'
    )
