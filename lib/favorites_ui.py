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
    find_favorite_by_name,
)
from lib.logging import log_debug

_handle = get_handle()
_addon = get_addon()


# Localized string IDs (defined in resources/language/.../strings.po)
_STR_FAVORITES = 30420
_STR_ADD_FAV = 30421
_STR_REMOVE_FAV = 30422
_STR_TAG_SEARCH = 30426
_STR_TAG_SERIES = 30427
_STR_TAG_MOVIE = 30428


def _label_for(entry):
    """Human-readable label for a favorite list row."""
    t = entry.get('type')
    if t == 'search':
        return (_addon.getLocalizedString(_STR_TAG_SEARCH) + ' '
                + entry.get('query', ''))
    if t == 'series':
        name = entry.get('display_name') or entry.get('canonical_key', '')
        return _addon.getLocalizedString(_STR_TAG_SERIES) + ' ' + name
    if t == 'movie':
        name = entry.get('display_name') or entry.get('canonical_key', '')
        year = entry.get('year')
        body = '{} ({})'.format(name, year) if year else name
        return _addon.getLocalizedString(_STR_TAG_MOVIE) + ' ' + body
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
    """Build the URL Kodi follows when the user clicks a favorite row.

    display_name rides along so the target handler can fall back to a
    substring match when the stored canonical_key has drifted in the
    current grouping (dual-name detection produces different keys when
    different files are present).
    """
    t = entry.get('type')
    if t == 'search':
        return get_url(action='search', what=entry.get('query', ''))
    if t in ('series', 'movie'):
        action = 'browse_series' if t == 'series' else 'select_movie_version'
        key_arg = 'series' if t == 'series' else 'movie_key'
        url_params = {
            'action': action,
            key_arg: entry.get('canonical_key', ''),
            'what': entry.get('search_query', '') or entry.get('display_name', ''),
            'fav_display_name': entry.get('display_name', ''),
        }
        # Reproduce the original search's category/sort so the re-fetch hits
        # the same result set (and cache key) the favorite was created from.
        if entry.get('category'):
            url_params['category'] = entry['category']
        if entry.get('sort'):
            url_params['sort'] = entry['sort']
        return get_url(**url_params)
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
        xbmcplugin.endOfDirectory(_handle, cacheToDisc=False)
        return

    # is_folder mirrors how each handler builds its UI: search and
    # browse_series open directories; select_movie_version opens a dialog
    # (Kodi calls non-folder handlers via PlayMedia rather than GetDirectory).
    is_folder_by_type = {'search': True, 'series': True, 'movie': False}
    for entry in items:
        listitem = xbmcgui.ListItem(label=_label_for(entry))
        listitem.setArt({'icon': _icon_for(entry)})
        commands = [(
            _addon.getLocalizedString(_STR_REMOVE_FAV),
            'RunPlugin(' + _remove_url(entry) + ')'
        )]
        listitem.addContextMenuItems(commands)
        is_folder = is_folder_by_type.get(entry.get('type'), True)
        xbmcplugin.addDirectoryItem(_handle, _click_url(entry), listitem, is_folder)

    xbmcplugin.endOfDirectory(_handle, cacheToDisc=False)


def add_favorite_action(params):
    """Add-favorite route handler.

    Accepts params: type, query|key, display_name, search_query, year,
    category, sort.
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
        # Preserve the originating search's category/sort so the favorite
        # click reproduces the same result set / cache key.
        if params.get('category'):
            entry['category'] = params['category']
        if params.get('sort'):
            entry['sort'] = params['sort']
        if t == 'movie' and params.get('year'):
            try:
                entry['year'] = int(params['year'])
            except (ValueError, TypeError):
                pass

    if add_favorite(entry):
        popinfo(_addon.getLocalizedString(_STR_ADD_FAV))


def remove_favorite_action(params):
    """Remove-favorite route handler."""
    t = params.get('type')
    key = params.get('key') or params.get('query', '')
    if remove_favorite(t, key):
        xbmc.executebuiltin('Container.Refresh')


def add_favorite_context_entry(entry):
    """Build a Kodi context-menu tuple to add (or remove if already) a favorite.

    Returns (label, command) suitable for listitem.addContextMenuItems().
    """
    t = entry.get('type')
    key_field = 'query' if t == 'search' else 'canonical_key'
    key = entry.get(key_field, '')

    # is_favorited normalizes the key, so it already recognizes a favorite
    # stored under a drifted canonical_key — pass the current key to remove
    # (it normalizes back to the same identity). find_favorite_by_name is a
    # last resort for when the aliases differ so much the normalized keys
    # can't bridge (English-only vs Czech-only fetch); there we must remove
    # by the STORED key, since the current key won't normalize to a match.
    remove_key = None
    if is_favorited(t, key):
        remove_key = key
    elif t in ('series', 'movie'):
        existing = find_favorite_by_name(t, entry.get('display_name', ''))
        if existing:
            remove_key = existing.get('canonical_key', key)

    if remove_key is not None:
        return (
            _addon.getLocalizedString(_STR_REMOVE_FAV),
            'RunPlugin(' + get_url(action='remove_favorite',
                                   type=t, key=remove_key) + ')'
        )

    url_params = {'action': 'add_favorite', 'type': t, 'key': key}
    if entry.get('display_name'):
        url_params['display_name'] = entry['display_name']
    if entry.get('search_query'):
        url_params['search_query'] = entry['search_query']
    if entry.get('category'):
        url_params['category'] = entry['category']
    if entry.get('sort'):
        url_params['sort'] = entry['sort']
    if entry.get('year'):
        url_params['year'] = str(entry['year'])
    return (
        _addon.getLocalizedString(_STR_ADD_FAV),
        'RunPlugin(' + get_url(**url_params) + ')'
    )
