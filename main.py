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
            xbmcgui.Dialog().notification(
                'yeplaya', str(e), xbmcgui.NOTIFICATION_ERROR)
        except Exception:
            pass
        try:
            import xbmcplugin
            handle = int(sys.argv[1])
            # Directory handlers are what predominantly reach here (play() wraps
            # its own body), so end the directory as failed to clear the spinner.
            xbmcplugin.endOfDirectory(handle, succeeded=False)
        except Exception:
            pass
