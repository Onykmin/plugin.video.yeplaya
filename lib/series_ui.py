# -*- coding: utf-8 -*-
# Module: series_ui
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Series browsing, version selection, and movie UI functions."""

import xbmcgui
import xbmcplugin

from lib.api import revalidate
from lib.utils import get_url, popinfo, tolistitem, get_handle, get_addon, set_webshare_id, set_video_info
from lib.parsing import parse_quality_metadata
from lib.cache import get_or_fetch_grouped
from lib.grouping import deduplicate_versions
from lib.metadata import enrich_file_metadata
from lib.logging import log_debug
from lib.playback import toqueue, resolve_and_play
from lib.ui import _build_version_metadata

_handle = get_handle()
_addon = get_addon()


def browse_series(params):
    """Display seasons for selected series."""
    series_name = params.get('series')
    if not series_name:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(_handle)
        return
    xbmcplugin.setPluginCategory(_handle, series_name)
    xbmcplugin.setContent(_handle, 'seasons')

    token = revalidate()
    cache_key, grouped = get_or_fetch_grouped(params, token, check_key=series_name, check_type='series')

    if grouped and series_name in grouped.get('series', {}):
        series_data = grouped['series'][series_name]

        for season_num in sorted(series_data['seasons'].keys()):
            episodes = series_data['seasons'][season_num]
            episode_count = len(episodes)
            episode_word = _addon.getLocalizedString(30416 if episode_count == 1 else 30417)
            label = _addon.getLocalizedString(30403).format(
                season_num, episode_count, episode_word)

            listitem = xbmcgui.ListItem(label=label)
            listitem.setArt({'icon': 'DefaultTVShows.png'})

            url = get_url(action='browse_season', series=series_name,
                         season=season_num, what=params['what'],
                         category=params.get('category'),
                         sort=params.get('sort'))
            xbmcplugin.addDirectoryItem(_handle, url, listitem, True)

    xbmcplugin.endOfDirectory(_handle)


def browse_season(params):
    """Display episodes for selected season."""
    token = revalidate()
    updateListing = False

    if 'toqueue' in params:
        toqueue(params['toqueue'], token)
        updateListing = True

    series_name = params['series']
    try:
        season_num = int(params['season'])
    except (ValueError, TypeError, KeyError):
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(_handle)
        return
    category = params.get('category', '')
    sort_val = params.get('sort', '')

    xbmcplugin.setPluginCategory(_handle,
        _addon.getLocalizedString(30404).format(series_name, season_num))
    xbmcplugin.setContent(_handle, 'episodes')

    cache_key, grouped = get_or_fetch_grouped(params, token, check_key=series_name, check_type='series')

    if grouped and series_name in grouped.get('series', {}):
        series_data = grouped['series'][series_name]

        if season_num in series_data['seasons']:
            episodes_dict = series_data['seasons'][season_num]

            for ep_num in sorted(episodes_dict.keys()):
                versions = episodes_dict[ep_num]

                if not versions:
                    continue

                label = _addon.getLocalizedString(30405).format(ep_num)

                if len(versions) == 1:
                    ep_data = versions[0]
                    commands = []
                    commands.append((
                        _addon.getLocalizedString(30214),
                        'Container.Update(' + get_url(
                            action='browse_season', series=series_name,
                            season=season_num, what=params['what'],
                            toqueue=ep_data['ident']) + ')'
                    ))

                    listitem = tolistitem(ep_data, commands)
                    listitem.setLabel(label)
                    xbmcplugin.addDirectoryItem(_handle,
                        get_url(action='play', ident=ep_data['ident'],
                               name=ep_data['name']),
                        listitem, False)
                else:
                    label = _addon.getLocalizedString(30406).format(ep_num, len(versions))

                    listitem = xbmcgui.ListItem(label=label)
                    listitem.setProperty('IsPlayable', 'true')
                    set_webshare_id(listitem, versions[0]['ident'])
                    if versions[0].get('img'):
                        listitem.setArt({'thumb': versions[0]['img']})

                    commands = []
                    for v in versions:
                        commands.append((
                            _addon.getLocalizedString(30214),
                            'Container.Update(' + get_url(
                                action='browse_season', series=series_name,
                                season=season_num, what=params['what'],
                                toqueue=v['ident']) + ')'
                        ))
                    listitem.addContextMenuItems(commands)

                    url = get_url(action='select_version', series=series_name,
                                 season=season_num, episode=ep_num,
                                 what=params['what'], category=category,
                                 sort=sort_val)

                    xbmcplugin.addDirectoryItem(_handle, url, listitem, False)

    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)


def show_version_dialog(params):
    """Show popup dialog to select episode version."""
    log_debug('show_version_dialog called with params: {}'.format(params))
    token = revalidate()
    log_debug('token: {}'.format('OK' if token else 'NONE'))

    series_name = params['series']
    try:
        season_num = int(params['season'])
        episode_num = int(params['episode'])
    except (ValueError, TypeError, KeyError):
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return
    log_debug('Looking for: {} S{}E{}'.format(series_name, season_num, episode_num))

    cache_key, grouped = get_or_fetch_grouped(params, token, check_key=series_name, check_type='series')
    log_debug('grouped keys: {}'.format(grouped.keys() if grouped else 'EMPTY'))

    versions = []
    if grouped and series_name in grouped.get('series', {}):
        series_data = grouped['series'][series_name]
        if season_num in series_data['seasons']:
            episodes_dict = series_data['seasons'][season_num]
            if episode_num in episodes_dict:
                versions = episodes_dict[episode_num]

    if not versions:
        xbmcgui.Dialog().ok(_addon.getLocalizedString(30407), _addon.getLocalizedString(30408))
        return

    versions = deduplicate_versions(versions)

    TOP_FILES_TO_ENRICH = 5
    for idx in range(min(TOP_FILES_TO_ENRICH, len(versions))):
        enrich_file_metadata(versions[idx], versions[idx].get('ident'), token)

    # Lazy quality metadata — only parse when dialog needs it
    for v in versions:
        if 'quality_meta' not in v:
            v['quality_meta'] = parse_quality_metadata(v.get('name', ''))

    listitems = []
    for file_dict in versions:
        label = file_dict.get('name', 'Unknown')
        meta_parts = _build_version_metadata(file_dict)
        listitem = xbmcgui.ListItem(label=label)
        if meta_parts:
            listitem.setLabel2(' | '.join(meta_parts))
        listitems.append(listitem)

    display_name = grouped.get('series', {}).get(series_name, {}).get('display_name', series_name)
    dialog = xbmcgui.Dialog()
    selected = dialog.select(
        '{0} - S{1:02d}E{2:02d}'.format(display_name, season_num, episode_num),
        listitems, useDetails=True)

    if selected >= 0:
        chosen_file = versions[selected]
        resolve_and_play(chosen_file['ident'], chosen_file['name'], token)
    else:
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())


def select_version(params):
    """Backward compatibility - redirect to show_version_dialog."""
    show_version_dialog(params)


def select_movie_version(params):
    """Show version selection dialog for movies."""
    token = revalidate()
    movie_key = params.get('movie_key')
    if not movie_key:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    cache_key, grouped = get_or_fetch_grouped(params, token, check_key=movie_key, check_type='movies')

    if not grouped or movie_key not in grouped.get('movies', {}):
        xbmcgui.Dialog().ok(_addon.getLocalizedString(30407), _addon.getLocalizedString(30409))
        return

    movie_data = grouped['movies'][movie_key]
    versions = movie_data['versions']
    display_name = f"{movie_data['display_name']} ({movie_data['year']})"

    versions = deduplicate_versions(versions)

    TOP_FILES_TO_ENRICH = 5
    for idx in range(min(TOP_FILES_TO_ENRICH, len(versions))):
        enrich_file_metadata(versions[idx], versions[idx].get('ident'), token)

    # Lazy quality metadata
    for v in versions:
        if 'quality_meta' not in v:
            v['quality_meta'] = parse_quality_metadata(v.get('name', ''))

    listitems = []
    for file_dict in versions:
        label = file_dict.get('name', 'Unknown')
        meta_parts = _build_version_metadata(file_dict)
        listitem = xbmcgui.ListItem(label=label)
        if meta_parts:
            listitem.setLabel2(' | '.join(meta_parts))
        listitems.append(listitem)

    dialog = xbmcgui.Dialog()
    selected = dialog.select(display_name, listitems, useDetails=True)
    log_debug('Movie dialog: selected index = {}'.format(selected))

    if selected >= 0:
        selected_version = versions[selected]
        log_debug('Playing movie: {} [ident={}]'.format(selected_version['name'], selected_version['ident']))
        resolve_and_play(selected_version['ident'], selected_version['name'], token)
    else:
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())


def browse_other(params):
    """Display movies and ungrouped files from search."""
    token = revalidate()
    updateListing = False

    if 'toqueue' in params:
        toqueue(params['toqueue'], token)
        updateListing = True

    xbmcplugin.setPluginCategory(_handle, 'Other files')
    xbmcplugin.setContent(_handle, 'files')

    cache_key, grouped = get_or_fetch_grouped(params, token)

    if grouped and grouped.get('movies'):
        listitem = xbmcgui.ListItem(label='[B]{}[/B]'.format(_addon.getLocalizedString(30410)))
        listitem.setArt({'icon': 'DefaultMovies.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='separator'), listitem, False)

        # Sort movies: most versions first (best match), then by year desc
        for canonical_key in sorted(grouped['movies'].keys(),
                                    key=lambda k: (-len(grouped['movies'][k].get('versions', [])),
                                                   -grouped['movies'][k].get('year', 0))):
            movie_data = grouped['movies'][canonical_key]
            versions = movie_data['versions']
            year = movie_data['year']
            display_name = movie_data['display_name']

            label = f"{display_name} ({year})"
            if len(versions) > 1:
                version_word = _addon.getLocalizedString(30419)
                label += f" [{len(versions)} {version_word}]"

            listitem = xbmcgui.ListItem(label=label)
            listitem.setArt({'icon': 'DefaultVideo.png'})

            if movie_data.get('plot'):
                set_video_info(listitem, {'plot': movie_data['plot']})

            if len(versions) == 1:
                listitem.setProperty('IsPlayable', 'true')
                set_webshare_id(listitem, versions[0]['ident'])
                url = get_url(action='play', ident=versions[0]['ident'], name=versions[0]['name'])
                xbmcplugin.addDirectoryItem(_handle, url, listitem, False)
            else:
                listitem.setProperty('IsPlayable', 'true')
                set_webshare_id(listitem, versions[0]['ident'])
                url = get_url(
                    action='select_movie_version',
                    movie_key=canonical_key,
                    what=params['what'],
                    category=params.get('category', ''),
                    sort=params.get('sort', '')
                )
                xbmcplugin.addDirectoryItem(_handle, url, listitem, False)

    if grouped and grouped.get('non_series'):
        if grouped.get('movies'):
            listitem = xbmcgui.ListItem(label='[B]{}[/B]'.format(_addon.getLocalizedString(30411)))
            listitem.setArt({'icon': 'DefaultFolder.png'})
            xbmcplugin.addDirectoryItem(_handle, get_url(action='separator'), listitem, False)

        for file_data in grouped['non_series']:
            commands = []
            commands.append((
                _addon.getLocalizedString(30214),
                'Container.Update(' + get_url(action='browse_other',
                    what=params['what'], toqueue=file_data['ident']) + ')'
            ))

            listitem = tolistitem(file_data, commands)
            xbmcplugin.addDirectoryItem(_handle,
                get_url(action='play', ident=file_data['ident'],
                       name=file_data['name']),
                listitem, False)

    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)
