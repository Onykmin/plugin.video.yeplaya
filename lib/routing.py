# -*- coding: utf-8 -*-
# Module: routing
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""URL routing logic."""

import xbmc
from lib.changelog import maybe_show_changelog
from lib.ui import history, settings, menu, info, goto_page
from lib.search_ui import search, newsearch
from lib.series_ui import browse_series, browse_season, browse_other, select_version, select_movie_version, show_random_episode_dialog
from lib.random_movie_ui import show_random_movie_dialog
from lib.playback import play, download, queue
from lib.database import db
from lib.favorites_ui import favorites, add_favorite_action, remove_favorite_action

try:
    from urllib.parse import parse_qsl
except ImportError:
    from urlparse import parse_qsl

def _state_action(params, fn_name):
    """Dispatch a mark_watched / mark_unwatched / clear_resume action."""
    key = params.get('key')
    if not key:
        return
    from lib import state
    getattr(state, fn_name)(key)
    xbmc.executebuiltin('Container.Refresh')


def _toqueue_action(params):
    """RunPlugin side-effect: add a file to the queue, then refresh.

    Invoked via RunPlugin so the side-effect URL never becomes the container
    path (a manual Refresh would otherwise re-queue). Container.Refresh
    re-renders the current listing without the side-effect param.
    """
    ident = params.get('toqueue')
    if not ident:
        return
    from lib.api import revalidate
    from lib.playback import toqueue
    token = revalidate()
    if token is None:
        return
    toqueue(ident, token)
    xbmc.executebuiltin('Container.Refresh')


def _dequeue_action(params):
    """RunPlugin side-effect: remove a file from the queue, then refresh."""
    ident = params.get('dequeue')
    if not ident:
        return
    from lib.playback import dequeue
    dequeue(ident)
    xbmc.executebuiltin('Container.Refresh')


def _remove_search_action(params):
    """RunPlugin side-effect: remove a search-history term, then refresh."""
    what = params.get('remove')
    if not what:
        return
    from lib.cache import removesearch
    removesearch(what)
    xbmc.executebuiltin('Container.Refresh')


def router(paramstring):
    params = dict(parse_qsl(paramstring))
    if params:
        action = params.get('action', '')
        if action == 'search':
            search(params)
        elif action == 'browse_series':
            browse_series(params)
        elif action == 'browse_season':
            browse_season(params)
        elif action == 'select_version':
            select_version(params)
        elif action == 'select_movie_version':
            select_movie_version(params)
        elif action == 'random_episode':
            show_random_episode_dialog(params)
        elif action == 'random_movie':
            show_random_movie_dialog(params)
        elif action == 'browse_other':
            browse_other(params)
        elif action == 'queue':
            queue(params)
        elif action == 'history':
            history(params)
        elif action == 'settings':
            settings(params)
        elif action == 'info':
            info(params)
        elif action == 'play':
            play(params)
        elif action == 'download':
            download(params)
        elif action == 'db':
            db(params)
        elif action == 'goto_page':
            goto_page(params)
        elif action == 'newsearch':
            newsearch(params)
        elif action == 'mark_watched':
            _state_action(params, 'mark_watched')
        elif action == 'mark_unwatched':
            _state_action(params, 'mark_unwatched')
        elif action == 'clear_resume':
            _state_action(params, 'clear_resume')
        elif action == 'toqueue':
            _toqueue_action(params)
        elif action == 'dequeue':
            _dequeue_action(params)
        elif action == 'remove_search':
            _remove_search_action(params)
        elif action == 'favorites':
            favorites(params)
        elif action == 'add_favorite':
            add_favorite_action(params)
        elif action == 'remove_favorite':
            remove_favorite_action(params)
        else:
            menu()
    else:
        menu()
        maybe_show_changelog()

# Start settings monitor

