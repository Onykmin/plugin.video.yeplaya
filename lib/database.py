# -*- coding: utf-8 -*-
# Module: database
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Database download and extraction."""

import os
import io
import json
import zipfile
import requests
import xbmc
import xbmcgui
import xbmcplugin
from lib.api import getlink, revalidate, get_addon, get_session
from lib.utils import popinfo, get_handle, get_url, tolistitem
from lib.playback import toqueue

try:
    from xbmcvfs import translatePath
except ImportError:
    from xbmc import translatePath

_addon = get_addon()
_profile = translatePath(_addon.getAddonInfo('profile'))
try:
    _profile = _profile.decode("utf-8")
except (AttributeError, UnicodeDecodeError):
    pass
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
        xbmc.log("YAWsP: Failed to load database: " + str(e), xbmc.LOGERROR)
        return {}


def safe_extract_zip(zip_path, extract_to):
    """Safely extract ZIP file with path traversal protection."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Validate all file paths before extraction
            for member in zf.namelist():
                # Normalize path and check for path traversal
                member_path = os.path.normpath(os.path.join(extract_to, member))
                if not member_path.startswith(os.path.abspath(extract_to)):
                    xbmc.log("YAWsP: Potential path traversal in ZIP: " + member, xbmc.LOGERROR)
                    return False
                # Check for absolute paths
                if os.path.isabs(member):
                    xbmc.log("YAWsP: Absolute path in ZIP: " + member, xbmc.LOGERROR)
                    return False
            # All paths validated, proceed with extraction
            zf.extractall(extract_to)
            return True
    except zipfile.BadZipFile as e:
        xbmc.log("YAWsP: Invalid ZIP file: " + str(e), xbmc.LOGERROR)
        return False
    except Exception as e:
        xbmc.log("YAWsP: ZIP extraction failed: " + str(e), xbmc.LOGERROR)
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
            popinfo("Failed to get database download link", icon=xbmcgui.NOTIFICATION_ERROR)
            return
        dbfile = os.path.join(_profile,'db.zip')
        try:
            with io.open(dbfile, 'wb') as bf:
                response = _session.get(link, stream=True, timeout=60)
                response.raise_for_status()
                bf.write(response.content)
                bf.flush()
                bf.close()
        except (IOError, OSError, requests.exceptions.RequestException) as e:
            xbmc.log("YAWsP: Failed to download database: " + str(e), xbmc.LOGERROR)
            popinfo("Failed to download database", icon=xbmcgui.NOTIFICATION_ERROR)
            if os.path.exists(dbfile):
                os.unlink(dbfile)
            return

        # Safely extract with validation
        if not safe_extract_zip(dbfile, _profile):
            popinfo("Failed to extract database", icon=xbmcgui.NOTIFICATION_ERROR)
            os.unlink(dbfile)
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
                listitem.setInfo('video', {'title': item['title'],'plot': item['plot']})
            xbmcplugin.addDirectoryItem(_handle, get_url(action='db',file=params['file'],key=item['id']), listitem, True)
    else:
        if os.path.exists(dbdir):
            dbfiles = [f for f in os.listdir(dbdir) if os.path.isfile(os.path.join(dbdir, f))]
            for dbfile in dbfiles:
                listitem = xbmcgui.ListItem(label=os.path.splitext(dbfile)[0])
                xbmcplugin.addDirectoryItem(_handle, get_url(action='db',file=dbfile), listitem, True)
    xbmcplugin.addSortMethod(_handle,xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)

