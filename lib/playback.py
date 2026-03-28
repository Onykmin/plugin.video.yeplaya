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
from lib.player import YePlayer
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


def resolve_and_play(ident, name, token):
    """Get stream link, attach headers, resolve URL and wait for playback.

    Returns True on success, False on failure. Calls setResolvedUrl internally.
    """
    from lib.player import YePlayer
    link = getlink(ident, token)
    if link is not None:
        headers = dict(_session.headers) if _session and hasattr(_session, 'headers') else None
        if headers:
            headers['Cookie'] = 'wst=' + token
            link = link + '|' + urlencode(headers)
        player = YePlayer()
        listitem = xbmcgui.ListItem(label=name, path=link)
        listitem.setProperty('mimetype', 'application/octet-stream')
        xbmcplugin.setResolvedUrl(_handle, True, listitem)
        player.wait_for_playback()
        return True
    else:
        popinfo(_addon.getLocalizedString(30308), icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return False

def play(params):
    try:
        token = revalidate()
        if token is None:
            popinfo(_addon.getLocalizedString(30102), icon=xbmcgui.NOTIFICATION_ERROR)
            xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
            return
        if 'ident' not in params:
            xbmc.log("YAWsP: Missing ident in play", xbmc.LOGERROR)
            xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
            return
        resolve_and_play(params['ident'], params['name'], token)
    except requests.exceptions.RequestException as e:
        xbmc.log("YAWsP: Network error in play: " + str(e), xbmc.LOGERROR)
        popinfo(_addon.getLocalizedString(30305), icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
    except Exception as e:
        xbmc.log("YAWsP: Playback error: " + str(e), xbmc.LOGERROR)
        popinfo(_addon.getLocalizedString(30306), icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())


def join(path, file):
    if path.endswith('/') or path.endswith('\\'):
        return path + file
    else:
        return path + '/' + file


_WINDOWS_RESERVED = frozenset(['CON', 'PRN', 'AUX', 'NUL'] +
    ['COM%d' % i for i in range(1, 10)] + ['LPT%d' % i for i in range(1, 10)])


def _sanitize_filename(name):
    """Sanitize filename: strip path components, control chars, reserved names."""
    # Strip null bytes and control characters
    name = re.sub(r'[\x00-\x1f]', '', name)
    # Remove path separators and parent references
    name = name.replace('..', '').replace('/', '_').replace('\\', '_')
    name = os.path.basename(name)
    # Remove Windows-reserved characters
    name = re.sub(r'[<>:"|?*]', '', name)
    # Check Windows reserved names
    stem = name.split('.')[0].upper()
    if stem in _WINDOWS_RESERVED:
        name = '_' + name
    return name.strip() or 'download'


def _unique_path(filepath):
    """Return filepath with numeric suffix if file already exists."""
    if not os.path.exists(filepath):
        return filepath
    base, ext = os.path.splitext(filepath)
    counter = 1
    while os.path.exists('{}_{}{}'.format(base, counter, ext)):
        counter += 1
    return '{}_{}{}'.format(base, counter, ext)


_active_downloads = set()
_download_lock = __import__('threading').Lock()


def download(params):
    token = revalidate()
    if 'ident' not in params:
        xbmc.log("YAWsP: Missing ident in download", xbmc.LOGERROR)
        return

    ident = params['ident']
    with _download_lock:
        if ident in _active_downloads:
            xbmc.log("YAWsP: Download already in progress: " + ident, xbmc.LOGWARNING)
            return
        _active_downloads.add(ident)

    try:
        _do_download(params, token)
    finally:
        with _download_lock:
            _active_downloads.discard(ident)


def _do_download(params, token):
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

    name = None
    filepath = None
    bf = None
    try:
        link = getlink(params['ident'],token,'file_download')
        if link is None:
            popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING, sound=True)
            return
        info = getinfo(params['ident'],token)
        if info is None:
            popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING, sound=True)
            return
        name_elem = info.find('name')
        if name_elem is None or name_elem.text is None:
            popinfo(_addon.getLocalizedString(30307), icon=xbmcgui.NOTIFICATION_ERROR, sound=True)
            return
        name = _sanitize_filename(name_elem.text)
        if normalize:
            normalized = unidecode(name)
            if not normalized or not normalized.strip():
                name = params.get('ident', 'download') + os.path.splitext(name)[1]
            else:
                name = normalized

        # Resolve filename collisions (local only)
        if local:
            filepath = _unique_path(os.path.join(where, name))
            name = os.path.basename(filepath)

        # Check for existing partial download (resume support, local only)
        dl = 0
        req_headers = {}
        if local and filepath and os.path.exists(filepath + '.part'):
            dl = os.path.getsize(filepath + '.part')
            req_headers['Range'] = 'bytes={}-'.format(dl)

        response = _session.get(link, stream=True, timeout=60, headers=req_headers)
        total = response.headers.get('content-length')

        # If server returned 206 Partial Content, we're resuming
        resuming = response.status_code == 206
        if total is not None:
            total = int(total) + (dl if resuming else 0)

        popinfo(_addon.getLocalizedString(30302) + name)

        if total is not None and total > 0:
            pct = total / 100
        else:
            total = None
            pct = 1

        # Write to .part file first, rename on completion
        if local:
            write_path = filepath + '.part'
            bf = io.open(write_path, 'ab' if resuming else 'wb')
        else:
            write_path = join(where, name)
            bf = xbmcvfs.File(write_path, 'w')

        lastpop = 0
        for data in response.iter_content(chunk_size=4096):
            dl += len(data)
            bf.write(data)
            if notify:
                if total is not None:
                    done = int(dl / pct)
                else:
                    done = dl // (1024 * 1024)
                if done % every == 0 and lastpop != done:
                    if total is not None:
                        popinfo(str(done) + '% - ' + name)
                    else:
                        popinfo(str(done) + 'MB - ' + name)
                    lastpop = done
        bf.close()
        bf = None

        # Rename .part to final name on success (local only)
        if local and filepath:
            os.rename(filepath + '.part', filepath)

        popinfo(_addon.getLocalizedString(30303) + name, sound=True)
    except (IOError, OSError, requests.exceptions.RequestException) as e:
        xbmc.log("YAWsP: Download failed: " + str(e), xbmc.LOGERROR)
        err_name = name if name else 'file'
        popinfo(_addon.getLocalizedString(30304) + err_name, icon=xbmcgui.NOTIFICATION_ERROR, sound=True)
    finally:
        if bf is not None:
            try:
                bf.close()
            except Exception:
                pass


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

