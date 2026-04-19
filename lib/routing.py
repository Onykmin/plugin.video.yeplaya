# -*- coding: utf-8 -*-
# Module: routing
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""URL routing logic."""

import xbmc
from lib.ui import history, settings, menu, info, goto_page
from lib.search_ui import search, newsearch
from lib.series_ui import browse_series, browse_season, browse_other, select_version, select_movie_version
from lib.playback import play, download, queue
from lib.database import db

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


def router(paramstring):
    params = dict(parse_qsl(paramstring))
    if params:
        if params['action'] == 'search':
            search(params)
        elif params['action'] == 'browse_series':
            browse_series(params)
        elif params['action'] == 'browse_season':
            browse_season(params)
        elif params['action'] == 'select_version':
            select_version(params)
        elif params['action'] == 'select_movie_version':
            select_movie_version(params)
        elif params['action'] == 'browse_other':
            browse_other(params)
        elif params['action'] == 'queue':
            queue(params)
        elif params['action'] == 'history':
            history(params)
        elif params['action'] == 'settings':
            settings(params)
        elif params['action'] == 'info':
            info(params)
        elif params['action'] == 'play':
            play(params)
        elif params['action'] == 'download':
            download(params)
        elif params['action'] == 'db':
            db(params)
        elif params['action'] == 'goto_page':
            goto_page(params)
        elif params['action'] == 'newsearch':
            newsearch(params)
        elif params['action'] == 'mark_watched':
            _state_action(params, 'mark_watched')
        elif params['action'] == 'mark_unwatched':
            _state_action(params, 'mark_unwatched')
        elif params['action'] == 'clear_resume':
            _state_action(params, 'clear_resume')
        else:
            menu()
    else:
        menu()

# Start settings monitor

