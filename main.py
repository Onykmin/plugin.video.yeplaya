# -*- coding: utf-8 -*-
# Module: default
# Author: cache
# Created on: 10.5.2020
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import sys
import xbmc
import traceback

# Import from modular lib structure
from lib.routing import router

if __name__ == '__main__':
    try:
        if len(sys.argv) > 2:
            router(sys.argv[2][1:])
        else:
            xbmc.log("yeplaya: Invalid arguments", xbmc.LOGERROR)
    except Exception as e:
        xbmc.log("yeplaya fatal error: " + str(e), xbmc.LOGERROR)
        traceback.print_exc()
        # Last-resort recovery for exceptions a handler didn't catch itself:
        # close the directory handle so Kodi doesn't hang on a spinner, and tell
        # the user. Every step is guarded — the failure path must never raise.
        try:
            import xbmcgui
        except Exception:
            xbmcgui = None
        if xbmcgui is not None:
            try:
                xbmcgui.Dialog().notification(
                    'yeplaya', str(e), xbmcgui.NOTIFICATION_ERROR)
            except Exception:
                pass
        try:
            import xbmcplugin
            try:
                from urllib.parse import parse_qsl
            except ImportError:
                from urlparse import parse_qsl
            handle = int(sys.argv[1])
            # Close with the primitive that matches how the handle was opened:
            # playable/resolve actions need setResolvedUrl(False); directory
            # actions need endOfDirectory(False). Calling the wrong one leaves
            # the spinner up, so derive the action from the plugin URL rather
            # than guessing. Unknown/blank action → treat as a directory.
            action = dict(parse_qsl(sys.argv[2][1:])).get('action', '') \
                if len(sys.argv) > 2 else ''
            _RESOLVE_ACTIONS = {'play', 'select_version', 'select_movie_version',
                                'newsearch'}
            if action in _RESOLVE_ACTIONS:
                xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
            else:
                xbmcplugin.endOfDirectory(handle, succeeded=False)
        except Exception:
            pass
