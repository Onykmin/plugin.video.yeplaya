# -*- coding: utf-8 -*-
# Module: series_ui
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Series browsing, version selection, and movie UI functions."""

import random

import xbmcgui
import xbmcplugin

from lib.api import revalidate
from lib.utils import get_url, popinfo, tolistitem, get_handle, get_addon, set_webshare_id, set_video_info, apply_playback_state
from lib.state import state_key_for, build_mv_state_key, get_states
from lib.keys import normalize_series_key, normalize_movie_key
from lib.parsing import parse_quality_metadata
from lib.cache import get_or_fetch_grouped
from lib.grouping import deduplicate_versions, _safe_size
from lib.metadata import enrich_file_metadata
from lib.logging import log_debug
from lib.playback import toqueue, resolve_and_play
from lib.ui import _build_version_metadata

_handle = get_handle()
_addon = get_addon()


def _resolve_drifted_key(bucket, stored_key, fav_display_name, normalize):
    """Resolve a favorite's (possibly drifted) key to a live grouping bucket key.

    Dual-name detection can emit a different canonical_key from one fetch to
    the next, so a favorite's stored key may be absent from the current
    `bucket` (grouped['series'] or grouped['movies']). Resolution order:

    1. Normalized-key equality — the same identity the favorites/state layers
       use; collapses dual-name prefix drift (e.g. "mestecko|south park" and
       "tucnak|south park" both normalize to "south park").
    2. Case-insensitive EXACT display_name match — last resort for the case
       where the aliases differ so much the normalized keys can't bridge.

    Substring matching is deliberately NOT used: it wrongly conflated sibling
    titles like "Panic" and "Panic at the Disco". Returns the matched live key,
    or the original stored_key if nothing matches.
    """
    if not bucket:
        return stored_key
    target_norm = normalize(stored_key) if stored_key else None
    if target_norm:
        for k in bucket:
            if normalize(k) == target_norm:
                return k
    target_name = (fav_display_name or '').lower()
    if target_name:
        for k, v in bucket.items():
            display = (v.get('display_name') or '').lower()
            if display and display == target_name:
                return k
    return stored_key


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

    # A favorite's stored canonical_key may have drifted out of the current
    # grouping (dual-name detection). Resolve it to a live bucket key via the
    # shared normalized-key / exact-name resolver.
    if grouped and series_name not in grouped.get('series', {}):
        series_name = _resolve_drifted_key(
            grouped.get('series', {}), series_name,
            params.get('fav_display_name'), normalize_series_key)

    if not grouped or series_name not in grouped.get('series', {}):
        popinfo(_addon.getLocalizedString(30431), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(_handle)
        return

    series_data = grouped['series'][series_name]

    if 'true' == _addon.getSetting('random_episode') and series_data.get('total_episodes', 0) > 0:
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30434))
        listitem.setArt({'icon': 'DefaultTVShows.png'})
        listitem.setProperty('IsPlayable', 'true')
        url = get_url(action='random_episode', series=series_name,
                     what=params['what'], category=params.get('category'),
                     sort=params.get('sort'))
        xbmcplugin.addDirectoryItem(_handle, url, listitem, False)

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

            if 'true' == _addon.getSetting('random_episode') and episodes_dict:
                listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30435))
                listitem.setArt({'icon': 'DefaultTVShows.png'})
                listitem.setProperty('IsPlayable', 'true')
                url = get_url(action='random_episode', series=series_name,
                             season=season_num, what=params['what'],
                             category=category, sort=sort_val)
                xbmcplugin.addDirectoryItem(_handle, url, listitem, False)

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
                        'RunPlugin(' + get_url(
                            action='toqueue', toqueue=ep_data['ident']) + ')'
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
                    label = _addon.getLocalizedString(30406).format(ep_num, len(versions))

                    listitem = xbmcgui.ListItem(label=label)
                    listitem.setProperty('IsPlayable', 'true')
                    set_webshare_id(listitem, versions[0]['ident'])
                    if versions[0].get('img'):
                        listitem.setArt({'thumb': versions[0]['img']})

                    ep_state_key = state_key_for({
                        'series_name': series_name,
                        'season': season_num,
                        'episode': ep_num,
                    })
                    state_cmds = apply_playback_state(listitem, ep_state_key)

                    commands = []
                    for v in versions:
                        commands.append((
                            _addon.getLocalizedString(30214),
                            'RunPlugin(' + get_url(
                                action='toqueue', toqueue=v['ident']) + ')'
                        ))
                    commands.extend(state_cmds)
                    listitem.addContextMenuItems(commands)

                    url = get_url(action='select_version', series=series_name,
                                 season=season_num, episode=ep_num,
                                 what=params['what'], category=category,
                                 sort=sort_val)

                    xbmcplugin.addDirectoryItem(_handle, url, listitem, False)

    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)


def _rank_versions(versions):
    """Order versions best-first: file size, then quality score as tiebreak.

    Size-first is deliberate and is the long-standing pick-variant order the
    episode and movie dialogs have always used — biggest file wins, quality
    score only separates equal-size entries. Note this differs from
    grouping._version_sort_key, which ranks quality first; that one feeds the
    grouping/merge passes, not the user-facing pick lists.

    `quality_meta` is populated for EVERY entry before sorting — reading it
    lazily during the sort would silently fall back to the default score of 50
    and produce a garbage tiebreak. Scores come from the filename via
    parse_quality_metadata, so ranking costs no API call.
    """
    for v in versions:
        if 'quality_meta' not in v:
            v['quality_meta'] = parse_quality_metadata(v.get('name', ''))

    versions.sort(
        key=lambda v: (_safe_size(v), v.get('quality_meta', {}).get('quality_score', 50)),
        reverse=True)

    return versions


def _prepare_episode_versions(versions, token):
    """Rank the list best-first, then enrich the top entries.

    Shared by the episode version picker, the movie version picker, and the
    random-episode dialog's "pick version" branch — despite the name, this
    is not episode-exclusive. Expects an already-deduplicated list and
    ranks/sorts it in place, mirroring the pick-variant ordering used by all
    three. Ranking happens BEFORE enrichment so the API budget is spent on
    the five genuinely-best versions rather than whichever five the API
    happened to return first. Enrichment hits the API, so callers only invoke
    this when the user has actually asked to see the version list.
    """
    _rank_versions(versions)

    TOP_FILES_TO_ENRICH = 5
    for idx in range(min(TOP_FILES_TO_ENRICH, len(versions))):
        if 'file_info' not in versions[idx]:
            enrich_file_metadata(versions[idx], versions[idx].get('ident'), token)

    return versions


def _enrich_displayed_version(file_dict, token):
    """Fetch real track metadata for the one version shown on the Play row.

    Only the displayed version is enriched — never the whole list — so the
    cost is a single getinfo per pick. `enrich_file_metadata` already logs
    and swallows its own failures, so a miss just leaves the row rendering
    from filename-parsed `quality_meta`.
    """
    if not file_dict or 'file_info' in file_dict:
        return
    try:
        enrich_file_metadata(file_dict, file_dict.get('ident'), token)
    except Exception as exc:
        log_debug('_enrich_displayed_version failed: {}'.format(exc))


def _build_version_listitems(versions):
    """label = filename, label2 = joined version metadata."""
    listitems = []
    for file_dict in versions:
        label = file_dict.get('name', 'Unknown')
        meta_parts = _build_version_metadata(file_dict)
        listitem = xbmcgui.ListItem(label=label)
        if meta_parts:
            listitem.setLabel2(' | '.join(meta_parts))
        listitems.append(listitem)
    return listitems


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
        # Non-folder/IsPlayable contract: must call setResolvedUrl(False)
        # on every error path or Kodi shows "Couldn't play item" spinner.
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    versions = deduplicate_versions(versions)
    versions = _prepare_episode_versions(versions, token)
    listitems = _build_version_listitems(versions)

    display_name = grouped.get('series', {}).get(series_name, {}).get('display_name', series_name)
    dialog = xbmcgui.Dialog()
    selected = dialog.select(
        '{0} - S{1:02d}E{2:02d}'.format(display_name, season_num, episode_num),
        listitems, useDetails=True)

    if selected >= 0:
        chosen_file = versions[selected]
        ep_state_key = state_key_for({
            'series_name': series_name,
            'season': season_num,
            'episode': episode_num,
        })
        resolve_and_play(chosen_file['ident'], chosen_file['name'], token, state_key=ep_state_key)
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

    # Drifted canonical_key fallback — see browse_series for context.
    if grouped and movie_key not in grouped.get('movies', {}):
        movie_key = _resolve_drifted_key(
            grouped.get('movies', {}), movie_key,
            params.get('fav_display_name'), normalize_movie_key)

    if not grouped or movie_key not in grouped.get('movies', {}):
        xbmcgui.Dialog().ok(_addon.getLocalizedString(30407), _addon.getLocalizedString(30409))
        # Non-folder/IsPlayable contract: setResolvedUrl(False) on error.
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    movie_data = grouped['movies'][movie_key]
    versions = movie_data['versions']
    display_name = f"{movie_data['display_name']} ({movie_data['year']})"

    versions = deduplicate_versions(versions)
    versions = _prepare_episode_versions(versions, token)

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
        state_key = build_mv_state_key(movie_key)
        resolve_and_play(selected_version['ident'], selected_version['name'], token, state_key=state_key)
    else:
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())


def _flatten_episode_keys(series_data, season_num=None):
    """[(season, episode), ...] for every episode with at least one version.

    Optionally restricted to a single season. Episodes that parsed but ended
    up with an empty version list are skipped — they are not selectable.
    """
    keys = []
    for s_num, episodes_dict in series_data.get('seasons', {}).items():
        if season_num is not None and s_num != season_num:
            continue
        for ep_num, versions in episodes_dict.items():
            if versions:
                keys.append((s_num, ep_num))
    return sorted(keys)


def _pick_random(all_keys, excluded):
    """Pick a uniformly-random unseen key. Returns (key, exhausted).

    Uniform over the flattened episode list, so every episode is equally
    likely regardless of how many episodes its season has. Never mutates
    `excluded` and never auto-resets it — the caller decides whether to
    offer "Start over" (see show_random_episode_dialog).
    """
    remaining = [k for k in all_keys if k not in excluded]
    if not remaining:
        return None, True
    return random.choice(remaining), False


def _build_dialog_rows(best, season_num, ep_num, pool_state, version_count):
    """Assemble the dialog rows plus the parallel action list.

    Returns (listitems, actions) where actions[i] names what selecting row i
    does, so row order and dispatch can never drift apart.
    """
    listitems = []
    actions = []

    label = 'S{0:02d}E{1:02d} - {2}'.format(season_num, ep_num, best.get('name', 'Unknown'))
    play_item = xbmcgui.ListItem(label=label)
    meta_parts = _build_version_metadata(best)
    if meta_parts:
        play_item.setLabel2(' | '.join(meta_parts))
    listitems.append(play_item)
    actions.append('play')

    if version_count > 1:
        listitems.append(xbmcgui.ListItem(label=_addon.getLocalizedString(30443).format(version_count)))
        actions.append('pick_version')

    if pool_state == 'reroll':
        listitems.append(xbmcgui.ListItem(label=_addon.getLocalizedString(30437)))
        actions.append('reroll')
    elif pool_state == 'start_over':
        start_over_item = xbmcgui.ListItem(label=_addon.getLocalizedString(30442))
        start_over_item.setLabel2(_addon.getLocalizedString(30441))
        listitems.append(start_over_item)
        actions.append('start_over')

    listitems.append(xbmcgui.ListItem(label=_addon.getLocalizedString(30438)))
    actions.append('cancel')

    return listitems, actions


def show_random_episode_dialog(params):
    """Pick a random episode and offer Play / Reroll / Cancel in one dialog.

    Series-wide when no `season` param is present, otherwise restricted to
    that season. Repeat avoidance is an in-memory exclusion set living only
    for this loop (one Kodi menu action = one process), so backing out and
    re-entering deliberately starts fresh.
    """
    log_debug('show_random_episode_dialog called with params: {}'.format(params))
    token = revalidate()

    series_name = params.get('series')
    if not series_name:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    try:
        season_num = int(params['season']) if 'season' in params else None
    except (ValueError, TypeError, KeyError):
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    cache_key, grouped = get_or_fetch_grouped(params, token, check_key=series_name, check_type='series')

    if not grouped or series_name not in grouped.get('series', {}):
        popinfo(_addon.getLocalizedString(30431), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    series_data = grouped['series'][series_name]
    display_name = series_data.get('display_name') or series_name

    all_keys = _flatten_episode_keys(series_data, season_num)
    if not all_keys:
        popinfo(_addon.getLocalizedString(30440), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    excluded = set()
    last_pick = None
    shown_best = shown_season = shown_ep = None
    shown_versions = None

    while True:
        picked, exhausted = _pick_random(all_keys, excluded)
        if exhausted:
            # Nothing was ever displayable — every key's version list turned
            # out empty. Bail like the pool==0 case instead of looping on a
            # Start over that can never produce anything.
            if shown_best is None:
                popinfo(_addon.getLocalizedString(30440), icon=xbmcgui.NOTIFICATION_WARNING)
                xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
                return
            # Keep the current pick on screen, but swap Reroll -> Start over
            # so clearing the exclusion set is an explicit user choice.
            pool_state = 'start_over'
        else:
            s_num, e_num = picked
            excluded.add(picked)
            last_pick = picked
            versions = deduplicate_versions(series_data['seasons'][s_num][e_num])
            if not versions:
                popinfo(_addon.getLocalizedString(30440), icon=xbmcgui.NOTIFICATION_WARNING)
                continue
            # deduplicate_versions preserves API order and does not rank, so
            # [0] would otherwise be arbitrary — rank (filename-based, no API
            # call) before picking the Play row's version.
            _rank_versions(versions)
            shown_versions = versions
            shown_best, shown_season, shown_ep = versions[0], s_num, e_num
            # Enrich just the displayed version so the Play row's label2 shows
            # real audio/subtitle tracks (lib/ui.py gates those on file_info).
            # One getinfo per pick; the inner redraw loop never re-enriches.
            _enrich_displayed_version(shown_best, token)
            pool_state = 'reroll' if len(all_keys) > 1 else 'none'

        # Inner redraw loop: lets the user open the version picker for the
        # CURRENT pick and come back to the same episode on back-out, without
        # re-entering the outer pick loop (which would draw a new episode).
        while True:
            version_count = len(shown_versions)
            listitems, actions = _build_dialog_rows(
                shown_best, shown_season, shown_ep, pool_state, version_count)
            selected = xbmcgui.Dialog().select(display_name, listitems, useDetails=True)
            action = actions[selected] if 0 <= selected < len(actions) else 'cancel'

            if action == 'play':
                ep_state_key = state_key_for({
                    'series_name': series_name,
                    'season': shown_season,
                    'episode': shown_ep,
                })
                resolve_and_play(shown_best['ident'], shown_best['name'], token, state_key=ep_state_key)
                return

            if action == 'pick_version':
                ordered = _prepare_episode_versions(list(shown_versions), token)
                version_listitems = _build_version_listitems(ordered)
                heading = '{0} - S{1:02d}E{2:02d}'.format(display_name, shown_season, shown_ep)
                version_selected = xbmcgui.Dialog().select(heading, version_listitems, useDetails=True)
                if version_selected >= 0:
                    chosen = ordered[version_selected]
                    ep_state_key = state_key_for({
                        'series_name': series_name,
                        'season': shown_season,
                        'episode': shown_ep,
                    })
                    resolve_and_play(chosen['ident'], chosen['name'], token, state_key=ep_state_key)
                    return
                # Backed out of the picker — redraw the same episode's rows,
                # no setResolvedUrl (we haven't resolved anything yet).
                continue

            if action == 'reroll':
                break
            if action == 'start_over':
                excluded.clear()
                if last_pick is not None:
                    excluded.add(last_pick)
                break

            xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
            return


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

        # Prime playback state for all movie rows in one batched query so
        # per-row apply_playback_state hits the in-memory cache (one SELECT
        # instead of one per movie).
        get_states([build_mv_state_key(k) for k in grouped['movies'].keys()])

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

            state_key = build_mv_state_key(canonical_key)
            state_cmds = apply_playback_state(listitem, state_key)
            if state_cmds:
                listitem.addContextMenuItems(state_cmds)
            if len(versions) == 1:
                listitem.setProperty('IsPlayable', 'true')
                set_webshare_id(listitem, versions[0]['ident'])
                url = get_url(action='play', ident=versions[0]['ident'],
                             name=versions[0]['name'], movie_key=canonical_key)
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
