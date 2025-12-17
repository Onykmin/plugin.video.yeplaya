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
            xbmc.log("YAWsP: Invalid arguments", xbmc.LOGERROR)
    except Exception as e:
        xbmc.log("YAWsP fatal error: " + str(e), xbmc.LOGERROR)
        traceback.print_exc()
