# -*- coding: utf-8 -*-
# Module: ui
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""UI navigation and list building for Kodi."""

import sys
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon

from lib.api import api, parse_xml, is_ok, revalidate, getinfo, getlink, get_url_base, get_session
from lib.utils import todict, get_url, popinfo, ask, tolistitem, sizelize, infonize, fpsize, get_handle, get_addon, refresh_settings
from lib.cache import loadsearch, removesearch, storesearch, build_cache_key, get_or_fetch_grouped, get_series_cache, cache_set, clear_cache
from lib.grouping import fetch_and_group_series, deduplicate_versions
from lib.search import calculate_search_relevance
from lib.metadata import enrich_file_metadata
from lib.logging import log_debug

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

_handle = get_handle()
_addon = get_addon()
_session = get_session()
_series_cache = get_series_cache()

from lib.playback import toqueue, play

# Constants
NONE_WHAT = '%#NONE#%'
CATEGORIES = ['','video','images','audio','archives','docs','adult']
SORTS = ['','recent','rating','largest','smallest']

def dosearch(token, what, category, sort, limit, offset, action, params=None):
    response = api('search',{'what':'' if what == NONE_WHAT else what, 'category':category, 'sort':sort, 'limit': limit, 'offset': offset, 'wst':token, 'maybe_removed':'true'})
    if response is None:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        return
    xml = parse_xml(response.content)
    if is_ok(xml):

        # Check if flat view requested (either by URL param or user setting)
        force_flat = params and 'flat' in params if params else False

        # Check user's default view preference
        if not force_flat:
            default_view = _addon.getSetting('default_view')
            prefer_series = (default_view == '0')  # '0' = Series view, '1' = Flat
            if not prefer_series:
                force_flat = True

        # Collect all files
        files = []
        for file in xml.iter('file'):
            item = todict(file)
            files.append(item)

        # Check if we should show series view (only on first page and if not forced flat)
        # Also show series view if 'page' param present (paginated series view)
        show_series_view = not force_flat and files and (offset == 0 or (params and 'page' in params))

        if show_series_view:
            # Fetch ALL pages for accurate counts
            grouped = fetch_and_group_series(token, what, category, sort)

            # Show series/movie view if we found any series OR movies
            if grouped and (len(grouped['series']) >= 1 or len(grouped.get('movies', {})) >= 1):
                # Cache for navigation (thread-safe)
                cache_key = build_cache_key(what, category, sort)
                cache_set(cache_key, grouped)

                # Get page number from params
                page = int(params.get('page', 0)) if params else 0

                # Display series list instead of flat files
                display_series_list(grouped, what, category, sort, limit, page)
                return

        # ORIGINAL: Flat file display (backward compatible)
        if offset > 0: #prev page
            listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30206))
            listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
            xbmcplugin.addDirectoryItem(_handle, get_url(action=action, what=what, category=category, sort=sort, limit=limit, offset=offset - limit if offset > limit else 0), listitem, True)

        for item in files:
            commands = []
            commands.append(( _addon.getLocalizedString(30214), 'Container.Update(' + get_url(action='search',toqueue=item['ident'], what=what, offset=offset) + ')'))
            listitem = tolistitem(item,commands)
            xbmcplugin.addDirectoryItem(_handle, get_url(action='play',ident=item['ident'],name=item['name']), listitem, False)

        try:
            total = int(xml.find('total').text)
        except (AttributeError, ValueError, TypeError):
            total = 0

        if offset + limit < total: #next page
            listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30207))
            listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
            xbmcplugin.addDirectoryItem(_handle, get_url(action=action, what=what, category=category, sort=sort, limit=limit, offset=offset+limit), listitem, True)

        xbmcplugin.endOfDirectory(_handle)
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(_handle)


def display_series_list(grouped, what, category, sort, limit, page=0):
    """Display list of series with counts."""
    log_debug("=== DISPLAY_SERIES_LIST called with page={} ===".format(page))
    xbmcplugin.setContent(_handle, 'tvshows')

    # Merge series, movies, and non_series into unified list sorted by relevance
    all_items = []

    # Add series to unified list
    for k, v in grouped['series'].items():
        score = calculate_search_relevance(v['display_name'], what, k) if what else -1
        all_items.append(('series', k, v, score))

    # Add movies to unified list
    if grouped.get('movies'):
        for k, v in grouped['movies'].items():
            score = calculate_search_relevance(v['display_name'], what, k) if what else -1
            all_items.append(('movie', k, v, score))

    # Add non_series files to unified list
    if grouped.get('non_series'):
        for file_data in grouped['non_series']:
            # Calculate relevance score for files too
            score = calculate_search_relevance(file_data['name'], what) if what else -1
            all_items.append(('file', file_data['name'], file_data, score))

    # Sort unified list by relevance (or alphabetically if no query)
    if what:
        # Sort by: relevance DESC, then type (movies before series at same score), then alpha ASC
        all_items.sort(key=lambda x: (-x[3], x[0] != 'movie', x[1]))
    else:
        # No query - alphabetical by display name (case-insensitive)
        all_items.sort(key=lambda x: x[2].get('display_name', x[2].get('name', '')).lower())

    # Pagination config
    items_per_page = 25  # Max items per page
    total_items = len(all_items)

    # Calculate page display numbers
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)

    # Validate page bounds
    original_page = page
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1
    if page != original_page:
        log_debug("Page {} out of bounds, clamped to {}".format(original_page, page))
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)

    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    current_display_page = page + 1

    # Back to search menu button (only on page 2+, since ".." works on page 1)
    if page > 0:
        search_menu_url = get_url(action='search')
        back_url = get_url(action='goto_page', target_url=search_menu_url)
        listitem = xbmcgui.ListItem(label='[{}]'.format(_addon.getLocalizedString(30400)))
        listitem.setArt({'icon': 'DefaultFolderBack.png'})
        listitem.setProperty('IsPlayable', 'false')
        xbmcplugin.addDirectoryItem(_handle, back_url, listitem, False)

    # Option to switch to flat view (SECOND button)
    listitem = xbmcgui.ListItem(label='[{}]'.format(_addon.getLocalizedString(30401)))
    listitem.setArt({'icon': 'DefaultFile.png'})
    xbmcplugin.addDirectoryItem(_handle,
        get_url(action='search', what=what, category=category,
                sort=sort, limit=limit, flat=1),
        listitem, True)

    # Display items for current page
    page_items = all_items[start_idx:end_idx]
    for item_type, key, data, score in page_items:
        if item_type == 'series':
            series_name = key
            series_data = data
            season_count = len(series_data['seasons'])
            episode_count = series_data['total_episodes']
            display_name = series_data.get('display_name', series_name.title())

            # Special case: single season with single episode - display as standalone file
            if season_count == 1 and episode_count == 1:
                # Get the single episode data
                season_num = list(series_data['seasons'].keys())[0]
                ep_num = list(series_data['seasons'][season_num].keys())[0]
                versions = series_data['seasons'][season_num][ep_num]

                if versions:  # Defensive check
                    ep_data = versions[0]  # Use best version (already sorted)

                    # Create label with series name (removed version count)
                    label = display_name

                    # Single version: play directly
                    if len(versions) == 1:
                        commands = []
                        commands.append((
                            _addon.getLocalizedString(30214),
                            'Container.Update(' + get_url(
                                action='search', what=what, category=category,
                                sort=sort, limit=limit, toqueue=ep_data['ident']) + ')'
                        ))

                        listitem = tolistitem(ep_data, commands)
                        listitem.setLabel(label)
                        xbmcplugin.addDirectoryItem(_handle,
                            get_url(action='play', ident=ep_data['ident'],
                                   name=ep_data['name']),
                            listitem, False)
                    else:
                        # Multiple versions: create folder to select version
                        season_word = _addon.getLocalizedString(30414 if season_count == 1 else 30415)
                        episode_word = _addon.getLocalizedString(30416 if episode_count == 1 else 30417)
                        label = '{0} ({1} {2}, {3} {4})'.format(
                            display_name, season_count, season_word, episode_count, episode_word)
                        listitem = xbmcgui.ListItem(label=label)
                        listitem.setArt({'icon': 'DefaultTVShows.png'})
                        url_params = {'action': 'browse_series'}
                        # Defensive checks for all URL params
                        if series_name:
                            url_params['series'] = series_name
                        if what:
                            url_params['what'] = what
                        if category:
                            url_params['category'] = category
                        if sort:
                            url_params['sort'] = sort
                        url = get_url(**url_params)
                        xbmcplugin.addDirectoryItem(_handle, url, listitem, True)
                continue

            # Normal case: multi-season or multi-episode series
            season_word = _addon.getLocalizedString(30414 if season_count == 1 else 30415)
            episode_word = _addon.getLocalizedString(30416 if episode_count == 1 else 30417)
            label = '{0} ({1} {2}, {3} {4})'.format(
                display_name, season_count, season_word, episode_count, episode_word)

            listitem = xbmcgui.ListItem(label=label)
            listitem.setArt({'icon': 'DefaultTVShows.png'})

            # Build URL params - defensive checks for all params
            url_params = {'action': 'browse_series'}
            if series_name:
                url_params['series'] = series_name
            if what:
                url_params['what'] = what
            if category:
                url_params['category'] = category
            if sort:
                url_params['sort'] = sort
            url = get_url(**url_params)
            xbmcplugin.addDirectoryItem(_handle, url, listitem, True)

        elif item_type == 'movie':
            movie_key = key
            movie_data = data
            versions = movie_data['versions']
            year = movie_data['year']
            display_name = movie_data['display_name']

            # Label with version count
            label = f"{display_name} ({year})"
            if len(versions) > 1:
                version_word = _addon.getLocalizedString(30419)
                label += f" [{len(versions)} {version_word}]"

            listitem = xbmcgui.ListItem(label=label)
            listitem.setArt({'icon': 'DefaultVideo.png'})

            # Set plot if available
            if movie_data.get('plot'):
                listitem.setInfo('video', {'plot': movie_data['plot']})

            # Single version: play directly
            if len(versions) == 1:
                listitem.setProperty('IsPlayable', 'true')
                url = get_url(action='play', ident=versions[0]['ident'], name=versions[0]['name'])
                xbmcplugin.addDirectoryItem(_handle, url, listitem, False)
            else:
                # Multiple versions: show dialog
                listitem.setProperty('IsPlayable', 'true')
                url = get_url(
                    action='select_movie_version',
                    movie_key=movie_key,
                    what=what,
                    category=category,
                    sort=sort
                )
                xbmcplugin.addDirectoryItem(_handle, url, listitem, False)

        elif item_type == 'file':
            # Display non-series file
            file_data = data
            commands = []
            commands.append((
                _addon.getLocalizedString(30214),
                'Container.Update(' + get_url(action='search',
                    what=what, category=category, sort=sort, limit=limit,
                    page=page, toqueue=file_data['ident']) + ')'
            ))

            listitem = tolistitem(file_data, commands)
            xbmcplugin.addDirectoryItem(_handle,
                get_url(action='play', ident=file_data['ident'],
                       name=file_data['name']),
                listitem, False)

    # Next page button (only show if more pages exist)
    if end_idx < total_items:
        next_url = get_url(action='search', what=what, category=category,
                    sort=sort, limit=limit, page=page+1)
        log_debug("Creating NEXT page button (direct): {}".format(next_url))
        listitem = xbmcgui.ListItem(label='[{}]'.format(_addon.getLocalizedString(30402)))
        listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
        xbmcplugin.addDirectoryItem(_handle, next_url, listitem, True)

    xbmcplugin.endOfDirectory(_handle)


def browse_series(params):
    """Display seasons for selected series."""
    series_name = params.get('series')
    if not series_name:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(_handle)
        return
    xbmcplugin.setPluginCategory(_handle, series_name)
    xbmcplugin.setContent(_handle, 'seasons')

    # Get from cache or fetch if needed
    token = revalidate()
    cache_key, grouped = get_or_fetch_grouped(params, token, check_key=series_name, check_type='series')

    if series_name in grouped.get('series', {}):
        series_data = grouped['series'][series_name]

        # Display each season
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
    season_num = int(params['season'])
    category = params.get('category', '')
    sort_val = params.get('sort', '')

    xbmcplugin.setPluginCategory(_handle,
        _addon.getLocalizedString(30404).format(series_name, season_num))
    xbmcplugin.setContent(_handle, 'episodes')

    # Get from cache or fetch if needed
    cache_key, grouped = get_or_fetch_grouped(params, token, check_key=series_name, check_type='series')

    if series_name in grouped.get('series', {}):
        series_data = grouped['series'][series_name]

        if season_num in series_data['seasons']:
            episodes_dict = series_data['seasons'][season_num]

            # Display each episode (dict is episode_num: [versions])
            for ep_num in sorted(episodes_dict.keys()):
                versions = episodes_dict[ep_num]

                if not versions:  # Skip if no versions (defensive)
                    continue

                # Create label
                label = _addon.getLocalizedString(30405).format(ep_num)

                # Single version: play directly
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
                    listitem.setLabel(label)  # Override label
                    xbmcplugin.addDirectoryItem(_handle,
                        get_url(action='play', ident=ep_data['ident'],
                               name=ep_data['name']),
                        listitem, False)

                # Multiple versions: show as playable item that opens dialog
                else:
                    label = _addon.getLocalizedString(30406).format(ep_num, len(versions))

                    # Use first (best) version for thumbnail
                    listitem = xbmcgui.ListItem(label=label)
                    listitem.setProperty('IsPlayable', 'true')
                    if versions[0].get('img'):
                        listitem.setArt({'thumb': versions[0]['img']})

                    # Context menu: Queue all versions
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

                    # URL to version selector - isFolder=False (playable)
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
    season_num = int(params['season'])
    episode_num = int(params['episode'])
    log_debug('Looking for: {} S{}E{}'.format(series_name, season_num, episode_num))

    # Get from cache or fetch if needed
    cache_key, grouped = get_or_fetch_grouped(params, token, check_key=series_name, check_type='series')
    log_debug('grouped keys: {}'.format(grouped.keys() if grouped else 'EMPTY'))

    # Get versions for this specific episode
    versions = []
    if series_name in grouped.get('series', {}):
        series_data = grouped['series'][series_name]
        if season_num in series_data['seasons']:
            episodes_dict = series_data['seasons'][season_num]
            if episode_num in episodes_dict:
                versions = episodes_dict[episode_num]

    if not versions:
        xbmcgui.Dialog().ok(_addon.getLocalizedString(30407), _addon.getLocalizedString(30408))
        return

    # Deduplicate versions (safety net)
    versions = deduplicate_versions(versions)

    # Fetch file_info for top 3-5 files (largest = best quality)
    TOP_FILES_TO_ENRICH = 5
    for idx in range(min(TOP_FILES_TO_ENRICH, len(versions))):
        enrich_file_metadata(versions[idx], versions[idx].get('ident'), token)

    # Build dialog options with ListItems (label + label2 for metadata)
    listitems = []
    for idx, file_dict in enumerate(versions):
        quality_meta = file_dict.get('quality_meta', {})
        file_info = file_dict.get('file_info', {})

        # Main label: filename
        label = file_dict.get('name', 'Unknown')

        # Secondary label (metadata line)
        meta_parts = []

        # Resolution from API or filename quality tag
        resolution = file_info.get('resolution')
        if resolution:
            meta_parts.append(resolution)
        elif quality_meta.get('quality'):
            meta_parts.append(quality_meta['quality'])

        # Source
        if quality_meta.get('source'):
            meta_parts.append(quality_meta['source'])

        # Video codec from API or filename
        codec = file_info.get('video_codec') or quality_meta.get('codec')
        if codec:
            meta_parts.append(codec)

        # Audio from API or filename
        audio = file_info.get('audio')
        if audio:
            meta_parts.append('Audio: {0}'.format(audio))
        elif quality_meta.get('audio'):
            meta_parts.append(quality_meta['audio'])

        # Subtitles from API
        if file_info.get('subtitles'):
            meta_parts.append('Subs: {0}'.format(file_info['subtitles']))

        # Language from filename (if no API data)
        if not file_info and file_dict.get('language'):
            meta_parts.append('[{0}]'.format(file_dict['language']))

        # File size
        if file_dict.get('size'):
            meta_parts.append(sizelize(file_dict['size']))

        # Create ListItem
        listitem = xbmcgui.ListItem(label=label)
        if meta_parts:
            listitem.setLabel2(' | '.join(meta_parts))

        listitems.append(listitem)

    # Show dialog
    # Get display name for dialog title
    display_name = grouped.get('series', {}).get(series_name, {}).get('display_name', series_name)

    dialog = xbmcgui.Dialog()
    selected = dialog.select(
        '{0} - S{1:02d}E{2:02d}'.format(display_name, season_num, episode_num),
        listitems,
        useDetails=True
    )

    # Handle selection - play directly without intermediate screen
    if selected >= 0:
        chosen_file = versions[selected]
        # Get playback link and resolve directly
        link = getlink(chosen_file['ident'], token)
        if link is not None:
            headers = _session.headers if _session and hasattr(_session, 'headers') else None
            if headers:
                headers.update({'Cookie': 'wst=' + token})
                link = link + '|' + urlencode(headers)
            listitem = xbmcgui.ListItem(label=chosen_file['name'], path=link)
            listitem.setProperty('mimetype', 'application/octet-stream')
            xbmcplugin.setResolvedUrl(_handle, True, listitem)
        else:
            popinfo(_addon.getLocalizedString(30308), icon=xbmcgui.NOTIFICATION_ERROR)
            xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
    else:
        # User canceled - must still resolve
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

    # Get from cache or fetch if needed
    cache_key, grouped = get_or_fetch_grouped(params, token, check_key=movie_key, check_type='movies')

    if movie_key not in grouped.get('movies', {}):
        xbmcgui.Dialog().ok(_addon.getLocalizedString(30407), _addon.getLocalizedString(30409))
        return

    movie_data = grouped['movies'][movie_key]
    versions = movie_data['versions']
    display_name = f"{movie_data['display_name']} ({movie_data['year']})"

    # Deduplicate versions (safety net)
    versions = deduplicate_versions(versions)

    # Fetch file_info for top 5 files (largest = best quality)
    TOP_FILES_TO_ENRICH = 5
    for idx in range(min(TOP_FILES_TO_ENRICH, len(versions))):
        enrich_file_metadata(versions[idx], versions[idx].get('ident'), token)

    # Build dialog list items
    listitems = []
    for idx, file_dict in enumerate(versions):
        quality_meta = file_dict.get('quality_meta', {})
        file_info = file_dict.get('file_info', {})

        label = file_dict.get('name', 'Unknown')

        # Build metadata line
        meta_parts = []
        if file_info.get('resolution'):
            meta_parts.append(file_info['resolution'])
        elif quality_meta.get('quality'):
            meta_parts.append(quality_meta['quality'])

        if quality_meta.get('source'):
            meta_parts.append(quality_meta['source'])

        if file_info.get('video_codec'):
            meta_parts.append(file_info['video_codec'])
        elif quality_meta.get('codec'):
            meta_parts.append(quality_meta['codec'])

        if file_info.get('audio'):
            meta_parts.append(f"Audio: {file_info['audio']}")

        if file_info.get('subtitles'):
            meta_parts.append(f"Subs: {file_info['subtitles']}")

        meta_parts.append(sizelize(file_dict.get('size', 0)))

        listitem = xbmcgui.ListItem(label=label)
        listitem.setLabel2(' | '.join(meta_parts))
        listitems.append(listitem)

    # Show dialog
    dialog = xbmcgui.Dialog()
    selected = dialog.select(display_name, listitems, useDetails=True)
    log_debug('Movie dialog: selected index = {}'.format(selected))

    if selected >= 0:
        selected_version = versions[selected]
        log_debug('Playing movie: {} [ident={}]'.format(selected_version['name'], selected_version['ident']))
        # Get playback link and resolve directly (same as show_version_dialog)
        link = getlink(selected_version['ident'], token)
        if link is not None:
            headers = _session.headers if _session and hasattr(_session, 'headers') else None
            if headers:
                headers.update({'Cookie': 'wst=' + token})
                link = link + '|' + urlencode(headers)
            listitem = xbmcgui.ListItem(label=selected_version['name'], path=link)
            listitem.setProperty('mimetype', 'application/octet-stream')
            xbmcplugin.setResolvedUrl(_handle, True, listitem)
        else:
            popinfo(_addon.getLocalizedString(30308), icon=xbmcgui.NOTIFICATION_ERROR)
            xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
    else:
        # User canceled - must still resolve
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

    # Get from cache or fetch if needed (thread-safe)
    cache_key, grouped = get_or_fetch_grouped(params, token)

    # Show grouped movies first
    if grouped.get('movies'):
        # Movies section header
        listitem = xbmcgui.ListItem(label='[B]{}[/B]'.format(_addon.getLocalizedString(30410)))
        listitem.setArt({'icon': 'DefaultMovies.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='separator'), listitem, False)

        for canonical_key in sorted(grouped['movies'].keys()):
            movie_data = grouped['movies'][canonical_key]
            versions = movie_data['versions']
            year = movie_data['year']
            display_name = movie_data['display_name']

            # Label with version count
            label = f"{display_name} ({year})"
            if len(versions) > 1:
                version_word = _addon.getLocalizedString(30419)
                label += f" [{len(versions)} {version_word}]"

            listitem = xbmcgui.ListItem(label=label)
            listitem.setArt({'icon': 'DefaultVideo.png'})

            # Set plot if available from CSFD
            if movie_data.get('plot'):
                listitem.setInfo('video', {'plot': movie_data['plot']})

            # Single version: play directly
            if len(versions) == 1:
                listitem.setProperty('IsPlayable', 'true')
                url = get_url(action='play', ident=versions[0]['ident'], name=versions[0]['name'])
                xbmcplugin.addDirectoryItem(_handle, url, listitem, False)
            else:
                # Multiple versions: show dialog
                listitem.setProperty('IsPlayable', 'true')
                url = get_url(
                    action='select_movie_version',
                    movie_key=canonical_key,
                    what=params['what'],
                    category=category,
                    sort=sort_val
                )
                xbmcplugin.addDirectoryItem(_handle, url, listitem, False)

    # Show ungrouped files
    if grouped.get('non_series'):
        # Other files section header (if movies exist)
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


def search(params):
    log_debug("search() called with params: {}".format(params))
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \\ " + _addon.getLocalizedString(30201))
    token = revalidate()

    updateListing=False

    if 'remove' in params:
        removesearch(params['remove'])
        updateListing=True

    if 'toqueue' in params:
        toqueue(params['toqueue'],token)
        updateListing=True

    what = None

    if 'what' in params:
        what = params['what']
        log_debug("what from params: {}".format(what))

    if 'ask' in params:
        slast = _addon.getSetting('slast')
        log_debug("ask=1, slast='{}', what={}".format(slast, what))
        # Only ask if slast is empty (first time only)
        # If slast has any value (including NONE_WHAT), user already searched, don't ask again
        if what is None and slast == '':
            log_debug("Showing search dialog")
            # Fix for Kodi 21.3: endOfDirectory before keyboard to prevent blank page
            xbmcplugin.endOfDirectory(_handle)
            what = ask(what)
            log_debug("Dialog result: {}".format(what))
            if what is not None:
                storesearch(what)
                _addon.setSetting('slast', what)
                clear_cache()  # Clear stale data on new search session
                log_debug("Stored search, set slast='{}', cleared cache".format(what))
                category = params['category'] if 'category' in params else CATEGORIES[int(_addon.getSetting('scategory'))]
                sort = params['sort'] if 'sort' in params else SORTS[int(_addon.getSetting('ssort'))]
                limit = int(params['limit']) if 'limit' in params else int(_addon.getSetting('slimit'))
                offset = int(params['offset']) if 'offset' in params else 0
                url = get_url(action='search',what=what,category=category,sort=sort,limit=limit,offset=offset)
                xbmc.executebuiltin("Container.Update({})".format(url))
                return
            else:
                # Clear search state on cancel so back navigation works
                log_debug("Search cancelled, clearing slast")
                _addon.setSetting('slast', '')
                updateListing=True
        else:
            log_debug("Skipping dialog, slast='{}' indicates previous interaction".format(slast))

    if what is not None:
        # Keep slast stable during search session (don't modify on pagination)
        # This ensures back navigation returns to search results, not previous search
        _addon.setSetting('slast', what)

        category = params['category'] if 'category' in params else CATEGORIES[int(_addon.getSetting('scategory'))]
        sort = params['sort'] if 'sort' in params else SORTS[int(_addon.getSetting('ssort'))]
        limit = int(params['limit']) if 'limit' in params else int(_addon.getSetting('slimit'))
        offset = int(params['offset']) if 'offset' in params else 0
        xbmcplugin.setContent(_handle, 'files')
        dosearch(token, what, category, sort, limit, offset, 'search', params)
    else:
        # Clear search state when returning to search menu
        _addon.setSetting('slast', '')
        history = loadsearch()
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30205))
        listitem.setArt({'icon': 'DefaultAddSource.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='search',ask=1), listitem, True)
        
        #newest
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30208))
        listitem.setArt({'icon': 'DefaultAddonsRecentlyUpdated.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='search',what=NONE_WHAT,sort=SORTS[1]), listitem, True)
        
        #biggest
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30209))
        listitem.setArt({'icon': 'DefaultHardDisk.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='search',what=NONE_WHAT,sort=SORTS[3]), listitem, True)
        
        for search in history:
            listitem = xbmcgui.ListItem(label=search)
            listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
            commands = []
            commands.append(( _addon.getLocalizedString(30213), 'Container.Update(' + get_url(action='search',remove=search) + ')'))
            listitem.addContextMenuItems(commands)
            xbmcplugin.addDirectoryItem(_handle, get_url(action='search',what=search), listitem, True)
    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)


def history(params):
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \\ " + _addon.getLocalizedString(30203))
    xbmcplugin.setContent(_handle, 'files')
    token = revalidate()
    updateListing=False
    
    if 'remove' in params:
        remove = params['remove']
        updateListing=True
        response = api('history',{'wst':token})
        if response is not None:
            xml = parse_xml(response.content)
            ids = []
            if is_ok(xml):
                for file in xml.iter('file'):
                    if remove == file.find('ident').text:
                        ids.append(file.find('download_id').text)
            else:
                popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
            if ids:
                rr = api('clear_history',{'ids[]':ids,'wst':token})
                if rr is None:
                    popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
                else:
                    xml = parse_xml(rr.content)
                    if is_ok(xml):
                        popinfo(_addon.getLocalizedString(30104))
                    else:
                        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
    
    if 'toqueue' in params:
        toqueue(params['toqueue'],token)
        updateListing=True
    
    response = api('history',{'wst':token})
    if response is None:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
    else:
        xml = parse_xml(response.content)
        files = []
        if is_ok(xml):
            for file in xml.iter('file'):
                item = todict(file, ['ended_at', 'download_id', 'started_at'])
                if item not in files:
                    files.append(item)
            for file in files:
                commands = []
                commands.append(( _addon.getLocalizedString(30213), 'Container.Update(' + get_url(action='history',remove=file['ident']) + ')'))
                commands.append(( _addon.getLocalizedString(30214), 'Container.Update(' + get_url(action='history',toqueue=file['ident']) + ')'))
                listitem = tolistitem(file, commands)
                xbmcplugin.addDirectoryItem(_handle, get_url(action='play',ident=file['ident'],name=file['name']), listitem, False)
        else:
            popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
    xbmcplugin.endOfDirectory(_handle,updateListing=updateListing)


def settings(params):
    _addon.openSettings()
    xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())


def info(params):
    token = revalidate()
    if 'ident' not in params:
        xbmc.log("YAWsP: Missing ident in info", xbmc.LOGERROR)
        return
    xml = getinfo(params['ident'],token)
    
    if xml is not None:
        info = todict(xml)
        text = ''
        text += infonize(info, 'name')
        text += infonize(info, 'size', sizelize)
        text += infonize(info, 'type')
        text += infonize(info, 'width')
        text += infonize(info, 'height')
        text += infonize(info, 'format')
        text += infonize(info, 'fps', fpsize)
        text += infonize(info, 'bitrate', lambda x:sizelize(x,['bps','Kbps','Mbps','Gbps']))
        if 'video' in info and 'stream' in info['video']:
            streams = info['video']['stream']
            if isinstance(streams, dict):
                streams = [streams]
            for stream in streams:
                text += 'Video stream: '
                text += infonize(stream, 'width', showkey=False, suffix='')
                text += infonize(stream, 'height', showkey=False, prefix='x', suffix='')
                text += infonize(stream,'format', showkey=False, prefix=', ', suffix='')
                text += infonize(stream,'fps', fpsize, showkey=False, prefix=', ', suffix='')
                text += '\n'
        if 'audio' in info and 'stream' in info['audio']:
            streams = info['audio']['stream']
            if isinstance(streams, dict):
                streams = [streams]
            for stream in streams:
                text += 'Audio stream: '
                text += infonize(stream, 'format', showkey=False, suffix='')
                text += infonize(stream,'channels', prefix=', ', showkey=False, suffix='')
                text += infonize(stream,'bitrate', lambda x:sizelize(x,['bps','Kbps','Mbps','Gbps']), prefix=', ', showkey=False, suffix='')
                text += '\n'
        text += infonize(info, 'removed', lambda x:'Yes' if x=='1' else 'No')
        xbmcgui.Dialog().textviewer(_addon.getAddonInfo('name'), text)


def menu():
    revalidate()
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name'))
    listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30201))
    listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='search'), listitem, True)
    
    listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30202))
    listitem.setArt({'icon': 'DefaultPlaylist.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='queue'), listitem, True)
    
    listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30203))
    listitem.setArt({'icon': 'DefaultAddonsUpdates.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='history'), listitem, True)
    
    if 'true' == _addon.getSetting('experimental'):
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30412))
        listitem.setArt({'icon': 'DefaultAddonsZip.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='db'), listitem, True)

    listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30204))
    listitem.setArt({'icon': 'DefaultAddonService.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='settings'), listitem, False)

    xbmcplugin.endOfDirectory(_handle)

# ============================================================================
# Pagination Navigation Helper
# ============================================================================

def goto_page(params):
    """Navigate to a page by replacing current directory (no stack).

    This handler is used for pagination to avoid stacking navigation history.
    When called via RunPlugin, it updates the container in-place.
    """
    log_debug("=== GOTO_PAGE CALLED ===")
    log_debug("goto_page params: {}".format(params))

    # Get target URL from params
    if 'target_url' in params:
        target_url = params['target_url']
        log_debug("Using target_url from params: {}".format(target_url))
    else:
        # Fallback: build from params (old method)
        target_params = {k: v for k, v in params.items() if k != 'action'}
        if 'target_action' in target_params:
            target_params['action'] = target_params.pop('target_action')
        target_url = get_url(**target_params)
        log_debug("Built target_url from params: {}".format(target_url))

    # Use Container.Update with replace to replace current page in stack
    # This allows "Back to search menu" to replace pagination pages
    log_debug("Executing Container.Update({}, replace)".format(target_url))
    xbmc.executebuiltin('Container.Update({},replace)'.format(target_url))
    log_debug("=== GOTO_PAGE FINISHED ===")

# ============================================================================
# Settings Monitor & Routing
# ============================================================================

class SettingsMonitor(xbmc.Monitor):
    """Monitor for settings changes to refresh cached addon object."""
    def onSettingsChanged(self):
        global _addon
        log_debug('Settings changed, refreshing cached values')
        _addon = xbmcaddon.Addon()
        refresh_settings()  # Also refresh utils module settings


# Instantiate settings monitor at module load
_settings_monitor = SettingsMonitor()

