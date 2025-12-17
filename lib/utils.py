# -*- coding: utf-8 -*-
# Module: utils
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import sys
import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

# Global state
_handle = int(sys.argv[1]) if len(sys.argv) > 1 else -1
_addon = xbmcaddon.Addon()
_label = _addon.getSetting('labelformat') if 'true' == _addon.getSetting('customformat') else "{name}"
_filesize = 'true' == _addon.getSetting('resultsize')


# ============================================================================
# Utility Functions
# ============================================================================

def get_url(**kwargs):
    """Build plugin URL with parameters."""
    from lib.api import get_url_base
    return '{0}?{1}'.format(get_url_base(), urlencode(kwargs, 'utf-8'))


def popinfo(message, heading=None, icon=xbmcgui.NOTIFICATION_INFO, time=3000, sound=False):
    """Show notification popup."""
    if heading is None:
        heading = _addon.getAddonInfo('name')
    xbmcgui.Dialog().notification(heading, message, icon, time, sound=sound)


def ask(what):
    """Show keyboard input dialog."""
    if what is None:
        what = ''
    kb = xbmc.Keyboard(what, _addon.getLocalizedString(30007))
    kb.doModal()
    if kb.isConfirmed():
        return kb.getText()
    return None


def todict(xml, skip=[]):
    """Convert XML element to dictionary."""
    result = {}
    # Capture XML attributes (ident, type, etc.)
    if xml.attrib:
        result.update(xml.attrib)
    for e in xml:
        if e.tag not in skip:
            value = e.text if len(list(e)) == 0 else todict(e, skip)
            if e.tag in result:
                if isinstance(result[e.tag], list):
                    result[e.tag].append(value)
                else:
                    result[e.tag] = [result[e.tag], value]
            else:
                result[e.tag] = value
    return result


def sizelize(txtsize, units=['B', 'KB', 'MB', 'GB']):
    """Convert bytes to human-readable size."""
    if txtsize:
        size = float(txtsize)
        if size < 1024:
            size = str(size) + units[0]
        else:
            size = size / 1024
            if size < 1024:
                size = str(int(round(size))) + units[1]
            else:
                size = size / 1024
                if size < 1024:
                    size = str(round(size, 2)) + units[2]
                else:
                    size = size / 1024
                    size = str(round(size, 2)) + units[3]
        return size
    return str(txtsize)


def labelize(file):
    """Create label for file item."""
    if 'size' in file:
        size = sizelize(file['size'])
    elif 'sizelized' in file:
        size = file['sizelized']
    else:
        size = '?'
    return _label.format(name=file['name'], size=size)


def tolistitem(file, addcommands=[]):
    """Create Kodi ListItem from file dict."""
    label = labelize(file)
    listitem = xbmcgui.ListItem(label=label)
    infotag = listitem.getVideoInfoTag()
    infotag.setTitle(label)
    if 'img' in file:
        listitem.setArt({'thumb': file['img']})
    if _filesize and 'size' in file and file['size'].isdigit():
        listitem.setInfo('video', {'size': int(file['size'])})
    listitem.setProperty('IsPlayable', 'true')
    commands = []
    commands.append((_addon.getLocalizedString(30211), 'RunPlugin(' + get_url(action='info', ident=file['ident']) + ')'))
    commands.append((_addon.getLocalizedString(30212), 'RunPlugin(' + get_url(action='download', ident=file['ident']) + ')'))
    if addcommands:
        commands = commands + addcommands
    listitem.addContextMenuItems(commands)
    return listitem


def infonize(data, key, process=str, showkey=True, prefix='', suffix='\n'):
    """Format info field for display."""
    if key in data:
        result = prefix
        if showkey:
            result += key + ': '
        result += process(data[key]) + suffix
        return result
    return ''


def fpsize(fps):
    """Format FPS value."""
    return str(round(float(fps), 2)) + 'fps'


def get_handle():
    """Get global plugin handle."""
    return _handle


def get_addon():
    """Get global addon object."""
    return _addon
