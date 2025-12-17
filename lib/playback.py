# -*- coding: utf-8 -*-
# Module: playback
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Playback, download, and queue operations."""

import os
import io
import re
import xbmc
import xbmcvfs
import requests
import xbmcgui
import xbmcplugin
from lib.api import revalidate, getlink, api, parse_xml, is_ok, get_session, get_addon, validate_ident, getinfo
from lib.utils import popinfo, todict, sizelize, get_handle, get_url, tolistitem

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

try:
    from xbmcvfs import translatePath
except ImportError:
    from xbmc import translatePath


try:
    from unidecode import unidecode
except ImportError:
    import unicodedata
    def unidecode(text):
        normalized = unicodedata.normalize('NFKD', text)
        return ''.join([c for c in normalized if not unicodedata.combining(c)])

_handle = get_handle()
_addon = get_addon()
_session = get_session()

def play(params):
    token = revalidate()
    if 'ident' not in params:
        xbmc.log("YAWsP: Missing ident in play", xbmc.LOGERROR)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return
    link = getlink(params['ident'],token)
    if link is not None:
        #headers experiment
        headers = _session.headers
        if headers:
            headers.update({'Cookie':'wst='+token})
            link = link + '|' + urlencode(headers)
        listitem = xbmcgui.ListItem(label=params['name'],path=link)
        listitem.setProperty('mimetype', 'application/octet-stream')
        xbmcplugin.setResolvedUrl(_handle, True, listitem)
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())


def join(path, file):
    if path.endswith('/') or path.endswith('\\'):
        return path + file
    else:
        return path + '/' + file


def download(params):
    token = revalidate()
    if 'ident' not in params:
        xbmc.log("YAWsP: Missing ident in download", xbmc.LOGERROR)
        return
    where = _addon.getSetting('dfolder')
    if not where or not xbmcvfs.exists(where):
        popinfo(_addon.getLocalizedString(30413), sound=True)
        _addon.openSettings()
        return
        
    local = os.path.exists(where)
        
    normalize = 'true' == _addon.getSetting('dnormalize')
    notify = 'true' == _addon.getSetting('dnotify')
    every = _addon.getSetting('dnevery')
    try:
        every = int(re.sub(r'[^\d]+', '', every))
    except (ValueError, TypeError):
        every = 10
        
    try:
        link = getlink(params['ident'],token,'file_download')
        info = getinfo(params['ident'],token)
        name = info.find('name').text
        # Sanitize filename - remove path separators and parent references
        name = os.path.basename(name.replace('..', '').replace('/', '_').replace('\\', '_'))
        if normalize:
            name = unidecode(name)
        bf = io.open(os.path.join(where,name), 'wb') if local else xbmcvfs.File(join(where,name), 'w')
        response = _session.get(link, stream=True, timeout=60)
        total = response.headers.get('content-length')
        if total is None:
            popinfo(_addon.getLocalizedString(30301) + name, icon=xbmcgui.NOTIFICATION_WARNING, sound=True)
            bf.write(response.content)
        elif not notify:
            popinfo(_addon.getLocalizedString(30302) + name)
            bf.write(response.content)
        else:
            popinfo(_addon.getLocalizedString(30302) + name)
            dl = 0
            total = int(total)
            pct = total / 100
            lastpop=0
            for data in response.iter_content(chunk_size=4096):
                dl += len(data)
                bf.write(data)
                done = int(dl / pct)
                if done % every == 0 and lastpop != done:
                    popinfo(str(done) + '% - ' + name)
                    lastpop = done
        bf.close()
        popinfo(_addon.getLocalizedString(30303) + name, sound=True)
    except (IOError, OSError, requests.exceptions.RequestException) as e:
        #TODO - remove unfinished file?
        xbmc.log("YAWsP: Download failed: " + str(e), xbmc.LOGERROR)
        popinfo(_addon.getLocalizedString(30304) + name, icon=xbmcgui.NOTIFICATION_ERROR, sound=True)


def queue(params):
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \\ " + _addon.getLocalizedString(30202))
    xbmcplugin.setContent(_handle, 'files')
    token = revalidate()
    updateListing=False
    
    if 'dequeue' in params:
        response = api('dequeue_file',{'ident':params['dequeue'],'wst':token})
        if response is None:
            popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
            updateListing=True
        else:
            xml = parse_xml(response.content)
            if is_ok(xml):
                popinfo(_addon.getLocalizedString(30106))
            else:
                popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
            updateListing=True
    
    response = api('queue',{'wst':token})
    if response is None:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
    else:
        xml = parse_xml(response.content)
        if is_ok(xml):
            for file in xml.iter('file'):
                item = todict(file)
                commands = []
                commands.append(( _addon.getLocalizedString(30215), 'Container.Update(' + get_url(action='queue',dequeue=item['ident']) + ')'))
                listitem = tolistitem(item,commands)
                xbmcplugin.addDirectoryItem(_handle, get_url(action='play',ident=item['ident'],name=item['name']), listitem, False)
        else:
            popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
    xbmcplugin.endOfDirectory(_handle,updateListing=updateListing)


def toqueue(ident,token):
    if not validate_ident(ident):
        xbmc.log("YAWsP: Invalid ident in toqueue", xbmc.LOGERROR)
        return
    response = api('queue_file',{'ident':ident,'wst':token})
    if response is None:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        return
    xml = parse_xml(response.content)
    if is_ok(xml):
        popinfo(_addon.getLocalizedString(30105))
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)

