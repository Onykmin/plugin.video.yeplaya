# -*- coding: utf-8 -*-
# Module: database
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Database download and extraction."""

import os
import io
import json
import shutil
import zipfile
import requests
import xbmc
import xbmcgui
import xbmcplugin
from lib.api import getlink, revalidate, get_addon, get_session
from lib.utils import popinfo, get_handle, get_url, tolistitem, set_video_info
from lib.playback import toqueue

try:
    from xbmcvfs import translatePath
except ImportError:
    from xbmc import translatePath

_addon = get_addon()
_profile = translatePath(_addon.getAddonInfo('profile'))
_session = get_session()

from lib.logging import log_warning

_handle = get_handle()

BACKUP_DB = 'D1iIcURxlR'

def loaddb(dbdir,file):
    try:
        data = {}
        with io.open(os.path.join(dbdir, file), 'r', encoding='utf8') as file:
            fdata = file.read()
            file.close()
            data = json.loads(fdata)['data']
        return data
    except (IOError, OSError, ValueError, KeyError) as e:
        xbmc.log("yeplaya: Failed to load database: " + str(e), xbmc.LOGERROR)
        return {}


def safe_extract_zip(zip_path, extract_to):
    """Safely extract ZIP file with path traversal protection."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            base = os.path.abspath(extract_to)
            # Validate all file paths before extraction
            for member in zf.namelist():
                # Normalize path and check for path traversal. Compare against
                # base + separator (not a bare prefix): a plain startswith lets
                # a sibling like ".../profile-evil" pass ".../profile".
                member_path = os.path.normpath(os.path.join(base, member))
                if member_path != base and not member_path.startswith(base + os.sep):
                    xbmc.log("yeplaya: Potential path traversal in ZIP: " + member, xbmc.LOGERROR)
                    return False
                # Check for absolute paths
                if os.path.isabs(member):
                    xbmc.log("yeplaya: Absolute path in ZIP: " + member, xbmc.LOGERROR)
                    return False
            # All paths validated, proceed with extraction
            zf.extractall(extract_to)
            return True
    except zipfile.BadZipFile as e:
        xbmc.log("yeplaya: Invalid ZIP file: " + str(e), xbmc.LOGERROR)
        return False
    except Exception as e:
        xbmc.log("yeplaya: ZIP extraction failed: " + str(e), xbmc.LOGERROR)
        return False


def db(params):
    token = revalidate()
    updateListing=False

    # Experimental feature warning
    log_warning("Experimental database feature accessed - use at your own risk")

    dbdir = os.path.join(_profile,'db')
    if not os.path.exists(dbdir):
        link = getlink(BACKUP_DB,token)
        if link is None:
            popinfo(_addon.getLocalizedString(30309), icon=xbmcgui.NOTIFICATION_ERROR)
            xbmcplugin.endOfDirectory(_handle, succeeded=False)
            return
        dbfile = os.path.join(_profile,'db.zip')
        try:
            with io.open(dbfile, 'wb') as bf:
                response = _session.get(link, stream=True, timeout=60)
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=4096):
                    bf.write(chunk)
                bf.flush()
                bf.close()
        except (IOError, OSError, requests.exceptions.RequestException) as e:
            xbmc.log("yeplaya: Failed to download database: " + str(e), xbmc.LOGERROR)
            popinfo(_addon.getLocalizedString(30310), icon=xbmcgui.NOTIFICATION_ERROR)
            if os.path.exists(dbfile):
                os.unlink(dbfile)
            xbmcplugin.endOfDirectory(_handle, succeeded=False)
            return

        # Safely extract with validation
        if not safe_extract_zip(dbfile, _profile):
            popinfo(_addon.getLocalizedString(30311), icon=xbmcgui.NOTIFICATION_ERROR)
            os.unlink(dbfile)
            # Remove any partially-extracted db dir so the next run re-downloads
            # rather than treating a bricked partial extract as installed.
            if os.path.isdir(dbdir):
                shutil.rmtree(dbdir, ignore_errors=True)
            xbmcplugin.endOfDirectory(_handle, succeeded=False)
            return
        os.unlink(dbfile)
    
    if 'toqueue' in params:
        toqueue(params['toqueue'],token)
        updateListing=True
    
    if 'file' in params and 'key' in params:
        # Sanitize filename to prevent path traversal
        filename = os.path.basename(params['file'])
        data = loaddb(dbdir,filename)
        item = next((x for x in data if x['id'] == params['key']), None)
        if item is not None:
            for stream in item['streams']:
                commands = []
                commands.append(( _addon.getLocalizedString(30214), 'Container.Update(' + get_url(action='db',file=params['file'],key=params['key'],toqueue=stream['ident']) + ')'))
                listitem = tolistitem({'ident':stream['ident'],'name':stream['quality'] + ' - ' + stream['lang'] + stream['ainfo'],'sizelized':stream['size']},commands)
                xbmcplugin.addDirectoryItem(_handle, get_url(action='play',ident=stream['ident'],name=item['title']), listitem, False)
    elif 'file' in params:
        # Sanitize filename to prevent path traversal
        filename = os.path.basename(params['file'])
        data = loaddb(dbdir,filename)
        for item in data:
            listitem = xbmcgui.ListItem(label=item['title'])
            if 'plot' in item:
                set_video_info(listitem, {'title': item['title'], 'plot': item['plot']})
            xbmcplugin.addDirectoryItem(_handle, get_url(action='db',file=params['file'],key=item['id']), listitem, True)
    else:
        if os.path.exists(dbdir):
            dbfiles = [f for f in os.listdir(dbdir) if os.path.isfile(os.path.join(dbdir, f))]
            for dbfile in dbfiles:
                listitem = xbmcgui.ListItem(label=os.path.splitext(dbfile)[0])
                xbmcplugin.addDirectoryItem(_handle, get_url(action='db',file=dbfile), listitem, True)
        else:
            # DB dir missing (download/extract never completed) — tell the user
            # instead of rendering a silent empty directory.
            popinfo(_addon.getLocalizedString(30311), icon=xbmcgui.NOTIFICATION_ERROR)
    xbmcplugin.addSortMethod(_handle,xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)

