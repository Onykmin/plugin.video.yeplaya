# -*- coding: utf-8 -*-
# Module: search_ui
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Search, display series list, and new search UI functions."""

import xbmc
import xbmcgui
import xbmcplugin

from lib.api import api, parse_xml, is_ok, revalidate
from lib.utils import todict, get_url, popinfo, ask, tolistitem, sizelize, get_handle, get_addon, set_webshare_id, set_video_info, apply_playback_state
from lib.cache import loadsearch, removesearch, storesearch, build_cache_key, cache_set, clear_cache
from lib.grouping import fetch_and_group_series
from lib.search import calculate_search_relevance
from lib.logging import log_debug
from lib.playback import toqueue
from lib.ui import NONE_WHAT, CATEGORIES, SORTS

_handle = get_handle()
_addon = get_addon()


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

        if not files and offset == 0:
            popinfo(_addon.getLocalizedString(30108), icon=xbmcgui.NOTIFICATION_INFO)
            xbmcplugin.endOfDirectory(_handle)
            return

        # Check if we should show series view (only on first page and if not forced flat)
        # Also show series view if 'page' param present (paginated series view)
        show_series_view = not force_flat and files and (offset == 0 or (params and 'page' in params))

        if show_series_view:
            # Fetch ALL pages for accurate counts (pass first page to avoid re-fetch)
            try:
                first_total = int(xml.find('total').text)
            except (AttributeError, ValueError, TypeError):
                first_total = None
            grouped = fetch_and_group_series(token, what, category, sort,
                                             first_page_files=files, first_page_total=first_total)

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
            score = calculate_search_relevance(file_data['name'], what) if what else -1
            all_items.append(('file', file_data['name'], file_data, score))

    # Sort unified list by relevance (or alphabetically if no query)
    if what:
        all_items.sort(key=lambda x: (-x[3], x[0] != 'movie', x[1]))
    else:
        all_items.sort(key=lambda x: x[2].get('display_name', x[2].get('name', '')).lower())

    # Pagination config
    items_per_page = 25
    total_items = len(all_items)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)

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

    # Back to search menu button (only on page 2+, since ".." works on page 1)
    if page > 0:
        search_menu_url = get_url(action='search')
        back_url = get_url(action='goto_page', target_url=search_menu_url)
        listitem = xbmcgui.ListItem(label='[{}]'.format(_addon.getLocalizedString(30400)))
        listitem.setArt({'icon': 'DefaultFolderBack.png'})
        listitem.setProperty('IsPlayable', 'false')
        xbmcplugin.addDirectoryItem(_handle, back_url, listitem, False)

    # Option to switch to flat view
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
                season_num = list(series_data['seasons'].keys())[0]
                ep_num = list(series_data['seasons'][season_num].keys())[0]
                versions = series_data['seasons'][season_num][ep_num]

                if versions:
                    ep_data = versions[0]
                    label = display_name

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
                                   name=ep_data['name'],
                                   series=series_name, season=season_num,
                                   episode=ep_num),
                            listitem, False)
                    else:
                        season_word = _addon.getLocalizedString(30414 if season_count == 1 else 30415)
                        episode_word = _addon.getLocalizedString(30416 if episode_count == 1 else 30417)
                        label = '{0} ({1} {2}, {3} {4})'.format(
                            display_name, season_count, season_word, episode_count, episode_word)
                        listitem = xbmcgui.ListItem(label=label)
                        listitem.setArt({'icon': 'DefaultTVShows.png'})
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
                continue

            # Normal case: multi-season or multi-episode series
            season_word = _addon.getLocalizedString(30414 if season_count == 1 else 30415)
            episode_word = _addon.getLocalizedString(30416 if episode_count == 1 else 30417)
            label = '{0} ({1} {2}, {3} {4})'.format(
                display_name, season_count, season_word, episode_count, episode_word)

            listitem = xbmcgui.ListItem(label=label)
            listitem.setArt({'icon': 'DefaultTVShows.png'})

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

            label = f"{display_name} ({year})"
            if len(versions) > 1:
                version_word = _addon.getLocalizedString(30419)
                label += f" [{len(versions)} {version_word}]"

            listitem = xbmcgui.ListItem(label=label)
            listitem.setArt({'icon': 'DefaultVideo.png'})

            if movie_data.get('plot'):
                set_video_info(listitem, {'plot': movie_data['plot']})

            mv_state_key = "mv:{0}".format(movie_key)
            state_cmds = apply_playback_state(listitem, mv_state_key)
            if state_cmds:
                listitem.addContextMenuItems(state_cmds)

            if len(versions) == 1:
                listitem.setProperty('IsPlayable', 'true')
                set_webshare_id(listitem, versions[0]['ident'])
                url = get_url(action='play', ident=versions[0]['ident'],
                             name=versions[0]['name'], movie_key=movie_key)
                xbmcplugin.addDirectoryItem(_handle, url, listitem, False)
            else:
                listitem.setProperty('IsPlayable', 'true')
                set_webshare_id(listitem, versions[0]['ident'])
                url = get_url(
                    action='select_movie_version',
                    movie_key=movie_key,
                    what=what,
                    category=category,
                    sort=sort
                )
                xbmcplugin.addDirectoryItem(_handle, url, listitem, False)

        elif item_type == 'file':
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

    # Next page button
    if end_idx < total_items:
        next_url = get_url(action='search', what=what, category=category,
                    sort=sort, limit=limit, page=page+1)
        log_debug("Creating NEXT page button (direct): {}".format(next_url))
        listitem = xbmcgui.ListItem(label='[{}]'.format(_addon.getLocalizedString(30402)))
        listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
        xbmcplugin.addDirectoryItem(_handle, next_url, listitem, True)

    xbmcplugin.endOfDirectory(_handle)


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
        if what is None and slast == '':
            log_debug("Showing search dialog")
            xbmcplugin.endOfDirectory(_handle)
            what = ask(what)
            log_debug("Dialog result: {}".format(what))
            if what is not None:
                storesearch(what)
                _addon.setSetting('slast', what)
                clear_cache()
                log_debug("Stored search, set slast='{}', cleared cache".format(what))
                category = params['category'] if 'category' in params else CATEGORIES[int(_addon.getSetting('scategory'))]
                sort = params['sort'] if 'sort' in params else SORTS[int(_addon.getSetting('ssort'))]
                limit = int(params['limit']) if 'limit' in params else int(_addon.getSetting('slimit'))
                offset = int(params['offset']) if 'offset' in params else 0
                url = get_url(action='search',what=what,category=category,sort=sort,limit=limit,offset=offset)
                xbmc.executebuiltin("Container.Update({})".format(url))
                return
            else:
                log_debug("Search cancelled, clearing slast")
                _addon.setSetting('slast', '')
                updateListing=True
        else:
            log_debug("Skipping dialog, slast='{}' indicates previous interaction".format(slast))

    if what is not None:
        _addon.setSetting('slast', what)

        category = params['category'] if 'category' in params else CATEGORIES[int(_addon.getSetting('scategory'))]
        sort = params['sort'] if 'sort' in params else SORTS[int(_addon.getSetting('ssort'))]
        limit = int(params['limit']) if 'limit' in params else int(_addon.getSetting('slimit'))
        offset = int(params['offset']) if 'offset' in params else 0
        xbmcplugin.setContent(_handle, 'files')
        dosearch(token, what, category, sort, limit, offset, 'search', params)
    else:
        _addon.setSetting('slast', '')
        history = loadsearch()
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30205))
        listitem.setArt({'icon': 'DefaultAddSource.png'})
        xbmcplugin.addDirectoryItem(_handle, 'plugin://plugin.video.yeplaya/?action=newsearch', listitem, False)

        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30208))
        listitem.setArt({'icon': 'DefaultAddonsRecentlyUpdated.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='search',what=NONE_WHAT,sort=SORTS[1]), listitem, True)

        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30209))
        listitem.setArt({'icon': 'DefaultHardDisk.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='search',what=NONE_WHAT,sort=SORTS[3]), listitem, True)

        for s in history:
            listitem = xbmcgui.ListItem(label=s)
            listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
            commands = []
            commands.append(( _addon.getLocalizedString(30213), 'Container.Update(' + get_url(action='search',remove=s) + ')'))
            listitem.addContextMenuItems(commands)
            xbmcplugin.addDirectoryItem(_handle, get_url(action='search',what=s), listitem, True)
    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)


def newsearch(params):
    """Handle new search - show keyboard and navigate to results without creating history entry."""
    what = ask(None)
    if what is not None:
        storesearch(what)
        _addon.setSetting('slast', what)
        clear_cache()
        category = CATEGORIES[int(_addon.getSetting('scategory'))]
        sort = SORTS[int(_addon.getSetting('ssort'))]
        limit = int(_addon.getSetting('slimit'))
        url = get_url(action='search', what=what, category=category, sort=sort, limit=limit, offset=0)
        xbmc.executebuiltin("Container.Update({})".format(url))
