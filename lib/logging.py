# -*- coding: utf-8 -*-
# Module: logging
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import xbmc


def log_debug(message):
    """Log debug message."""
    xbmc.log("yeplaya [DEBUG]: " + str(message), xbmc.LOGDEBUG)


def log_warning(message):
    """Log warning message."""
    xbmc.log("yeplaya [WARNING]: " + str(message), xbmc.LOGWARNING)


def log_error(message):
    """Log error message."""
    xbmc.log("yeplaya [ERROR]: " + str(message), xbmc.LOGERROR)
