# -*- coding: utf-8 -*-
# Module: ui
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""UI core: shared state, helpers, menu, history, settings, info."""

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon

from lib.api import api, parse_xml, is_ok, revalidate, getinfo, refresh_addon
from lib.utils import todict, get_url, popinfo, tolistitem, sizelize, infonize, fpsize, get_handle, get_addon, refresh_settings
from lib.cache import clear_cache
from lib.logging import log_debug

_handle = get_handle()
_addon = get_addon()

from lib.playback import toqueue

# Constants
NONE_WHAT = '%#NONE#%'
CATEGORIES = ['','video','images','audio','archives','docs','adult']
SORTS = ['','recent','rating','largest','smallest']


def _build_version_metadata(file_dict):
    """Build metadata label parts for a file version dialog entry."""
    quality_meta = file_dict.get('quality_meta', {})
    file_info = file_dict.get('file_info', {})
    meta_parts = []

    resolution = file_info.get('resolution')
    if resolution:
        meta_parts.append(resolution)
    elif quality_meta.get('quality'):
        meta_parts.append(quality_meta['quality'])

    if quality_meta.get('source'):
        meta_parts.append(quality_meta['source'])

    codec = file_info.get('video_codec') or quality_meta.get('codec')
    if codec:
        meta_parts.append(codec)

    audio = file_info.get('audio')
    if audio:
        meta_parts.append('Audio: {0}'.format(audio))
    elif quality_meta.get('audio'):
        meta_parts.append(quality_meta['audio'])

    if file_info.get('subtitles'):
        meta_parts.append('Subs: {0}'.format(file_info['subtitles']))

    if not file_info and file_dict.get('language'):
        meta_parts.append('[{0}]'.format(file_dict['language']))

    if file_dict.get('size'):
        meta_parts.append(sizelize(file_dict['size']))

    return meta_parts


def history(params):
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \\ " + _addon.getLocalizedString(30203))
    xbmcplugin.setContent(_handle, 'files')
    token = revalidate()
    updateListing=False

    if 'remove' in params:
        remove = params['remove']
        updateListing=True
        response = api('history',{'wst':token})
        if response is not None:
            xml = parse_xml(response.content)
            ids = []
            if is_ok(xml):
                for file in xml.iter('file'):
                    if remove == file.find('ident').text:
                        ids.append(file.find('download_id').text)
            else:
                popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
            if ids:
                rr = api('clear_history',{'ids[]':ids,'wst':token})
                if rr is None:
                    popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
                else:
                    xml = parse_xml(rr.content)
                    if is_ok(xml):
                        popinfo(_addon.getLocalizedString(30104))
                    else:
                        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)

    if 'toqueue' in params:
        toqueue(params['toqueue'],token)
        updateListing=True

    response = api('history',{'wst':token})
    if response is None:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
    else:
        xml = parse_xml(response.content)
        files = []
        if is_ok(xml):
            for file in xml.iter('file'):
                item = todict(file, ['ended_at', 'download_id', 'started_at'])
                if item not in files:
                    files.append(item)
            for file in files:
                commands = []
                commands.append(( _addon.getLocalizedString(30213), 'Container.Update(' + get_url(action='history',remove=file['ident']) + ')'))
                commands.append(( _addon.getLocalizedString(30214), 'Container.Update(' + get_url(action='history',toqueue=file['ident']) + ')'))
                listitem = tolistitem(file, commands)
                xbmcplugin.addDirectoryItem(_handle, get_url(action='play',ident=file['ident'],name=file['name']), listitem, False)
        else:
            popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
    xbmcplugin.endOfDirectory(_handle,updateListing=updateListing)


def settings(params):
    _addon.openSettings()
    xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())


def info(params):
    token = revalidate()
    if 'ident' not in params:
        xbmc.log("YAWsP: Missing ident in info", xbmc.LOGERROR)
        return
    xml = getinfo(params['ident'],token)

    if xml is not None:
        info = todict(xml)
        text = ''
        text += infonize(info, 'name')
        text += infonize(info, 'size', sizelize)
        text += infonize(info, 'type')
        text += infonize(info, 'width')
        text += infonize(info, 'height')
        text += infonize(info, 'format')
        text += infonize(info, 'fps', fpsize)
        text += infonize(info, 'bitrate', lambda x:sizelize(x,['bps','Kbps','Mbps','Gbps']))
        if 'video' in info and 'stream' in info['video']:
            streams = info['video']['stream']
            if isinstance(streams, dict):
                streams = [streams]
            for stream in streams:
                text += 'Video stream: '
                text += infonize(stream, 'width', showkey=False, suffix='')
                text += infonize(stream, 'height', showkey=False, prefix='x', suffix='')
                text += infonize(stream,'format', showkey=False, prefix=', ', suffix='')
                text += infonize(stream,'fps', fpsize, showkey=False, prefix=', ', suffix='')
                text += '\n'
        if 'audio' in info and 'stream' in info['audio']:
            streams = info['audio']['stream']
            if isinstance(streams, dict):
                streams = [streams]
            for stream in streams:
                text += 'Audio stream: '
                text += infonize(stream, 'format', showkey=False, suffix='')
                text += infonize(stream,'channels', prefix=', ', showkey=False, suffix='')
                text += infonize(stream,'bitrate', lambda x:sizelize(x,['bps','Kbps','Mbps','Gbps']), prefix=', ', showkey=False, suffix='')
                text += '\n'
        text += infonize(info, 'removed', lambda x:'Yes' if x=='1' else 'No')
        xbmcgui.Dialog().textviewer(_addon.getAddonInfo('name'), text)


def menu():
    revalidate()
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name'))
    listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30201))
    listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='search'), listitem, True)

    listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30202))
    listitem.setArt({'icon': 'DefaultPlaylist.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='queue'), listitem, True)

    listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30203))
    listitem.setArt({'icon': 'DefaultAddonsUpdates.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='history'), listitem, True)

    if 'true' == _addon.getSetting('experimental'):
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30412))
        listitem.setArt({'icon': 'DefaultAddonsZip.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='db'), listitem, True)

    listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30204))
    listitem.setArt({'icon': 'DefaultAddonService.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='settings'), listitem, False)

    xbmcplugin.endOfDirectory(_handle)

# ============================================================================
# Pagination Navigation Helper
# ============================================================================

def goto_page(params):
    """Navigate to a page by replacing current directory (no stack)."""
    log_debug("=== GOTO_PAGE CALLED ===")
    log_debug("goto_page params: {}".format(params))

    if 'target_url' in params:
        target_url = params['target_url']
        log_debug("Using target_url from params: {}".format(target_url))
    else:
        target_params = {k: v for k, v in params.items() if k != 'action'}
        if 'target_action' in target_params:
            target_params['action'] = target_params.pop('target_action')
        target_url = get_url(**target_params)
        log_debug("Built target_url from params: {}".format(target_url))

    log_debug("Executing Container.Update({}, replace)".format(target_url))
    xbmc.executebuiltin('Container.Update({},replace)'.format(target_url))
    log_debug("=== GOTO_PAGE FINISHED ===")

# ============================================================================
# Settings Monitor
# ============================================================================

class SettingsMonitor(xbmc.Monitor):
    """Monitor for settings changes to refresh cached addon object."""
    def onSettingsChanged(self):
        global _addon
        log_debug('Settings changed, refreshing cached values')
        _addon = xbmcaddon.Addon()
        refresh_addon()  # Refresh api module addon
        refresh_settings()  # Refresh utils module addon
        clear_cache()  # Invalidate cached data that may depend on settings


# Instantiate settings monitor at module load
_settings_monitor = SettingsMonitor()
